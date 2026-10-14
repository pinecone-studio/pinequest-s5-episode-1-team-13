"""When does a "NO" become a saved violation?

- It must be seen (almost) continuously for VIOLATION_CONFIRM_SECONDS. One wrong frame is not enough.
- After saving, the same person + same type waits VIOLATION_COOLDOWN_SECONDS. No spam of 100 rows per minute.
Person = tracker id. People without an id share one "unknown" slot per camera, which is safer than spamming.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.detection.types import PersonResult

NO_HELMET, NO_WORK_UNIFORM = "NO_HELMET", "NO_WORK_UNIFORM"  # = violation_type enum in the DB
MAX_GAP = 1.5  # seconds a "NO" may disappear (blur, someone walks in front) without restarting the timer


@dataclass
class _Streak:
    first_seen: float
    last_seen: float
    reported_at: float | None = None


def violation_types(person: PersonResult) -> list[str]:
    types = []
    if person.helmet_required and person.helmet == "NO":
        types.append(NO_HELMET)
    if person.uniform == "NO":
        types.append(NO_WORK_UNIFORM)
    return types


class ViolationRules:
    def __init__(self, confirm_seconds: float, cooldown_seconds: float) -> None:
        self._confirm = confirm_seconds
        self._cooldown = cooldown_seconds
        self._streaks: dict[tuple, _Streak] = {}

    def update(self, people: list[PersonResult], now: float) -> list[tuple[str, PersonResult]]:
        """Feed every AI result. Returns the violations to save NOW."""
        to_report = []
        seen = set()
        for person in people:
            for vtype in violation_types(person):
                key = (person.id, vtype)
                if key in seen:
                    continue
                seen.add(key)
                streak = self._streaks.get(key)
                if streak is None or now - streak.last_seen > MAX_GAP:
                    reported_at = streak.reported_at if streak else None
                    streak = self._streaks[key] = _Streak(first_seen=now, last_seen=now, reported_at=reported_at)
                streak.last_seen = now
                cooled = streak.reported_at is None or now - streak.reported_at >= self._cooldown
                if now - streak.first_seen >= self._confirm and cooled:
                    streak.reported_at = now
                    to_report.append((vtype, person))
        self._forget_old(now)
        return to_report

    def _forget_old(self, now: float) -> None:
        keep_for = self._cooldown + MAX_GAP
        for key in [k for k, s in self._streaks.items() if now - s.last_seen > keep_for]:
            del self._streaks[key]
