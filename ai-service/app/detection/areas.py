"""Restricted areas: a person whose feet are inside a forbidden polygon is a violation.

No new model is needed: the model already finds people, this is only geometry.
Feet = bottom middle of the person box, so someone standing *next to* the area (head inside it in the picture)
does not count.

Areas live in the DB (app_settings key "restricted_areas"), per camera, as polygons in 0..1 coordinates of the
picture the AI sees (after ROTATION, before MIRROR):
    {"<camera_id>": [[[0.6, 0.5], [0.95, 0.5], [0.95, 0.95], [0.6, 0.95]]]}
Set them with:  python -m scripts.set_area "Camera name" "0.6,0.5 0.95,0.5 0.95,0.95 0.6,0.95"
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Sequence

from app.db import Database
from app.detection.types import Box, PersonResult

logger = logging.getLogger("ai.areas")

SETTING_KEY = "restricted_areas"
Point = tuple[float, float]
Polygon = tuple[Point, ...]


def parse_points(text: str) -> Polygon:
    """"0.6,0.5 0.95,0.5 0.95,0.95" -> ((0.6, 0.5), ...). At least 3 points, each 0..1."""
    points = []
    for part in text.replace(";", " ").split():
        try:
            x, y = (float(v) for v in part.split(","))
        except ValueError:
            raise ValueError(f"Bad point {part!r}: use x,y like 0.5,0.25") from None
        if not (0 <= x <= 1 and 0 <= y <= 1):
            raise ValueError(f"Point {part!r} is outside 0..1 (use parts of the picture width/height)")
        points.append((x, y))
    if len(points) < 3:
        raise ValueError("An area needs at least 3 points")
    return tuple(points)


def clean_polygons(value: object) -> list[Polygon]:
    """DB value for one camera -> valid polygons only (bad ones are skipped, never crash the camera)."""
    if not isinstance(value, list):
        return []
    if value and all(isinstance(p, (list, tuple)) and len(p) == 2 and all(isinstance(v, (int, float)) for v in p) for p in value):
        value = [value]  # one polygon given directly
    polygons = []
    for poly in value:
        try:
            points = tuple((float(x), float(y)) for x, y in poly)
        except (TypeError, ValueError):
            continue
        if len(points) >= 3 and all(0 <= x <= 1 and 0 <= y <= 1 for x, y in points):
            polygons.append(points)
    return polygons


def to_pixels(polygon: Polygon, width: int, height: int) -> tuple[tuple[int, int], ...]:
    return tuple((round(x * width), round(y * height)) for x, y in polygon)


def feet(box: Box) -> Point:
    x1, _, x2, y2 = box
    return (x1 + x2) / 2, y2


def inside(point: Point, polygon: Sequence[Sequence[float]]) -> bool:
    """Ray casting: count how many polygon edges a line going right from the point crosses."""
    x, y = point
    result = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            result = not result
        j = i
    return result


def mark(people: list[PersonResult], polygons: Sequence[Polygon], width: int, height: int) -> list[PersonResult]:
    """Marks people standing in a restricted area: restricted=True, violation=True (red box on the dashboard)."""
    if not polygons:
        return people
    pixel_polys = [to_pixels(p, width, height) for p in polygons]
    for person in people:
        spot = feet(person.box)
        for poly in pixel_polys:
            if inside(spot, poly):
                person.restricted, person.area, person.violation = True, poly, True
                break
    return people


class RestrictedAreaConfig:
    """Shared by all cameras. Reads the areas from the DB at most every `refresh` seconds."""

    def __init__(self, db: Database, refresh: float = 10.0) -> None:
        self._db, self._refresh = db, refresh
        self._lock = threading.Lock()
        self._areas: dict[str, list[Polygon]] = {}
        self._loaded_at = float("-inf")

    def get(self, camera_id: str) -> list[Polygon]:
        with self._lock:
            if time.monotonic() - self._loaded_at >= self._refresh:
                self._loaded_at = time.monotonic()
                try:
                    rows = self._db.fetch("SELECT value FROM app_settings WHERE key = %s", (SETTING_KEY,))
                    value = rows[0][0] if rows else {}
                    value = value if isinstance(value, dict) else {}
                    self._areas = {str(k): clean_polygons(v) for k, v in value.items()}
                except Exception as exc:  # noqa: BLE001 — keep the last known areas
                    logger.warning("Could not read restricted areas: %s", type(exc).__name__)
            return self._areas.get(str(camera_id), [])
