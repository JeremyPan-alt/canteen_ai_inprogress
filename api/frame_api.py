"""Camera frame and snapshot HTTP endpoints."""

from __future__ import annotations

import queue
from typing import Any, Dict

from flask import Blueprint, Response, current_app, jsonify, request

from services.capture_service import CaptureRequest


frame_api = Blueprint("frame_api", __name__, url_prefix="/api")


@frame_api.get("/health")
def health() -> Response:
    return jsonify({"ok": True})


@frame_api.get("/cameras")
def list_cameras() -> Response:
    manager = _camera_manager()
    return jsonify({"names": manager.names(), **manager.status()})


@frame_api.get("/cameras/status")
def camera_status() -> Response:
    return jsonify(_camera_manager().status())


@frame_api.get("/cameras/<name>/frame")
def latest_frame(name: str) -> Response:
    packet = _camera_manager().get_latest_frame(name)
    if packet is None:
        return jsonify({"error": f"no frame available for camera '{name}'"}), 404

    return Response(
        _encode_jpeg(packet.frame),
        mimetype="image/jpeg",
        headers={
            "X-Camera-Name": packet.camera_name,
            "X-Frame-Index": str(packet.frame_index),
            "X-Captured-At": str(packet.captured_at),
        },
    )


@frame_api.post("/cameras/<name>/snapshot")
def camera_snapshot(name: str) -> Response:
    packet = _camera_manager().capture_snapshot(name)
    if packet is None:
        return jsonify({"error": f"no frame available for camera '{name}'"}), 404
    return jsonify(packet.to_metadata())


@frame_api.post("/capture/manual")
def trigger_manual_capture() -> Response:
    payload = _json_payload()
    try:
        result = _capture_service().trigger_manual_capture(
            recorded_by=payload.get("recorded_by"),
            batch_id=payload.get("batch_id"),
        )
    except queue.Full:
        return jsonify({"error": "capture scheduler queue is full"}), 429
    return jsonify(result), 202


@frame_api.post("/capture/intrusion")
def trigger_intrusion_capture() -> Response:
    payload = _json_payload()
    try:
        result = _capture_service().trigger_intrusion_capture(
            recorded_by=payload.get("recorded_by"),
            batch_id=payload.get("batch_id"),
        )
    except queue.Full:
        return jsonify({"error": "capture scheduler queue is full"}), 429
    return jsonify(result), 202


@frame_api.post("/capture/now")
def capture_now() -> Response:
    payload = _json_payload()
    result = _capture_service().capture_now(
        CaptureRequest(
            trigger_type=str(payload.get("trigger_type", "manual")),
            recorded_by=payload.get("recorded_by"),
            batch_id=payload.get("batch_id"),
        )
    )
    return jsonify(result)


@frame_api.get("/capture/last")
def last_capture() -> Response:
    result = _capture_service().get_last_result()
    if result is None:
        return jsonify({"result": None}), 404
    return jsonify(result)


def _encode_jpeg(frame: Any) -> bytes:
    import cv2  # type: ignore

    quality = int(current_app.config.get("FRAME_JPEG_QUALITY", 85))
    ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise RuntimeError("failed to encode frame")
    return encoded.tobytes()


def _camera_manager() -> Any:
    return current_app.extensions["camera_manager"]


def _capture_service() -> Any:
    return current_app.extensions["capture_service"]


def _json_payload() -> Dict[str, Any]:
    return request.get_json(silent=True) or {}
