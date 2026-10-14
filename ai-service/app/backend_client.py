"""Talks to the backend's internal API (/internal/...).

Flow: AI SERVICE -> FASTAPI (/internal) -> WEBSOCKET -> NEXT.JS dashboard
Every request sends the X-Internal-Key header (same key as backend/.env).
Errors are logged, never raised: the AI loop must keep running even if the backend restarts.
"""

from __future__ import annotations

import logging
import threading

import httpx

logger = logging.getLogger("ai.backend")

TIMEOUT = httpx.Timeout(5.0)


class BackendClient:
    def __init__(self, base_url: str, internal_key: str, transport: httpx.BaseTransport | None = None) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"X-Internal-Key": internal_key},
            timeout=TIMEOUT,
            transport=transport,
        )
        self._lock = threading.Lock()  # one shared client, used from many camera threads

    def _send(self, method: str, path: str, json: dict | None = None) -> bool:
        try:
            with self._lock:
                response = self._client.request(method, path, json=json)
        except httpx.HTTPError as exc:
            logger.warning("Backend unreachable: %s %s (%s)", method, path, type(exc).__name__)
            return False
        if response.status_code >= 400:
            logger.warning("Backend refused: %s %s -> %s", method, path, response.status_code)
            return False
        return True

    def heartbeat(self) -> bool:
        """Dashboard shows AI status ONLINE while heartbeats keep coming."""
        return self._send("POST", "/internal/heartbeat")

    def camera_status(self, camera_id: str) -> bool:
        """Call after writing the new status to the DB. Backend broadcasts CAMERA_UPDATED."""
        return self._send("POST", f"/internal/cameras/{camera_id}/status")

    def detections(self, camera_id: str, people: list[dict]) -> bool:
        """Live boxes for the dashboard overlay. Not saved, only forwarded over WebSocket (max 50 people)."""
        return self._send("PUT", f"/internal/cameras/{camera_id}/detections", json={"people": people[:50]})

    def violation_created(self, violation_id: str) -> bool:
        """Call after the violation row is in the DB. Backend broadcasts VIOLATION_CREATED (with a signed snapshot URL)."""
        return self._send("POST", f"/internal/violations/{violation_id}/created")

    def close(self) -> None:
        self._client.close()
