"""Industrial AI Security — FastAPI backend."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import auth, cameras, dashboard, health, internal, mediamtx, training, users, violations, zones
from app.api.deps import COOKIE_NAME, user_from_token
from app.config import get_settings
from app.core.logging import setup_logging
from app.database.database import get_engine, new_session
from app.services.retention import retention_loop
from app.websocket.manager import manager

settings = get_settings()
setup_logging(settings.log_level, settings.resolved_log_dir)
logger = logging.getLogger("backend")

_UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}

# localhost дээрх cookie бүх порт дээр хуваалцагддаг тул browser бусад төслүүдийн (Supabase, Clerk…) cookie-г хамт илгээж,
# Cookie header 8 KB-аас хэтэрдэг. websockets-ийн 8192 байтын мөрийн хязгаар хэтэрвэл WebSocket handshake hang болно.
try:
    import websockets.http11 as _ws_http11

    _ws_http11.MAX_LINE_LENGTH = max(_ws_http11.MAX_LINE_LENGTH, 65_536)
except Exception:  # websockets-sansio ашиглаагүй бол хамаагүй
    logger.debug("websockets MAX_LINE_LENGTH тохируулсангүй")


@asynccontextmanager
async def lifespan(_: FastAPI):
    problems = settings.startup_problems()
    if problems:
        raise RuntimeError("backend/.env дутуу эсвэл буруу байна: " + ", ".join(problems))
    get_engine()
    logger.info("Backend started (env=%s, origins=%s)", settings.app_env, settings.cors_origin_list)
    purge_task = asyncio.create_task(retention_loop())
    try:
        yield
    finally:
        purge_task.cancel()


app = FastAPI(
    title="Industrial AI Security API",
    lifespan=lifespan,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None,
    openapi_url=None if settings.is_production else "/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    # CSRF: cookie-ээр нэвтэрсэн browser-ийн өөрчлөх хүсэлт зөвхөн итгэмжлэгдсэн origin-оос
    if request.method in _UNSAFE and not request.url.path.startswith("/internal"):
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") not in settings.cors_origin_list:
            return JSONResponse({"detail": "Origin not allowed"}, status_code=403)
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(zones.router)
app.include_router(cameras.router)
app.include_router(violations.router)
app.include_router(dashboard.router)
app.include_router(internal.router)
app.include_router(mediamtx.router)
app.include_router(training.router)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """Нэвтэрсэн хэрэглэгчид real-time event: VIOLATION_CREATED / VIOLATION_UPDATED / CAMERA_UPDATED."""
    origin = ws.headers.get("origin")
    if origin and origin.rstrip("/") not in settings.cors_origin_list:  # cross-site WebSocket hijacking
        logger.warning("WebSocket татгалзлаа: Origin зөвшөөрөгдөөгүй | origin=%s зөвшөөрөгдсөн=%s", origin, settings.cors_origin_list)
        await ws.close(code=1008)
        return

    def lookup():
        with new_session() as db:
            token = ws.query_params.get("token")  # Vercel proxy-оор нэвтэрсэн browser (cookie энд ирэхгүй)
            return user_from_token(db, token, ws=True) if token else user_from_token(db, ws.cookies.get(COOKIE_NAME))

    user = await run_in_threadpool(lookup)  # event loop дээр DB хүлээхгүй (pool дүүрэхэд бүх сервер гацна)
    if not user:
        logger.warning(
            "WebSocket татгалзлаа: нэвтрээгүй эсвэл session дууссан | cookie_байгаа=%s origin=%s", COOKIE_NAME in ws.cookies, origin
        )
        await ws.close(code=1008)
        return

    await manager.connect(ws)
    logger.info("WebSocket холбогдлоо | role=%s clients=%d", user.role.value, manager.count)
    try:
        await ws.send_json({"type": "CONNECTED", "data": {"role": user.role.value}})
        while True:
            message = await ws.receive_text()
            if message == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error("WEBSOCKET_ERROR: %s", type(exc).__name__)
    finally:
        await manager.disconnect(ws)
        logger.info("WebSocket салав | clients=%d", manager.count)
