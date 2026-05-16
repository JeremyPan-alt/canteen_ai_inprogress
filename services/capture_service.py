"""Capture orchestration for manual and intrusion-triggered snapshots."""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, Optional

from camera.manager import CameraManager
from services.model_inference import DetectionSettings, OcrReader, YoloDetector


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class CaptureRequest:
    trigger_type: str
    recorded_by: Optional[str] = None
    batch_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DetectionJob:
    job_id: str
    request: CaptureRequest
    batch_id: str
    batch_dir: Path
    captured_at: float
    entrance_frame: Any
    scale_frame: Any
    snapshots: Dict[str, Any]


class CaptureService:
    """Runs capture scheduling plus independent YOLO and OCR worker threads."""

    def __init__(
        self,
        camera_manager: CameraManager,
        snapshot_root: Path,
        detection_settings: DetectionSettings,
        project_root: Path,
        entrance_camera: str = "entrance",
        scale_camera: str = "scale",
    ) -> None:
        self._camera_manager = camera_manager
        self._snapshot_root = snapshot_root
        self._detection_settings = detection_settings
        self._entrance_camera = entrance_camera
        self._scale_camera = scale_camera
        self._requests: queue.Queue[CaptureRequest] = queue.Queue(maxsize=32)
        self._yolo_jobs: queue.Queue[DetectionJob] = queue.Queue(maxsize=16)
        self._ocr_jobs: queue.Queue[DetectionJob] = queue.Queue(maxsize=16)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._yolo_thread: Optional[threading.Thread] = None
        self._ocr_thread: Optional[threading.Thread] = None
        self._yolo_detector = YoloDetector(detection_settings.yolo, project_root)
        self._ocr_reader = OcrReader(detection_settings.ocr)
        self._project_root = project_root
        self._pending_results: Dict[str, Dict[str, Any]] = {}
        self._pending_lock = threading.RLock()
        self._last_result: Optional[Dict[str, Any]] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._scheduler_loop,
            name="capture-scheduler",
            daemon=True,
        )
        self._thread.start()
        self._yolo_thread = threading.Thread(
            target=self._yolo_loop,
            name="yolo-detector",
            daemon=True,
        )
        self._ocr_thread = threading.Thread(
            target=self._ocr_loop,
            name="ocr-reader",
            daemon=True,
        )
        self._yolo_thread.start()
        self._ocr_thread.start()
        LOGGER.info("Capture scheduler started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        if self._yolo_thread and self._yolo_thread.is_alive():
            self._yolo_thread.join(timeout=5)
        if self._ocr_thread and self._ocr_thread.is_alive():
            self._ocr_thread.join(timeout=5)
        LOGGER.info("Capture scheduler stopped")

    def trigger_manual_capture(
        self,
        recorded_by: Optional[str] = None,
        batch_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self._enqueue(CaptureRequest("manual", recorded_by, batch_id, metadata or {}))

    def trigger_intrusion_capture(
        self,
        recorded_by: Optional[str] = None,
        batch_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self._enqueue(CaptureRequest("intrusion", recorded_by, batch_id, metadata or {}))

    def capture_now(self, request: CaptureRequest) -> Dict[str, Any]:
        job = self._build_detection_job(request)
        self._submit_detection_job(job)
        return {
            "accepted": True,
            "job_id": job.job_id,
            "batch_id": job.batch_id,
            "trigger_type": request.trigger_type,
            "message": "snapshot captured; YOLO and OCR workers are processing asynchronously",
        }

    def capture_and_wait(self, request: CaptureRequest, timeout_seconds: float = 30.0) -> Dict[str, Any]:
        """Synchronous helper for API tests or debugging; normal API uses workers."""
        job = self._build_detection_job(request)
        yolo_result = self._run_yolo(job)
        ocr_result = self._run_ocr(job)
        return self._finalize_job(job, yolo_result, ocr_result)

    def get_last_result(self) -> Optional[Dict[str, Any]]:
        return self._last_result

    def get_pending_count(self) -> int:
        with self._pending_lock:
            return len(self._pending_results)

    def _build_detection_job(self, request: CaptureRequest) -> DetectionJob:
        batch_id = request.batch_id or self._new_batch_id()
        job_id = uuid.uuid4().hex
        timestamp = time.time()
        batch_dir = self._snapshot_root / batch_id
        batch_dir.mkdir(parents=True, exist_ok=True)

        entrance_path = self._frame_path(batch_dir, self._entrance_camera, timestamp)
        scale_path = self._frame_path(batch_dir, self._scale_camera, timestamp)

        entrance = self._camera_manager.capture_snapshot(self._entrance_camera, entrance_path)
        scale = self._camera_manager.capture_snapshot(self._scale_camera, scale_path)
        if entrance is None or scale is None:
            missing = []
            if entrance is None:
                missing.append(self._entrance_camera)
            if scale is None:
                missing.append(self._scale_camera)
            raise RuntimeError(f"no latest frame available for: {', '.join(missing)}")

        return DetectionJob(
            job_id=job_id,
            request=request,
            batch_id=batch_id,
            batch_dir=batch_dir,
            captured_at=timestamp,
            entrance_frame=entrance.frame,
            scale_frame=scale.frame,
            snapshots={
                self._entrance_camera: {
                    **entrance.to_metadata(),
                    "path": str(entrance_path),
                },
                self._scale_camera: {
                    **scale.to_metadata(),
                    "path": str(scale_path),
                },
            },
        )

    def _submit_detection_job(self, job: DetectionJob) -> None:
        with self._pending_lock:
            self._pending_results[job.job_id] = {"job": job, "yolo": None, "ocr": None}
        self._yolo_jobs.put_nowait(job)
        self._ocr_jobs.put_nowait(job)

    def _enqueue(self, request: CaptureRequest) -> Dict[str, Any]:
        self._requests.put_nowait(request)
        return {
            "accepted": True,
            "trigger_type": request.trigger_type,
            "batch_id": request.batch_id,
        }

    def _scheduler_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                request = self._requests.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                job = self._build_detection_job(request)
                self._submit_detection_job(job)
            except Exception:
                LOGGER.exception("Capture request failed: %s", request)
            finally:
                self._requests.task_done()

    def _yolo_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                job = self._yolo_jobs.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                result = self._run_yolo(job)
                self._record_partial_result(job.job_id, "yolo", result)
            except Exception:
                LOGGER.exception("YOLO job failed: %s", job.job_id)
            finally:
                self._yolo_jobs.task_done()

    def _ocr_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                job = self._ocr_jobs.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                result = self._run_ocr(job)
                self._record_partial_result(job.job_id, "ocr", result)
            except Exception:
                LOGGER.exception("OCR job failed: %s", job.job_id)
            finally:
                self._ocr_jobs.task_done()

    def _run_yolo(self, job: DetectionJob) -> Dict[str, Any]:
        output_path = job.batch_dir / "entrance_yolo.jpg"
        metadata = job.request.metadata or {}
        weights = metadata.get("yolo_weight") or metadata.get("yolo_model")
        confidence = metadata.get("confidence")
        detector = self._yolo_detector
        if weights or confidence is not None:
            weights_path = str(weights) if weights else self._detection_settings.yolo.weights
            if weights and not Path(weights_path).is_absolute() and "/" not in weights_path and "\\" not in weights_path:
                weights_path = str(Path("weights") / weights_path)
            settings = replace(
                self._detection_settings.yolo,
                weights=weights_path,
                confidence=float(confidence) if confidence is not None else self._detection_settings.yolo.confidence,
            )
            detector = YoloDetector(settings, self._project_root)
        return detector.detect(job.entrance_frame, output_path)

    def _run_ocr(self, job: DetectionJob) -> Dict[str, Any]:
        metadata = job.request.metadata or {}
        backend = metadata.get("ocr_backend") or metadata.get("ocr_model")
        reader = self._ocr_reader
        if backend:
            settings = replace(self._detection_settings.ocr, backend=str(backend))
            reader = OcrReader(settings)
        return reader.read_weight(job.scale_frame)

    def _record_partial_result(self, job_id: str, key: str, value: Dict[str, Any]) -> None:
        final_result: Optional[Dict[str, Any]] = None
        with self._pending_lock:
            pending = self._pending_results.get(job_id)
            if not pending:
                return
            pending[key] = value
            if pending.get("yolo") is not None and pending.get("ocr") is not None:
                job = pending["job"]
                final_result = self._finalize_job(job, pending["yolo"], pending["ocr"])
                self._pending_results.pop(job_id, None)

        if final_result is not None:
            self._post_to_spring_backend(final_result)

    def _finalize_job(
        self,
        job: DetectionJob,
        yolo_result: Dict[str, Any],
        ocr_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        vegetables = yolo_result.get("vegetables", [])
        weight = ocr_result.get("weight")
        result = {
            "job_id": job.job_id,
            "batch_id": job.batch_id,
            "trigger_type": job.request.trigger_type,
            "recorded_by": job.request.recorded_by,
            "captured_at": job.captured_at,
            "vegetables": vegetables,
            "weight": weight,
            "intake_items": [
                {
                    "vegetable": vegetable,
                    "weight": weight,
                    "unit": "kg",
                }
                for vegetable in vegetables
            ],
            "snapshots": job.snapshots,
            "detection": {
                "yolo": yolo_result,
                "ocr": ocr_result,
            },
            "metadata": job.request.metadata,
            "storage_status": "pending_confirmation",
        }
        metadata_path = job.batch_dir / "metadata.json"
        metadata_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        result["metadata_path"] = str(metadata_path)
        self._last_result = result
        return result

    def _post_to_spring_backend(self, result: Dict[str, Any]) -> None:
        backend_url = self._detection_settings.spring_backend_url
        if not backend_url:
            return

        try:
            import requests  # type: ignore

            url = backend_url.rstrip("/") + "/api/intake-records"
            response = requests.post(url, json=result, timeout=5)
            response.raise_for_status()
        except Exception:
            LOGGER.exception("Failed to post intake result to SpringBoot backend")

    @staticmethod
    def _new_batch_id() -> str:
        return time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]

    @staticmethod
    def _frame_path(batch_dir: Path, camera_name: str, timestamp: float) -> Path:
        return batch_dir / f"{camera_name}_{int(timestamp * 1000)}.jpg"
