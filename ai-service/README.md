# ai-service — PPE detection

Watches the cameras, finds people without a **helmet** or **work uniform**, and reports to the backend.

```
camera ──► ai-service (YOLO) ──► backend /internal/* ──► WebSocket ──► web dashboard
```

## Run

```bash
cd ai-service
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env      # then fill in the values
python -m app.main
```

`INTERNAL_API_KEY` must be the same as in `backend/.env`.

Video publishing needs **ffmpeg** (`brew install ffmpeg`). Without it, detection still works but the dashboard
can't play IP cameras and webcams.

## How video flows

| Camera type | AI reads from | Dashboard plays from |
|---|---|---|
| DAHUA / HIKVISION / GENERIC_RTSP | the camera's RTSP URL | MediaMTX `cam_<id>` (AI publishes it with ffmpeg) |
| LOCAL_WEBCAM | device number (`0`, `1`) | MediaMTX `cam_<id>` (AI publishes it) |
| BROWSER | MediaMTX `cam_<id>` (user `ai`, password = `INTERNAL_API_KEY`) | MediaMTX (the browser publishes it) |

The camera list is re-read every `CAMERA_REFRESH_SECONDS`. Each camera runs in its own thread and reconnects by itself.
The AI analyses the **rotated** picture (same as the dashboard shows); mirror is applied by the dashboard only.

## Test

```bash
python -m pytest
```

## What talks to the backend

| Call | When |
|---|---|
| `POST /internal/heartbeat` | every `HEARTBEAT_SECONDS` — dashboard shows "AI ONLINE" |
| `POST /internal/cameras/{id}/status` | after the camera status changes in the DB (CONNECTING, STREAMING, RECONNECTING, ERROR, OFFLINE) |
