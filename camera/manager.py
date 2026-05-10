"""Camera construction and lifecycle management."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import yaml

from camera.base import BaseCamera, FramePacket
from camera.gstreamer_camera import build_gstreamer_camera
from camera.opencv_camera import build_opencv_camera


LOGGER = logging.getLogger(__name__)


class CameraManager:
    """Owns all camera instances and exposes a small API to Flask/services."""

    def __init__(self, cameras: Iterable[BaseCamera]) -> None:
        self._cameras = {camera.name: camera for camera in cameras}

    @classmethod
    def from_yaml(cls, config_path: Path) -> "CameraManager":
        with config_path.open("r", encoding="utf-8") as file:
            raw_config = yaml.safe_load(file) or {}

        camera_configs = raw_config.get("cameras", [])
        if not isinstance(camera_configs, list):
            raise ValueError("camera.yaml field 'cameras' must be a list")

        cameras = [build_camera(raw) for raw in camera_configs]
        return cls(cameras)

    def start_all(self) -> None:
        for camera in self._cameras.values():
            camera.start()

    def stop_all(self) -> None:
        for camera in self._cameras.values():
            camera.stop()

    def names(self) -> list[str]:
        return sorted(self._cameras.keys())

    def get_camera(self, name: str) -> BaseCamera:
        try:
            return self._cameras[name]
        except KeyError as exc:
            raise KeyError(f"unknown camera: {name}") from exc

    def get_latest_frame(self, name: str) -> Optional[FramePacket]:
        return self.get_camera(name).get_latest_frame()

    def capture_snapshot(self, name: str, output_path: Optional[Path] = None) -> Optional[FramePacket]:
        return self.get_camera(name).capture_snapshot(output_path)

    def status(self) -> Dict[str, Any]:
        return {
            "cameras": {
                name: camera.get_status().to_dict()
                for name, camera in sorted(self._cameras.items())
            }
        }


def build_camera(raw: Dict[str, Any]) -> BaseCamera:
    if "name" not in raw:
        raise ValueError("each camera config requires a name")

    backend = str(raw.get("backend", "opencv")).lower()
    if backend == "opencv":
        return build_opencv_camera(raw)
    if backend == "gstreamer":
        return build_gstreamer_camera(raw)

    raise ValueError(f"unsupported camera backend '{backend}'")
