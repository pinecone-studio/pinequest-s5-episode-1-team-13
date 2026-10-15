"""Камерын CRUD туслахууд, RTSP URL үүсгэх, холболт шалгах (TEST CONNECTION).

Камерын нууц үг DB-д Fernet-ээр шифрлэгдэж хадгалагдана; API response, log-д хэзээ ч гарахгүй.
"""

from __future__ import annotations

import os

# TCP transport (UDP-ээс найдвартай). cv2 import-оос ӨМНӨ.
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

import base64
import hashlib
import hmac
import logging
import socket
import time
from urllib.parse import quote, urlsplit

import cv2

from app.config import get_settings
from app.core.security import decrypt_secret
from app.database.models import AppSetting, Camera, CameraType
from app.schemas.camera import CameraOut, ConnectionTestResult

logger = logging.getLogger("backend.camera")

OPEN_TIMEOUT_MS = 8000
READ_TIMEOUT_MS = 8000


def build_rtsp_url(
    username: str,
    password: str,
    ip: str,
    port: int,
    channel: int,
    subtype: int,
    camera_type: str = "DAHUA",
) -> str:
    """DAHUA: rtsp://user:pass@ip:554/cam/realmonitor?channel=1&subtype=0 (нууц үгийг URL-encode хийнэ)."""
    user, pwd = quote(username, safe=""), quote(password, safe="")
    kind = camera_type.upper()
    if kind == "DAHUA":
        return f"rtsp://{user}:{pwd}@{ip}:{port}/cam/realmonitor?channel={channel}&subtype={subtype}"
    if kind == "HIKVISION":
        return f"rtsp://{user}:{pwd}@{ip}:{port}/Streaming/Channels/{channel * 100 + subtype + 1}"
    if kind == "GENERIC_RTSP":  # ai-service/app/cameras/sources.py-тэй ижил
        if ip.lower().startswith(("rtsp://", "rtsps://")):  # бүтэн хаяг: нэр/нууц үгийг host-ын өмнө нэмнэ
            parts = urlsplit(ip)
            netloc = f"{user}:{pwd}@{parts.hostname}" + (f":{parts.port}" if parts.port else "")
            return parts._replace(netloc=netloc).geturl()
        return f"rtsp://{user}:{pwd}@{ip}:{port}/"
    raise ValueError(f"{camera_type} төрлийн камерын RTSP хаягийг автоматаар үүсгэх боломжгүй")


def stream_path(camera_id) -> str:
    """MediaMTX path нэр. ai-service-тэй ЯГ ИЖИЛ байх ёстой."""
    return f"cam_{camera_id}"


EDGE_KEY = "mediamtx_edge"
EDGE_MAX_AGE_SECONDS = 180  # edge машин минут тутам шинэчилнэ; 3 минут чимээгүй бол tunnel унтарсан гэж үзнэ
EDGE_URL_MAX_LENGTH = 300


def clean_edge_url(url: str) -> str | None:
    """Edge-ийн мэдэгдсэн MediaMTX хаяг: зөвхөн `https://host[:port]` (browser-т шууд очих тул path/query/нууц үг хориглоно)."""
    url = url.strip().rstrip("/")
    if len(url) > EDGE_URL_MAX_LENGTH:
        return None
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        return None
    if parts.path or parts.query or parts.fragment:
        return None
    host = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
    return f"https://{host}" + (f":{port}" if port else "")


def public_media_url(db, now: float | None = None) -> str:
    """Browser-ийн холбогдох MediaMTX (WHEP/WHIP) хаяг.

    Cloud backend (CAMERA_PROBE_ENABLED=false, Railway)-д камертай нэг сүлжээний edge машин (start-edge.command) cloudflared tunnel-ийн
    хаягийг ажиллах бүрт өөрчилдөг. Railway-ийн хувьсагчийг гараар солихын оронд edge хаягаа хуваалцсан DB-д (`app_settings`) минут
    тутам бичиж, backend эндээс уншина. Шинэ (<3 мин) https хаяг байвал тэрийг, үгүй бол MEDIAMTX_PUBLIC_URL-ийг ашиглана.
    Локал backend-д (probe асаалттай) үргэлж MEDIAMTX_PUBLIC_URL (localhost) — өөр хүний edge-д холбогдохгүй.
    """
    settings = get_settings()
    if not settings.camera_probe_enabled:
        row = db.get(AppSetting, EDGE_KEY)
        value = row.value if row is not None else None
        if isinstance(value, dict):
            url, at = value.get("url"), value.get("at")
            fresh = isinstance(at, (int, float)) and 0 <= (now if now is not None else time.time()) - at <= EDGE_MAX_AGE_SECONDS
            if isinstance(url, str) and url.startswith("https://") and fresh:
                return url.rstrip("/")
    return settings.mediamtx_public_url.rstrip("/")


_STUN_SCHEMES = ("stun:", "stuns:")
_TURN_SCHEMES = ("turn:", "turns:")
TURN_USER_SUFFIX = "pinequest"


def _split_urls(value: str, schemes: tuple[str, ...]) -> tuple[list[str], list[str]]:
    """(зөв, буруу) хаягууд. Буруу хаягтай iceServers өгвөл browser-ийн RTCPeerConnection exception шиддэг."""
    urls = [u.strip() for u in value.split(",") if u.strip()]
    return [u for u in urls if u.lower().startswith(schemes)], [u for u in urls if not u.lower().startswith(schemes)]


def _turn_credentials(now: float | None = None) -> tuple[str, str] | None:
    s = get_settings()
    if s.turn_secret:
        # coturn REST API (use-auth-secret): username = "<дуусах unix хугацаа>:<нэр>", credential = base64(HMAC-SHA1(secret, username))
        expiry = int(now if now is not None else time.time()) + s.turn_credential_ttl_seconds
        username = f"{expiry}:{TURN_USER_SUFFIX}"
        digest = hmac.new(s.turn_secret.encode("utf-8"), username.encode("utf-8"), hashlib.sha1).digest()
        return username, base64.b64encode(digest).decode("ascii")
    if s.turn_username and s.turn_password:
        return s.turn_username, s.turn_password
    return None


def ice_servers(now: float | None = None) -> list[dict]:
    """Browser-ийн RTCPeerConnection `iceServers` (STUN + TURN). Credential-гүй TURN-ийг browser хүлээж авахгүй тул алгасна."""
    s = get_settings()
    servers: list[dict] = []
    stun, _ = _split_urls(s.webrtc_stun_urls, _STUN_SCHEMES)
    if stun:
        servers.append({"urls": stun})
    turn, _ = _split_urls(s.turn_urls, _TURN_SCHEMES)
    credentials = _turn_credentials(now) if turn else None
    if credentials:
        servers.append({"urls": turn, "username": credentials[0], "credential": credentials[1]})
    return servers


def ice_config_warnings() -> list[str]:
    """Backend асахад log-д бичих WebRTC ICE тохиргооны алдаанууд (хүсэлт бүрт давтахгүй)."""
    s = get_settings()
    warnings = []
    _, bad_stun = _split_urls(s.webrtc_stun_urls, _STUN_SCHEMES)
    turn, bad_turn = _split_urls(s.turn_urls, _TURN_SCHEMES)
    if bad_stun:
        warnings.append(f"WEBRTC_STUN_URLS: stun:/stuns:-ээр эхлээгүй хаягийг алгаслаа: {', '.join(bad_stun)}")
    if bad_turn:
        warnings.append(f"TURN_URLS: turn:/turns:-ээр эхлээгүй хаягийг алгаслаа: {', '.join(bad_turn)}")
    if turn and _turn_credentials() is None:
        warnings.append("TURN_URLS тохируулсан ч TURN_SECRET эсвэл TURN_USERNAME/TURN_PASSWORD байхгүй — TURN ашиглагдахгүй")
    return warnings


def to_out(camera: Camera) -> CameraOut:
    # `zone` нь ORM-д relationship тул from_attributes ашиглахгүй, талбар бүрийг тодорхой зааж өгнө
    return CameraOut(
        id=camera.id,
        name=camera.name,
        ip_address=camera.ip_address,
        rtsp_port=camera.rtsp_port,
        username=camera.username,
        camera_type=camera.camera_type,
        channel=camera.channel,
        subtype=camera.subtype,
        zone_id=camera.zone_id,
        zone=camera.zone.name if camera.zone else None,
        status=camera.status,
        mirror=camera.mirror,
        rotation=camera.rotation or 0,
        ai_enabled=camera.ai_enabled,
        enabled=camera.enabled,
        last_connected_at=camera.last_connected_at,
        created_at=camera.created_at,
        updated_at=camera.updated_at,
    )


def probe_rtsp(*, username: str, password: str, ip: str, port: int, channel: int, subtype: int, camera_type: str) -> ConnectionTestResult:
    """Блоклодог функц — threadpool дотор дуудна. Нууц үг буцаах message-д ОРОХГҮЙ."""
    try:
        url = build_rtsp_url(username, password, ip, port, channel, subtype, camera_type)
    except ValueError as exc:
        return ConnectionTestResult(success=False, status="ERROR", message="Unable to connect to RTSP stream", reason=str(exc))

    if ip.lower().startswith(("rtsp://", "rtsps://")):  # бүтэн RTSP хаяг: TCP шалгалтад host/порт-ыг URL-аас авна
        parts = urlsplit(ip)
        ip, port = parts.hostname or ip, parts.port or (322 if parts.scheme.lower() == "rtsps" else 554)

    def fail(reason: str) -> ConnectionTestResult:
        logger.warning("Camera connection test failed | ip=%s port=%s reason=%s", ip, port, reason)
        return ConnectionTestResult(success=False, status="ERROR", message="Unable to connect to RTSP stream", reason=reason)

    try:
        with socket.create_connection((ip, port), timeout=3):
            pass
    except socket.gaierror:
        return fail(f"'{ip}' хаягийг олсонгүй (IP/hostname буруу байна)")
    except TimeoutError:
        return fail(f"{ip}:{port} руу TCP холболт хугацаа хэтэрлээ (IP буруу, камер унтраалттай, эсвэл өөр сүлжээнд байна)")
    except OSError as exc:
        return fail(
            f"{ip}:{port} руу TCP холболт амжилтгүй: {exc.strerror or type(exc).__name__} (порт буруу эсвэл камерын RTSP хаалттай байж магадгүй)"
        )

    cap = cv2.VideoCapture(
        url,
        cv2.CAP_FFMPEG,
        [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, OPEN_TIMEOUT_MS, cv2.CAP_PROP_READ_TIMEOUT_MSEC, READ_TIMEOUT_MS],
    )
    try:
        if not cap.isOpened():
            return fail("Порт нээлттэй боловч RTSP stream нээгдсэнгүй (хэрэглэгчийн нэр/нууц үг, channel/subtype-ээ шалгана уу)")
        frame = None
        for _ in range(5):
            ok, frame = cap.read()
            if ok and frame is not None:
                break
        if frame is None:
            return fail("RTSP stream нээгдсэн ч зураг (frame) ирсэнгүй (codec/stream тохиргоог шалгана уу)")
        h, w = frame.shape[:2]
        return ConnectionTestResult(success=True, status="ONLINE", message="Camera connected successfully", resolution=f"{w}x{h}")
    finally:
        cap.release()


def probe_webcam(index: int) -> ConnectionTestResult:
    """Mac/ноутбукийн камер. Блоклодог — threadpool дотор дуудна."""
    import sys

    cap = cv2.VideoCapture(index, cv2.CAP_AVFOUNDATION) if sys.platform == "darwin" else cv2.VideoCapture(index)
    try:
        if not cap.isOpened():
            reason = (
                f"Камер #{index} нээгдсэнгүй. macOS: System Settings → Privacy & Security → Camera хэсэгт "
                "backend ажиллаж буй програмд (Terminal/Claude) зөвшөөрөл өгнө үү; дугаар буруу байж болно."
            )
            logger.warning("Webcam test failed | index=%s", index)
            return ConnectionTestResult(success=False, status="ERROR", message="Unable to connect to RTSP stream", reason=reason)
        frame = None
        for _ in range(15):  # вэбкамер эхний хэдэн frame-д гэрэлтүүлгээ тохируулдаг
            ok, frame = cap.read()
            if ok and frame is not None:
                break
        if frame is None:
            return ConnectionTestResult(
                success=False,
                status="ERROR",
                message="Unable to connect to RTSP stream",
                reason=f"Камер #{index} нээгдсэн ч зураг ирсэнгүй (өөр програм ашиглаж байж магадгүй)",
            )
        h, w = frame.shape[:2]
        return ConnectionTestResult(success=True, status="ONLINE", message="Camera connected successfully", resolution=f"{w}x{h}")
    finally:
        cap.release()


BROWSER_PROBE = ConnectionTestResult(
    success=True,
    status="ONLINE",
    message="Browser camera",
    reason='Browser камерыг шалгах шаардлагагүй: хадгалаад dashboard дээр "Энэ төхөөрөмжөөс дамжуулах" дарна.',
)


def probe_stored_camera(camera: Camera) -> ConnectionTestResult:
    if camera.camera_type is CameraType.BROWSER:
        return BROWSER_PROBE
    if camera.camera_type is CameraType.LOCAL_WEBCAM:
        return probe_webcam(int(camera.ip_address) if camera.ip_address.isdigit() else 0)
    password = decrypt_secret(camera.password_encrypted) if camera.password_encrypted else None
    if password is None:
        return ConnectionTestResult(
            success=False,
            status="ERROR",
            message="Unable to connect to RTSP stream",
            reason="Камерын нууц үг хадгалагдаагүй эсвэл тайлж чадсангүй (камерыг засаж нууц үгийг дахин оруулна уу)",
        )
    return probe_rtsp(
        username=camera.username,
        password=password,
        ip=camera.ip_address,
        port=camera.rtsp_port,
        channel=camera.channel,
        subtype=camera.subtype,
        camera_type=camera.camera_type.value,
    )
