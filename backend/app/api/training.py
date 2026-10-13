"""Модель сургалт: өгөгдөл цуглуулалт, шошглолт, сургалт. Зөвхөн ADMIN."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.config import get_settings
from app.database.database import get_db
from app.database.models import AppSetting, User
from app.services import training_service as svc

router = APIRouter(prefix="/api/training", tags=["training"])

COLLECTION_KEY = "dataset_collection"
MAX_IMAGES = 5000
INTERVAL_RANGE = (2, 3600)


def _root():
    return get_settings().resolved_training_dir


def _fail(exc: Exception) -> HTTPException:
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Зураг олдсонгүй")
    return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


class CollectionIn(BaseModel):
    enabled: bool
    interval_seconds: int = Field(10, ge=INTERVAL_RANGE[0], le=INTERVAL_RANGE[1])


class BoxIn(BaseModel):
    class_name: str
    x1: float = Field(ge=0, le=1)
    y1: float = Field(ge=0, le=1)
    x2: float = Field(ge=0, le=1)
    y2: float = Field(ge=0, le=1)


class LabelsIn(BaseModel):
    boxes: list[BoxIn] = Field(max_length=svc.MAX_BOXES)


class TrainIn(BaseModel):
    epochs: int = Field(40, ge=svc.EPOCHS_RANGE[0], le=svc.EPOCHS_RANGE[1])
    base: Literal["n", "s"] = "n"
    imgsz: Literal[512, 640, 960, 1280] = 512


def _collection(db: Session) -> dict:
    row = db.get(AppSetting, COLLECTION_KEY)
    value = row.value if row else {}
    return {
        "enabled": bool(value.get("enabled", False)),
        "interval_seconds": int(value.get("interval_seconds", 10)),
        "max_images": MAX_IMAGES,
    }


@router.get("/status")
def get_status(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return {
        "collection": _collection(db),
        **svc.counts(_root()),
        **svc.training_info(_root()),
        "interval_min": INTERVAL_RANGE[0],
        "interval_max": INTERVAL_RANGE[1],
    }


@router.put("/collection")
def set_collection(body: CollectionIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    value = {"enabled": body.enabled, "interval_seconds": body.interval_seconds, "max_images": MAX_IMAGES}
    row = db.get(AppSetting, COLLECTION_KEY)
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=COLLECTION_KEY, value=value))
    db.commit()
    return _collection(db)


@router.get("/images")
def list_images(
    filter: Literal["all", "unlabeled", "labeled"] = "all",
    offset: int = Query(0, ge=0),
    limit: int = Query(24, ge=1, le=100),
    _: User = Depends(require_admin),
):
    total, items = svc.list_images(_root(), filter, offset, limit)
    return {"total": total, "items": items}


@router.get("/images/{name}")
def get_image(name: str, _: User = Depends(require_admin)):
    try:
        path = svc.image_path(_root(), name)
    except (svc.TrainingError, FileNotFoundError) as exc:
        raise _fail(exc) from exc
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=300"})


@router.get("/images/{name}/labels")
def get_labels(name: str, _: User = Depends(require_admin)):
    try:
        svc.image_path(_root(), name)
        boxes, source = svc.read_boxes(_root(), name)
    except (svc.TrainingError, FileNotFoundError) as exc:
        raise _fail(exc) from exc
    return {"boxes": boxes, "source": source}


@router.put("/images/{name}/labels")
def put_labels(name: str, body: LabelsIn, _: User = Depends(require_admin)):
    try:
        svc.write_boxes(_root(), name, [b.model_dump() for b in body.boxes])
    except (svc.TrainingError, FileNotFoundError) as exc:
        raise _fail(exc) from exc
    return {"saved": len(body.boxes)}


@router.delete("/images/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_image(name: str, _: User = Depends(require_admin)):
    try:
        svc.delete_image(_root(), name)
    except svc.TrainingError as exc:
        raise _fail(exc) from exc


@router.delete("/images")
def delete_all_images(_: User = Depends(require_admin)):
    return {"deleted": svc.delete_all(_root())}


@router.get("/train")
def train_status(_: User = Depends(require_admin)):
    return svc.read_state(_root())


@router.post("/train", status_code=status.HTTP_202_ACCEPTED)
def train_start(body: TrainIn, _: User = Depends(require_admin)):
    python, script = svc.python_and_script(_root())
    try:
        svc.start_training(_root(), epochs=body.epochs, base=body.base, python=python, script=script, imgsz=body.imgsz)
    except svc.TrainingError as exc:
        raise _fail(exc) from exc
    return svc.read_state(_root())


@router.post("/train/stop")
def train_stop(_: User = Depends(require_admin)):
    return {"stopped": svc.stop_training(_root())}
