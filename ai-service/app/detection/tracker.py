"""Gives each person a stable id from frame to frame (needed for "same person, same violation" cooldowns).

Why our own tracker: ultralytics' built-in tracker drops boxes that are not tracked yet — in tests it threw away a
Vest box with score 0.42 on the first frame, so helmets and vests were often missed. Now YOLO only detects, and
this small tracker numbers the PEOPLE; helmet and vest boxes are never dropped.

Matching: each new person box goes to the previous person with the biggest overlap (IoU). No match = new id.
A person not seen for `max_missing` frames is forgotten.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.detection.types import Box


def iou(a: Box, b: Box) -> float:
    x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    if inter == 0:
        return 0.0
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (area_a + area_b - inter)


@dataclass
class _Track:
    box: Box
    missing: int = 0


class PersonTracker:
    def __init__(self, min_iou: float = 0.3, max_missing: int = 15) -> None:
        self._min_iou = min_iou
        self._max_missing = max_missing
        self._tracks: dict[int, _Track] = {}
        self._next_id = 1

    def update(self, boxes: list[Box]) -> list[int]:
        """Returns one id per box, in the same order."""
        pairs = sorted(
            ((iou(box, track.box), i, tid) for i, box in enumerate(boxes) for tid, track in self._tracks.items()),
            reverse=True,
        )
        ids: list[int | None] = [None] * len(boxes)
        used = set()
        for score, i, tid in pairs:  # best overlaps first, each track and box used once
            if score < self._min_iou:
                break
            if ids[i] is None and tid not in used:
                ids[i] = tid
                used.add(tid)
        for i, box in enumerate(boxes):
            if ids[i] is None:
                ids[i] = self._next_id
                self._next_id += 1
            self._tracks[ids[i]] = _Track(box)
        for tid in [t for t in self._tracks if t not in ids]:
            self._tracks[tid].missing += 1
            if self._tracks[tid].missing > self._max_missing:
                del self._tracks[tid]
        return ids
