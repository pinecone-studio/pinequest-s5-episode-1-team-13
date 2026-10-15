"""Decides for each person: is there a helmet? a work uniform? Is it a violation?

The model finds separate boxes: person, helmet / no_helmet (head), work_uniform / no_work_uniform (body).
We give each head box to the person whose HEAD area contains it, and each body box to the person whose
BODY area contains it. Unclear = UNKNOWN, and UNKNOWN is never a violation (avoids false alarms).
"""

from __future__ import annotations

from app.detection.types import Box, Detection, PersonResult

MIN_PERSON_HEIGHT = 40  # pixels; smaller people are too far away to judge PPE
HEAD_ZONE = (-0.10, 0.30)  # from the top of the person box, as a fraction of its height
BODY_ZONE = (0.15, 0.80)
SIDE_MARGIN = 0.10  # allow boxes slightly outside the person box horizontally


def _center(box: Box) -> tuple[float, float]:
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2


def _zone(person: Box, zone: tuple[float, float]) -> Box:
    x1, y1, x2, y2 = person
    w, h = x2 - x1, y2 - y1
    return x1 - w * SIDE_MARGIN, y1 + h * zone[0], x2 + w * SIDE_MARGIN, y1 + h * zone[1]


def _inside(point: tuple[float, float], box: Box) -> bool:
    return box[0] <= point[0] <= box[2] and box[1] <= point[1] <= box[3]


def _assign(items: list[Detection], people: list[PersonResult], zone: tuple[float, float]) -> dict[int, Detection]:
    """person index -> best item. Each item goes to ONE person: the one whose zone centre is nearest."""
    best: dict[int, Detection] = {}
    for item in items:
        point = _center(item.box)
        candidates = []
        for i, person in enumerate(people):
            area = _zone(person.box, zone)
            if _inside(point, area):
                zc = _center(area)
                candidates.append(((point[0] - zc[0]) ** 2 + (point[1] - zc[1]) ** 2, i))
        if not candidates:
            continue
        _, i = min(candidates)
        if i not in best or item.conf > best[i].conf:
            best[i] = item
    return best


def analyse(detections: list[Detection], helmet_required: bool, max_people: int = 50, no_conf: float = 0.0) -> list[PersonResult]:
    """`no_conf`: a no_helmet / no_work_uniform box needs at least this score to count. A missed "NO" only delays an
    alarm by a frame; a wrong "NO" is a false alarm in front of the user — so "NO" must be surer than "YES"."""
    persons = sorted((d for d in detections if d.cls == "person"), key=lambda d: d.conf, reverse=True)[:max_people]
    people = [PersonResult(id=d.track_id, box=d.box, conf=d.conf, helmet_required=helmet_required) for d in persons]
    judgeable = [p for p in people if p.box[3] - p.box[1] >= MIN_PERSON_HEIGHT]

    sure = [d for d in detections if not (d.cls in ("no_helmet", "no_work_uniform") and d.conf < no_conf)]
    heads = [d for d in sure if d.cls in ("helmet", "no_helmet")]
    bodies = [d for d in sure if d.cls in ("work_uniform", "no_work_uniform")]

    for i, head in _assign(heads, judgeable, HEAD_ZONE).items():
        p = judgeable[i]
        p.helmet, p.helmet_box, p.helmet_conf = ("YES" if head.cls == "helmet" else "NO"), head.box, head.conf
    for i, body in _assign(bodies, judgeable, BODY_ZONE).items():
        p = judgeable[i]
        p.uniform, p.uniform_conf = ("YES" if body.cls == "work_uniform" else "NO"), body.conf

    for p in people:
        p.violation = (p.helmet_required and p.helmet == "NO") or p.uniform == "NO"
    return people
