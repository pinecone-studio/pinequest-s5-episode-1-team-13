import numpy as np

from app.cameras.models import CameraInfo
from app.detection.pipeline import CameraAI
from app.detection.smoothing import PersonSmoother
from app.detection.types import Detection, PersonResult


def person(pid, helmet="YES", uniform="YES", required=True):
    p = PersonResult(pid, (0, 0, 10, 10), 0.9, helmet=helmet, uniform=uniform, helmet_required=required)
    p.violation = (required and helmet == "NO") or uniform == "NO"
    return p


def run(smoother, states, pid=1):
    return [smoother.apply([person(pid, helmet=s)])[0].helmet for s in states]


def test_one_bad_frame_does_not_flip_the_label():
    assert run(PersonSmoother(5), ["YES", "YES", "NO", "YES", "YES"]) == ["YES"] * 5


def test_real_change_wins_after_a_majority():
    shown = run(PersonSmoother(5), ["YES"] * 5 + ["NO"] * 5)
    assert shown[:5] == ["YES"] * 5 and shown[-1] == "NO"
    assert shown.index("NO") == 7  # 3 of the last 5


def test_violation_follows_the_smoothed_state():
    s = PersonSmoother(3)
    for _ in range(3):
        s.apply([person(1, helmet="YES")])
    [p] = s.apply([person(1, helmet="NO")])
    assert p.helmet == "YES" and p.violation is False


def test_people_are_smoothed_separately_and_no_id_is_untouched():
    s = PersonSmoother(5)
    for _ in range(3):
        a, b = s.apply([person(1, helmet="YES"), person(2, helmet="NO")])
    assert (a.helmet, b.helmet) == ("YES", "NO")
    [anon] = s.apply([person(None, helmet="NO")])
    assert anon.helmet == "NO"


def test_window_one_is_off():
    assert run(PersonSmoother(1), ["YES", "NO", "YES"]) == ["YES", "NO", "YES"]


class FakeClient:
    def __init__(self):
        self.sent = []

    def detections(self, camera_id, people):
        self.sent.append(people)
        return True


CAM = CameraInfo("cam-1", "Gate", "DAHUA", "1.1.1.1", 554, "u", "p", 1, 0, 0, False, True, "FACTORY")
PERSON = Detection("person", 0.9, (100, 100, 200, 400), track_id=7)
HAT = Detection("helmet", 0.8, (125, 85, 175, 135))
BARE = Detection("no_helmet", 0.8, (125, 85, 175, 135))


def test_pipeline_sends_smoothed_labels():
    client = FakeClient()
    frames = iter([[PERSON, HAT], [PERSON, HAT], [PERSON, BARE], [PERSON, HAT]])
    ai = CameraAI(client, lambda: (lambda f: next(frames)), detect_fps=10, smooth_window=5)
    for t in range(4):
        ai.process(np.zeros((480, 640, 3), dtype=np.uint8), CAM, now=float(t))
    assert [msg[0]["helmet"] for msg in client.sent] == ["YES", "YES", "YES", "YES"]
