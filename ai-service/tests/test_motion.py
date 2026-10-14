import numpy as np

from app.cameras.models import CameraInfo
from app.detection.motion import MotionGate, changed_fraction, small_grey
from app.detection.pipeline import CameraAI
from app.detection.types import Detection

EMPTY = np.full((480, 640, 3), 90, dtype=np.uint8)


def with_person(x: int) -> np.ndarray:
    frame = EMPTY.copy()
    frame[100:400, x : x + 120] = 230  # a bright "person" block
    return frame


def noisy(frame: np.ndarray, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.clip(frame.astype(int) + rng.integers(-6, 7, frame.shape), 0, 255).astype(np.uint8)


def test_camera_noise_is_not_motion():
    assert changed_fraction(small_grey(noisy(EMPTY, 1)), small_grey(noisy(EMPTY, 2))) < 0.001


def test_person_walking_in_is_motion():
    assert changed_fraction(small_grey(EMPTY), small_grey(with_person(200))) > 0.05


def test_gate_skips_still_empty_scene_but_checks_again_later():
    gate = MotionGate(threshold=0.01, max_skip_seconds=5)
    assert gate.should_run(EMPTY, 0.0, people_last_time=False)  # first frame always runs
    assert not gate.should_run(noisy(EMPTY, 3), 1.0, people_last_time=False)
    assert not gate.should_run(noisy(EMPTY, 4), 2.0, people_last_time=False)
    assert gate.should_run(EMPTY, 5.0, people_last_time=False)  # forced check
    assert gate.skipped == 2


def test_gate_runs_on_motion_and_while_people_are_there():
    gate = MotionGate(threshold=0.01, max_skip_seconds=60)
    gate.should_run(EMPTY, 0.0, people_last_time=False)
    assert gate.should_run(with_person(200), 1.0, people_last_time=False)
    assert gate.should_run(with_person(200), 2.0, people_last_time=True)  # standing still, still tracked


def test_slow_motion_adds_up():
    gate = MotionGate(threshold=0.05, max_skip_seconds=60)
    gate.should_run(with_person(100), 0.0, people_last_time=False)
    results = [gate.should_run(with_person(100 + 4 * i), float(i), people_last_time=False) for i in range(1, 30)]
    assert any(results)  # compared with the last YOLO frame, not the previous frame


class FakeClient:
    def __init__(self):
        self.sent = []

    def detections(self, camera_id, people):
        self.sent.append(people)
        return True


CAM = CameraInfo("cam-1", "Gate", "DAHUA", "1.1.1.1", 554, "u", "p", 1, 0, 0, False, True, "FACTORY")


def test_pipeline_does_not_call_model_on_still_empty_scene():
    calls = []

    def detector(frame):
        calls.append(1)
        return []

    ai = CameraAI(FakeClient(), lambda: detector, detect_fps=1, motion=MotionGate(0.01, 30))
    for t in range(10):
        ai.process(noisy(EMPTY, t), CAM, now=float(t))
    assert len(calls) == 1


def test_pipeline_keeps_running_while_person_visible():
    calls = []
    person = Detection("person", 0.9, (200, 100, 320, 400), track_id=1)

    def detector(frame):
        calls.append(1)
        return [person]

    ai = CameraAI(FakeClient(), lambda: detector, detect_fps=1, motion=MotionGate(0.01, 30))
    for t in range(5):
        ai.process(with_person(200), CAM, now=float(t))
    assert len(calls) == 5
