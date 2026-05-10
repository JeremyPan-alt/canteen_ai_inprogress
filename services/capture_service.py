"""Capture orchestration for manual and intrusion-triggered snapshots."""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from camera.manager import CameraManager


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class CaptureRequest:
    trigger_type: str
    recorded_by: Optional[str] = None
    batch_id: Optional[str] = None


class CaptureService:
    """Runs the third worker thread that schedules capture/detection jobs.

    The first milestone only stores synchronized snapshots and JSON metadata.
    YOLO/OCR can be plugged into ``_run_detection_placeholder`` without changing
    camera threads or Flask routes.
    """

    def __init__(
        self,
        camera_manager: CameraManager,
        snapshot_root: Path,
        entrance_camera: str = "entrance",
        scale_camera: str = "scale",
    ) -> None:
        self._camera_manager = camera_manager
        self._snapshot_root = snapshot_root
        self._entrance_camera = entrance_camera
        self._scale_camera = scale_camera
        self._requests: queue.Queue[CaptureRequest] = queue.Queue(maxsize=32)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
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
        LOGGER.info("Capture scheduler started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        LOGGER.info("Capture scheduler stopped")

    def trigger_manual_capture(
        self,
        recorded_by: Optional[str] = None,
        batch_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._enqueue(CaptureRequest("manual", recorded_by, batch_id))

    def trigger_intrusion_capture(
        self,
        recorded_by: Optional[str] = None,
        batch_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._enqueue(CaptureRequest("intrusion", recorded_by, batch_id))

    def capture_now(self, request: CaptureRequest) -> Dict[str, Any]:
        batch_id = request.batch_id or self._new_batch_id()
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

        result = {
            "batch_id": batch_id,
            "trigger_type": request.trigger_type,
            "recorded_by": request.recorded_by,
            "captured_at": timestamp,
            "snapshots": {
                self._entrance_camera: {
                    **entrance.to_metadata(),
                    "path": str(entrance_path),
                },
                self._scale_camera: {
                    **scale.to_metadata(),
                    "path": str(scale_path),
                },
            },
            "detection": self._run_detection_placeholder(),
        }
        metadata_path = batch_dir / "metadata.json"
        metadata_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        result["metadata_path"] = str(metadata_path)
        self._last_result = result
        return result

    def get_last_result(self) -> Optional[Dict[str, Any]]:
        return self._last_result

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
                self.capture_now(request)
            except Exception:
                LOGGER.exception("Capture request failed: %s", request)
            finally:
                self._requests.task_done()

    @staticmethod
    def _new_batch_id() -> str:
        return time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]

    @staticmethod
    def _frame_path(batch_dir: Path, camera_name: str, timestamp: float) -> Path:
        return batch_dir / f"{camera_name}_{int(timestamp * 1000)}.jpg"

    @staticmethod
    def _run_detection_placeholder() -> Dict[str, Any]:
        return {
            "status": "pending",
            "message": "YOLO vegetable detection and OCR weight parsing are not wired yet.",
        }
