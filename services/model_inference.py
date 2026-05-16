"""YOLO and OCR adapters used by background worker threads."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class YoloSettings:
    weights: str = "weights/vegetables.pt"
    confidence: float = 0.45
    image_size: int = 640
    device: Optional[str] = None
    enabled: bool = True


@dataclass(frozen=True)
class OcrSettings:
    backend: str = "paddleocr"
    language: str = "eng"
    enabled: bool = True
    digit_regex: str = r"\d+(?:\.\d+)?"
    easyocr_gpu: bool = False
    paddleocr_use_gpu: bool = False
    paddleocr_det_model_dir: Optional[str] = None
    paddleocr_rec_model_dir: Optional[str] = None
    paddleocr_cls_model_dir: Optional[str] = None
    paddleocr_use_angle_cls: bool = True


@dataclass(frozen=True)
class DetectionSettings:
    yolo: YoloSettings = field(default_factory=YoloSettings)
    ocr: OcrSettings = field(default_factory=OcrSettings)
    spring_backend_url: Optional[str] = None

    @classmethod
    def from_config(cls, raw: Dict[str, Any]) -> "DetectionSettings":
        yolo_raw = raw.get("yolo", {}) or {}
        ocr_raw = raw.get("ocr", {}) or {}
        return cls(
            yolo=YoloSettings(
                weights=str(yolo_raw.get("weights", "weights/vegetables.pt")),
                confidence=float(yolo_raw.get("confidence", 0.45)),
                image_size=int(yolo_raw.get("image_size", 640)),
                device=yolo_raw.get("device"),
                enabled=bool(yolo_raw.get("enabled", True)),
            ),
            ocr=OcrSettings(
                backend=str(ocr_raw.get("backend", "paddleocr")),
                language=str(ocr_raw.get("language", "eng")),
                enabled=bool(ocr_raw.get("enabled", True)),
                digit_regex=str(ocr_raw.get("digit_regex", r"\d+(?:\.\d+)?")),
                easyocr_gpu=bool(ocr_raw.get("easyocr_gpu", False)),
                paddleocr_use_gpu=bool(ocr_raw.get("paddleocr_use_gpu", False)),
                paddleocr_det_model_dir=ocr_raw.get("paddleocr_det_model_dir"),
                paddleocr_rec_model_dir=ocr_raw.get("paddleocr_rec_model_dir"),
                paddleocr_cls_model_dir=ocr_raw.get("paddleocr_cls_model_dir"),
                paddleocr_use_angle_cls=bool(ocr_raw.get("paddleocr_use_angle_cls", True)),
            ),
            spring_backend_url=raw.get("spring_backend_url"),
        )


class YoloDetector:
    """Lazy ultralytics YOLO wrapper.

    The object is only called from the YOLO worker thread, so model inference is
    intentionally isolated from realtime camera acquisition.
    """

    def __init__(self, settings: YoloSettings, project_root: Path) -> None:
        self._settings = settings
        self._project_root = project_root
        self._model: Any = None

    def detect(self, frame: Any, output_path: Optional[Path] = None) -> Dict[str, Any]:
        started = time.perf_counter()
        if not self._settings.enabled:
            return self._disabled_result(started)

        try:
            model = self._load_model()
            kwargs: Dict[str, Any] = {
                "source": frame,
                "imgsz": self._settings.image_size,
                "conf": self._settings.confidence,
                "verbose": False,
            }
            if self._settings.device:
                kwargs["device"] = self._settings.device
            results = model.predict(**kwargs)
            if not results:
                return self._empty_result(started)

            result = results[0]
            detections = self._extract_detections(result)
            annotated_path = None
            if output_path is not None:
                annotated_path = self._write_annotated_frame(result, output_path)

            return {
                "status": "ok",
                "duration_ms": self._duration_ms(started),
                "vegetables": sorted({item["label"] for item in detections}),
                "detections": detections,
                "annotated_path": str(annotated_path) if annotated_path else None,
                "model": self._settings.weights,
                "confidence_threshold": self._settings.confidence,
            }
        except Exception as exc:  # pragma: no cover - depends on native model stack
            LOGGER.exception("YOLO detection failed")
            return {
                "status": "error",
                "duration_ms": self._duration_ms(started),
                "message": str(exc),
                "vegetables": [],
                "detections": [],
                "annotated_path": None,
                "model": self._settings.weights,
            }

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model

        try:
            from ultralytics import YOLO  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "ultralytics is not installed; install requirements-ai.txt to enable YOLO"
            ) from exc

        weights_path = Path(self._settings.weights)
        if not weights_path.is_absolute():
            weights_path = self._project_root / weights_path
        self._model = YOLO(str(weights_path))
        return self._model

    def _extract_detections(self, result: Any) -> List[Dict[str, Any]]:
        names = getattr(result, "names", {}) or {}
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            return []

        detections: List[Dict[str, Any]] = []
        for box in boxes:
            cls_value = int(box.cls[0].item()) if hasattr(box.cls[0], "item") else int(box.cls[0])
            conf_value = float(box.conf[0].item()) if hasattr(box.conf[0], "item") else float(box.conf[0])
            xyxy_values = box.xyxy[0].tolist() if hasattr(box.xyxy[0], "tolist") else list(box.xyxy[0])
            detections.append(
                {
                    "label": str(names.get(cls_value, cls_value)),
                    "confidence": round(conf_value, 4),
                    "bbox_xyxy": [round(float(value), 2) for value in xyxy_values],
                }
            )
        return detections

    @staticmethod
    def _write_annotated_frame(result: Any, output_path: Path) -> Path:
        import cv2  # type: ignore

        output_path.parent.mkdir(parents=True, exist_ok=True)
        annotated = result.plot()
        ok = cv2.imwrite(str(output_path), annotated)
        if not ok:
            raise RuntimeError(f"failed to write YOLO result: {output_path}")
        return output_path

    def _disabled_result(self, started: float) -> Dict[str, Any]:
        return {
            "status": "disabled",
            "duration_ms": self._duration_ms(started),
            "vegetables": [],
            "detections": [],
            "annotated_path": None,
            "model": self._settings.weights,
        }

    def _empty_result(self, started: float) -> Dict[str, Any]:
        return {
            "status": "ok",
            "duration_ms": self._duration_ms(started),
            "vegetables": [],
            "detections": [],
            "annotated_path": None,
            "model": self._settings.weights,
            "confidence_threshold": self._settings.confidence,
        }

    @staticmethod
    def _duration_ms(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)


class OcrReader:
    """OCR wrapper for scale-display frames."""

    def __init__(self, settings: OcrSettings) -> None:
        self._settings = settings
        self._easyocr_reader: Any = None
        self._paddleocr_reader: Any = None

    def read_weight(self, frame: Any) -> Dict[str, Any]:
        started = time.perf_counter()
        if not self._settings.enabled:
            return self._result("disabled", "", None, started)

        try:
            text = self._read_text(frame)
            weight = self._parse_weight(text)
            return self._result("ok", text, weight, started)
        except Exception as exc:  # pragma: no cover - depends on OCR stack
            LOGGER.exception("OCR failed")
            return {
                "status": "error",
                "duration_ms": self._duration_ms(started),
                "text": "",
                "weight": None,
                "message": str(exc),
            }

    def _read_text(self, frame: Any) -> str:
        backend = self._settings.backend.lower()
        if backend == "none":
            return ""
        if backend == "easyocr":
            return self._read_with_easyocr(frame)
        if backend == "paddleocr":
            return self._read_with_paddleocr(frame)
        if backend == "pytesseract":
            return self._read_with_pytesseract(frame)
        raise RuntimeError(f"unsupported OCR backend: {self._settings.backend}")

    def _read_with_pytesseract(self, frame: Any) -> str:
        try:
            import cv2  # type: ignore
            import pytesseract  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "pytesseract and OpenCV are required for OCR; install requirements-ai.txt"
            ) from exc

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        config = "--psm 7 -c tessedit_char_whitelist=0123456789."
        return pytesseract.image_to_string(binary, lang=self._settings.language, config=config).strip()

    def _read_with_easyocr(self, frame: Any) -> str:
        if self._easyocr_reader is None:
            try:
                import easyocr  # type: ignore
            except ImportError as exc:
                raise RuntimeError("easyocr is not installed; install requirements-ai.txt") from exc
            self._easyocr_reader = easyocr.Reader([self._settings.language], gpu=self._settings.easyocr_gpu)

        results = self._easyocr_reader.readtext(frame, detail=0, paragraph=False)
        return " ".join(str(item) for item in results).strip()

    def _read_with_paddleocr(self, frame: Any) -> str:
        if self._paddleocr_reader is None:
            try:
                from paddleocr import PaddleOCR  # type: ignore
            except ImportError as exc:
                raise RuntimeError("paddleocr is not installed; install requirements-ai.txt") from exc

            kwargs: Dict[str, Any] = {
                "lang": self._settings.language,
                "use_gpu": self._settings.paddleocr_use_gpu,
                "use_angle_cls": self._settings.paddleocr_use_angle_cls,
                "show_log": False,
            }
            if self._settings.paddleocr_det_model_dir:
                kwargs["det_model_dir"] = self._settings.paddleocr_det_model_dir
            if self._settings.paddleocr_rec_model_dir:
                kwargs["rec_model_dir"] = self._settings.paddleocr_rec_model_dir
            if self._settings.paddleocr_cls_model_dir:
                kwargs["cls_model_dir"] = self._settings.paddleocr_cls_model_dir
            self._paddleocr_reader = PaddleOCR(**kwargs)

        results = self._paddleocr_reader.ocr(frame, cls=self._settings.paddleocr_use_angle_cls)
        texts: List[str] = []
        for page in results or []:
            for item in page or []:
                if len(item) >= 2 and isinstance(item[1], (list, tuple)) and item[1]:
                    texts.append(str(item[1][0]))
        return " ".join(texts).strip()

    def _parse_weight(self, text: str) -> Optional[float]:
        match = re.search(self._settings.digit_regex, text)
        if not match:
            return None
        return float(match.group(0))

    def _result(self, status: str, text: str, weight: Optional[float], started: float) -> Dict[str, Any]:
        return {
            "status": status,
            "duration_ms": self._duration_ms(started),
            "text": text,
            "weight": weight,
        }

    @staticmethod
    def _duration_ms(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)
