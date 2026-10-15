"""One log line per camera every STATS_SECONDS, so you can see where it is slow.

    Gate | video 14.8 fps | AI 3.0/s, 41 ms avg, 63 ms max | people max 2 | violation frames 4 | status STREAMING
"""

from __future__ import annotations

import logging

logger = logging.getLogger("ai.stats")


class CameraStats:
    def __init__(self, name: str, every_seconds: float, start: float) -> None:
        self._name = name
        self._every = every_seconds
        self._reset(start)

    def _reset(self, now: float) -> None:
        self._since = now
        self.frames = 0
        self.ai_runs = 0
        self.ai_ms_total = 0.0
        self.ai_ms_max = 0.0
        self.people_max = 0
        self.violation_frames = 0

    def frame(self) -> None:
        self.frames += 1

    def ai_step(self, ms: float, people: int, violations: int) -> None:
        self.ai_runs += 1
        self.ai_ms_total += ms
        self.ai_ms_max = max(self.ai_ms_max, ms)
        self.people_max = max(self.people_max, people)
        self.violation_frames += violations > 0

    def line(self, seconds: float, status: str) -> str:
        avg = self.ai_ms_total / self.ai_runs if self.ai_runs else 0.0
        return (
            f"{self._name} | video {self.frames / seconds:.1f} fps | "
            f"AI {self.ai_runs / seconds:.1f}/s, {avg:.0f} ms avg, {self.ai_ms_max:.0f} ms max | "
            f"people max {self.people_max} | violation frames {self.violation_frames} | status {status}"
        )

    def maybe_log(self, now: float, status: str) -> str | None:
        """Logs and starts a new period when the time is up. Returns the line (for tests)."""
        if not self._every or now - self._since < self._every:
            return None
        text = self.line(max(now - self._since, 1e-6), status)
        logger.info(text)
        self._reset(now)
        return text
