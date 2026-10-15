from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class ZoneType(str, enum.Enum):
    FACTORY = "FACTORY"
    OFFICE = "OFFICE"


class CameraType(str, enum.Enum):
    DAHUA = "DAHUA"
    HIKVISION = "HIKVISION"
    GENERIC_RTSP = "GENERIC_RTSP"
    LOCAL_WEBCAM = "LOCAL_WEBCAM"  # Mac/ноутбукийн камер: ip_address = төхөөрөмжийн дугаар ("0")
    BROWSER = "BROWSER"  # dashboard-ыг нээсэн browser-ийн камер — WHIP-ээр MediaMTX руу дамжуулна


class CameraStatus(str, enum.Enum):
    OFFLINE = "OFFLINE"
    CONNECTING = "CONNECTING"
    ONLINE = "ONLINE"
    STREAMING = "STREAMING"
    ERROR = "ERROR"
    RECONNECTING = "RECONNECTING"


class ViolationType(str, enum.Enum):
    NO_HELMET = "NO_HELMET"
    NO_WORK_UNIFORM = "NO_WORK_UNIFORM"
    OTHER_SAFETY_VIOLATION = "OTHER_SAFETY_VIOLATION"


class ViolationStatus(str, enum.Enum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    HUB_EMPLOYEE = "HUB_EMPLOYEE"


def pg_enum(py_enum: type[enum.Enum], name: str) -> Enum:
    return Enum(py_enum, name=name, create_type=False, native_enum=True, values_callable=lambda e: [m.value for m in e])


class Base(DeclarativeBase):
    pass


class Zone(Base):
    __tablename__ = "zones"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    name: Mapped[str] = mapped_column(Text, unique=True)
    type: Mapped[ZoneType] = mapped_column(pg_enum(ZoneType, "zone_type"))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    name: Mapped[str] = mapped_column(Text, unique=True)
    ip_address: Mapped[str] = mapped_column(Text)
    rtsp_port: Mapped[int] = mapped_column(Integer, default=554)
    username: Mapped[str] = mapped_column(Text)
    password_encrypted: Mapped[str | None] = mapped_column(Text)  # Fernet. API-д хэзээ ч буцаахгүй
    camera_type: Mapped[CameraType] = mapped_column(pg_enum(CameraType, "camera_type"), default=CameraType.DAHUA)
    channel: Mapped[int] = mapped_column(Integer, default=1)
    subtype: Mapped[int] = mapped_column(Integer, default=0)
    zone_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("zones.id"))
    status: Mapped[CameraStatus] = mapped_column(pg_enum(CameraStatus, "camera_status"), default=CameraStatus.OFFLINE)
    mirror: Mapped[bool] = mapped_column(Boolean, default=False)
    rotation: Mapped[int] = mapped_column(Integer, default=0)  # 0/90/180/270° цагийн зүүнд
    ai_enabled: Mapped[bool] = mapped_column(Boolean, default=True)  # false: зөвхөн шууд видео, AI шинжилгээгүй
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    zone: Mapped[Zone | None] = relationship(lazy="joined")


class Violation(Base):
    __tablename__ = "violations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    camera_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cameras.id"))
    zone_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("zones.id"))
    violation_type: Mapped[ViolationType] = mapped_column(pg_enum(ViolationType, "violation_type"))
    person_id: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    snapshot_url: Mapped[str | None] = mapped_column(Text)
    storage_path: Mapped[str | None] = mapped_column(Text)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[ViolationStatus] = mapped_column(pg_enum(ViolationStatus, "violation_status"), default=ViolationStatus.OPEN)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    camera: Mapped[Camera] = relationship(lazy="joined")
    zone: Mapped[Zone | None] = relationship(lazy="joined")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    email: Mapped[str] = mapped_column(String, unique=True)
    full_name: Mapped[str | None] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[UserRole] = mapped_column(pg_enum(UserRole, "user_role"), default=UserRole.HUB_EMPLOYEE)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
