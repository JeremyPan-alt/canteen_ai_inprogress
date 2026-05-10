"""OpenCV camera backend for Windows, USB cameras and RTSP/IP streams."""

from __future__ import annotations

import platform
from typing import Any, Dict

from camera.base import BaseCamera, CameraConfig


_BACKEND_FLAGS: Dict[str, str] = {
    "any": "CAP_ANY",
    "dshow": "CAP_DSHOW",
    "ffmpeg": "CAP_FFMPEG",
    "msmf": "CAP_MSMF",
    "v4l2": "CAP_V4L2",
}


class OpenCVCamera(BaseCamera):
    """Camera using cv2.VideoCapture with an optional platform backend flag."""

    def _open_capture(self) -> Any:
        import cv2  # type: ignore

        backend_name = str(self.config.extra.get("api_preference", "auto")).lower()
        if backend_name == "auto":
            backend_name = self._default_backend_name()
        backend_attr = _BACKEND_FLAGS.get(backend_name, "CAP_ANY")
        backend_flag = getattr(cv2, backend_attr)
        capture = cv2.VideoCapture(self.config.source, backend_flag)

        if self.config.width:
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
        if self.config.height:
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
        if self.config.fps:
            capture.set(cv2.CAP_PROP_FPS, self.config.fps)
        capture.set(cv2.CAP_PROP_BUFFERSIZE, int(self.config.extra.get("buffer_size", 1)))
        if self.config.extra.get("open_timeout_msec") is not None:
            capture.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, int(self.config.extra["open_timeout_msec"]))
        if self.config.extra.get("read_timeout_msec") is not None:
            capture.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, int(self.config.extra["read_timeout_msec"]))

        return capture

    def _default_backend_name(self) -> str:
        source = self.config.source
        if isinstance(source, str) and self._is_stream_source(source):
            return "ffmpeg"
        if platform.system().lower() == "windows":
            return "dshow"
        return "any"

    @staticmethod
    def _is_stream_source(source: str) -> bool:
        lowered = source.lower()
        return lowered.startswith(("rtsp://", "rtmp://", "http://", "https://"))


def build_opencv_camera(raw: Dict[str, Any]) -> OpenCVCamera:
    return OpenCVCamera(
        CameraConfig(
            name=str(raw["name"]),
            role=str(raw.get("role", raw["name"])),
            backend="opencv",
            source=raw.get("source", 0),
            enabled=bool(raw.get("enabled", True)),
            width=raw.get("width"),
            height=raw.get("height"),
            fps=raw.get("fps"),
            reconnect_interval_seconds=float(raw.get("reconnect_interval_seconds", 2.0)),
            read_sleep_seconds=float(raw.get("read_sleep_seconds", 0.01)),
            extra=dict(raw.get("extra", {})),
        )
    )
