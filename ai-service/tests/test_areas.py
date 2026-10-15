import json

import cv2
import numpy as np
import pytest

from app.cameras.models import CameraInfo
from app.detection.areas import RestrictedAreaConfig, clean_polygons, feet, inside, mark, parse_points
from app.detection.pipeline import CameraAI
from app.detection.types import Detection, PersonResult
from app.violations.rules import RESTRICTED_AREA, ViolationRules, violation_types
from app.violations.snapshot import make_snapshot
from scripts.demo import demo_image, label
from scripts.set_area import update

SQUARE = ((0.5, 0.5), (1.0, 0.5), (1.0, 1.0), (0.5, 1.0))  # bottom-right quarter


def person(box, **kw):
    return PersonResult(1, box, 0.9, **kw)


def test_parse_points():
    assert parse_points("0.5,0.5 1,0.5 1,1") == ((0.5, 0.5), (1.0, 0.5), (1.0, 1.0))
    assert parse_points("0,0;1,0;1,1") == ((0, 0), (1, 0), (1, 1))
    for bad in ("0.5,0.5 1,1", "0.5,0.5 1,0.5 2,1", "a,b 1,1 0,0"):
        with pytest.raises(ValueError):
            parse_points(bad)


def test_inside_and_feet():
    poly = ((0, 0), (10, 0), (10, 10), (0, 10))
    assert inside((5, 5), poly) and not inside((15, 5), poly) and not inside((5, -1), poly)
    triangle = ((0, 0), (10, 0), (0, 10))
    assert inside((2, 2), triangle) and not inside((8, 8), triangle)
    assert feet((10, 20, 30, 100)) == (20, 98.4)


def test_person_cut_off_by_the_bottom_edge_is_caught():
    p = person((120, 60, 180, 200))  # box ends exactly at the bottom of a 200 px picture
    mark([p], [((0.5, 0.5), (1.0, 0.5), (1.0, 0.99), (0.5, 0.99))], 200, 200)  # area clicked a bit above the edge
    assert p.restricted


def test_feet_decide_not_the_head():
    # 200x200 picture, area = bottom-right quarter (100..200)
    standing_in = person((120, 60, 180, 190))  # feet at (150, 190): inside
    leaning_in = person((60, 110, 95, 190))  # feet at (77, 190): left of the area
    tall_next_to = person((120, 10, 180, 90))  # body in the top-right, feet at y=90: above the area
    mark([standing_in, leaning_in, tall_next_to], [SQUARE], 200, 200)
    assert standing_in.restricted and standing_in.violation and standing_in.area == ((100, 100), (200, 100), (200, 200), (100, 200))
    assert not leaning_in.restricted and not leaning_in.violation
    assert not tall_next_to.restricted


def test_no_area_changes_nothing():
    p = person((120, 60, 180, 190))
    mark([p], [], 200, 200)
    assert not p.restricted and not p.violation


def test_rule_type_and_payload():
    p = person((120, 60, 180, 190), helmet="YES", uniform="YES")
    mark([p], [SQUARE], 200, 200)
    assert violation_types(p) == [RESTRICTED_AREA] == ["OTHER_SAFETY_VIOLATION"]
    data = p.to_payload(200, 200)
    assert data["restricted"] is True and data["violation"] is True
    rules = ViolationRules(confirm_seconds=1, cooldown_seconds=60)
    assert rules.update([p], 0.0) == []
    assert rules.update([p], 1.0) == [(RESTRICTED_AREA, p)]


def test_clean_polygons_skips_bad_data():
    assert clean_polygons([[0.1, 0.1], [0.9, 0.1], [0.5, 0.9]]) == [((0.1, 0.1), (0.9, 0.1), (0.5, 0.9))]  # one polygon
    assert clean_polygons([[[0, 0], [1, 0], [1, 1]], [[0, 0], [1, 1]], "x", [[0, 0], [5, 0], [1, 1]]]) == [((0, 0), (1, 0), (1, 1))]
    assert clean_polygons(None) == [] and clean_polygons({"a": 1}) == []


class AreaDB:
    def __init__(self, value):
        self.value, self.calls = value, 0

    def fetch(self, sql, params):
        self.calls += 1
        if isinstance(self.value, Exception):
            raise self.value
        return [(self.value,)] if self.value is not None else []


def test_config_reads_db_and_caches():
    db = AreaDB({"cam-1": [[[0.5, 0.5], [1, 0.5], [1, 1], [0.5, 1]]], "cam-2": "broken"})
    config = RestrictedAreaConfig(db, refresh=60)
    assert config.get("cam-1") == [SQUARE]
    assert config.get("cam-2") == [] and config.get("other") == []
    assert db.calls == 1  # cached
    db.value = RuntimeError("db down")
    config._loaded_at = float("-inf")
    assert config.get("cam-1") == [SQUARE]  # keeps the last known areas


class FakeClient:
    def __init__(self):
        self.sent = []

    def detections(self, camera_id, people):
        self.sent.append(people)
        return True


class FakeReporter:
    def __init__(self):
        self.saved = []

    def submit(self, camera, frame, person, vtype):
        self.saved.append(vtype)


def test_pipeline_saves_restricted_area_violation():
    cam = CameraInfo("cam-1", "Gate", "DAHUA", "1.1.1.1", 554, "u", "p", 1, 0, 0, False, True, "OFFICE")
    walker = Detection("person", 0.9, (260, 150, 340, 390), track_id=4)  # feet (300, 390) in a 400x400 frame
    vest, helmet = Detection("work_uniform", 0.8, (265, 200, 335, 300)), Detection("helmet", 0.8, (280, 140, 320, 175))
    client, reporter = FakeClient(), FakeReporter()
    areas = RestrictedAreaConfig(AreaDB({"cam-1": [list(map(list, SQUARE))]}))
    ai = CameraAI(client, lambda: (lambda frame: [walker, vest, helmet]), detect_fps=10, rules=ViolationRules(1, 60),
                  reporter=reporter, areas=areas)  # fmt: skip
    frame = np.full((400, 400, 3), 120, dtype=np.uint8)
    for t in (0.0, 0.5, 1.0):
        [p] = ai.process(frame, cam, now=t)
    assert p.helmet == "YES" and p.uniform == "YES" and p.restricted  # fully dressed, but in the wrong place
    assert client.sent[-1][0]["violation"] is True and client.sent[-1][0]["restricted"] is True
    assert reporter.saved == [RESTRICTED_AREA]


def test_snapshot_draws_area():
    p = person((120, 60, 180, 190))
    mark([p], [SQUARE], 200, 200)
    frame = np.zeros((200, 200, 3), dtype=np.uint8)
    img = cv2.imdecode(np.frombuffer(make_snapshot(frame, p, RESTRICTED_AREA, quality=100), np.uint8), cv2.IMREAD_COLOR)
    assert img[150, 101:104].max() > 100  # left edge of the area is drawn in red


def test_demo_image_with_area(tmp_path):
    src, out = tmp_path / "a.png", tmp_path / "a_demo.png"
    cv2.imwrite(str(src), np.zeros((200, 200, 3), dtype=np.uint8))
    [p] = demo_image(src, out, lambda f: [Detection("person", 0.9, (120, 60, 180, 190), track_id=1)], True, 0.0, [SQUARE])
    assert p.restricted and "RESTRICTED" in label(p) and out.is_file()


def test_set_area_update():
    one = update({}, "cam-1", SQUARE)
    assert one == {"cam-1": [[[0.5, 0.5], [1.0, 0.5], [1.0, 1.0], [0.5, 1.0]]]}
    two = update(one, "cam-1", ((0, 0), (0.2, 0), (0.2, 0.2)), add=True)
    assert len(two["cam-1"]) == 2 and json.loads(json.dumps(two)) == two
    assert update(two, "cam-1", clear=True) == {}
