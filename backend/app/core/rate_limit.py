"""Нэвтрэх оролдлогын brute-force хамгаалалт (нэг instance-ийн санах ойд)."""

from __future__ import annotations

import threading
import time


class LoginLimiter:
    def __init__(self, max_failures: int = 5, window_seconds: int = 900) -> None:
        self.max_failures = max_failures
        self.window = window_seconds
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> list[float]:
        recent = [t for t in self._failures.get(key, []) if now - t < self.window]
        self._failures[key] = recent
        return recent

    def is_locked(self, key: str) -> int:
        """Түгжигдсэн бол үлдсэн секунд, үгүй бол 0."""
        now = time.time()
        with self._lock:
            recent = self._recent(key, now)
            if len(recent) >= self.max_failures:
                return int(self.window - (now - recent[0])) + 1
            return 0

    def fail(self, key: str) -> None:
        with self._lock:
            self._recent(key, time.time()).append(time.time())

    def success(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


login_limiter = LoginLimiter()
