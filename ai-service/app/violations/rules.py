"""When does a "NO" become a saved violation?

- It must be seen (almost) continuously for VIOLATION_CONFIRM_SECONDS. One wrong frame is not enough.
- One violation per person per VISIT. While the same person keeps the same problem (short gaps under VISIT_GAP are
  the same visit: someone walks in front, the AI misses a frame), it is saved once, and again only every
  VIOLATION_REPEAT_SECONDS for very long violations (0 = never during one visit).
- A new visit (the problem was gone for longer than VISIT_GAP) is saved again, but not sooner than
  VIOLATION_COOLDOWN_SECONDS after the last one.
- Tracker ids can change when a person is lost for a moment. A "new" person with the same problem in almost the same
  place (boxes overlap) shortly after a saved violation is treated as the same person, so one person is not saved twice.
People without an id share one "unknown" slot per camera, which is safer than spamming.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.detection.tracker import iou
from app.detection.types import Box, PersonResult

NO_HELMET, NO_WORK_UNIFORM = "NO_HELMET", "NO_WORK_UNIFORM"  # = violation_type enum in the DB
# The DB has no own type for this yet; OTHER_SAFETY_VIOLATION already exists in the DB, backend and web
RESTRICTED_AREA = "OTHER_SAFETY_VIOLATION"
MAX_GAP = 1.5  # seconds a "NO" may disappear while it is still being confirmed, without restarting the timer
VISIT_GAP = 10.0  # after it was saved: gone for longer than this = the person left, the next time is a new visit
SAME_PLACE_IOU = 0.3  # a new tracker id this close to a just-saved violation of the same type = the same person


def violation_types(person: PersonResult) -> list[str]:
    types = []
    if person.helmet_required and person.helmet == "NO":
        types.append(NO_HELMET)
    if person.uniform == "NO":
        types.append(NO_WORK_UNIFORM)
    if person.restricted:
        types.append(RESTRICTED_AREA)
    return types


@dataclass
class _Streak:
    first_seen: float
    last_seen: float
    reported_at: float | None = None  # last save in THIS visit
    last_report: float | None = None  # last save in any visit (for the cooldown)
    report: _Report | None = None  # where this person was last seen, for catching tracker id changes


@dataclass
class _Report:
    vtype: str
    box: Box  # latest box of the person, kept up to date during the visit
    at: float  # when it was saved
    seen: float  # when the person was last seen with this problem


class ViolationRules:
    def __init__(self, confirm_seconds: float, cooldown_seconds: float, repeat_seconds: float = 0) -> None:
        self._confirm = confirm_seconds
        self._cooldown = cooldown_seconds
        self._repeat = repeat_seconds
        self._streaks: dict[tuple, _Streak] = {}
        self._recent: list[_Report] = []

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
                if self._should_report(key, vtype, person, now):
                    to_report.append((vtype, person))
        self._forget_old(now)
        return to_report

    def _should_report(self, key: tuple, vtype: str, person: PersonResult, now: float) -> bool:
        streak = self._streaks.get(key)
        if streak is not None:
            gap = now - streak.last_seen
            visit_over = gap > (VISIT_GAP if streak.reported_at is not None else MAX_GAP)
            if visit_over:  # new visit (or a confirm timer that was interrupted): start again, remember the cooldown
                streak = self._streaks[key] = _Streak(first_seen=now, last_seen=now, last_report=streak.last_report)
        else:
            streak = self._streaks[key] = _Streak(first_seen=now, last_seen=now)
            twin = self._same_place(vtype, person.box, now)
            if twin is not None:  # tracker gave the same person a new id: continue that person's visit
                streak.first_seen = streak.reported_at = streak.last_report = twin.at
                streak.report = twin
        streak.last_seen = now
        if streak.report is not None:
            streak.report.box, streak.report.seen = person.box, now

        if now - streak.first_seen < self._confirm:
            return False
        if streak.reported_at is not None:  # already saved in this visit
            if not self._repeat or now - streak.reported_at < self._repeat:
                return False
        elif streak.last_report is not None and now - streak.last_report < self._cooldown:
            return False
        streak.reported_at = streak.last_report = now
        streak.report = _Report(vtype, person.box, at=now, seen=now)
        self._recent.append(streak.report)
        return True

    def _same_place(self, vtype: str, box: Box, now: float) -> _Report | None:
        for report in reversed(self._recent):
            if report.vtype == vtype and now - report.seen <= VISIT_GAP and iou(report.box, box) >= SAME_PLACE_IOU:
                return report
        return None

    def _forget_old(self, now: float) -> None:
        keep_for = max(self._cooldown, VISIT_GAP) + VISIT_GAP
        for key in [k for k, s in self._streaks.items() if now - s.last_seen > keep_for]:
            del self._streaks[key]
        self._recent = [r for r in self._recent if now - r.seen <= VISIT_GAP]
