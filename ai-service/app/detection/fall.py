"""Person down (fallen / lying on the floor), from the person box shape only.

A standing or sitting person's box is taller than wide. A person lying on the floor is much wider than tall.
No extra model: it uses the person boxes the PPE model already finds. The violation rules then require it to be
seen for VIOLATION_CONFIRM_SECONDS before anything is saved, so someone bending for a moment is not an alarm.
Known limit: a person lying straight toward the camera can still look tall, and is missed.
"""

from __future__ import annotations

from app.detection.types import Box, PersonResult


def is_down(box: Box, ratio: float) -> bool:
    x1, y1, x2, y2 = box
    width, height = x2 - x1, y2 - y1
    return height > 0 and width > height * ratio


CUT_OFF_MARGIN = 0.02  # a box touching the bottom of the picture is a person cut off by the frame, not lying down


def mark_down(people: list[PersonResult], ratio: float, frame_height: int | None = None) -> None:
    """ratio <= 0 = off."""
    if ratio <= 0:
        return
    for p in people:
        if frame_height and p.box[3] >= frame_height * (1 - CUT_OFF_MARGIN):
            continue
        if is_down(p.box, ratio):
            p.down = True
            p.violation = True
