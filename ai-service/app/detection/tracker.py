"""Gives each person a stable id from frame to frame (needed for "same person, same violation" cooldowns).

Why our own tracker: ultralytics' built-in tracker drops boxes that are not tracked yet — in tests it threw away a
Vest box with score 0.42 on the first frame, so helmets and vests were often missed. Now YOLO only detects, and
this small tracker numbers the PEOPLE; helmet and vest boxes are never dropped.

Matching: each person box goes to the track it fits best. A track predicts where its person will be from their
last movement (people walk in straight lines over a fraction of a second), and a box matches when it overlaps that
prediction OR its centre is close to it and it has about the same size. Overlap alone is not enough: at 3 checks a
second a walking person moves about one body width between checks, so the boxes barely overlap and every check
used to create a "new" person (new id, helmet/uniform memory lost, label jumping).
A person not seen for `max_missing` checks is forgotten.
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
    vx: float = 0.0  # centre movement per check (pixels)
    vy: float = 0.0
    missing: int = 0

    def predicted(self) -> Box:
        steps = self.missing + 1
        dx, dy = self.vx * steps, self.vy * steps
        x1, y1, x2, y2 = self.box
        return (x1 + dx, y1 + dy, x2 + dx, y2 + dy)


def _centre(b: Box) -> tuple[float, float]:
    return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2


def match_score(box: Box, track: _Track, min_iou: float, max_dist: float) -> float | None:
    """How well a new box fits a track (higher = better), or None when it is not the same person."""
    pred = track.predicted()
    overlap = iou(box, pred)
    pw, ph = pred[2] - pred[0], pred[3] - pred[1]
    bw, bh = box[2] - box[0], box[3] - box[1]
    if ph <= 0 or pw <= 0 or bh <= 0 or bw <= 0:
        return None
    (cx, cy), (px, py) = _centre(box), _centre(pred)
    dist = ((cx - px) ** 2 + (cy - py) ** 2) ** 0.5 / max(pw, ph)  # in person sizes
    same_size = 0.6 <= bh / ph <= 1 / 0.6 and 0.5 <= bw / pw <= 2.0
    if overlap >= min_iou or (same_size and dist <= max_dist):
        return overlap + (1 - min(dist, 1.0))
    return None


class PersonTracker:
    def __init__(self, min_iou: float = 0.3, max_missing: int = 15, max_dist: float = 0.9) -> None:
        self._min_iou = min_iou
        self._max_dist = max_dist
        self._max_missing = max_missing
        self._tracks: dict[int, _Track] = {}
        self._next_id = 1

    def update(self, boxes: list[Box]) -> list[int]:
        """Returns one id per box, in the same order."""
        pairs = []
        for i, box in enumerate(boxes):
            for tid, track in self._tracks.items():
                score = match_score(box, track, self._min_iou, self._max_dist)
                if score is not None:
                    pairs.append((score, i, tid))
        pairs.sort(reverse=True)
        ids: list[int | None] = [None] * len(boxes)
        used = set()
        for _, i, tid in pairs:  # best fits first, each track and box used once
            if ids[i] is None and tid not in used:
                ids[i] = tid
                used.add(tid)
        for i, box in enumerate(boxes):
            if ids[i] is None:
                ids[i] = self._next_id
                self._next_id += 1
                self._tracks[ids[i]] = _Track(box)
                continue
            track = self._tracks[ids[i]]
            steps = track.missing + 1
            (cx, cy), (ox, oy) = _centre(box), _centre(track.box)
            vx, vy = (cx - ox) / steps, (cy - oy) / steps
            new = track.vx == 0 and track.vy == 0
            track.vx = vx if new else 0.5 * track.vx + 0.5 * vx  # smoothed walking speed
            track.vy = vy if new else 0.5 * track.vy + 0.5 * vy
            track.box, track.missing = box, 0
        for tid in [t for t in self._tracks if t not in ids]:
            self._tracks[tid].missing += 1
            if self._tracks[tid].missing > self._max_missing:
                del self._tracks[tid]
        return ids
