from fastapi import APIRouter
from sqlalchemy import func, select, text

from app.database.database import new_session
from app.database.models import Camera, CameraStatus
from app.services.frame_store import ai_heartbeat

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    """Нийтэд нээлттэй, зөвхөн ерөнхий төлөв (нууц/дэлгэрэнгүйгүй)."""
    database, camera = "disconnected", "unknown"
    try:
        with new_session() as db:
            db.execute(text("select 1"))
            database = "connected"
            online = db.execute(
                select(func.count()).select_from(Camera).where(Camera.status.in_((CameraStatus.ONLINE, CameraStatus.STREAMING)))
            ).scalar_one()
            camera = "online" if online else "offline"
    except Exception:
        pass
    return {
        "status": "ok" if database == "connected" else "degraded",
        "database": database,
        "ai": "running" if ai_heartbeat.alive else "offline",
        "camera": camera,
    }
