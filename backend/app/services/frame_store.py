"""AI service-ийн heartbeat (dashboard-ийн "AI ТӨЛӨВ"). Видео MediaMTX-ээр дамждаг тул frame хадгалахгүй."""

from __future__ import annotations

import time


class AIHeartbeat:
    def __init__(self, timeout: float = 30.0) -> None:
        self._last = 0.0
        self._timeout = timeout

    def beat(self) -> None:
        self._last = time.time()

    @property
    def alive(self) -> bool:
        return time.time() - self._last <= self._timeout


ai_heartbeat = AIHeartbeat()
