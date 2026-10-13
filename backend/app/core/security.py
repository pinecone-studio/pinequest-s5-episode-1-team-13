"""Нууц үгийн hash, JWT, камерын нууц үгийн шифрлэлт.

- Хэрэглэгчийн нууц үг: bcrypt (sha256-аар урьдчилан hash хийж, bcrypt-ийн 72 byte хязгаарыг тойрно).
- JWT: HS256, богино хугацаатай. Cookie-д (httpOnly) хадгалагдана.
- Камерын нууц үг: Fernet (AES-128-CBC + HMAC). Түлхүүр нь CAMERA_SECRET_KEY (зөвхөн сервер талд).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

JWT_ALGORITHM = "HS256"
MIN_PASSWORD_LENGTH = 10


def _prehash(password: str) -> bytes:
    return base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prehash(password), bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_prehash(password), password_hash.encode("ascii"))
    except ValueError:
        return False


# Хэрэглэгч байхгүй үед ч ижил хугацаа зарцуулж timing-аар имэйл тандахаас сэргийлнэ
_DUMMY_HASH = hash_password("dummy-password-for-timing")


def verify_password_constant_time(password: str, password_hash: str | None) -> bool:
    return verify_password(password, password_hash or _DUMMY_HASH) and password_hash is not None


def create_access_token(user_id: str) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {"sub": user_id, "iat": now, "exp": now + timedelta(minutes=settings.jwt_expire_minutes)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> str | None:
    """Хүчинтэй бол user_id буцаана, үгүй бол None. Тусгай зориулалтын (scope-той) токеныг session гэж хүлээж авахгүй."""
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=[JWT_ALGORITHM], options={"require": ["exp", "sub"]})
    except jwt.PyJWTError:
        return None
    return None if "scope" in payload else str(payload["sub"])


_WS_SCOPE = "ws"
WS_TOKEN_SECONDS = 60


def create_ws_token(user_id: str) -> str:
    """WebSocket handshake-ийн 60 секундын токен. Frontend нь API-г өөрийн домэйнээр (Vercel proxy) дууддаг тул
    cookie нь backend-ийн домэйнд явахгүй (Safari 3rd-party cookie хориглодог) — WS-д энэ токеныг query-ээр өгнө."""
    s = get_settings()
    now = datetime.now(UTC)
    payload = {"sub": user_id, "scope": _WS_SCOPE, "iat": now, "exp": now + timedelta(seconds=WS_TOKEN_SECONDS)}
    return jwt.encode(payload, s.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_ws_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=[JWT_ALGORITHM], options={"require": ["exp", "sub", "scope"]})
    except jwt.PyJWTError:
        return None
    return str(payload["sub"]) if payload.get("scope") == _WS_SCOPE else None


_STREAM_SCOPE = "stream"


def create_stream_token(path: str, action: str = "read") -> str:
    """Тухайн MediaMTX path-д л (read: үзэх, publish: browser камераас дамжуулах) хүчинтэй, богино хугацаатай токен
    (session токен БИШ: `sub` байхгүй)."""
    s = get_settings()
    now = datetime.now(UTC)
    payload = {
        "scope": _STREAM_SCOPE,
        "path": path,
        "act": action,
        "iat": now,
        "exp": now + timedelta(seconds=s.stream_token_expire_seconds),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=JWT_ALGORITHM)


def verify_stream_token(token: str, path: str, action: str = "read") -> bool:
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=[JWT_ALGORITHM], options={"require": ["exp", "path", "scope"]})
    except jwt.PyJWTError:
        return False
    # "act"-гүй хуучин токен = read (үзэх токеноор хэзээ ч publish хийж болохгүй)
    return payload.get("scope") == _STREAM_SCOPE and payload.get("path") == path and payload.get("act", "read") == action


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def _fernet() -> Fernet:
    return Fernet(get_settings().camera_secret_key.encode("ascii"))


def encrypt_secret(plain: str) -> str:
    return _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str) -> str | None:
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return None
