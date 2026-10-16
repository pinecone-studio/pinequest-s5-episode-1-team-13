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

Every `STATS_SECONDS` (default 60, `0` = off) each camera logs one line:

```
Gate | video 14.8 fps | AI 3.0/s, 41 ms avg, 63 ms max | people max 2 | violation frames 4 | status STREAMING
```

Low video fps = network/camera problem. High AI ms = model too slow (try `DEVICE`, ONNX or a smaller `IMGSZ`).

The camera list is re-read every `CAMERA_REFRESH_SECONDS`. Each camera runs in its own thread and reconnects by itself.
If MediaMTX is down, the AI waits longer between tries (5 s, 10 s, 20 s … up to 60 s) and goes back to 5 s once
publishing has worked for 30 s.
The AI analyses the **rotated** picture (same as the dashboard shows); mirror is applied by the dashboard only.

## How detection works

1. Every `1 / DETECT_FPS` seconds the YOLO model looks at the newest frame of each camera.
2. It finds 5 kinds of boxes: `person, helmet, no_helmet, work_uniform, no_work_uniform`.
3. `app/detection/ppe.py` gives each **head** box to the person whose head area contains it, and each **body** box
   to the person whose body area contains it.
4. For every person: `helmet` and `uniform` = `YES` / `NO` / `UNKNOWN`.
   **Violation** = no helmet (where required) or no uniform. `UNKNOWN` is never a violation, to avoid false alarms.
   A "NO" box must score at least `NO_CONF_THRESHOLD` (0.55), higher than a normal box (`CONF_THRESHOLD` 0.4).
   Each person's state is the **majority of their last `SMOOTH_WINDOW` (5) results**, so labels don't flicker.
5. In **OFFICE** zones a helmet is not required.
6. **Motion skip:** if nobody was in the picture and less than `MOTION_THRESHOLD` (1 %) of it changed,
   YOLO is skipped. It still runs at least every `MOTION_MAX_SKIP_SECONDS`, and always while people are visible.
7. The boxes go to the dashboard live (`DETECTIONS` over WebSocket). Person ids come from the tracker (ByteTrack).

## How violations are saved

- A "NO" must be seen for `VIOLATION_CONFIRM_SECONDS` (default 2 s) — one wrong frame is not enough.
- Then: snapshot (person marked in red) → Supabase Storage `violation-snapshots/<camera>/<yyyy/mm/dd>/<id>.jpg`
  → new row in `violations` → `POST /internal/violations/{id}/created` → the dashboard shows it instantly.
- **One violation per person per visit.** While a person keeps the same problem it is saved once (gaps under 10 s,
  like someone walking in front, are the same visit). `VIOLATION_REPEAT_SECONDS` saves it again during a very long
  visit (default 0 = never).
- A person who leaves and comes back is a new visit, but it is saved again only after `VIOLATION_COOLDOWN_SECONDS`.
- If the tracker loses a person and gives them a new id in the same place, it still counts as the same person.
- If the upload fails the violation is still saved, just without a picture.
- Frames that are too **dark** (`MIN_BRIGHTNESS`) or too **blurry** (`MIN_SHARPNESS`) are not used for violations or
  training pictures; the live boxes still show. Night or a dirty lens no longer creates false "NO helmet" alarms.

## Training data collection

Turn it on in the web **Training** page. While it's on, every `interval_seconds` each camera saves:

- `training/datasets/raw/<name>.jpg` — the picture
- `training/datasets/labels_auto/<name>.txt` — the AI's guess (YOLO format), so labelling starts half-done

Pictures with nobody in them are kept 5 times less often. Collection pauses at `max_images`.
After training, point `MODEL_PATH` to the new model and leave `CLASS_MAPPING` empty.

**Speed:** `DEVICE=auto` uses the Apple GPU (`mps`) on M-chip Macs for `.pt` models, an NVIDIA GPU (`cuda`) when
there is one, otherwise the CPU. `.onnx` models always run on the CPU with ONNX Runtime. The start-up log shows `AI device: ...`.

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

## Docker

```bash
cd ai-service
docker build -t pinequest-ai .
docker run --rm --env-file .env \
  -e MODEL_PATH=/models/ppe.onnx \
  -e BACKEND_URL=http://host.docker.internal:8000 \
  -e MEDIAMTX_RTSP_URL=rtsp://host.docker.internal:8554 \
  -v "$PWD/../training/models:/models:ro" \
  -v "$PWD/../training:/training" \
  pinequest-ai
```

- The image has no model inside. Mount the folder with your model at `/models` and set `MODEL_PATH`.
- Mount `training/` at `/training` so the Training page sees collected pictures.
- Inside Docker, `localhost` is the container itself: use `host.docker.internal` (Mac/Windows) or the service
  names from docker compose (e.g. `http://backend:8000`, `rtsp://mediamtx:8554`).
- Runs on the CPU (`DEVICE=cpu`). `LOCAL_WEBCAM` cameras don't work in Docker on a Mac — run the service
  directly with Python for the laptop camera.

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

## Demo without cameras

Runs the model on a photo or video and saves a copy with boxes (green = OK, red = violation, grey = unknown).
Only needs the model, not the backend or database. Good backup for presentations.

```bash
python -m scripts.demo factory.jpg            # -> factory_demo.jpg
python -m scripts.demo walk.mp4 --max-seconds 20   # -> walk_demo.mp4 + how many violations would be saved
```

## Training pictures from your own photos and videos

Use any model (even a public PPE model) to pre-label photos/videos for the Training page.
`--only-hard` keeps only pictures the model is unsure about (a box scored 0.3–0.6): those teach the most.

```bash
python -m scripts.prelabel ~/Documents/ppe-photos --model models/ppe-public.pt \
  --mapping "Worker:person,Hard_hat:helmet,No-Helmet:no_helmet,Vest:work_uniform,No-Vest:no_work_uniform"
python -m scripts.prelabel walk.mp4 --every 0.5 --only-hard
```

Pictures go to `training/datasets/raw`, the model's guesses to `labels_auto`. Then check and fix the boxes on the
Training page and train. Near-duplicate video frames are skipped.

## Our model

`models/ppe-ours-v2.pt` is the team model (in git, 22 MB). It is the default `MODEL_PATH` in `.env.example`.
Classes match ours, so `CLASS_MAPPING` stays empty. Trained at `IMGSZ=512`.

Scores on 443 test pictures it never saw while learning (mAP50, 1 = perfect):

| person | helmet | no_helmet | work_uniform | no_work_uniform | all |
|---|---|---|---|---|---|
| 0.96 | 0.91 | 0.86 | 0.79 | 0.94 | 0.89 |

These test pictures are from public datasets, not our cameras, so add our own labelled frames over time.

Trained (YOLO, about 2,700 training pictures) on:

- "hard-hat & safety-vest" by chihs-workspace, Roboflow Universe, CC BY 4.0
- "Hard Hat Workers" by joseph-nelson, Roboflow Universe, Public Domain
- "Safety Vests" by echo-dotf3, Roboflow Universe, CC BY 4.0

## Restricted area

A camera can have one or more forbidden areas (polygons). Anyone whose **feet** (bottom middle of the person box) are
inside one is a violation: red box on the dashboard, and after `VIOLATION_CONFIRM_SECONDS` a saved violation with the
area drawn on the picture. Helmet and vest don't matter here. No new model is needed.

The DB has no own violation type for this yet, so it is saved as `OTHER_SAFETY_VIOLATION`
(already in the DB, backend and web). The live boxes also get `"restricted": true`.

Points are parts of the picture width/height (0..1), at least 3, on the picture the AI sees
(after rotation, before mirroring). Try them on a photo first, then save them:

```bash
python -m scripts.demo photo.jpg --area "0.6,0.5 0.95,0.5 0.95,0.95 0.6,0.95"   # check the red area
python -m scripts.set_area "Gate camera" "0.6,0.5 0.95,0.5 0.95,0.95 0.6,0.95"   # save (DATABASE_URL)
python -m scripts.set_area --list
python -m scripts.set_area "Gate camera" --clear
```

The AI reads the areas from `app_settings` (key `restricted_areas`) every ~10 s, so no restart is needed.
