from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.database import get_db
from app.database.models import User, Zone, ZoneType

router = APIRouter(prefix="/api/zones", tags=["zones"])


class ZoneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    type: ZoneType
    description: str | None


@router.get("", response_model=list[ZoneOut])
def list_zones(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.execute(select(Zone).order_by(Zone.name)).scalars().all()
