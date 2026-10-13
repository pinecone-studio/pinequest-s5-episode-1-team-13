from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin, require_staff
from app.database.database import get_db
from app.database.models import User, Violation, ViolationStatus, ViolationType, ZoneType
from app.schemas.violation import ViolationOut, ViolationPage
from app.services import violation_service as svc
from app.services.retention import _storage_remove
from app.websocket.manager import manager

router = APIRouter(prefix="/api/violations", tags=["violations"])
logger = logging.getLogger("backend.violations")


def _get_or_404(db: Session, violation_id: uuid.UUID) -> Violation:
    violation = db.get(Violation, violation_id)
    if not violation:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Violation not found")
    return violation


@router.get("", response_model=ViolationPage)
async def list_violations(
    status_: ViolationStatus | None = Query(None, alias="status"),
    zone: ZoneType | None = None,
    violation_type: ViolationType | None = None,
    camera_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=svc.MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    def work():
        rows, total = svc.list_violations(
            db, status=status_, zone=zone, violation_type=violation_type, camera_id=camera_id, page=page, page_size=page_size
        )
        return ViolationPage(items=svc.serialize_many(rows), total=total, page=page, page_size=page_size)

    return await run_in_threadpool(work)


@router.get("/{violation_id}", response_model=ViolationOut)
async def get_violation(violation_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    def work():
        return svc.serialize_many([_get_or_404(db, violation_id)])[0]

    return await run_in_threadpool(work)


async def _transition(db: Session, violation_id: uuid.UUID, action) -> ViolationOut:
    def work():
        violation = _get_or_404(db, violation_id)
        try:
            action(violation)
        except svc.InvalidTransition as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        db.refresh(violation)
        return svc.serialize_many([violation])[0]

    out = await run_in_threadpool(work)
    await manager.broadcast("VIOLATION_UPDATED", out.model_dump(mode="json"))
    return out


@router.patch("/{violation_id}/acknowledge", response_model=ViolationOut)
async def acknowledge(violation_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(require_staff)):
    return await _transition(db, violation_id, lambda v: svc.acknowledge(db, v))


@router.patch("/{violation_id}/resolve", response_model=ViolationOut)
async def resolve(violation_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    return await _transition(db, violation_id, lambda v: svc.resolve(db, v, user))


@router.delete("/{violation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_violation(violation_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """Зөрчил + snapshot зургийг бүрмөсөн устгана. Зураг устгаж чадаагүй бол мөрийг үлдээнэ (retention-тэй адил)."""

    def work():
        violation = _get_or_404(db, violation_id)
        if violation.storage_path:
            try:
                _storage_remove([violation.storage_path])
            except Exception as exc:
                logger.warning("Snapshot устгаж чадсангүй | violation=%s: %s", violation_id, type(exc).__name__)
                raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Зургийг Storage-аас устгаж чадсангүй. Дахин оролдоно уу.") from exc
        db.delete(violation)
        db.commit()
        logger.info("Violation deleted | id=%s by=%s", violation_id, user.email)

    await run_in_threadpool(work)
    await manager.broadcast("VIOLATION_DELETED", {"id": str(violation_id)})
