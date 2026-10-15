from __future__ import annotations

import ipaddress
import re
import uuid
from datetime import datetime
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from app.database.models import CameraStatus, CameraType

_HOST_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")


def _validate_host(value: str) -> str:
    value = value.strip()
    try:
        ipaddress.ip_address(value)
        return value
    except ValueError:
        pass
    if not _HOST_RE.match(value):
        raise ValueError("ip_address must be a valid IP address or hostname")
    return value


RTSP_URL_PREFIXES = ("rtsp://", "rtsps://")


def _validate_address(value: str) -> str:
    """IP/hostname, эсвэл GENERIC_RTSP-д бүтэн RTSP хаяг (утасны апп гэх мэт өөр path-тай камер):
    rtsp://192.168.1.50:8080/h264.sdp. Нэвтрэх нэр/нууц үгийг URL-д бичихгүй — Username/Password талбарт
    (нууц үг шифрлэгдэж хадгалагдана, ip_address харин API-д нээлттэй буцдаг)."""
    value = value.strip()
    if not value.lower().startswith(RTSP_URL_PREFIXES):
        return _validate_host(value)
    if len(value) > 300 or any(c.isspace() for c in value):
        raise ValueError("RTSP хаяг буруу байна")
    parts = urlsplit(value)
    if parts.username is not None or parts.password is not None:
        raise ValueError("RTSP хаягт нэр/нууц үг бичихгүй — Username, Password талбарт оруулна уу")
    if not parts.hostname:
        raise ValueError("RTSP хаягт host алга")
    _validate_host(parts.hostname)
    try:
        parts.port  # noqa: B018 — буруу порт бол ValueError
    except ValueError:
        raise ValueError("RTSP хаягийн порт буруу байна") from None
    return value


_ROTATIONS = (0, 90, 180, 270)


def _validate_rotation(v):
    if v is not None and v not in _ROTATIONS:
        raise ValueError("rotation нь 0, 90, 180, 270 байна")
    return v


class CameraBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    ip_address: str  # LOCAL_WEBCAM үед төхөөрөмжийн дугаар ("0", "1")
    rtsp_port: int = Field(554, ge=1, le=65535)
    username: str | None = Field(None, max_length=100)
    camera_type: CameraType = CameraType.DAHUA
    channel: int = Field(1, ge=1, le=256)
    subtype: int = Field(0, ge=0, le=9)
    zone_id: uuid.UUID | None = None
    mirror: bool = False  # LOCAL_WEBCAM: толин тусгал (selfie) харагдац
    rotation: int = 0  # хараа цагийн зүүнд 0/90/180/270° эргүүлэх
    ai_enabled: bool = True  # AI-тай холбох (хүн/каск/хувцас илрүүлж зөрчил бүртгэнэ)

    @field_validator("ip_address")
    @classmethod
    def _host(cls, v: str) -> str:
        return _validate_address(v)

    @field_validator("name", "username")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        return v.strip() if v is not None else v

    _rotation = field_validator("rotation")(_validate_rotation)

    @model_validator(mode="after")
    def _webcam_or_rtsp(self):
        if self.camera_type is CameraType.LOCAL_WEBCAM:
            if not self.ip_address.isdigit() or len(self.ip_address) > 2:
                raise ValueError("LOCAL_WEBCAM: ip_address талбарт камерын төхөөрөмжийн дугаар (0, 1, ...) оруулна")
            self.username = "-"
        elif self.camera_type is CameraType.BROWSER:  # хаяг/нэвтрэлт хэрэггүй
            self.ip_address, self.username = "browser", "-"
        elif not self.username:
            raise ValueError("username шаардлагатай")
        if self.ip_address.lower().startswith(RTSP_URL_PREFIXES) and self.camera_type is not CameraType.GENERIC_RTSP:
            raise ValueError("Бүтэн RTSP хаягийг зөвхөн GENERIC_RTSP төрөлд оруулна")
        return self


class CameraCreate(CameraBase):
    password: SecretStr | None = Field(None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def _password_for_rtsp(self):
        if self.camera_type not in (CameraType.LOCAL_WEBCAM, CameraType.BROWSER) and self.password is None:
            raise ValueError("password шаардлагатай")
        return self


class CameraUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    ip_address: str | None = None
    rtsp_port: int | None = Field(None, ge=1, le=65535)
    username: str | None = Field(None, min_length=1, max_length=100)
    password: SecretStr | None = Field(None, min_length=1, max_length=200)  # өгөхгүй бол хуучин нууц үг хэвээр
    camera_type: CameraType | None = None
    channel: int | None = Field(None, ge=1, le=256)
    subtype: int | None = Field(None, ge=0, le=9)
    zone_id: uuid.UUID | None = None
    mirror: bool | None = None
    rotation: int | None = None
    ai_enabled: bool | None = None

    @field_validator("ip_address")
    @classmethod
    def _host(cls, v: str | None) -> str | None:
        return _validate_address(v) if v is not None else v

    _rotation = field_validator("rotation")(_validate_rotation)


class CameraTestRequest(CameraCreate):
    pass


class CameraOut(BaseModel):
    """Нууц үг, RTSP URL-ийг ХЭЗЭЭ Ч агуулахгүй."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    ip_address: str
    rtsp_port: int
    username: str
    camera_type: CameraType
    channel: int
    subtype: int
    zone_id: uuid.UUID | None
    zone: str | None = None
    status: CameraStatus
    mirror: bool
    rotation: int = 0
    ai_enabled: bool
    enabled: bool
    last_connected_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ConnectionTestResult(BaseModel):
    success: bool
    status: str  # ONLINE | ERROR
    message: str
    reason: str | None = None  # алдааны тодорхой шалтгаан (нууц үг агуулахгүй)
    resolution: str | None = None


# Хориотой бүс: AI-ийн харж буй зураг дээрх (эргүүлсний дараа, толин тусгалаас өмнө) 0..1 координаттай олон өнцөгт.
# Хүний хөл (боксын доод төв) дотор нь орвол зөрчил. ai-service/app/detection/areas.py-тэй ижил формат.
MAX_AREAS, MAX_AREA_POINTS = 5, 30


class RestrictedAreas(BaseModel):
    areas: list[list[tuple[float, float]]] = Field(default_factory=list, max_length=MAX_AREAS)

    @field_validator("areas")
    @classmethod
    def _check(cls, areas: list[list[tuple[float, float]]]) -> list[list[tuple[float, float]]]:
        for poly in areas:
            if not 3 <= len(poly) <= MAX_AREA_POINTS:
                raise ValueError(f"each area needs 3..{MAX_AREA_POINTS} points")
            for x, y in poly:
                if not (0 <= x <= 1 and 0 <= y <= 1):
                    raise ValueError("points must be between 0 and 1")
        return [[(round(x, 4), round(y, 4)) for x, y in poly] for poly in areas]
