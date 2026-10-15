"""Edge-ийн MediaMTX нийтийн HTTPS хаягийг backend-д минут тутам мэдэгдэнэ (PUT /internal/edge).

Горим (env-ээр):
  EDGE_PUBLIC_URL + CLOUDFLARED_METRICS_URL  named tunnel: cloudflared Cloudflare-тэй холбогдсон (/ready = 200) үед л мэдэгдэнэ
  EDGE_PUBLIC_URL                            VPS домэйн: үргэлж мэдэгдэнэ
  CLOUDFLARED_METRICS_URL                    quick tunnel: /quicktunnel-ийн хаяг (асах бүрт солигддог)
Backend 180 сек мэдэгдэл аваагүй бол tunnel унтарсан гэж үзээд MEDIAMTX_PUBLIC_URL руу буцна.
Зөвхөн Python stdlib — python:3.12-alpine image дээр шууд ажиллана.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

INTERVAL_SECONDS = 60
RETRY_SECONDS = 5
TIMEOUT_SECONDS = 10


def log(message: str) -> None:
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} edge-announcer: {message}", flush=True)


def tunnel_url(metrics_url: str) -> str | None:
    """cloudflared-ийн /quicktunnel -> {"hostname": "xxx.trycloudflare.com"} (tunnel бэлэн болтол хоосон)."""
    with urllib.request.urlopen(f"{metrics_url.rstrip('/')}/quicktunnel", timeout=TIMEOUT_SECONDS) as response:
        hostname = str(json.load(response).get("hostname") or "").strip()
    return f"https://{hostname}" if hostname else None


def tunnel_ready(metrics_url: str) -> bool:
    """cloudflared-ийн /ready: Cloudflare-тэй ядаж нэг холболттой бол 200, үгүй бол 503."""
    try:
        with urllib.request.urlopen(f"{metrics_url.rstrip('/')}/ready", timeout=TIMEOUT_SECONDS) as response:
            return response.status == 200
    except urllib.error.HTTPError:
        return False


def edge_url(static_url: str, metrics_url: str) -> str | None:
    """Мэдэгдэх хаяг, tunnel хараахан бэлэн биш бол None."""
    if not metrics_url:
        return static_url or None
    if static_url:
        return static_url if tunnel_ready(metrics_url) else None
    return tunnel_url(metrics_url)


def announce(backend_url: str, internal_key: str, url: str) -> None:
    request = urllib.request.Request(
        f"{backend_url.rstrip('/')}/internal/edge",
        data=json.dumps({"url": url}).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Internal-Key": internal_key},
        method="PUT",
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS):
        pass


def run_once(backend_url: str, internal_key: str, static_url: str, metrics_url: str) -> str | None:
    """Мэдэгдсэн хаягийг буцаана, tunnel хараахан бэлэн биш бол None."""
    url = edge_url(static_url, metrics_url)
    if url:
        announce(backend_url, internal_key, url)
    return url


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # кирилл log ASCII/cp1252 console дээр унахгүй
    backend_url = os.environ.get("BACKEND_URL", "").strip()
    internal_key = os.environ.get("INTERNAL_API_KEY", "").strip()
    static_url = os.environ.get("EDGE_PUBLIC_URL", "").strip().rstrip("/")
    metrics_url = os.environ.get("CLOUDFLARED_METRICS_URL", "").strip()
    if not backend_url.startswith(("http://", "https://")) or internal_key in ("", "CHANGE_ME"):
        log("BACKEND_URL болон INTERNAL_API_KEY-г infra/edge/.env-д бөглөнө үү")
        return 1
    if not static_url and not metrics_url:
        log("EDGE_PUBLIC_URL эсвэл CLOUDFLARED_METRICS_URL хэрэгтэй")
        return 1

    last: str | None = ""
    while True:
        try:
            url = run_once(backend_url, internal_key, static_url, metrics_url)
        except urllib.error.HTTPError as err:
            # 401 = INTERNAL_API_KEY backend-тэй таарахгүй, 400 = хаяг https://host биш
            log(f"backend татгалзлаа: HTTP {err.code}")
            last = None
            time.sleep(RETRY_SECONDS)
            continue
        except (OSError, ValueError) as err:
            log(f"алдаа: {err.__class__.__name__}: {err}")
            last = None
            time.sleep(RETRY_SECONDS)
            continue
        if url != last:
            log(f"мэдэгдлээ: {url}" if url else "tunnel Cloudflare-тэй холбогдоогүй байна, хүлээж байна")
            last = url
        time.sleep(INTERVAL_SECONDS if url else RETRY_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
