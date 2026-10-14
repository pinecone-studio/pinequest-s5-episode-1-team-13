"""Where to read each camera's video from (same URL rules as backend/app/services/camera_service.py)."""

from __future__ import annotations

from urllib.parse import quote, urlsplit, urlunsplit

from app.cameras.models import CameraInfo


def stream_path(camera_id: str) -> str:
    """MediaMTX path name. Must be EXACTLY the same as backend camera_service.stream_path."""
    return f"cam_{camera_id}"


def mediamtx_url(base: str, camera_id: str, internal_key: str) -> str:
    """rtsp://ai:<INTERNAL_API_KEY>@host:8554/cam_<id> — MediaMTX asks the backend, which allows user 'ai' with this key."""
    parts = urlsplit(base.rstrip("/"))
    netloc = f"ai:{quote(internal_key, safe='')}@{parts.hostname}" + (f":{parts.port}" if parts.port else "")
    return urlunsplit((parts.scheme or "rtsp", netloc, f"/{stream_path(camera_id)}", "", ""))


def _with_credentials(url: str, user: str, password: str | None) -> str:
    parts = urlsplit(url)
    if parts.username or not user or user == "-":
        return url
    cred = quote(user, safe="") + (f":{quote(password, safe='')}" if password else "")
    host = parts.hostname or ""
    netloc = f"{cred}@{host}" + (f":{parts.port}" if parts.port else "")
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def source_for(camera: CameraInfo, mediamtx_base: str, internal_key: str) -> str | int:
    """Returns an RTSP URL, or an int device index for LOCAL_WEBCAM."""
    kind = camera.camera_type
    user, pwd = quote(camera.username, safe=""), quote(camera.password or "", safe="")
    ip, port = camera.ip_address, camera.rtsp_port
    if kind == "LOCAL_WEBCAM":
        return int(camera.ip_address)
    if kind == "BROWSER":
        return mediamtx_url(mediamtx_base, camera.id, internal_key)
    if kind == "DAHUA":
        return f"rtsp://{user}:{pwd}@{ip}:{port}/cam/realmonitor?channel={camera.channel}&subtype={camera.subtype}"
    if kind == "HIKVISION":
        return f"rtsp://{user}:{pwd}@{ip}:{port}/Streaming/Channels/{camera.channel * 100 + camera.subtype + 1}"
    if kind == "GENERIC_RTSP":
        if ip.startswith(("rtsp://", "rtsps://")):  # full URL typed in the IP field
            return _with_credentials(ip, camera.username, camera.password)
        return f"rtsp://{user}:{pwd}@{ip}:{port}/"
    raise ValueError(f"Unknown camera type: {kind}")


def safe_label(source: str | int) -> str:
    """For logs: never print passwords."""
    if isinstance(source, int):
        return f"webcam #{source}"
    parts = urlsplit(source)
    return f"{parts.scheme}://{parts.hostname}:{parts.port or ''}{parts.path}"
