import re

import cv2
import numpy as np

from app.detection.types import Detection
from scripts.prelabel import collect_files, is_hard, main, prelabel, stem_for

IMAGE_RE = re.compile(r"^[A-Za-z0-9_\-]{1,120}\.jpg$")  # backend Training page rule
SURE = [Detection("person", 0.9, (40, 20, 100, 200)), Detection("helmet", 0.85, (55, 10, 85, 40))]
UNSURE = [Detection("person", 0.9, (40, 20, 100, 200)), Detection("no_helmet", 0.45, (55, 10, 85, 40))]


def picture(value: int) -> np.ndarray:
    frame = np.full((240, 320, 3), 60, dtype=np.uint8)
    cv2.rectangle(frame, (value, 40), (value + 60, 200), (220, 220, 220), -1)
    return frame


def test_hard_means_unsure():
    assert is_hard(UNSURE, 0.3, 0.6) and not is_hard(SURE, 0.3, 0.6)


def test_names_fit_the_training_page():
    from pathlib import Path

    assert IMAGE_RE.match(stem_for(Path("Анар vest photo (1).HEIC.jpg"), 3) + ".jpg")
    assert stem_for(Path("IMG_2041.JPG"), 0) == "IMG-2041_00000"


def test_photos_are_saved_with_auto_labels(tmp_path):
    photos = tmp_path / "photos"
    photos.mkdir()
    cv2.imwrite(str(photos / "a.jpg"), picture(20))
    cv2.imwrite(str(photos / "b.png"), picture(200))
    (photos / "notes.txt").write_text("skip me")
    files = collect_files([photos])
    assert [f.name for f in files] == ["a.jpg", "b.png"]

    r = prelabel(files, lambda f: UNSURE, tmp_path / "training")
    assert (r.saved, r.hard) == (2, 2)
    label = (tmp_path / "training/datasets/labels_auto/a_00000.txt").read_text().splitlines()
    assert label[0].startswith("0 ") and label[1].startswith("2 ")  # person, no_helmet
    again = prelabel(files, lambda f: UNSURE, tmp_path / "training")
    assert again.saved == 0 and again.skipped_existing == 2


def test_only_hard_and_video_duplicates(tmp_path):
    video = tmp_path / "walk.avi"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), 10, (320, 240))
    for i in range(40):  # 4 s: still for 2 s, then moving
        writer.write(picture(20 if i < 20 else 20 + (i - 20) * 8))
    writer.release()

    answers = iter([SURE, UNSURE] * 20)
    r = prelabel([video], lambda f: next(answers), tmp_path / "t", every_seconds=0.5, only_hard=True)
    assert r.seen == 8
    assert r.skipped_duplicate >= 3  # the still part
    assert r.saved == r.hard and r.skipped_easy >= 1


def test_nothing_to_do(tmp_path):
    assert main([str(tmp_path)]) == 1
