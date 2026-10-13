"""WebSocket холболтуудын менежер. Нэвтэрсэн хэрэглэгчдэд event broadcast хийнэ."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger("backend.websocket")


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    @property
    def count(self) -> int:
        return len(self._connections)

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(ws)

    async def broadcast(self, event_type: str, data: Any) -> None:
        message = json.dumps({"type": event_type, "data": data}, default=str)
        async with self._lock:
            targets = list(self._connections)
        dead: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_text(message)
            except Exception as exc:  # WEBSOCKET_ERROR: тасарсан холболтыг цэвэрлэнэ
                logger.error("WEBSOCKET_ERROR: send failed (%s)", type(exc).__name__)
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._connections.discard(ws)


manager = ConnectionManager()
