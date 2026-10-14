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

## How detection works

1. Every `1 / DETECT_FPS` seconds the YOLO model looks at the newest frame of each camera.
2. It finds 5 kinds of boxes: `person, helmet, no_helmet, work_uniform, no_work_uniform`.
3. `app/detection/ppe.py` gives each **head** box to the person whose head area contains it, and each **body** box
   to the person whose body area contains it.
4. For every person: `helmet` and `uniform` = `YES` / `NO` / `UNKNOWN`.
   **Violation** = no helmet (where required) or no uniform. `UNKNOWN` is never a violation, to avoid false alarms.
5. In **OFFICE** zones a helmet is not required.
6. **Motion skip:** if nobody was in the picture and less than `MOTION_THRESHOLD` (1 %) of it changed,
   YOLO is skipped. It still runs at least every `MOTION_MAX_SKIP_SECONDS`, and always while people are visible.
7. The boxes go to the dashboard live (`DETECTIONS` over WebSocket). Person ids come from the tracker (ByteTrack).

## How violations are saved

- A "NO" must be seen for `VIOLATION_CONFIRM_SECONDS` (default 2 s) — one wrong frame is not enough.
- Then: snapshot (person marked in red) → Supabase Storage `violation-snapshots/<camera>/<yyyy/mm/dd>/<id>.jpg`
  → new row in `violations` → `POST /internal/violations/{id}/created` → the dashboard shows it instantly.
- The same person (tracker id) with the same violation is saved again only after `VIOLATION_COOLDOWN_SECONDS`.
- If the upload fails the violation is still saved, just without a picture.

## Training data collection

Turn it on in the web **Training** page. While it's on, every `interval_seconds` each camera saves:

- `training/datasets/raw/<name>.jpg` — the picture
- `training/datasets/labels_auto/<name>.txt` — the AI's guess (YOLO format), so labelling starts half-done

Pictures with nobody in them are kept 5 times less often. Collection pauses at `max_images`.
After training, point `MODEL_PATH` to the new model and leave `CLASS_MAPPING` empty.

Using a model with other class names (for example a public hard-hat model)? Set `CLASS_MAPPING`.

**Check a model before using it** (classes, mapping, READY / PARTIAL / NOT USABLE):

```bash
python -m scripts.check_model                      # MODEL_PATH from .env
python -m scripts.check_model model.onnx --image test.jpg
```

**Faster on CPU:** convert a `.pt` model to ONNX. It prints the classes and a `CLASS_MAPPING` hint.

```bash
python -m scripts.export_onnx path/to/model.pt --imgsz 640
```

Models from the Training page are already `.onnx`.

## Test

```bash
python -m pytest
```

## What talks to the backend

| Call | When |
|---|---|
| `POST /internal/heartbeat` | every `HEARTBEAT_SECONDS` — dashboard shows "AI ONLINE" |
| `PUT /internal/cameras/{id}/detections` | every AI step: people, boxes (0..1), helmet/uniform state |
| `POST /internal/violations/{id}/created` | right after a new violation row is saved |
| `POST /internal/cameras/{id}/status` | after the camera status changes in the DB (CONNECTING, STREAMING, RECONNECTING, ERROR, OFFLINE) |
