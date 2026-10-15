"""Edge-ийн MediaMTX нийтийн HTTPS хаягийг backend-д минут тутам мэдэгдэнэ (PUT /internal/edge).

Хаяг: EDGE_PUBLIC_URL (VPS домэйн) эсвэл cloudflared quick tunnel-ийн хаяг (асах бүрт солигддог).
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
    url = static_url or tunnel_url(metrics_url)
    if url:
        announce(backend_url, internal_key, url)
    return url


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # кирилл log ASCII/cp1252 console дээр унахгүй
    backend_url = os.environ.get("BACKEND_URL", "").strip()
    internal_key = os.environ.get("INTERNAL_API_KEY", "").strip()
    static_url = os.environ.get("EDGE_PUBLIC_URL", "").strip().rstrip("/")
    metrics_url = os.environ.get("CLOUDFLARED_METRICS_URL", "http://cloudflared:2000").strip()
    if not backend_url.startswith(("http://", "https://")) or internal_key in ("", "CHANGE_ME"):
        log("BACKEND_URL болон INTERNAL_API_KEY-г infra/edge/.env-д бөглөнө үү")
        return 1

    last = None
    while True:
        try:
            url = run_once(backend_url, internal_key, static_url, metrics_url)
        except urllib.error.HTTPError as err:
            # 401 = INTERNAL_API_KEY backend-тэй таарахгүй, 400 = хаяг https://host биш
            log(f"backend татгалзлаа: HTTP {err.code}")
            url = None
        except (OSError, ValueError) as err:
            log(f"алдаа: {err.__class__.__name__}: {err}")
            url = None
        if url and url != last:
            log(f"мэдэгдлээ: {url}")
            last = url
        time.sleep(INTERVAL_SECONDS if url else RETRY_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
