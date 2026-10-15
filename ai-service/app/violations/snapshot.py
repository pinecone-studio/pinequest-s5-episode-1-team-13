"""Snapshot picture for a violation: the frame with the person marked in red.

Privacy: faces of everyone in the picture are pixelated (BLUR_FACES). We have no face detector, so the face area is
guessed from the head box the model found (helmet / bare head) or, without one, from the top of the person box.
The top of a bare head stays visible, so the picture still proves "no helmet".
"""

from __future__ import annotations

from collections.abc import Sequence

import cv2
import numpy as np

from app.detection.types import PersonResult

RED, WHITE = (40, 40, 230), (255, 255, 255)
LABELS = {"NO_HELMET": "NO HELMET", "NO_WORK_UNIFORM": "NO UNIFORM"}


def face_area(person: PersonResult) -> tuple[int, int, int, int]:
    """Where the face most likely is (pixels, x1 y1 x2 y2)."""
    px1, py1, px2, py2 = person.box
    ph = py2 - py1
    if person.helmet_box is not None:
        hx1, hy1, hx2, hy2 = person.helmet_box
        hw, hh = hx2 - hx1, hy2 - hy1
        if person.helmet == "YES":  # helmet box: the face is just under it
            x1, y1, x2, y2 = hx1 - 0.15 * hw, hy2 - 0.15 * hh, hx2 + 0.15 * hw, hy2 + 1.1 * hh
        else:  # bare-head box: keep the top (hair = proof of no helmet), hide the lower part (face)
            x1, y1, x2, y2 = hx1 - 0.05 * hw, hy1 + 0.4 * hh, hx2 + 0.05 * hw, hy2 + 0.1 * hh
    else:  # no head box: a standing person's face sits in the top ~20 % of the body box
        x1, y1, x2, y2 = px1, py1, px2, py1 + 0.2 * ph  # full width: side views put the face near the edge
    x1, y1 = max(x1, px1), max(y1, py1)
    x2, y2 = min(x2, px2), min(y2, py2)
    return int(x1), int(y1), int(x2), int(y2)


def pixelate(image: np.ndarray, area: tuple[int, int, int, int], blocks: int = 8) -> None:
    """Turns the area into big squares, in place (stronger than a soft blur: faces can't be recovered)."""
    h, w = image.shape[:2]
    x1, y1, x2, y2 = max(0, area[0]), max(0, area[1]), min(w, area[2]), min(h, area[3])
    if x2 - x1 < 2 or y2 - y1 < 2:
        return
    part = image[y1:y2, x1:x2]
    small = cv2.resize(part, (max(1, min(blocks, x2 - x1)), max(1, min(blocks, y2 - y1))), interpolation=cv2.INTER_AREA)
    image[y1:y2, x1:x2] = cv2.resize(small, (x2 - x1, y2 - y1), interpolation=cv2.INTER_NEAREST)


def make_snapshot(
    frame: np.ndarray,
    person: PersonResult,
    vtype: str,
    quality: int = 85,
    others: Sequence[PersonResult] = (),
    blur_faces: bool = True,
) -> bytes:
    image = frame.copy()
    if blur_faces:
        for p in (person, *others):
            pixelate(image, face_area(p))
    thickness = max(2, image.shape[1] // 400)
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
