"""Camera row from the database, as the AI needs it."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CameraInfo:
    id: str
    name: str
    camera_type: str  # DAHUA | HIKVISION | GENERIC_RTSP | LOCAL_WEBCAM | BROWSER
    ip_address: str
    rtsp_port: int
    username: str
    password: str | None  # already decrypted
    channel: int
    subtype: int
    rotation: int  # 0/90/180/270, clockwise
    mirror: bool
    ai_enabled: bool
    zone_type: str | None  # FACTORY | OFFICE | None

    @property
    def is_browser(self) -> bool:
        return self.camera_type == "BROWSER"

    def connection_key(self) -> tuple:
        """If any of these change, the video connection must be reopened."""
        return (self.camera_type, self.ip_address, self.rtsp_port, self.username, self.password, self.channel, self.subtype)
