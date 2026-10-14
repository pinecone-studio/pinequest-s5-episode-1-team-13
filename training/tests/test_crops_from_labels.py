import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import dataset_split as ds  # noqa: E402


def make(root: Path, n: int, label="3 0.5 0.5 0.2 0.2\n", cams=("camA",)):
    (root / "datasets/raw").mkdir(parents=True, exist_ok=True)
    (root / "datasets/labels").mkdir(parents=True, exist_ok=True)
    for cam in cams:
        for i in range(n):
            stem = f"{cam}_20261009_{i:06d}"
            (root / "datasets/raw" / f"{stem}.jpg").write_bytes(b"\xff\xd8\xff\xd9")
            (root / "datasets/labels" / f"{stem}.txt").write_text(label)


def make_images(root: Path, n: int, width=640, height=480):
    import cv2
    import numpy as np

    (root / "datasets/raw").mkdir(parents=True, exist_ok=True)
    (root / "datasets/labels").mkdir(parents=True, exist_ok=True)
    for i in range(n):
        stem = f"camA_20261009_{i:06d}"
        img = np.full((height, width, 3), 90, np.uint8)
        cv2.rectangle(img, (200, 100), (360, 440), (30, 120, 220), -1)  # хүн
        cv2.imwrite(str(root / "datasets/raw" / f"{stem}.jpg"), img)
        # helmet (толгой дээр), work_uniform (их бие), мөн хүнд хамаарахгүй "шүүгээн дээрх" helmet
        (root / "datasets/labels" / f"{stem}.txt").write_text(
            "1 0.4375 0.2500 0.1000 0.1000\n3 0.4375 0.5500 0.2500 0.3500\n1 0.9000 0.1000 0.0600 0.0600\n")


def test_crops_follow_the_person_remap_classes_and_skip_unrelated_boxes(tmp_path):
    import crops

    make_images(tmp_path, 40)
    person = lambda image: [(200 / 640, 100 / 480, 360 / 640, 440 / 480)]  # COCO-ийн хүн
    out = tmp_path / "runs" / "crops"
    summary = crops.build_crops(tmp_path, out, person, variants=2)
    assert sum(summary["crops"].values()) == 80                      # 40 зураг x 1 хүн x 2 хувилбар
    assert summary["images"]["train"] + summary["images"]["val"] + summary["images"]["test"] == 40
    lines = next((out / "labels" / "train").glob("*_v0.txt")).read_text().splitlines()
    ids = sorted(int(l.split()[0]) for l in lines)
    assert ids == [0, 2]                                             # helmet=0, work_uniform=2 (хүнд хамаарахгүй helmet орсонгүй)
    for l in lines:
        _, cx, cy, w, h = map(float, l.split())
        assert 0 <= cx <= 1 and 0 <= cy <= 1 and 0 < w <= 1 and 0 < h <= 1
    yaml = (out / "data.yaml").read_text()
    names = yaml.split("names:")[1]
    assert "0: helmet" in names and "3: no_work_uniform" in names and "person" not in names  # хүн анги байхгүй
    assert summary["missing_in_train"] == ["no_helmet", "no_work_uniform"]


def test_crop_boxes_land_on_the_right_pixels(tmp_path):
    import cv2
    import numpy as np

    import crops
    from person_crops import scale_for

    im = np.zeros((480, 640, 3), np.uint8)
    out = crops.crop_one(im, (200.0, 100.0, 360.0, 440.0), [(2, 200 / 640, 240 / 480, 360 / 640, 340 / 480)], 0, __import__("random").Random(0))
    img, lines = out
    cid, cx, cy, w, h = lines[0].split(); cx, cy, w, h = map(float, (cx, cy, w, h))
    # хүний өргөн 160 px, margin 35%x2 => хайчилбар ~272 px; хайрцаг 160 px өргөн => ~0.59
    assert cid == "2" and abs(w - 160 / 272) < 0.02 and abs(cx - 0.5) < 0.02
    k = scale_for(272, 389)
    assert abs(img.shape[0] - round(389 * k)) <= 2 and max(img.shape[:2]) <= 512 + 1


def test_far_variant_is_degraded_but_keeps_labels(tmp_path):
    import random

    import numpy as np

    import crops

    rng = np.random.default_rng(0)
    im = rng.integers(0, 255, (1200, 800, 3), dtype=np.uint8)
    ppe = [(0, 0.45, 0.05, 0.55, 0.12)]
    near = crops.crop_one(im, (200.0, 60.0, 600.0, 1100.0), ppe, 0, random.Random(1))
    far = crops.crop_one(im, (200.0, 60.0, 600.0, 1100.0), ppe, 1, random.Random(1))
    assert near and far and near[1] and far[1]
    # хол хувилбар бүдэг: хөрш пикселийн ялгаа багасна
    sharp = lambda a: float(np.abs(np.diff(a.astype(float), axis=1)).mean())
    assert sharp(far[0]) < sharp(near[0])
