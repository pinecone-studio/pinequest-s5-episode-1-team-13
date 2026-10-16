"""Edge дээрх MediaMTX-ийн нэвтрэлт (authHTTPAddress). Backend-ийн дүрэмтэй яг адил (backend/app/api/mediamtx.py).

MediaMTX нэвтрэлтийг НЭГ НЭГЭЭР асуудаг: backend (Railway) удаан хариулбал (2-10 сек) dashboard-ын хүсэлтүүд дараалалд
хуримтлагдаж, ai-service-ийн RTSP нээлт (8 сек) timeout болдог байсан ("AI · дохио алга"). Тиймээс энд шууд шийднэ:
  user=ai + INTERNAL_API_KEY       -> зөвшөөрнө (publish, read, api)
  нууц үг, токен огт байхгүй       -> 401 шууд (RTSP client эхлээд нууц үггүй оролдоод дараа нь нууц үгтэйгээ дахин асууна)
  stream токен (dashboard, browser) -> JWT_SECRET өгсөн бол энд шалгана (backend-ийн verify_stream_token-той адил),
                                      өгөөгүй бол backend руу дамжуулна (хуучин шиг, удаан)
Зөвхөн Python stdlib — python:3.12-alpine image дээр шууд ажиллана.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PATH_RE = re.compile(r"^cam_[0-9a-fA-F-]{36}$")
STREAM_SCOPE = "stream"
FORWARD_TIMEOUT_SECONDS = 8  # MediaMTX өөрөө 10 сек хүлээнэ: түүнээс өмнө хариулна
ALLOW, DENY = 200, 401
FORWARD = None  # backend шийднэ


def log(message: str) -> None:
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} mtx-auth: {message}", flush=True)


def _b64url(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


def verify_stream_token(token: str, path: str, action: str, secret: str, now: float | None = None) -> bool:
    """backend/app/core/security.py verify_stream_token-той адил: HS256, exp/path/scope заавал, path ба act таарна."""
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
        if json.loads(_b64url(header_b64)).get("alg") != "HS256":
            return False
        expected = hmac.new(secret.encode("utf-8"), f"{header_b64}.{payload_b64}".encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64url(signature_b64)):
            return False
        payload = json.loads(_b64url(payload_b64))
    except (ValueError, TypeError, AttributeError):
        return False
    if not isinstance(payload, dict) or not all(k in payload for k in ("exp", "path", "scope")):
        return False
    now = time.time() if now is None else now
    try:
        if float(payload["exp"]) <= now or ("nbf" in payload and float(payload["nbf"]) > now):
            return False
    except (TypeError, ValueError):
        return False
    # "act"-гүй хуучин токен = read (үзэх токеноор хэзээ ч publish хийж болохгүй)
    return payload.get("scope") == STREAM_SCOPE and payload.get("path") == path and payload.get("act", "read") == action


def decide(request: dict, internal_key: str, jwt_secret: str) -> int | None:
    """200 / 401, эсвэл FORWARD (токеныг backend шалгана: JWT_SECRET өгөөгүй үед)."""
    password, token = str(request.get("password") or ""), str(request.get("token") or "")
    action, path = str(request.get("action") or ""), str(request.get("path") or "")
    if not request.get("user") and not password and not token:
        return DENY
    internal = bool(internal_key) and hmac.compare_digest(password.encode("utf-8"), internal_key.encode("utf-8"))
    path_ok = bool(PATH_RE.match(path))

    if action in ("publish", "api"):
        if internal:
            return ALLOW
        if action == "publish" and path_ok and token:
            if not jwt_secret:
                return FORWARD
            return ALLOW if verify_stream_token(token, path, "publish", jwt_secret) else DENY
        return DENY

    if action == "read":
        if internal:
            return ALLOW
        if path_ok and token:
            if not jwt_secret:
                return FORWARD
            return ALLOW if verify_stream_token(token, path, "read", jwt_secret) else DENY
        return DENY

    return DENY  # playback, metrics, pprof


def forward(backend_url: str, body: bytes) -> int:
    request = urllib.request.Request(
        f"{backend_url.rstrip('/')}/internal/mediamtx/auth", data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=FORWARD_TIMEOUT_SECONDS) as response:
            return ALLOW if response.status == 200 else DENY
    except urllib.error.HTTPError:
        return DENY
    except (OSError, ValueError) as err:
        log(f"backend хариулсангүй ({err.__class__.__name__}) — татгалзлаа")
        return DENY


def make_handler(internal_key: str, jwt_secret: str, backend_url: str):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 — http.server-ийн нэр
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            try:
                request = json.loads(body or b"{}")
            except ValueError:
                request = {}
            result = decide(request if isinstance(request, dict) else {}, internal_key, jwt_secret)
            code = forward(backend_url, body) if result is FORWARD else result
            payload = b"{}" if code == ALLOW else b'{"detail":"denied"}'
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args) -> None:  # noqa: A002 — хүсэлт бүрийг log-д бичихгүй
            pass

    return Handler


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # кирилл log ASCII/cp1252 console дээр унахгүй
    internal_key = os.environ.get("INTERNAL_API_KEY", "").strip()
    jwt_secret = os.environ.get("JWT_SECRET", "").strip()
    backend_url = os.environ.get("BACKEND_URL", "").strip()
    host = os.environ.get("MTX_AUTH_HOST", "127.0.0.1").strip()
    port = int(os.environ.get("MTX_AUTH_PORT", "8002"))
    if internal_key in ("", "CHANGE_ME"):
        log("INTERNAL_API_KEY-г infra/edge/.env-д бөглөнө үү")
        return 1
    if jwt_secret == "CHANGE_ME":
        jwt_secret = ""
    if not jwt_secret and not backend_url.startswith(("http://", "https://")):
        log("JWT_SECRET эсвэл BACKEND_URL хэрэгтэй (dashboard-ын токеныг шалгахад)")
        return 1
    mode = "токеныг энд шалгана (JWT_SECRET)" if jwt_secret else f"токеныг backend шалгана ({backend_url})"
    log(f"{host}:{port} дээр асав — ai-service шууд, {mode}")
    ThreadingHTTPServer((host, port), make_handler(internal_key, jwt_secret, backend_url)).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
