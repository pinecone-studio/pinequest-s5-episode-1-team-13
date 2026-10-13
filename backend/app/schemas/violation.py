from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.database.models import ViolationStatus, ViolationType, ZoneType


class ViolationOut(BaseModel):
    id: uuid.UUID
    camera_id: uuid.UUID
    camera_name: str
    zone_id: uuid.UUID | None
    zone: ZoneType | None
    violation_type: ViolationType
    person_id: str | None
    confidence: float | None
    snapshot_url: str | None  # богино хугацаатай signed URL (bucket private)
    detected_at: datetime
    status: ViolationStatus
    resolved_at: datetime | None
    resolved_by: str | None
    created_at: datetime


class ViolationPage(BaseModel):
    items: list[ViolationOut]
    total: int
    page: int
    page_size: int
