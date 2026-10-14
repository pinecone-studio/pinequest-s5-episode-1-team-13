import cv2
import numpy as np

from app.detection.types import Detection, PersonResult
from scripts.demo import GREEN, GREY, RED, colour, demo_image, demo_video, draw, label, main

PERSON = Detection("person", 0.9, (40, 20, 100, 200), track_id=3)
BARE = Detection("no_helmet", 0.8, (55, 10, 85, 40))


def fake_detect(frame):
    return [PERSON, BARE]


def test_colours_and_labels():
    bad = PersonResult(1, (0, 0, 10, 10), 0.9, helmet="NO", violation=True)
    unknown = PersonResult(2, (0, 0, 10, 10), 0.9)
    ok = PersonResult(3, (0, 0, 10, 10), 0.9, helmet="YES", uniform="YES")
    assert (colour(bad), colour(unknown), colour(ok)) == (RED, GREY, GREEN)
    assert label(bad) == "#1 helmet:NO uniform:UNKNOWN"
    office = PersonResult(None, (0, 0, 10, 10), 0.9, helmet_required=False)
    assert label(office) == "? uniform:UNKNOWN"


def test_draw_does_not_change_the_original():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    out = draw(frame, [PersonResult(1, (40, 20, 100, 200), 0.9, helmet="NO", helmet_box=(55, 10, 85, 40), violation=True)])
    assert frame.sum() == 0 and out.sum() > 0


def test_demo_image(tmp_path):
    src, out = tmp_path / "in.jpg", tmp_path / "out.jpg"
    cv2.imwrite(str(src), np.full((240, 320, 3), 80, dtype=np.uint8))
    [p] = demo_image(src, out, fake_detect, helmet_required=True)
    assert p.violation and cv2.imread(str(out)).shape == (240, 320, 3)


def test_demo_video_counts_like_live_system(tmp_path):
    src, out = tmp_path / "in.avi", tmp_path / "out.mp4"
    writer = cv2.VideoWriter(str(src), cv2.VideoWriter_fourcc(*"MJPG"), 10, (320, 240))
    for _ in range(40):  # 4 seconds
        writer.write(np.full((240, 320, 3), 80, dtype=np.uint8))
    writer.release()
    summary = demo_video(src, out, fake_detect, helmet_required=True)
    assert summary["frames"] == 40 and summary["people"] == 1
    assert summary["violations"] == {"NO_HELMET": 1}  # confirmed after 2 s, then cooldown
    assert out.stat().st_size > 0
    short = demo_video(src, tmp_path / "short.mp4", fake_detect, helmet_required=True, max_seconds=1)
    assert short["frames"] == 10 and short["violations"] == {}


def test_missing_file(tmp_path):
    assert main([str(tmp_path / "nope.jpg")]) == 1
