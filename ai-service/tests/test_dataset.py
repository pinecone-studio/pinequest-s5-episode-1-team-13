import re
from datetime import datetime
from pathlib import Path

import numpy as np

from app.dataset.collector import CollectionConfig, CollectionSettings, DatasetCollector, ImageCounter, file_stem, yolo_lines
from app.detection.types import Detection

IMAGE_RE = re.compile(r"^[A-Za-z0-9_\-]{1,120}\.jpg$")  # same rule as backend training_service
PERSON = Detection("person", 0.9, (100, 50, 200, 450))
HELMET = Detection("helmet", 0.8, (125, 40, 175, 90))
FRAME = np.zeros((500, 400, 3), dtype=np.uint8)


class StaticConfig:
    def __init__(self, **kw):
        self.value = CollectionSettings(**kw)

    def get(self):
        return self.value


def make(tmp_path: Path, **kw):
    config = StaticConfig(**kw)
    return DatasetCollector(tmp_path, config, ImageCounter(tmp_path / "datasets" / "raw")), config


def test_file_names_are_accepted_by_backend():
    when = datetime(2026, 10, 14, 10, 30, 5, 123000)
    assert IMAGE_RE.match(file_stem("Үйлдвэр 1", "abcdef12-3456", when) + ".jpg")
    assert file_stem("Gate A", "abcdef12-3456", when) == "Gate-A_abcdef12_20261014_103005_123"
    assert file_stem("Хаалга", "abcdef12", when).startswith("cam_")


def test_yolo_lines_use_backend_class_ids():
    [person, helmet] = yolo_lines([PERSON, HELMET], 400, 500)
    assert person == "0 0.375000 0.500000 0.250000 0.800000"
    assert helmet.startswith("1 ")


def test_saves_picture_and_auto_labels(tmp_path):
    collector, _ = make(tmp_path, enabled=True, interval_seconds=10)
    name = collector.maybe_save(FRAME, "Gate", "cam-0001", [PERSON, HELMET], now=100.0)
    assert (tmp_path / "datasets/raw" / name).read_bytes()[:3] == b"\xff\xd8\xff"
    labels = (tmp_path / "datasets/labels_auto" / name.replace(".jpg", ".txt")).read_text().splitlines()
    assert len(labels) == 2
    assert collector.maybe_save(FRAME, "Gate", "cam-0001", [PERSON], now=105.0) is None  # interval
    assert collector.maybe_save(FRAME, "Gate", "cam-0001", [PERSON], now=110.0) is not None


def test_off_by_default_and_respects_max(tmp_path):
    collector, config = make(tmp_path)
    assert collector.maybe_save(FRAME, "Gate", "cam-1", [PERSON], now=1.0) is None
    config.value = CollectionSettings(enabled=True, interval_seconds=2, max_images=1)
    assert collector.maybe_save(FRAME, "Gate", "cam-1", [PERSON], now=10.0) is not None
    assert collector.maybe_save(FRAME, "Gate", "cam-1", [PERSON], now=20.0) is None  # full


def test_empty_frames_are_kept_five_times_less(tmp_path):
    collector, _ = make(tmp_path, enabled=True, interval_seconds=2)
    saved = [collector.maybe_save(FRAME, "Gate", "cam-1", [], now=float(t * 2)) for t in range(10)]
    assert sum(s is not None for s in saved) == 2


class FakeDB:
    def __init__(self, rows):
        self.rows, self.calls = rows, 0

    def fetch(self, sql, params):
        self.calls += 1
        return self.rows


def test_collection_setting_from_db_is_cached():
    db = FakeDB([({"enabled": True, "interval_seconds": 30, "max_images": 5000},)])
    config = CollectionConfig(db, refresh=60)
    assert config.get() == CollectionSettings(enabled=True, interval_seconds=30, max_images=5000)
    config.get()
    assert db.calls == 1
    assert CollectionConfig(FakeDB([])).get().enabled is False
