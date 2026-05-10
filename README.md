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
- Dedicated YOLO and OCR worker threads:
  - camera threads only update latest-frame buffers;
  - the capture scheduler clones snapshots from those buffers;
  - YOLO consumes the intake-area snapshot;
  - OCR consumes the scale-display snapshot;
  - once both workers finish, Flask writes one JSON result and optionally posts
    it to SpringBoot.
- Flask API routes for camera status, live JPEG frames, and capture triggers.
- A Vue3 + Element Plus frontend adapted from the crop disease UI style for
  ingredient intake.
- A SpringBoot backend that proxies capture commands to Flask and receives
  finalized intake records.

YOLO and OCR dependencies are optional at install time because Jetson deployments
often use platform-specific OpenCV/TensorRT/PyTorch builds. Without those
dependencies, the worker threads return explicit error metadata instead of
blocking camera acquisition.

## Project layout

```text
project/
├── app.py
├── frontend/
├── backend/
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

Optional AI dependencies on the machine that runs Flask inference:

```bash
pip install -r requirements-ai.txt
```

OpenCV installation differs by platform:

- Windows: install `opencv-python` in the project virtual environment.
- Jetson: prefer the system OpenCV build with GStreamer support, for example
  `python3-opencv` from the Jetson/L4T packages. Confirm GStreamer support with
  `cv2.getBuildInformation()`.

## Configure cameras

Edit `config/camera.yaml`. Besides cameras, it also configures YOLO/OCR:

```yaml
detection:
  spring_backend_url: http://localhost:9999
  yolo:
    weights: weights/vegetables.pt
    confidence: 0.45
    image_size: 640
  ocr:
    backend: pytesseract
    language: eng
```

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

Flask camera and inference service:

```bash
python app.py
```

SpringBoot record backend:

```bash
cd backend
mvn spring-boot:run
```

Vue frontend:

```bash
cd frontend
npm install
npm run dev
```

Optional environment variables:

- `CAMERA_CONFIG`: path to an alternate camera YAML file.
- `FLASK_HOST`: default `0.0.0.0`.
- `FLASK_PORT`: default `5000`.
- `LOG_LEVEL`: default `INFO`.

## API

Flask service:

- `GET /api/health`
- `GET /api/cameras`
- `GET /api/cameras/status`
- `GET /api/cameras/<name>/frame`
- `GET /api/cameras/<name>/stream`
- `GET /api/models`
- `POST /api/cameras/<name>/snapshot`
- `POST /api/capture/manual`
- `POST /api/capture/intrusion`
- `POST /api/capture/now`
- `POST /api/capture/wait`
- `GET /api/capture/last`
- `GET /api/capture/status`

SpringBoot service:

- `POST /api/intake/capture/manual`
- `POST /api/intake/capture/intrusion`
- `GET /api/intake/cameras/status`
- `POST /api/intake-records`
- `GET /api/intake-records`
- `DELETE /api/intake-records/{id}`

Manual capture body example:

```json
{
  "recorded_by": "operator-001",
  "supplier": "供应商A",
  "batch_id": "optional-existing-batch",
  "metadata": {
    "confidence": 0.45,
    "remark": "上午批次"
  }
}
```

Snapshots are written under `logs/snapshots/<batch_id>/` with a `metadata.json`
file that records camera metadata, YOLO detections, OCR weight, intake items and
operator metadata. A MySQL table sketch is available at
`backend/src/main/resources/mysql-schema.sql` for the next persistence step.
