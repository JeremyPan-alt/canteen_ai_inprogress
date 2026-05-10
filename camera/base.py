"""Base camera interface and shared threaded capture loop."""

from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from camera.buffer import LatestFrameBuffer


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class CameraConfig:
    """Runtime configuration for one physical camera."""

    name: str
    backend: str
    source: Any
    role: str
    enabled: bool = True
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[int] = None
    reconnect_interval_seconds: float = 2.0
    read_sleep_seconds: float = 0.01
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FramePacket:
    """Latest camera frame with metadata needed by API and services."""

    camera_name: str
    role: str
    frame: Any
    captured_at: float
    frame_index: int
    width: int
    height: int

    def clone(self) -> "FramePacket":
        frame = self.frame.copy() if hasattr(self.frame, "copy") else self.frame
        return FramePacket(
            camera_name=self.camera_name,
            role=self.role,
            frame=frame,
            captured_at=self.captured_at,
            frame_index=self.frame_index,
            width=self.width,
            height=self.height,
        )

    def to_metadata(self) -> Dict[str, Any]:
        return {
            "camera_name": self.camera_name,
            "role": self.role,
            "captured_at": self.captured_at,
            "frame_index": self.frame_index,
            "width": self.width,
            "height": self.height,
        }


@dataclass(frozen=True)
class CameraStatus:
    """Serializable camera health snapshot."""

    name: str
    role: str
    backend: str
    enabled: bool
    running: bool
    connected: bool
    frame_count: int
    last_frame_at: Optional[float]
    last_error: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role,
            "backend": self.backend,
            "enabled": self.enabled,
            "running": self.running,
            "connected": self.connected,
            "frame_count": self.frame_count,
            "last_frame_at": self.last_frame_at,
            "last_error": self.last_error,
        }


class BaseCamera(ABC):
    """Common start/stop/latest-frame/reconnect/snapshot camera contract."""

    def __init__(self, config: CameraConfig) -> None:
        self.config = config
        self._buffer: LatestFrameBuffer[FramePacket] = LatestFrameBuffer()
        self._capture: Any = None
        self._capture_lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._connected = False
        self._frame_count = 0
        self._last_frame_at: Optional[float] = None
        self._last_error: Optional[str] = None

    @property
    def name(self) -> str:
        return self.config.name

    def start(self) -> None:
        """Start the background acquisition thread."""
        if not self.config.enabled:
            LOGGER.info("Camera %s is disabled; skip start", self.name)
            return
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._capture_loop,
            name=f"camera-{self.name}",
            daemon=True,
        )
        self._thread.start()
        LOGGER.info("Camera %s capture thread started", self.name)

    def stop(self) -> None:
        """Stop the acquisition thread and release native camera resources."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        with self._capture_lock:
            self._release_capture()
            self._connected = False
        LOGGER.info("Camera %s stopped", self.name)

    def get_latest_frame(self) -> Optional[FramePacket]:
        """Return a cloned frame so callers cannot mutate the shared cache."""
        packet = self._buffer.get_latest()
        return packet.clone() if packet else None

    def capture_snapshot(self, output_path: Optional[Path] = None) -> Optional[FramePacket]:
        """Capture the current cached frame and optionally write it as JPEG."""
        packet = self.get_latest_frame()
        if packet is None:
            return None

        if output_path is not None:
            self._write_frame(output_path, packet.frame)
        return packet

    def reconnect(self) -> bool:
        """Release and reopen the backend capture handle."""
        with self._capture_lock:
            self._release_capture()
            try:
                self._capture = self._open_capture()
                self._connected = self._capture_is_opened(self._capture)
                self._last_error = None if self._connected else "camera open failed"
            except Exception as exc:  # pragma: no cover - backend dependent
                self._capture = None
                self._connected = False
                self._last_error = str(exc)
                LOGGER.exception("Camera %s reconnect failed", self.name)
        return self._connected

    def get_status(self) -> CameraStatus:
        return CameraStatus(
            name=self.name,
            role=self.config.role,
            backend=self.config.backend,
            enabled=self.config.enabled,
            running=bool(self._thread and self._thread.is_alive()),
            connected=self._connected,
            frame_count=self._frame_count,
            last_frame_at=self._last_frame_at,
            last_error=self._last_error,
        )

    def _capture_loop(self) -> None:
        while not self._stop_event.is_set():
            if not self._connected and not self.reconnect():
                time.sleep(self.config.reconnect_interval_seconds)
                continue

            ok, frame = self._read_frame()
            if not ok or frame is None:
                self._connected = False
                self._last_error = "frame read failed"
                LOGGER.warning("Camera %s frame read failed; reconnecting", self.name)
                time.sleep(self.config.reconnect_interval_seconds)
                continue

            self._frame_count += 1
            captured_at = time.time()
            height, width = self._frame_shape(frame)
            self._last_frame_at = captured_at
            self._last_error = None
            self._buffer.put(
                FramePacket(
                    camera_name=self.name,
                    role=self.config.role,
                    frame=frame,
                    captured_at=captured_at,
                    frame_index=self._frame_count,
                    width=width,
                    height=height,
                )
            )
            time.sleep(self.config.read_sleep_seconds)

    def _read_frame(self) -> tuple[bool, Any]:
        with self._capture_lock:
            if self._capture is None:
                return False, None
            return self._capture.read()

    def _release_capture(self) -> None:
        if self._capture is not None:
            try:
                self._capture.release()
            finally:
                self._capture = None

    @staticmethod
    def _capture_is_opened(capture: Any) -> bool:
        return bool(capture is not None and capture.isOpened())

    @staticmethod
    def _frame_shape(frame: Any) -> tuple[int, int]:
        if hasattr(frame, "shape") and len(frame.shape) >= 2:
            return int(frame.shape[0]), int(frame.shape[1])
        return 0, 0

    @staticmethod
    def _write_frame(output_path: Path, frame: Any) -> None:
        import cv2  # type: ignore

        output_path.parent.mkdir(parents=True, exist_ok=True)
        ok = cv2.imwrite(str(output_path), frame)
        if not ok:
            raise RuntimeError(f"failed to write snapshot: {output_path}")

    @abstractmethod
    def _open_capture(self) -> Any:
        """Open and return the native backend capture object."""
