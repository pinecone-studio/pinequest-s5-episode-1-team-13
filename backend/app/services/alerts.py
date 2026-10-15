"""Мониторинг: DB, AI service, камер, edge tunnel унтарвал (мөн сэргэвэл) webhook-оор alert илгээнэ.

ALERT_WEBHOOK_URL (backend/.env, Railway): Discord, Slack, Telegram эсвэл {"text": ...} хүлээн авдаг ямар ч webhook.
URL нь token агуулдаг тул log-д хэзээ ч бичихгүй (зөвхөн host). Backend өөрөө унавал энэ ажиллахгүй — гаднаас
/health-ийг UptimeRobot шалгана (SECURITY.md).
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit, urlunsplit

import httpx
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select, text

from app.config import get_settings
from app.database.database import new_session
from app.database.models import AppSetting, Camera, CameraStatus
from app.services.camera_service import EDGE_KEY, EDGE_MAX_AGE_SECONDS
from app.services.frame_store import ai_heartbeat

logger = logging.getLogger("backend.alerts")
# httpx INFO log-д хүсэлтийн бүтэн URL (webhook token) гардаг
logging.getLogger("httpx").setLevel(logging.WARNING)

FAIL_THRESHOLD = 2  # дараалсан хэдэн шалгалт амжилтгүй бол alert (нэг удаагийн тасалдлыг алгасна)
TIMEOUT_SECONDS = 10.0
MAX_TEXT = 1900  # Discord-ийн content 2000 тэмдэгтээс хэтрэхгүй
MAX_PENDING = 50
_DISCORD_HOSTS = {"discord.com", "discordapp.com", "ptb.discord.com", "canary.discord.com"}
_PROBLEM_STATUSES = (CameraStatus.OFFLINE, CameraStatus.ERROR)


@dataclass(frozen=True)
class Problem:
    key: str  # шалгалтын тогтмол түлхүүр ("db", "ai", "edge", "camera:<id>")
    label: str  # хүний унших нэр
    detail: str


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def webhook_problem(url: str) -> str | None:
    """ALERT_WEBHOOK_URL-ийн тохиргооны алдаа (URL-ийг өөрийг нь буцаахгүй)."""
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        return "ALERT_WEBHOOK_URL https://... байх ёстой"
    if parts.hostname.lower() == "api.telegram.org" and not parse_qs(parts.query).get("chat_id"):
        return "Telegram: ALERT_WEBHOOK_URL=https://api.telegram.org/bot<TOKEN>/sendMessage?chat_id=<CHAT_ID>"
    return None


def webhook_payload(url: str, message: str) -> tuple[str, dict]:
    """Webhook-ийн төрлийг URL-аас таньж (POST хаяг, JSON body)-г буцаана."""
    message = message[:MAX_TEXT]
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if host in _DISCORD_HOSTS and parts.path.startswith("/api/webhooks/"):
        # allowed_mentions: камерын нэр дотор @everyone байсан ч хэнийг ч дуудахгүй
        return url, {"content": message, "allowed_mentions": {"parse": []}}
    if host == "api.telegram.org":
        chat_id = parse_qs(parts.query)["chat_id"][0]
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", "")), {"chat_id": chat_id, "text": message}
    # Slack incoming webhook болон бусад (Mattermost, Google Chat, ...)
    return url, {"text": message}


async def send_alert(url: str, message: str) -> bool:
    post_url, body = webhook_payload(url, message)
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.post(post_url, json=body)
    except httpx.HTTPError as exc:  # exception-ий текстэд URL байж болзошгүй — зөвхөн төрөл
        logger.warning("Alert илгээж чадсангүй: %s (%s)", type(exc).__name__, _host(url))
        return False
    if response.status_code >= 400:
        logger.warning("Alert илгээж чадсангүй: HTTP %d (%s)", response.status_code, _host(url))
        return False
    return True


@dataclass
class Monitor:
    """Шалгалт бүрийн асуудлуудаас илгээх мессежийг гаргана.

    Эхний шалгалт зөвхөн суурь төлөв: аль хэдийн унтарсан зүйлийг мэдэгдэхгүй, тэр нь сэргэхэд ч мэдэгдэхгүй
    (redeploy бүрт spam болохгүй). Дараа нь `threshold` удаа дараалан унтарвал нэг удаа, сэргэхэд нэг удаа мэдэгдэнэ.
    """

    threshold: int = FAIL_THRESHOLD
    _started: bool = False
    _fails: dict[str, int] = field(default_factory=dict)
    _down: dict[str, str] = field(default_factory=dict)  # key -> label
    _quiet: set[str] = field(default_factory=set)

    def update(self, problems: list[Problem]) -> list[str]:
        current = {p.key: p for p in problems}
        if not self._started:
            self._started = True
            self._down = {key: p.label for key, p in current.items()}
            self._quiet = set(current)
            return []

        messages = []
        for key, p in current.items():
            if key in self._down:
                continue
            self._fails[key] = self._fails.get(key, 0) + 1
            if self._fails[key] >= self.threshold:
                self._down[key] = p.label
                messages.append(f"[АСУУДАЛ] {p.label}: {p.detail}")
        for key in [k for k in self._fails if k not in current or k in self._down]:
            del self._fails[key]
        for key in [k for k in self._down if k not in current]:
            label = self._down.pop(key)
            if key in self._quiet:
                self._quiet.discard(key)
            else:
                messages.append(f"[СЭРГЭЛЭЭ] {label}")
        return messages


def check_all(now: float | None = None) -> list[Problem]:
    """Одоо асуудалтай байгаа зүйлс. DB холбогдохгүй бол зөвхөн тэрийг (камер/edge-ийг DB-гүй шалгах боломжгүй)."""
    settings = get_settings()
    now = time.time() if now is None else now
    problems: list[Problem] = []
    try:
        with new_session() as db:
            db.execute(text("select 1"))
            cameras = db.execute(
                select(Camera.id, Camera.name, Camera.status).where(Camera.enabled.is_(True)).order_by(Camera.name)
            ).all()
            edge = db.get(AppSetting, EDGE_KEY) if not settings.camera_probe_enabled else None
    except Exception as exc:
        return [Problem("db", "Database", f"холбогдохгүй байна ({type(exc).__name__})")]

    if not ai_heartbeat.alive:
        problems.append(Problem("ai", "AI service", "30 секундээс дээш heartbeat ирээгүй"))
    for camera_id, name, status in cameras:
        if status in _PROBLEM_STATUSES:
            problems.append(Problem(f"camera:{camera_id}", f"Камер '{name}'", status.value))
    if not settings.camera_probe_enabled:
        value = edge.value if edge is not None else None
        at = value.get("at") if isinstance(value, dict) else None
        if not isinstance(at, (int, float)) or not 0 <= now - at <= EDGE_MAX_AGE_SECONDS:
            problems.append(Problem("edge", "Edge (MediaMTX tunnel)", f"{EDGE_MAX_AGE_SECONDS} секундээс дээш мэдэгдэл ирээгүй"))
    return problems


async def alert_loop() -> None:
    settings = get_settings()
    url = settings.alert_webhook_url.strip()
    if not url:
        logger.info("Alert унтраалттай (ALERT_WEBHOOK_URL хоосон)")
        return
    problem = webhook_problem(url)
    if problem:
        logger.warning("Alert унтраалттай: %s", problem)
        return
    interval = settings.alert_check_seconds
    logger.info("Alert: %d сек тутам шалгаж %s руу илгээнэ", interval, _host(url))
    monitor = Monitor()
    pending: list[str] = []
    while True:
        await asyncio.sleep(interval)  # эхлээд хүлээнэ: backend асаад AI heartbeat ирэх хугацаа
        try:
            pending = (pending + monitor.update(await run_in_threadpool(check_all)))[-MAX_PENDING:]
            if pending and await send_alert(url, f"PineQuest ({settings.app_env})\n" + "\n".join(pending)):
                pending = []
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # дараагийн мөчлөгт дахин оролдоно
            logger.error("Alert шалгалтын алдаа: %s", type(exc).__name__)
