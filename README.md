# canteen_ai_inprogress

Flask camera-loading skeleton for a canteen ingredient intake system. The first
milestone focuses on 24/7 video acquisition that can run on Windows USB cameras
and NVIDIA Jetson Orin devices.

## Current scope

- Two independent camera acquisition threads: intake area and scale display.
- A shared camera interface:
  - `start()`
  - `stop()`
  - `get_latest_frame()`
  - `reconnect()`
  - `capture_snapshot()`
- A `LatestFrameBuffer` backed by `queue.Queue(maxsize=1)` so stale frames do
  not accumulate.
- Backend implementations for:
  - OpenCV `VideoCapture` on Windows/generic USB/IP cameras.
  - OpenCV + GStreamer pipeline on Jetson CSI/USB cameras.
- A third scheduler thread in `CaptureService` for manual/intrusion capture
  requests.
- Flask API routes for camera status, live JPEG frames, and capture triggers.

YOLO vegetable detection and OCR weight parsing are intentionally represented as
a placeholder in this milestone. They can be wired into `CaptureService` without
changing the camera acquisition threads.

## Project layout

```text
project/
├── app.py
├── config/
│   └── camera.yaml
├── camera/
│   ├── base.py
│   ├── opencv_camera.py
│   ├── gstreamer_camera.py
│   ├── manager.py
│   └── buffer.py
├── services/
│   └── capture_service.py
├── api/
│   └── frame_api.py
└── logs/
```

## Install

Base Python dependencies:

```bash
pip install -r requirements.txt
```

OpenCV installation differs by platform:

- Windows: install `opencv-python` in the project virtual environment.
- Jetson: prefer the system OpenCV build with GStreamer support, for example
  `python3-opencv` from the Jetson/L4T packages. Confirm GStreamer support with
  `cv2.getBuildInformation()`.

## Configure cameras

Edit `config/camera.yaml`.

Windows USB cameras usually use:

```yaml
backend: opencv
source: 0
extra:
  api_preference: dshow
```

Jetson CSI cameras use:

```yaml
backend: gstreamer
source: 0
extra:
  flip_method: 0
```

For Jetson USB/RTSP cameras, provide a full GStreamer `pipeline` in `extra`.

## Run

```bash
python app.py
```

Optional environment variables:

- `CAMERA_CONFIG`: path to an alternate camera YAML file.
- `FLASK_HOST`: default `0.0.0.0`.
- `FLASK_PORT`: default `5000`.
- `LOG_LEVEL`: default `INFO`.

## API

- `GET /api/health`
- `GET /api/cameras`
- `GET /api/cameras/status`
- `GET /api/cameras/<name>/frame`
- `POST /api/cameras/<name>/snapshot`
- `POST /api/capture/manual`
- `POST /api/capture/intrusion`
- `POST /api/capture/now`
- `GET /api/capture/last`

Manual capture body example:

```json
{
  "recorded_by": "operator-001",
  "batch_id": "optional-existing-batch"
}
```

Snapshots are written under `logs/snapshots/<batch_id>/` with a `metadata.json`
file that records camera metadata and a placeholder detection result.
