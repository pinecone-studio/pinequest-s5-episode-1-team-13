import numpy as np

from app.cameras import publisher as pub
from app.cameras.publisher import RETRY_MAX, STABLE_SECONDS, VideoPublisher, next_wait

FRAME = np.zeros((48, 64, 3), dtype=np.uint8)


def test_wait_doubles_up_to_a_limit():
    waits, w = [], None
    for _ in range(7):
        w = next_wait(w)
        waits.append(w)
    assert waits == [5, 10, 20, 40, 60, 60, 60] and RETRY_MAX == 60


class Clock:
    def __init__(self):
        self.now = 1000.0

    def time(self):
        return self.now


class DeadStdin:
    def write(self, data):
        raise BrokenPipeError

    def close(self):
        pass


class OkStdin:
    def write(self, data):
        pass

    def close(self):
        pass


class FakeProc:
    def __init__(self, broken):
        self.stdin = DeadStdin() if broken else OkStdin()

    def poll(self):
        return None

    def wait(self, timeout=None):
        return 0


def setup(monkeypatch, broken):
    clock, starts = Clock(), []

    def popen(cmd, stdin=None):
        starts.append(clock.now)
        return FakeProc(broken["now"])

    monkeypatch.setattr(pub.time, "time", clock.time)
    monkeypatch.setattr(pub.subprocess, "Popen", popen)
    monkeypatch.setattr(VideoPublisher, "available", staticmethod(lambda: True))
    return clock, starts


def run_for(publisher, clock, seconds, step=1.0):
    end = clock.now + seconds
    while clock.now < end:
        publisher.send(FRAME)
        clock.now += step


def test_mediamtx_down_retries_less_and_less_often(monkeypatch):
    broken = {"now": True}
    clock, starts = setup(monkeypatch, broken)
    p = VideoPublisher("rtsp://x/cam_1", 15, "Gate")
    run_for(p, clock, 200)
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    assert gaps == [5, 10, 20, 40, 60, 60]  # old code: every 5 s forever (40 restarts in 200 s)


def test_back_to_fast_retry_after_it_works_again(monkeypatch):
    broken = {"now": True}
    clock, starts = setup(monkeypatch, broken)
    p = VideoPublisher("rtsp://x/cam_1", 15, "Gate")
    run_for(p, clock, 40)  # 4 failures: next wait is already 40 s
    broken["now"] = False
    run_for(p, clock, 40 + STABLE_SECONDS + 5)  # reconnects, then stays healthy long enough
    broken["now"] = True
    before = len(starts)
    p._proc = FakeProc(True)  # the running ffmpeg now breaks
    run_for(p, clock, 6)
    assert len(starts) == before + 1  # retried after 5 s again, not 40 s
