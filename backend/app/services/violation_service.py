from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import Camera, CameraStatus, User, Violation, ViolationStatus, ViolationType, Zone, ZoneType
from app.schemas.dashboard import DashboardStats
from app.schemas.violation import ViolationOut
from app.services.frame_store import ai_heartbeat
from app.services.storage_service import sign_paths

MAX_PAGE_SIZE = 100


class InvalidTransition(Exception):
    pass


def to_out(v: Violation, signed: dict[str, str]) -> ViolationOut:
    return ViolationOut(
        id=v.id,
        camera_id=v.camera_id,
        camera_name=v.camera.name,
        zone_id=v.zone_id,
        zone=v.zone.type if v.zone else None,
        violation_type=v.violation_type,
        person_id=v.person_id,
        confidence=v.confidence,
        snapshot_url=signed.get(v.storage_path) if v.storage_path else None,
        detected_at=v.detected_at,
        status=v.status,
        resolved_at=v.resolved_at,
        resolved_by=v.resolved_by,
        created_at=v.created_at,
    )


def serialize_many(violations: list[Violation]) -> list[ViolationOut]:
    signed = sign_paths(v.storage_path for v in violations)
    return [to_out(v, signed) for v in violations]


def list_violations(
    db: Session,
    *,
    status: ViolationStatus | None,
    zone: ZoneType | None,
    violation_type: ViolationType | None,
    camera_id: uuid.UUID | None,
    page: int,
    page_size: int,
) -> tuple[list[Violation], int]:
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    query = select(Violation)
    count = select(func.count()).select_from(Violation)
    if zone:
        query = query.join(Zone, Violation.zone_id == Zone.id).where(Zone.type == zone)
        count = count.join(Zone, Violation.zone_id == Zone.id).where(Zone.type == zone)
    for column, value in ((Violation.status, status), (Violation.violation_type, violation_type), (Violation.camera_id, camera_id)):
        if value is not None:
            query = query.where(column == value)
            count = count.where(column == value)
    rows = (
        db.execute(query.order_by(Violation.detected_at.desc()).limit(page_size).offset((max(page, 1) - 1) * page_size))
        .unique()
        .scalars()
        .all()
    )
    return list(rows), db.execute(count).scalar_one()


def acknowledge(db: Session, violation: Violation) -> Violation:
    if violation.status is not ViolationStatus.OPEN:
        raise InvalidTransition(f"Зөвхөн OPEN төлөвтэй violation-ыг acknowledge хийнэ (одоо: {violation.status.value})")
    violation.status = ViolationStatus.ACKNOWLEDGED
    db.commit()
    return violation


def resolve(db: Session, violation: Violation, user: User) -> Violation:
    if violation.status is ViolationStatus.RESOLVED:
        raise InvalidTransition("Violation аль хэдийн RESOLVED болсон")
    violation.status = ViolationStatus.RESOLVED
    violation.resolved_at = datetime.now(UTC)
    violation.resolved_by = user.email
    db.commit()
    return violation


def dashboard_stats(db: Session) -> DashboardStats:
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    online = (CameraStatus.ONLINE, CameraStatus.STREAMING)
    by_type = dict(db.execute(select(Violation.violation_type, func.count()).group_by(Violation.violation_type)).all())
    by_zone = dict(db.execute(select(Zone.type, func.count()).join(Violation, Violation.zone_id == Zone.id).group_by(Zone.type)).all())
    # Нэг query-гээр (нэг snapshot) тоолж, total >= open >= today-ийн зөрүүгүй байлгана
    total, open_count, today_count = db.execute(
        select(
            func.count(),
            func.count().filter(Violation.status == ViolationStatus.OPEN),
            func.count().filter(Violation.detected_at >= today),
        ).select_from(Violation)
    ).one()
    return DashboardStats(
        cameras_total=db.execute(select(func.count()).select_from(Camera)).scalar_one(),
        cameras_online=db.execute(select(func.count()).select_from(Camera).where(Camera.status.in_(online))).scalar_one(),
        violations_total=total,
        violations_open=open_count,
        violations_today=today_count,
        by_type={k.value: v for k, v in by_type.items()},
        by_zone={k.value: v for k, v in by_zone.items()},
        ai_status="ONLINE" if ai_heartbeat.alive else "OFFLINE",
    )


def event_payload(v: Violation, signed: dict[str, str]) -> dict:
    """WebSocket VIOLATION_CREATED data (spec §23)."""
    out = to_out(v, signed)
    return {
        "id": str(out.id),
        "camera_id": str(out.camera_id),
        "camera_name": out.camera_name,
        "zone": out.zone.value if out.zone else None,
        "violation_type": out.violation_type.value,
        "person_id": out.person_id,
        "confidence": out.confidence,
        "snapshot_url": out.snapshot_url,
        "detected_at": out.detected_at.isoformat(),
        "status": out.status.value,
    }
