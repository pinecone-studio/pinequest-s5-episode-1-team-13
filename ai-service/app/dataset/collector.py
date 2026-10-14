"""Collects training pictures while the cameras run (turned on/off in the web "Training" page).

Saves:  <DATASET_DIR>/datasets/raw/<name>.jpg          the (rotated) frame
        <DATASET_DIR>/datasets/labels_auto/<name>.txt  the AI's guess in YOLO format — a starting point the user corrects
The backend reads these files (backend/app/services/training_service.py). File names must match ^[A-Za-z0-9_-]{1,120}\\.jpg$
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from app.db import Database
from app.detection.classes import CLASSES
from app.detection.types import Detection

logger = logging.getLogger("ai.dataset")

SETTING_KEY = "dataset_collection"  # app_settings row written by the backend (PUT /api/training/collection)
EMPTY_EVERY = 5  # frames with nobody in them: keep only 1 out of 5 ("empty" examples reduce false alarms)
COUNT_REFRESH_SECONDS = 60


@dataclass(frozen=True)
class CollectionSettings:
    enabled: bool = False
    interval_seconds: int = 10
    max_images: int = 5000


class CollectionConfig:
    """Shared by all cameras. Reads the setting from the DB at most every `refresh` seconds."""

    def __init__(self, db: Database, refresh: float = 15.0) -> None:
        self._db, self._refresh = db, refresh
        self._lock = threading.Lock()
        self._value = CollectionSettings()
        self._loaded_at = 0.0

    def get(self) -> CollectionSettings:
        with self._lock:
            if time.time() - self._loaded_at >= self._refresh:
                self._loaded_at = time.time()
                try:
                    rows = self._db.fetch("SELECT value FROM app_settings WHERE key = %s", (SETTING_KEY,))
                    value = rows[0][0] if rows else {}
                    self._value = CollectionSettings(
                        enabled=bool(value.get("enabled", False)),
                        interval_seconds=int(value.get("interval_seconds", 10)),
                        max_images=int(value.get("max_images", 5000)),
                    )
                except Exception as exc:  # noqa: BLE001 — keep the last known setting
                    logger.warning("Could not read collection setting: %s", type(exc).__name__)
            return self._value


def file_stem(camera_name: str, camera_id: str, when: datetime) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", camera_name).strip("-")[:40] or "cam"  # Mongolian names -> "cam"
    return f"{slug}_{camera_id[:8]}_{when:%Y%m%d_%H%M%S}_{when.microsecond // 1000:03d}"


def yolo_lines(detections: list[Detection], width: int, height: int) -> list[str]:
    lines = []
    for d in detections:
        x1, y1, x2, y2 = (min(max(v, 0.0), 1.0) for v in (d.box[0] / width, d.box[1] / height, d.box[2] / width, d.box[3] / height))
        if x2 - x1 <= 0 or y2 - y1 <= 0:
            continue
        lines.append(f"{CLASSES.index(d.cls)} {(x1 + x2) / 2:.6f} {(y1 + y2) / 2:.6f} {x2 - x1:.6f} {y2 - y1:.6f}")
    return lines


def _write_atomic(target: Path, data: bytes) -> None:
    tmp = target.with_name(target.name + ".tmp")  # .tmp never matches the backend's *.jpg / *.txt patterns
    tmp.write_bytes(data)
    os.replace(tmp, target)


class ImageCounter:
    """How many pictures are in raw/. Shared by all cameras; rescans the folder only once a minute."""

    def __init__(self, raw_dir: Path) -> None:
        self._raw = raw_dir
        self._lock = threading.Lock()
        self._count = 0
        self._scanned_at = 0.0

    def get(self) -> int:
        with self._lock:
            if time.time() - self._scanned_at >= COUNT_REFRESH_SECONDS:
                self._scanned_at = time.time()
                self._count = sum(1 for p in self._raw.glob("*.jpg")) if self._raw.is_dir() else 0
            return self._count

    def added(self) -> None:
        with self._lock:
            self._count += 1


class DatasetCollector:
    """One per camera."""

    def __init__(self, root: Path, config: CollectionConfig, counter: ImageCounter) -> None:
        self.raw = root / "datasets" / "raw"
        self.auto = root / "datasets" / "labels_auto"
        self._config, self._counter = config, counter
        self._last_saved = 0.0
        self._empty_seen = 0
        self._warned_full = False

    def maybe_save(self, frame: np.ndarray, camera_name: str, camera_id: str, detections: list[Detection], now: float) -> str | None:
        setting = self._config.get()
        if not setting.enabled or now - self._last_saved < setting.interval_seconds:
            return None
        if self._counter.get() >= setting.max_images:
            if not self._warned_full:
                logger.warning("Training folder is full (%d pictures): collection paused", setting.max_images)
                self._warned_full = True
            return None
        self._warned_full = False
        self._last_saved = now  # the interval counts even when an empty frame is skipped

        if not any(d.cls == "person" for d in detections):
            self._empty_seen += 1
            if self._empty_seen % EMPTY_EVERY != 1:
                return None

        ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
        if not ok:
            return None
        stem = file_stem(camera_name, camera_id, datetime.now())
        height, width = frame.shape[:2]
        try:
            self.raw.mkdir(parents=True, exist_ok=True)
            self.auto.mkdir(parents=True, exist_ok=True)
            lines = yolo_lines(detections, width, height)
            _write_atomic(self.auto / f"{stem}.txt", ("\n".join(lines) + ("\n" if lines else "")).encode())
            _write_atomic(self.raw / f"{stem}.jpg", jpg.tobytes())  # picture last: it "appears" only when complete
        except OSError as exc:
            logger.error("Could not save training picture: %s", exc)
            return None
        self._counter.added()
        return f"{stem}.jpg"
