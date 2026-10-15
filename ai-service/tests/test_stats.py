import logging

from app.cameras.stats import CameraStats


def test_line_every_period_then_reset(caplog):
    stats = CameraStats("Gate", every_seconds=60, start=0.0)
    for _ in range(900):
        stats.frame()
    for ms, people, bad in [(40, 1, 0), (60, 2, 1), (20, 2, 1)]:
        stats.ai_step(ms, people, bad)
    assert stats.maybe_log(30.0, "STREAMING") is None  # not time yet
    with caplog.at_level(logging.INFO, logger="ai.stats"):
        line = stats.maybe_log(60.0, "STREAMING")
    assert line == "Gate | video 15.0 fps | AI 0.1/s, 40 ms avg, 60 ms max | people max 2 | violation frames 2 | status STREAMING"
    assert line in caplog.text
    assert stats.frames == 0 and stats.ai_runs == 0  # new period
    assert stats.maybe_log(90.0, "STREAMING") is None


def test_no_ai_runs_does_not_divide_by_zero():
    stats = CameraStats("Gate", every_seconds=10, start=0.0)
    assert "AI 0.0/s, 0 ms avg" in stats.maybe_log(10.0, "RECONNECTING")


def test_zero_turns_it_off():
    stats = CameraStats("Gate", every_seconds=0, start=0.0)
    assert stats.maybe_log(10_000.0, "STREAMING") is None
