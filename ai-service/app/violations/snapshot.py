"""Snapshot picture for a violation: the frame with the person marked in red."""

from __future__ import annotations

import cv2
import numpy as np

from app.detection.types import PersonResult
from app.violations.rules import PERSON_DOWN, RESTRICTED_AREA

RED, WHITE = (40, 40, 230), (255, 255, 255)
LABELS = {"NO_HELMET": "NO HELMET", "NO_WORK_UNIFORM": "NO UNIFORM", RESTRICTED_AREA: "RESTRICTED AREA", PERSON_DOWN: "PERSON DOWN"}


def make_snapshot(frame: np.ndarray, person: PersonResult, vtype: str, quality: int = 85) -> bytes:
    image = frame.copy()
    thickness = max(2, image.shape[1] // 400)
    if vtype == RESTRICTED_AREA and person.area:
        cv2.polylines(image, [np.array(person.area, dtype=np.int32)], True, RED, thickness, cv2.LINE_AA)
    x1, y1, x2, y2 = (int(v) for v in person.box)
    cv2.rectangle(image, (x1, y1), (x2, y2), RED, thickness)
    if vtype == "NO_HELMET" and person.helmet_box:
        hx1, hy1, hx2, hy2 = (int(v) for v in person.helmet_box)
        cv2.rectangle(image, (hx1, hy1), (hx2, hy2), RED, max(1, thickness - 1))
    label = LABELS.get(vtype, vtype)
    scale = max(0.5, image.shape[1] / 1600)
    (tw, th), base = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, scale, 2)
    ty = max(y1, th + base + 4)
    cv2.rectangle(image, (x1, ty - th - base - 4), (x1 + tw + 8, ty), RED, -1)
    cv2.putText(image, label, (x1 + 4, ty - base - 2), cv2.FONT_HERSHEY_SIMPLEX, scale, WHITE, 2, cv2.LINE_AA)
    ok, jpg = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("JPEG encode failed")
    return jpg.tobytes()
