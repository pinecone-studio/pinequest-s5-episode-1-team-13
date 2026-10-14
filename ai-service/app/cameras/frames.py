"""Frame helpers."""

from __future__ import annotations

import cv2
import numpy as np

_ROTATE = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}


def rotate(frame: np.ndarray, degrees: int) -> np.ndarray:
    """Rotate clockwise, like the dashboard does with CSS. The AI analyses the rotated (upright) picture,
    so boxes it sends match what the user sees. Mirror is NOT applied: the dashboard flips boxes itself."""
    code = _ROTATE.get(degrees % 360)
    return frame if code is None else cv2.rotate(frame, code)
