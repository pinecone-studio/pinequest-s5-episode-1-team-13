"""Stops boxes flickering YES/NO/YES between frames: each person's helmet and uniform state is the majority of
their last `window` results (window 5 at 3 AI runs per second = the last ~1.7 s).

Only people with a tracker id are smoothed. A tie keeps the state shown before, so the label only changes when the
new state really wins. People not seen for a while are forgotten.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field

from app.detection.types import PersonResult

FORGET_AFTER = 30  # AI runs without seeing that person


@dataclass
class _History:
    helmet: deque = field(default_factory=deque)
    uniform: deque = field(default_factory=deque)
    shown_helmet: str = "UNKNOWN"
    shown_uniform: str = "UNKNOWN"
    unseen: int = 0


def majority(values: deque, shown: str) -> str:
    counts = Counter(values).most_common()
    best, best_n = counts[0]
    if len(counts) > 1 and counts[1][1] == best_n:  # tie: keep what the user already sees
        return shown if Counter(values)[shown] == best_n else best
    return best


class PersonSmoother:
    def __init__(self, window: int = 5) -> None:
        self._window = max(1, window)
        self._people: dict[int, _History] = {}

    def apply(self, people: list[PersonResult]) -> list[PersonResult]:
        seen = set()
        for p in people:
            if p.id is None or self._window == 1:
                continue
            seen.add(p.id)
            h = self._people.setdefault(p.id, _History(deque(maxlen=self._window), deque(maxlen=self._window)))
            h.unseen = 0
            h.helmet.append(p.helmet)
            h.uniform.append(p.uniform)
            h.shown_helmet = p.helmet = majority(h.helmet, h.shown_helmet)
            h.shown_uniform = p.uniform = majority(h.uniform, h.shown_uniform)
            p.violation = (p.helmet_required and p.helmet == "NO") or p.uniform == "NO"
        for pid in [k for k in self._people if k not in seen]:
            self._people[pid].unseen += 1
            if self._people[pid].unseen > FORGET_AFTER:
                del self._people[pid]
        return people
