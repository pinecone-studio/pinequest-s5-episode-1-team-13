"""build_crops: хүний хайрцгийг хуурамч detector-оор өгч, хайчилбар болон шошгын хөрвүүлэлтийг шалгана."""

import cv2
import numpy as np

import crops


def make_dataset(root, n=30):
    raw, labels = root / "datasets" / "raw", root / "datasets" / "labels"
    raw.mkdir(parents=True)
    labels.mkdir(parents=True)
    for i in range(n):
        cv2.imwrite(str(raw / f"cam_{i:03d}.jpg"), np.full((200, 300, 3), 120, np.uint8))
        # person(0), helmet(1), work_uniform(3) — нормчилсон YOLO мөр
        (labels / f"cam_{i:03d}.txt").write_text("0 0.5 0.5 0.4 0.8\n1 0.5 0.2 0.1 0.12\n3 0.5 0.55 0.35 0.3\n")


def test_read_labels_maps_ppe_classes_and_keeps_persons_separately():
    import pathlib, tempfile

    with tempfile.TemporaryDirectory() as d:
        f = pathlib.Path(d) / "a.txt"
        f.write_text("0 0.5 0.5 0.4 0.8\n2 0.5 0.2 0.1 0.1\n9 0.1 0.1 0.1 0.1\n")
        ppe, persons = crops.read_labels(f)
    assert [c for c, *_ in ppe] == [1]            # no_helmet (2) -> PPE моделийн 1
    assert len(persons) == 1


def test_build_crops_writes_yolo_crop_dataset(tmp_path):
    make_dataset(tmp_path)
    detect = lambda image: [(0.3, 0.1, 0.7, 0.9)]  # бүх зурагт нэг хүн
    out = tmp_path / "runs" / "dataset"
    summary = crops.build_crops(tmp_path, out, detect, variants=2)
    assert sum(summary["crops"].values()) > 0 and summary["missing_in_train"] == ["no_helmet", "no_work_uniform"]
    assert (out / "data.yaml").is_file()
    label = next((out / "labels" / "train").glob("*.txt")).read_text().split()
    assert label[0] in {"0", "2"}                  # helmet=0, work_uniform=2
