"""Skip YOLO when the picture has not changed and nobody was there.

Compares the new frame with the frame from the LAST time YOLO ran (not just the previous frame),
so slow movement still adds up. Works on a tiny grey copy, so it costs almost nothing.
"""

from __future__ import annotations

import cv2
import numpy as np

SMALL_WIDTH = 160  # pixels; enough to see a person walking in
PIXEL_DIFF = 25  # grey-level change that counts as "changed" (ignores camera noise)


def small_grey(frame: np.ndarray) -> np.ndarray:
    height, width = frame.shape[:2]
    small = cv2.resize(frame, (SMALL_WIDTH, max(1, round(height * SMALL_WIDTH / width))), interpolation=cv2.INTER_AREA)
    grey = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY) if small.ndim == 3 else small
    return cv2.GaussianBlur(grey, (5, 5), 0)


def changed_fraction(a: np.ndarray, b: np.ndarray) -> float:
    """Share of pixels (0..1) that changed between two small grey frames."""
    if a.shape != b.shape:
        return 1.0  # resolution or rotation changed: treat as motion
    return float(np.count_nonzero(cv2.absdiff(a, b) > PIXEL_DIFF)) / a.size


class MotionGate:
    def __init__(self, threshold: float, max_skip_seconds: float) -> None:
        self._threshold = threshold  # e.g. 0.01 = 1 % of the picture changed
        self._max_skip = max_skip_seconds  # run YOLO at least this often, even with no motion
        self._reference: np.ndarray | None = None
        self._last_run = 0.0
        self.skipped = 0

    def should_run(self, frame: np.ndarray, now: float, people_last_time: bool) -> bool:
        current = small_grey(frame)
        run = (
            people_last_time  # someone is there: keep tracking them, even if they stand still
            or self._reference is None
            or now - self._last_run >= self._max_skip
            or changed_fraction(self._reference, current) >= self._threshold
        )
        if run:
            self._reference, self._last_run = current, now
        else:
            self.skipped += 1
        return run
