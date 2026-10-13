from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_camera_manager
from app.config import get_settings
from app.core.security import create_stream_token, encrypt_secret
from app.database.database import get_db
from app.database.models import AppSetting, Camera, CameraStatus, CameraType, User, Violation, Zone
from app.schemas.camera import CameraCreate, CameraOut, CameraTestRequest, CameraUpdate, ConnectionTestResult
from app.services import camera_service
from app.websocket.manager import manager

router = APIRouter(prefix="/api/cameras", tags=["cameras"])


def _get_or_404(db: Session, camera_id: uuid.UUID) -> Camera:
    camera = db.get(Camera, camera_id)
    if not camera:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Camera not found")
    return camera


DEMO_CAMERAS_KEY = "demo_cameras"  # app_settings: demo хэрэглэгчийн нэмсэн камерын id-ууд


def _demo_camera_ids(db: Session) -> set[str]:
    row = db.get(AppSetting, DEMO_CAMERAS_KEY)
    return set(row.value.get("ids", [])) if row else set()


def _remember_demo_camera(db: Session, camera_id: uuid.UUID) -> None:
    ids = sorted(_demo_camera_ids(db) | {str(camera_id)})
    db.merge(AppSetting(key=DEMO_CAMERAS_KEY, value={"ids": ids}))


def _get_managed(db: Session, camera_id: uuid.UUID, user: User) -> Camera:
    """Demo хэрэглэгч бодит камеруудыг өөрчилж/устгаж чадахгүй — зөвхөн өөрийн нэмснийг."""
    camera = _get_or_404(db, camera_id)
    if get_settings().is_demo_email(user.email) and str(camera_id) not in _demo_camera_ids(db):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Demo эрхээр зөвхөн өөрийн нэмсэн камерыг өөрчилнө")
    return camera


def _check_zone(db: Session, zone_id: uuid.UUID | None) -> None:
    if zone_id is not None and db.get(Zone, zone_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown zone_id")


async def _announce(out: CameraOut) -> None:
    await manager.broadcast("CAMERA_UPDATED", out.model_dump(mode="json"))


# АНХААР: async endpoint дотор DB-г (sync SQLAlchemy) шууд дуудахгүй — run_in_threadpool-оор.
# Event loop дээр pool-оос холболт хүлээвэл (pool дүүрсэн үед 30 сек) бүх сервер гацна:
# бусад request-үүд холболтоо суллахын тулд яг тэр event loop хэрэгтэй (deadlock).


@router.get("", response_model=list[CameraOut])
def list_cameras(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    cameras = db.execute(select(Camera).order_by(Camera.name)).unique().scalars().all()
    return [camera_service.to_out(c) for c in cameras]


@router.post("", response_model=CameraOut, status_code=status.HTTP_201_CREATED)
async def create_camera(body: CameraCreate, db: Session = Depends(get_db), user: User = Depends(require_camera_manager)):
    def work() -> CameraOut:
        _check_zone(db, body.zone_id)
        data = body.model_dump(exclude={"password"})
        password = encrypt_secret(body.password.get_secret_value()) if body.password else None
        if body.camera_type not in (CameraType.LOCAL_WEBCAM, CameraType.BROWSER):
            data["mirror"] = False  # толин тусгал зөвхөн вэбкамерт; IP камер үргэлж анхдагч (эргүүлэхгүй)
        camera = Camera(**data, password_encrypted=password, status=CameraStatus.OFFLINE)
        db.add(camera)
        try:
            db.flush()
            if get_settings().is_demo_email(user.email):
                _remember_demo_camera(db, camera.id)
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status.HTTP_409_CONFLICT, "Энэ нэртэй камер аль хэдийн байна") from None
        db.refresh(camera)
        return camera_service.to_out(camera)

    out = await run_in_threadpool(work)
    await _announce(out)
    return out


_PROBE_DISABLED = ConnectionTestResult(
    success=False,
    status="ERROR",
    message="Connection test unavailable",
    reason="Backend cloud дээр ажиллаж байгаа тул камерыг шууд шалгах боломжгүй. Хадгалаад асаавал "
    "камертай нэг сүлжээнд байгаа AI service холбогдож, төлөв dashboard дээр харагдана.",
)


@router.post("/test-connection", response_model=ConnectionTestResult)
async def test_unsaved(body: CameraTestRequest, _: User = Depends(require_camera_manager)):
    """Камерыг хадгалахаас өмнө (Add form дээр) холболтыг шалгана."""
    if body.camera_type is CameraType.BROWSER:
        return camera_service.BROWSER_PROBE
    if not get_settings().camera_probe_enabled:
        return _PROBE_DISABLED
    if body.camera_type.value == "LOCAL_WEBCAM":
        return await run_in_threadpool(camera_service.probe_webcam, int(body.ip_address))
    return await run_in_threadpool(
        camera_service.probe_rtsp,
        username=body.username,
        password=body.password.get_secret_value(),
        ip=body.ip_address,
        port=body.rtsp_port,
        channel=body.channel,
        subtype=body.subtype,
        camera_type=body.camera_type.value,
    )


@router.get("/{camera_id}", response_model=CameraOut)
def get_camera(camera_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return camera_service.to_out(_get_or_404(db, camera_id))


@router.put("/{camera_id}", response_model=CameraOut)
async def update_camera(
    camera_id: uuid.UUID, body: CameraUpdate, db: Session = Depends(get_db), user: User = Depends(require_camera_manager)
):
    def work() -> CameraOut:
        camera = _get_managed(db, camera_id, user)
        changes = body.model_dump(exclude_unset=True, exclude={"password"})
        if "zone_id" in changes:
            _check_zone(db, changes["zone_id"])
        for key, value in changes.items():
            setattr(camera, key, value)
        if camera.camera_type not in (CameraType.LOCAL_WEBCAM, CameraType.BROWSER):
            camera.mirror = False
        if body.password is not None:
            camera.password_encrypted = encrypt_secret(body.password.get_secret_value())
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status.HTTP_409_CONFLICT, "Энэ нэртэй камер аль хэдийн байна") from None
        db.refresh(camera)
        return camera_service.to_out(camera)

    out = await run_in_threadpool(work)
    await _announce(out)
    return out


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_camera(
    camera_id: uuid.UUID, force: bool = False, db: Session = Depends(get_db), user: User = Depends(require_camera_manager)
):
    def work() -> None:
        camera = _get_managed(db, camera_id, user)
        count = db.execute(select(func.count()).select_from(Violation).where(Violation.camera_id == camera_id)).scalar_one()
        if count and not force:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Энэ камерт {count} violation бүртгэлтэй. Нотолгоо устахаас сэргийлж устгахгүй; "
                "Disconnect хийж орхино уу, эсвэл ?force=true-ээр violation-уудын хамт устгана уу.",
            )
        db.delete(camera)
        db.commit()

    await run_in_threadpool(work)
    await manager.broadcast("CAMERA_DELETED", {"id": str(camera_id)})


@router.post("/{camera_id}/test-connection", response_model=ConnectionTestResult)
async def test_connection(camera_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_camera_manager)):
    camera = await run_in_threadpool(_get_managed, db, camera_id, user)
    if not get_settings().camera_probe_enabled and camera.camera_type is not CameraType.BROWSER:
        return _PROBE_DISABLED
    return await run_in_threadpool(camera_service.probe_stored_camera, camera)


@router.post("/{camera_id}/connect", response_model=CameraOut)
async def connect_camera(camera_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_camera_manager)):
    """AI service идэвхтэй (enabled) камеруудыг DB-ээс уншиж ажиллуулна."""

    def work() -> CameraOut:
        camera = _get_managed(db, camera_id, user)
        camera.enabled = True
        if camera.status is CameraStatus.OFFLINE:
            camera.status = CameraStatus.CONNECTING
        db.commit()
        db.refresh(camera)
        return camera_service.to_out(camera)

    out = await run_in_threadpool(work)
    await _announce(out)
    return out


@router.post("/{camera_id}/disconnect", response_model=CameraOut)
async def disconnect_camera(camera_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_camera_manager)):
    def work() -> CameraOut:
        camera = _get_managed(db, camera_id, user)
        camera.enabled = False
        camera.status = CameraStatus.OFFLINE
        db.commit()
        db.refresh(camera)
        return camera_service.to_out(camera)

    out = await run_in_threadpool(work)
    await _announce(out)
    return out


@router.get("/{camera_id}/webrtc")
def webrtc_access(camera_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Шууд видеоны WebRTC (WHEP) хаяг + 2 минутын токен. Raw RTSP URL browser-д огт очихгүй."""
    camera = _get_or_404(db, camera_id)
    path = camera_service.stream_path(camera.id)
    settings = get_settings()
    return {
        "whep_url": f"{camera_service.public_media_url(db)}/{path}/whep",
        "token": create_stream_token(path),
        "expires_in": settings.stream_token_expire_seconds,
    }


@router.get("/{camera_id}/publish")
def publish_access(camera_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_camera_manager)):
    """BROWSER камер: энэ browser-ийн камерыг MediaMTX руу дамжуулах WHIP хаяг + publish токен."""
    camera = _get_managed(db, camera_id, user)
    if camera.camera_type is not CameraType.BROWSER:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Зөвхөн BROWSER төрлийн камераас дамжуулна")
    path = camera_service.stream_path(camera.id)
    settings = get_settings()
    return {
        "whip_url": f"{camera_service.public_media_url(db)}/{path}/whip",
        "token": create_stream_token(path, "publish"),
        "expires_in": settings.stream_token_expire_seconds,
    }
