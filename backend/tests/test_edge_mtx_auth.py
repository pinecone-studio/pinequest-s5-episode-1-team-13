"""infra/edge/mtx_auth.py нь backend-ийн MediaMTX нэвтрэлттэй (app/api/mediamtx.py) яг адил шийдвэр гаргах ёстой."""

import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
import pytest
from fastapi import HTTPException

from app.api.mediamtx import AuthRequest, mediamtx_auth
from app.config import get_settings
from app.core.security import JWT_ALGORITHM, create_access_token, create_stream_token

_spec = importlib.util.spec_from_file_location("mtx_auth", Path(__file__).resolve().parents[2] / "infra" / "edge" / "mtx_auth.py")
mtx_auth = importlib.util.module_from_spec(_spec)
_write_bytecode, sys.dont_write_bytecode = sys.dont_write_bytecode, True  # infra/edge/__pycache__ үүсгэхгүй
_spec.loader.exec_module(mtx_auth)
sys.dont_write_bytecode = _write_bytecode

KEY = "k" * 40
CAM = "cam_b5103ce1-8e9d-44c8-8c4a-a1e55bbb07ad"
OTHER = "cam_602d6271-7083-4ffd-897c-7d8de153c193"


def backend_code(request: dict) -> int:
    try:
        mediamtx_auth(AuthRequest(**request))
        return 200
    except HTTPException as exc:
        return exc.status_code


def _token(payload: dict, secret: str | None = None) -> str:
    return jwt.encode(payload, secret or get_settings().jwt_secret, algorithm=JWT_ALGORITHM)


def _cases() -> list[dict]:
    now = datetime.now(UTC)
    read, publish = create_stream_token(CAM), create_stream_token(CAM, "publish")
    expired = _token({"scope": "stream", "path": CAM, "act": "read", "exp": now - timedelta(seconds=5)})
    foreign = _token({"scope": "stream", "path": CAM, "act": "read", "exp": now + timedelta(minutes=2)}, secret="x" * 40)
    no_act = _token({"scope": "stream", "path": CAM, "exp": now + timedelta(minutes=2)})
    no_exp = _token({"scope": "stream", "path": CAM, "act": "read"})
    return [
        {"user": "ai", "password": KEY, "action": "read", "path": CAM, "protocol": "rtsp"},
        {"user": "ai", "password": KEY, "action": "publish", "path": CAM, "protocol": "rtsp"},
        {"user": "ai", "password": KEY, "action": "api", "path": ""},
        {"user": "ai", "password": KEY, "action": "playback", "path": CAM},
        {"user": "ai", "password": "wrong", "action": "read", "path": CAM},
        {"user": "ai", "password": "wrong", "action": "publish", "path": CAM},
        {"action": "read", "path": CAM, "protocol": "rtsp"},  # RTSP-ийн нууц үггүй анхны оролдлого
        {"action": "publish", "path": CAM},
        {"token": read, "action": "read", "path": CAM, "protocol": "webrtc"},
        {"token": read, "action": "read", "path": OTHER},
        {"token": read, "action": "read", "path": "cam_x"},
        {"token": read, "action": "publish", "path": CAM},
        {"token": publish, "action": "publish", "path": CAM, "protocol": "webrtc"},
        {"token": publish, "action": "read", "path": CAM},
        {"token": publish, "action": "api", "path": CAM},
        {"token": expired, "action": "read", "path": CAM},
        {"token": foreign, "action": "read", "path": CAM},
        {"token": no_act, "action": "read", "path": CAM},
        {"token": no_act, "action": "publish", "path": CAM},
        {"token": no_exp, "action": "read", "path": CAM},
        {"token": create_access_token("user-1"), "action": "read", "path": CAM},  # session токен stream биш
        {"token": "garbage", "action": "read", "path": CAM},
        {"token": read[:-2] + "xx", "action": "read", "path": CAM},
    ]


@pytest.fixture
def internal_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "internal_api_key", KEY)


def test_edge_auth_matches_backend_for_every_case(internal_key):
    secret = get_settings().jwt_secret
    for request in _cases():
        assert mtx_auth.decide(request, KEY, secret) == backend_code(request), request


def test_without_jwt_secret_tokens_go_to_backend_but_ai_is_answered_at_once(internal_key):
    for request in _cases():
        result = mtx_auth.decide(request, KEY, "")
        if request.get("token") and mtx_auth.PATH_RE.match(request["path"]) and request["action"] in ("read", "publish"):
            assert result is mtx_auth.FORWARD, request
        else:
            assert result == backend_code(request), request
