import cv2
import numpy as np

from app.cameras.models import CameraInfo
from app.cameras.quality import Quality, measure
from app.detection.pipeline import CameraAI
from app.detection.types import Detection
from app.violations.rules import ViolationRules


def scene() -> np.ndarray:
    """A sharp, bright test picture: checkerboard with some shapes."""
    frame = np.full((480, 640, 3), 140, dtype=np.uint8)
    for y in range(0, 480, 40):
        for x in range((y // 40) % 2 * 40, 640, 80):
            frame[y : y + 40, x : x + 40] = 220
    cv2.circle(frame, (320, 240), 90, (30, 60, 200), -1)
    return frame


def test_sharp_bright_frame_is_ok():
    q = measure(scene())
    assert q.brightness > 100 and q.sharpness > 200
    assert q.problem(35, 25) is None


def test_dark_and_blurry_are_caught():
    dark = (scene() * 0.12).astype(np.uint8)
    blurry = cv2.GaussianBlur(scene(), (0, 0), 12)
    assert measure(dark).problem(35, 25) == "too dark"
    assert measure(blurry).problem(35, 25) == "too blurry"


def test_zero_turns_a_check_off():
    assert Quality(brightness=5, sharpness=1).problem(0, 0) is None
    assert Quality(brightness=5, sharpness=500).problem(0, 25) is None


def test_resolution_does_not_change_the_numbers_much():
    small, big = measure(scene()), measure(cv2.resize(scene(), (1920, 1440)))
    assert abs(small.brightness - big.brightness) < 2


class FakeClient:
    def __init__(self):
        self.sent = []

    def detections(self, camera_id, people):
        self.sent.append(people)
        return True


class FakeReporter:
    def __init__(self):
        self.saved = []

    def submit(self, camera, frame, person, vtype, others=()):
        self.saved.append(vtype)


CAM = CameraInfo("cam-1", "Gate", "DAHUA", "1.1.1.1", 554, "u", "p", 1, 0, 0, False, True, "FACTORY")
BARE = [Detection("person", 0.9, (200, 100, 320, 400), track_id=1), Detection("no_helmet", 0.8, (230, 85, 290, 140))]


def run(frame):
    client, reporter = FakeClient(), FakeReporter()
    ai = CameraAI(client, lambda: (lambda f: BARE), detect_fps=2, rules=ViolationRules(0, 60), reporter=reporter,
                  min_brightness=35, min_sharpness=25)  # fmt: skip
    for t in range(3):
        ai.process(frame, CAM, now=float(t))
    return client, reporter


def test_dark_frame_still_shows_boxes_but_saves_nothing():
    client, reporter = run((scene() * 0.12).astype(np.uint8))
    assert len(client.sent) == 3 and reporter.saved == []


def test_good_frame_saves_violation():
    _, reporter = run(scene())
    assert reporter.saved == ["NO_HELMET"]
