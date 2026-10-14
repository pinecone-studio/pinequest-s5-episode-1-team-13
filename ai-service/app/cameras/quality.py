"""Is this frame good enough to trust? Too dark or too blurry frames give wrong "NO helmet" results.

Brightness = average grey level (0 black .. 255 white).
Sharpness  = variance of the Laplacian (edges). Sharp photos: hundreds or more; strong blur: under ~20.
Both are measured on a 320 px wide grey copy, so it is cheap and the numbers don't depend on camera resolution.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

WIDTH = 320


@dataclass(frozen=True)
class Quality:
    brightness: float
    sharpness: float

    def problem(self, min_brightness: float, min_sharpness: float) -> str | None:
        """None = OK. Otherwise 'too dark' / 'too blurry'. A limit of 0 turns that check off."""
        if min_brightness and self.brightness < min_brightness:
            return "too dark"
        if min_sharpness and self.sharpness < min_sharpness:
            return "too blurry"
        return None


def measure(frame: np.ndarray) -> Quality:
    height, width = frame.shape[:2]
    small = cv2.resize(frame, (WIDTH, max(1, round(height * WIDTH / width))), interpolation=cv2.INTER_AREA)
    grey = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY) if small.ndim == 3 else small
    return Quality(brightness=float(grey.mean()), sharpness=float(cv2.Laplacian(grey, cv2.CV_64F).var()))
