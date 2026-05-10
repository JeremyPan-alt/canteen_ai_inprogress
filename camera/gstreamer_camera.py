"""GStreamer camera backend for Jetson CSI/USB pipelines."""

from __future__ import annotations

from typing import Any, Dict

from camera.base import BaseCamera, CameraConfig


class GStreamerCamera(BaseCamera):
    """Camera using cv2.VideoCapture with CAP_GSTREAMER."""

    def _open_capture(self) -> Any:
        import cv2  # type: ignore

        pipeline = self._build_pipeline()
        return cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)

    def _build_pipeline(self) -> str:
        custom_pipeline = self.config.extra.get("pipeline")
        if custom_pipeline:
            return str(custom_pipeline)

        sensor_id = int(self.config.source)
        width = int(self.config.width or 1280)
        height = int(self.config.height or 720)
        fps = int(self.config.fps or 30)
        flip_method = int(self.config.extra.get("flip_method", 0))

        return (
            f"nvarguscamerasrc sensor-id={sensor_id} ! "
            f"video/x-raw(memory:NVMM), width={width}, height={height}, "
            f"framerate={fps}/1 ! "
            f"nvvidconv flip-method={flip_method} ! "
            "video/x-raw, format=BGRx ! "
            "videoconvert ! "
            "video/x-raw, format=BGR ! appsink drop=true max-buffers=1 sync=false"
        )


def build_gstreamer_camera(raw: Dict[str, Any]) -> GStreamerCamera:
    return GStreamerCamera(
        CameraConfig(
            name=str(raw["name"]),
            role=str(raw.get("role", raw["name"])),
            backend="gstreamer",
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
