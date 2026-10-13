"""Snapshot зураг + зөрчлийн бүртгэлийг хугацаа хэтэрмэгц автоматаар устгана (retention).

SNAPSHOT_RETENTION_MINUTES (backend/.env). 0 = унтраалттай. Хугацаа нь `detected_at`-аас тооцогдоно.
Эхлээд Storage-ийн зургийг, дараа нь DB-ийн мөрийг устгана (зураг устгаж чадаагүй бол мөрийг устгахгүй — дараагийн удаа дахин оролдоно).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import delete, select

from app.config import get_settings
from app.database.database import new_session
from app.database.models import Violation
from app.websocket.manager import manager

logger = logging.getLogger("backend.retention")
BATCH = 50


def purge_older_than(cutoff: datetime, remove_objects: Callable[[list[str]], None]) -> int:
    """`cutoff`-оос өмнөх зөрчил + зургийг устгана. Устгасан зөрчлийн тоог буцаана."""
    deleted = 0
    with new_session() as db:
        while True:
            rows = db.execute(select(Violation.id, Violation.storage_path).where(Violation.detected_at < cutoff).limit(BATCH)).all()
            if not rows:
                break
            paths = [p for _, p in rows if p]
            if paths:
                remove_objects(paths)  # алдаа гарвал exception — мөрүүд хэвээр үлдэнэ
            db.execute(delete(Violation).where(Violation.id.in_([i for i, _ in rows])))
            db.commit()
            deleted += len(rows)
    return deleted


def _storage_remove(paths: Iterable[str]) -> None:
    from app.services.storage_service import _bucket

    _bucket().remove(list(paths))


async def retention_loop() -> None:
    minutes = get_settings().snapshot_retention_minutes
    if minutes <= 0:
        logger.info("Snapshot retention унтраалттай (SNAPSHOT_RETENTION_MINUTES=0)")
        return
    interval = 60 if minutes <= 120 else 600
    logger.info("Snapshot retention: %d минутаас хуучныг %d сек тутам устгана", minutes, interval)
    while True:
        try:
            cutoff = datetime.now(UTC) - timedelta(minutes=minutes)
            count = await run_in_threadpool(purge_older_than, cutoff, _storage_remove)
            if count:
                logger.info("Retention: %d зөрчил (зурагтай нь) устгагдлаа", count)
                await manager.broadcast("VIOLATIONS_PURGED", {"count": count})
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # дараагийн мөчлөгт дахин оролдоно
            logger.error("Retention алдаа: %s", type(exc).__name__)
        await asyncio.sleep(interval)
