"""Flask entrypoint for the canteen ingredient intake service."""

from __future__ import annotations

import atexit
import logging
import os
from pathlib import Path
from typing import Any, Dict

import yaml
from flask import Flask

from api.frame_api import frame_api
from camera.manager import CameraManager
from services.capture_service import CaptureService
from services.model_inference import DetectionSettings


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config" / "camera.yaml"


def create_app(config_path: str | os.PathLike[str] | None = None) -> Flask:
    _configure_logging()

    path = Path(config_path or os.getenv("CAMERA_CONFIG", DEFAULT_CONFIG_PATH))
    raw_config = _load_yaml(path)
    runtime_config = raw_config.get("runtime", {})
    detection_config = raw_config.get("detection", {})

    app = Flask(__name__)
    app.config["FRAME_JPEG_QUALITY"] = int(runtime_config.get("frame_jpeg_quality", 85))

    camera_manager = CameraManager.from_yaml(path)
    snapshot_root = BASE_DIR / str(runtime_config.get("snapshot_dir", "logs/snapshots"))
    detection_settings = DetectionSettings.from_config(detection_config)
    capture_service = CaptureService(
        camera_manager=camera_manager,
        snapshot_root=snapshot_root,
        detection_settings=detection_settings,
        project_root=BASE_DIR,
        entrance_camera=str(runtime_config.get("entrance_camera", "entrance")),
        scale_camera=str(runtime_config.get("scale_camera", "scale")),
    )

    camera_manager.start_all()
    capture_service.start()

    app.extensions["camera_manager"] = camera_manager
    app.extensions["capture_service"] = capture_service
    app.register_blueprint(frame_api)

    def shutdown() -> None:
        capture_service.stop()
        camera_manager.stop_all()

    atexit.register(shutdown)
    return app


def _configure_logging() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s [%(threadName)s] %(name)s: %(message)s",
    )


def _load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


app = create_app()


if __name__ == "__main__":
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_PORT", "5000"))
    app.run(host=host, port=port, threaded=True, use_reloader=False)
