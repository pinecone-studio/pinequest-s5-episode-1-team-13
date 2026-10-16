"""Talks to the backend's internal API (/internal/...).

Flow: AI SERVICE -> FASTAPI (/internal) -> WEBSOCKET -> NEXT.JS dashboard
Every request sends the X-Internal-Key header (same key as backend/.env).
Errors are logged, never raised: the AI loop must keep running even if the backend restarts.
Camera status and live boxes come from the camera threads, so they are sent from a background thread: a slow backend
must never slow down the camera loop, or a violation is never seen long enough in a row to be confirmed.
Status changes are all sent in order; boxes still waiting are replaced by newer ones.
"""

from __future__ import annotations

import itertools
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
        self._pending: dict[str, tuple[str, str, dict | None]] = {}  # key -> (method, path, json), sent oldest first
        self._wake = threading.Condition()
        self._closed = False
        self._sender: threading.Thread | None = None
        self._status_seq = itertools.count()  # next() is atomic: safe from many camera threads

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
        """Call after writing the new status to the DB. Backend broadcasts CAMERA_UPDATED. Sent in the background."""
        # a unique key per change: every status change is sent (in order), none is replaced
        return self._queue(f"status:{camera_id}:{next(self._status_seq)}", "POST", f"/internal/cameras/{camera_id}/status")

    def detections(self, camera_id: str, people: list[dict]) -> bool:
        """Live boxes for the dashboard overlay. Not saved, only forwarded over WebSocket (max 50 people).
        Sent in the background; boxes still waiting for this camera are replaced by the newer ones."""
        return self._queue(f"boxes:{camera_id}", "PUT", f"/internal/cameras/{camera_id}/detections", {"people": people[:50]})

    def _queue(self, key: str, method: str, path: str, json: dict | None = None) -> bool:
        """Returns at once: True = will be sent, False = client already closed."""
        with self._wake:
            if self._closed:
                return False
            self._pending.pop(key, None)  # a replaced request goes to the back, behind the ones queued before it
            self._pending[key] = (method, path, json)
            if self._sender is None:
                self._sender = threading.Thread(target=self._send_queued, name="backend-sender", daemon=True)
                self._sender.start()
            self._wake.notify()
        return True

    def _send_queued(self) -> None:
        while True:
            with self._wake:
                while not self._pending and not self._closed:
                    self._wake.wait()
                if not self._pending:  # closed and nothing left
                    return
                method, path, json = self._pending.pop(next(iter(self._pending)))
            self._send(method, path, json)

    def violation_created(self, violation_id: str) -> bool:
        """Call after the violation row is in the DB. Backend broadcasts VIOLATION_CREATED (with a signed snapshot URL)."""
        return self._send("POST", f"/internal/violations/{violation_id}/created")

    def close(self) -> None:
        """Sends what is still waiting (the last status and boxes clear the dashboard), then closes."""
        with self._wake:
            self._closed = True
            self._wake.notify()
        if self._sender is not None:
            self._sender.join(timeout=10)
        self._client.close()
