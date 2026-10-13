"""ai-service -> backend дотоод endpoint-ууд (X-Internal-Key). Browser-д зориулагдаагүй.

AI SERVICE -> FASTAPI -> WEBSOCKET -> NEXT.JS
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool

from app.api.deps import verify_internal_key
from app.database.database import new_session
from app.database.models import Camera, Violation
from app.services import camera_service
from app.services import violation_service as svc
from app.services.frame_store import ai_heartbeat
from app.services.storage_service import sign_paths
from app.websocket.manager import manager

router = APIRouter(prefix="/internal", tags=["internal"], dependencies=[Depends(verify_internal_key)])


def _violation_event(violation_id: uuid.UUID) -> dict | None:
    with new_session() as db:
        v = db.get(Violation, violation_id)
        if not v:
            return None
        return svc.event_payload(v, sign_paths([v.storage_path]))


def _camera_event(camera_id: uuid.UUID) -> dict | None:
    with new_session() as db:
        c = db.get(Camera, camera_id)
        return camera_service.to_out(c).model_dump(mode="json") if c else None


@router.post("/heartbeat", status_code=status.HTTP_204_NO_CONTENT)
def heartbeat():
    ai_heartbeat.beat()


@router.post("/violations/{violation_id}/created", status_code=status.HTTP_204_NO_CONTENT)
async def violation_created(violation_id: uuid.UUID):
    ai_heartbeat.beat()
    payload = await run_in_threadpool(_violation_event, violation_id)
    if payload is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Violation not found")
    await manager.broadcast("VIOLATION_CREATED", payload)


@router.post("/cameras/{camera_id}/status", status_code=status.HTTP_204_NO_CONTENT)
async def camera_status(camera_id: uuid.UUID):
    ai_heartbeat.beat()
    payload = await run_in_threadpool(_camera_event, camera_id)
    if payload is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Camera not found")
    await manager.broadcast("CAMERA_UPDATED", payload)


@router.put("/cameras/{camera_id}/detections", status_code=status.HTTP_204_NO_CONTENT)
async def put_detections(camera_id: uuid.UUID, payload: dict):
    """AI-ийн илрүүлэлт (normalized box + PPE төлөв). Хадгалахгүй, зөвхөн WebSocket-ээр dashboard-д дамжуулна."""
    ai_heartbeat.beat()
    people = payload.get("people")
    if not isinstance(people, list) or len(people) > 50:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid detections")
    await manager.broadcast("DETECTIONS", {"camera_id": str(camera_id), **payload})
