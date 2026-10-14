"""SQL for cameras. Enum columns are cast to text when reading and back to the enum type when writing."""

from __future__ import annotations

import logging

from app.cameras.models import CameraInfo
from app.crypto import SecretBox
from app.db import Database

logger = logging.getLogger("ai.cameras")

CAMERAS_SQL = """
SELECT c.id::text, c.name, c.camera_type::text, c.ip_address, c.rtsp_port, c.username, c.password_encrypted,
       c.channel, c.subtype, COALESCE(c.rotation, 0), c.mirror, c.ai_enabled, z.type::text
FROM cameras c LEFT JOIN zones z ON z.id = c.zone_id
WHERE c.enabled
ORDER BY c.created_at
"""

STATUSES = {"OFFLINE", "CONNECTING", "ONLINE", "STREAMING", "ERROR", "RECONNECTING"}


def load_cameras(db: Database, secrets: SecretBox) -> list[CameraInfo]:
    cameras = []
    for row in db.fetch(CAMERAS_SQL):
        cid, name, kind, ip, port, user, pwd_enc, channel, subtype, rotation, mirror, ai_enabled, zone_type = row
        password = secrets.decrypt(pwd_enc)
        if pwd_enc and password is None:
            logger.error("Camera '%s': cannot decrypt password (CAMERA_SECRET_KEY differs from backend?)", name)
        cameras.append(
            CameraInfo(
                id=cid, name=name, camera_type=kind, ip_address=ip, rtsp_port=port or 554, username=user or "",
                password=password, channel=channel or 1, subtype=subtype or 0, rotation=rotation or 0,
                mirror=bool(mirror), ai_enabled=bool(ai_enabled), zone_type=zone_type,
            )
        )  # fmt: skip
    return cameras


def set_status(db: Database, camera_id: str, status: str) -> None:
    if status not in STATUSES:
        raise ValueError(status)
    if status == "STREAMING":
        db.execute("UPDATE cameras SET status = %s::camera_status, last_connected_at = now() WHERE id = %s", (status, camera_id))
    else:
        db.execute("UPDATE cameras SET status = %s::camera_status WHERE id = %s", (status, camera_id))
