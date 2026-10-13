"""Industrial AI Security — FastAPI backend."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import health
from app.config import get_settings
from app.core.logging import setup_logging
from app.database.database import get_engine

settings = get_settings()
setup_logging(settings.log_level, settings.resolved_log_dir)
logger = logging.getLogger("backend")

_UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}

@asynccontextmanager
async def lifespan(_: FastAPI):
    problems = settings.startup_problems()
    if problems:
        raise RuntimeError("backend/.env дутуу эсвэл буруу байна: " + ", ".join(problems))
    get_engine()
    logger.info("Backend started (env=%s, origins=%s)", settings.app_env, settings.cors_origin_list)
    yield


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

