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

## Runtime architecture

The system is split into three services:

1. **Flask camera/inference service** (`app.py`)
   - opens the two cameras;
   - keeps one latest-frame buffer for each camera;
   - owns YOLO and OCR worker threads;
   - writes snapshot metadata under `logs/snapshots/`;
   - posts finalized intake JSON to SpringBoot.
2. **SpringBoot record service** (`backend/`)
   - proxies frontend capture commands to Flask;
   - stores operator-confirmed intake records in local SQLite;
   - reads connected MySQL records by storage date;
   - exposes list/update/delete APIs for the Vue tables.
3. **Vue frontend** (`frontend/`)
   - shows live camera streams;
   - triggers manual/intrusion capture;
   - shows and edits intake records.

## Install

Base Python dependencies:

```bash
pip install -r requirements.txt
```

Optional AI dependencies on the machine that runs Flask inference:

```bash
pip install -r requirements-ai.txt
```

For the intended YOLOv11 + PaddleOCR setup:

- Put YOLOv11 weights under `weights/`.
- Install `ultralytics` for YOLO.
- Install `paddleocr` and the PaddlePaddle runtime that matches your Windows,
  Linux or Jetson environment.

OpenCV installation differs by platform:

- Windows: install `opencv-python` in the project virtual environment.
- Jetson: prefer the system OpenCV build with GStreamer support, for example
  `python3-opencv` from the Jetson/L4T packages. Confirm GStreamer support with
  `cv2.getBuildInformation()`.

## MySQL setup

The SpringBoot service needs MySQL before it can store records. The application
can create the table automatically at startup, but the database/user must be
reachable and must have permission to create tables.

### Option A: let SpringBoot create the table

Create the database and grant privileges once:

```sql
CREATE DATABASE IF NOT EXISTS canteen_intake
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'canteen'@'%' IDENTIFIED BY 'canteen123';
GRANT ALL PRIVILEGES ON canteen_intake.* TO 'canteen'@'%';
FLUSH PRIVILEGES;
```

Then configure `backend/src/main/resources/application.yml` or environment
variables:

```bash
export MYSQL_URL="jdbc:mysql://localhost:3306/canteen_intake?useUnicode=true&characterEncoding=utf8&serverTimezone=Asia/Shanghai&createDatabaseIfNotExist=true"
export MYSQL_USERNAME="canteen"
export MYSQL_PASSWORD="canteen123"
```

### Option B: manually create the table first

Use this SQL if you prefer to create the table yourself:

```sql
CREATE DATABASE IF NOT EXISTS canteen_intake
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE canteen_intake;

CREATE TABLE IF NOT EXISTS intake_records (
  id VARCHAR(64) PRIMARY KEY,
  job_id VARCHAR(64),
  batch_id VARCHAR(64) NOT NULL,
  trigger_type VARCHAR(32),
  recorded_by VARCHAR(128),
  supplier VARCHAR(255),
  vegetables LONGTEXT,
  weight DECIMAL(10, 3),
  storage_date VARCHAR(32),
  captured_at TIMESTAMP NULL,
  raw_json LONGTEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

The same table definition is kept in
`backend/src/main/resources/mysql-schema.sql`.

SpringBoot also creates a local SQLite database for operator-confirmed records:

```text
backend/data/local-intake.db
```

Override it with:

```bash
export LOCAL_SQLITE_PATH="data/local-intake.db"
```

SQLite records are written only after the frontend confirmation dialog is
accepted.

Local SQLite table schema:

```sql
CREATE TABLE IF NOT EXISTS local_intake_records (
  id TEXT PRIMARY KEY,
  job_id TEXT,
  batch_id TEXT NOT NULL,
  trigger_type TEXT,
  recorded_by TEXT,
  supplier TEXT,
  vegetables TEXT,
  weight REAL,
  storage_date TEXT,
  captured_at TEXT,
  raw_json TEXT,
  created_at_millis INTEGER NOT NULL,
  updated_at_millis INTEGER NOT NULL
);
```

When the operator clicks `数据入库`, the current local pending records are
inserted into MySQL through SpringBoot and then deleted from local SQLite.

## Configure cameras and AI

All camera, YOLO, OCR and snapshot settings are in:

```text
config/camera.yaml
```

### Runtime section

```yaml
runtime:
  entrance_camera: entrance
  scale_camera: scale
  snapshot_dir: logs/snapshots
  frame_jpeg_quality: 85
```

- `entrance_camera`: camera name for the intake/receiving area.
- `scale_camera`: camera name for the weighing scale display.
- `snapshot_dir`: where captured images and `metadata.json` are stored.
- `frame_jpeg_quality`: JPEG quality for live frontend streams.

### YOLO model configuration

Put your trained vegetable YOLO model under:

```text
weights/
```

For example:

```text
weights/vegetables.pt
```

Multiple model files can be placed in `weights/`; the frontend model dropdown
reads this directory through `GET /api/models`. Supported suffixes are `.pt`,
`.onnx`, and `.engine`.

Then edit:

```yaml
detection:
  # Leave empty when using frontend confirmation before SQLite insertion.
  spring_backend_url:
  yolo:
    enabled: true
    weights: weights/vegetables.pt
    confidence: 0.45
    image_size: 640
    device:
```

- `spring_backend_url`: Flask posts finalized records to this SpringBoot URL.
  Leave it empty if you only want local JSON files.
- `weights`: relative or absolute model path.
- `confidence`: minimum confidence threshold.
- `image_size`: YOLO inference image size.
- `device`: leave empty for CPU/default; use `0` on CUDA/Jetson if supported.

### OCR configuration

```yaml
detection:
  ocr:
    enabled: true
    backend: paddleocr
    language: ch
    digit_regex: "\\d+(?:\\.\\d+)?"
    easyocr_gpu: false
    paddleocr_use_gpu: false
    paddleocr_use_angle_cls: true
    paddleocr_det_model_dir:
    paddleocr_rec_model_dir:
    paddleocr_cls_model_dir:
```

- `backend`: `paddleocr`, `pytesseract`, `easyocr`, or `none`.
- `language`: OCR language code.
- `digit_regex`: extracts the numeric weight from OCR text.
- `easyocr_gpu`: set `true` only when EasyOCR GPU runtime is installed.
- `paddleocr_*_model_dir`: optional custom PaddleOCR model directories.
- `paddleocr_use_gpu`: set `true` only when PaddlePaddle GPU runtime is ready.

### Windows USB camera configuration

Windows USB cameras usually use the OpenCV backend:

```yaml
cameras:
  - name: entrance
    role: intake_area
    backend: opencv
    enabled: true
    source: 0
    width: 1280
    height: 720
    fps: 30
    reconnect_interval_seconds: 2
    read_sleep_seconds: 0.01
    extra:
      api_preference: auto
      buffer_size: 1

  - name: scale
    role: scale_display
    backend: opencv
    enabled: true
    source: 1
    width: 1280
    height: 720
    fps: 30
    reconnect_interval_seconds: 2
    read_sleep_seconds: 0.01
    extra:
      api_preference: auto
      buffer_size: 1
```

If a Windows test machine only has one camera, disable the missing second camera
or point it to a real RTSP stream. Otherwise OpenCV may repeatedly log backend
warnings such as invalid/null capture handles while trying to reconnect:

```yaml
  - name: scale
    role: scale_display
    backend: opencv
    enabled: false
    source: 1
```

### RTSP stream configuration

If you push camera streams to the detection device, configure `source` as the
RTSP URL. The OpenCV backend will use FFmpeg:

```yaml
cameras:
  - name: entrance
    role: intake_area
    backend: opencv
    enabled: true
    source: "rtsp://user:password@192.168.1.10:554/stream1"
    width: 1280
    height: 720
    fps: 25
    reconnect_interval_seconds: 2
    read_sleep_seconds: 0.01
    extra:
      api_preference: ffmpeg
      buffer_size: 1
      open_timeout_msec: 5000
      read_timeout_msec: 5000

  - name: scale
    role: scale_display
    backend: opencv
    enabled: true
    source: "rtsp://user:password@192.168.1.11:554/stream1"
    width: 1920
    height: 1080
    fps: 25
    reconnect_interval_seconds: 2
    read_sleep_seconds: 0.01
    extra:
      api_preference: ffmpeg
      buffer_size: 1
      open_timeout_msec: 5000
      read_timeout_msec: 5000
```

You can verify RTSP independently with VLC or FFmpeg before starting Flask.

### Jetson CSI camera configuration

Jetson CSI cameras use the GStreamer backend:

```yaml
cameras:
  - name: entrance
    role: intake_area
    backend: gstreamer
    enabled: true
    source: 0
    width: 1280
    height: 720
    fps: 30
    reconnect_interval_seconds: 2
    read_sleep_seconds: 0.01
    extra:
      flip_method: 0
```

For Jetson USB/RTSP cameras, provide a full GStreamer `pipeline` in `extra`.

## Run order

Start services in this order during development.

### 1. Start MySQL

Make sure MySQL is running and accessible with the credentials in
`backend/src/main/resources/application.yml` or the `MYSQL_*` environment
variables.

### 2. Start Flask camera and inference service

```bash
python app.py
```

Useful Flask checks:

```text
http://localhost:5000/api/health
http://localhost:5000/api/cameras/status
http://localhost:5000/api/cameras/entrance/stream
http://localhost:5000/api/cameras/scale/stream
```

If a camera has not produced frames yet, the stream endpoint still returns a
placeholder JPEG so the frontend does not show a broken image.

### 3. Start SpringBoot record backend

```bash
cd backend
mvn spring-boot:run
```

The SpringBoot backend writes intake records to MySQL. Defaults are configured
for local development and can be overridden with environment variables:

```bash
export MYSQL_URL="jdbc:mysql://localhost:3306/canteen_intake?useUnicode=true&characterEncoding=utf8&serverTimezone=Asia/Shanghai&createDatabaseIfNotExist=true"
export MYSQL_USERNAME="root"
export MYSQL_PASSWORD="123456"
```

If `mvn spring-boot:run` only prints `Process terminated with exit code: 1`,
scroll up to the first `Caused by:` line. The most common causes are:

- MySQL is not running on the host/port in `MYSQL_URL`.
- `MYSQL_USERNAME` / `MYSQL_PASSWORD` is incorrect.
- The MySQL user cannot create the `canteen_intake` database or tables.
- Port `9999` is already occupied.

Useful SpringBoot checks:

```text
http://localhost:9999/api/intake/cameras/status
http://localhost:9999/api/intake-records
http://localhost:9999/api/local-intake-records/session
```

### 4. Start Vue frontend

```bash
cd frontend
npm install
npm run dev
```

If the Vue app is not served by Vite's dev proxy, set the Flask API prefix:

```bash
VITE_FLASK_API_PREFIX=http://localhost:5000/api npm run dev
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
- `GET /api/intake-records?date=YYYY-MM-DD`
- `PUT /api/intake-records/{id}`
- `DELETE /api/intake-records/{id}`
- `POST /api/local-intake-records`
- `GET /api/local-intake-records/session`
- `GET /api/local-intake-records`
- `POST /api/local-intake-records/upload-to-mysql`
- `PUT /api/local-intake-records/{id}`
- `DELETE /api/local-intake-records/{id}`

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
operator metadata.

The normal operator workflow is:

1. Select the YOLO target detection model and OCR backend in the top toolbar.
2. Click `拍照识别` or let intrusion detection trigger capture.
3. Flask reads latest-frame buffers and runs YOLO + OCR worker threads.
4. The frontend polls `GET /api/capture/status` and opens a confirmation dialog
   when the detection result is ready.
5. The operator corrects vegetable names, weight, supplier, recorder or storage
   date if needed.
6. Clicking `确认录入 SQLite` writes the confirmed record to local SQLite.
7. The lower-left table shows local SQLite records confirmed during this app
   session.
8. Clicking `数据入库` writes all rows currently shown in the lower-left table to
   MySQL and clears the local pending table. The area then displays
   `数据已入库，本地数据库暂无待上传数据`.
9. The lower-right table queries connected MySQL records for the selected date.
