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

## Test

```bash
python -m pytest
```

## What talks to the backend

| Call | When |
|---|---|
| `POST /internal/heartbeat` | every `HEARTBEAT_SECONDS` — dashboard shows "AI ONLINE" |
