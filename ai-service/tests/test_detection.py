import numpy as np
import pytest

from app.cameras.models import CameraInfo
from app.detection.classes import CLASSES, parse_mapping, resolve_names
from app.detection.pipeline import CameraAI
from app.detection.ppe import analyse
from app.detection.types import Detection

PERSON = Detection("person", 0.9, (100, 100, 200, 400), track_id=7)  # 300 px tall
HEAD_HELMET = Detection("helmet", 0.8, (125, 85, 175, 135))
HEAD_BARE = Detection("no_helmet", 0.7, (125, 85, 175, 135))
VEST = Detection("work_uniform", 0.8, (105, 170, 195, 300))
NO_VEST = Detection("no_work_uniform", 0.6, (105, 170, 195, 300))


def test_classes_match_backend_order():
    assert CLASSES == ("person", "helmet", "no_helmet", "work_uniform", "no_work_uniform")


def test_class_mapping():
    mapping = parse_mapping("Hardhat:helmet, NO-Hardhat:no_helmet, safety vest:work_uniform")
    assert mapping == {"hardhat": "helmet", "no-hardhat": "no_helmet", "safety vest": "work_uniform"}
    assert resolve_names({0: "Hardhat", 1: "Mask", 2: "NO-Hardhat"}, mapping) == {0: "helmet", 2: "no_helmet"}
    assert resolve_names({0: "person", 1: "helmet", 2: "dog"}, {}) == {0: "person", 1: "helmet"}
    with pytest.raises(ValueError):
        parse_mapping("hardhat:hat")


def test_safe_worker():
    [p] = analyse([PERSON, HEAD_HELMET, VEST], helmet_required=True)
    assert (p.id, p.helmet, p.uniform, p.violation) == (7, "YES", "YES", False)
    assert p.helmet_box == HEAD_HELMET.box


def test_no_helmet_is_violation_only_where_required():
    [p] = analyse([PERSON, HEAD_BARE, VEST], helmet_required=True)
    assert p.helmet == "NO" and p.violation
    [office] = analyse([PERSON, HEAD_BARE, VEST], helmet_required=False)  # OFFICE zone
    assert office.helmet == "NO" and not office.violation


def test_no_uniform_is_violation():
    [p] = analyse([PERSON, HEAD_HELMET, NO_VEST], helmet_required=False)
    assert p.uniform == "NO" and p.violation


def test_unknown_is_not_a_violation():
    [p] = analyse([PERSON], helmet_required=True)
    assert (p.helmet, p.uniform, p.violation) == ("UNKNOWN", "UNKNOWN", False)


def test_helmet_on_the_feet_does_not_count():
    feet = Detection("helmet", 0.9, (130, 370, 170, 400))
    [p] = analyse([PERSON, feet], helmet_required=True)
    assert p.helmet == "UNKNOWN"


def test_each_head_goes_to_the_right_person():
    right = Detection("person", 0.85, (300, 100, 400, 400), track_id=8)
    bare_right = Detection("no_helmet", 0.7, (325, 85, 375, 135))
    a, b = analyse([PERSON, right, HEAD_HELMET, bare_right], helmet_required=True)
    assert (a.id, a.helmet) == (7, "YES") and (b.id, b.helmet) == (8, "NO")


def test_far_away_person_is_not_judged():
    tiny = Detection("person", 0.9, (10, 10, 20, 40))
    bare = Detection("no_helmet", 0.9, (11, 8, 19, 16))
    [p] = analyse([tiny, bare], helmet_required=True)
    assert p.helmet == "UNKNOWN" and not p.violation


def test_payload_is_normalised():
    [p] = analyse([PERSON, HEAD_HELMET], helmet_required=True)
    data = p.to_payload(400, 500)
    assert data["box"] == [0.25, 0.2, 0.5, 0.8]
    assert set(data) == {"id", "box", "helmet_box", "helmet", "uniform", "violation", "helmet_required"}


class FakeClient:
    def __init__(self):
        self.sent = []

    def detections(self, camera_id, people):
        self.sent.append((camera_id, people))
        return True


CAM = CameraInfo("cam-1", "Gate", "DAHUA", "1.1.1.1", 554, "u", "p", 1, 0, 0, False, True, "FACTORY")


def test_pipeline_rate_limit_and_clear():
    client = FakeClient()
    found = [[PERSON, HEAD_BARE], [PERSON, HEAD_BARE], []]
    ai = CameraAI(client, lambda: (lambda frame: found.pop(0)), detect_fps=2)
    frame = np.zeros((500, 400, 3), dtype=np.uint8)

    people = ai.process(frame, CAM, now=10.0)
    assert people[0].violation and client.sent[-1][1][0]["helmet"] == "NO"
    assert ai.process(frame, CAM, now=10.2) is None  # too soon (2 fps = every 0.5 s)
    ai.process(frame, CAM, now=10.6)
    ai.process(frame, CAM, now=11.2)  # nobody now -> one empty message to clear the overlay
    assert client.sent[-1] == ("cam-1", []) and len(client.sent) == 3


def test_pipeline_ai_disabled_clears_once():
    client = FakeClient()
    ai = CameraAI(client, lambda: (lambda frame: [PERSON]), detect_fps=5)
    frame = np.zeros((500, 400, 3), dtype=np.uint8)
    ai.process(frame, CAM, now=1.0)
    off = CameraInfo(**{**CAM.__dict__, "ai_enabled": False})
    assert ai.process(frame, off, now=2.0) is None
    ai.process(frame, off, now=3.0)
    assert client.sent[-1] == ("cam-1", []) and len(client.sent) == 2
