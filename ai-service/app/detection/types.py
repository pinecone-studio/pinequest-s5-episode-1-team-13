from __future__ import annotations

from dataclasses import dataclass

Box = tuple[float, float, float, float]  # x1, y1, x2, y2 in pixels


@dataclass(frozen=True)
class Detection:
    cls: str  # one of CLASSES
    conf: float
    box: Box
    track_id: int | None = None


@dataclass
class PersonResult:
    id: int | None
    box: Box  # pixels
    conf: float
    helmet: str = "UNKNOWN"  # YES | NO | UNKNOWN
    uniform: str = "UNKNOWN"
    helmet_box: Box | None = None
    helmet_conf: float = 0.0
    uniform_conf: float = 0.0
    helmet_required: bool = True
    violation: bool = False
    restricted: bool = False  # feet inside a restricted area
    area: tuple[tuple[int, int], ...] | None = None  # that area in pixels (for the snapshot picture)

    def to_payload(self, width: int, height: int) -> dict:
        """JSON for the dashboard: boxes normalised to 0..1 (web/types DetectionsData)."""
        return {
            "id": self.id,
            "box": normalise(self.box, width, height),
            "helmet_box": normalise(self.helmet_box, width, height) if self.helmet_box else None,
            "helmet": self.helmet,
            "uniform": self.uniform,
            "violation": self.violation,
            "helmet_required": self.helmet_required,
            "restricted": self.restricted,
        }


def normalise(box: Box, width: int, height: int) -> list[float]:
    x1, y1, x2, y2 = box
    clamp = lambda v: round(min(max(v, 0.0), 1.0), 4)  # noqa: E731
    return [clamp(x1 / width), clamp(y1 / height), clamp(x2 / width), clamp(y2 / height)]
