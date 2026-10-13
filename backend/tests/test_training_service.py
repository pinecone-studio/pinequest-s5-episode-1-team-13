"""Сургалтын файлын үйлчилгээ: шошгоны формат, path traversal, тоолол, устгал, сургалтын төлөв."""

import json
import os
from pathlib import Path

import pytest

from app.services import training_service as svc


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "datasets" / "raw").mkdir(parents=True)
    return tmp_path


def add_image(root: Path, name: str, mtime: float | None = None) -> None:
    path = root / "datasets" / "raw" / name
    path.write_bytes(b"\xff\xd8\xff\xd9")
    if mtime:
        os.utime(path, (mtime, mtime))


BOX = {"class_name": "work_uniform", "x1": 0.1, "y1": 0.2, "x2": 0.5, "y2": 0.8}


def test_write_then_read_roundtrip_in_yolo_format(root):
    add_image(root, "cam_1.jpg")
    svc.write_boxes(root, "cam_1.jpg", [BOX, {**BOX, "class_name": "no_helmet", "y2": 0.5}])
    line = (root / "datasets/labels/cam_1.txt").read_text().splitlines()[0]
    assert line.split()[0] == "3"  # work_uniform = 3
    assert [round(float(v), 4) for v in line.split()[1:]] == [0.3, 0.5, 0.4, 0.6]  # cx cy w h
    boxes, source = svc.read_boxes(root, "cam_1.jpg")
    assert source == "manual" and [b["class_name"] for b in boxes] == ["work_uniform", "no_helmet"]
    assert boxes[0]["x1"] == pytest.approx(0.1) and boxes[0]["y2"] == pytest.approx(0.8)


def test_person_is_hidden_from_labeling_but_preserved_on_save(root):
    add_image(root, "cam_p.jpg")
    (root / "datasets/labels_auto").mkdir()
    (root / "datasets/labels_auto/cam_p.txt").write_text("0 0.5 0.5 0.4 0.9\n3 0.5 0.6 0.3 0.3\n")
    boxes, source = svc.read_boxes(root, "cam_p.jpg")
    assert source == "auto" and [b["class_name"] for b in boxes] == ["work_uniform"]  # хүн харагдахгүй
    svc.write_boxes(root, "cam_p.jpg", [{**BOX, "class_name": "helmet"}])
    saved = (root / "datasets/labels/cam_p.txt").read_text().splitlines()
    assert sorted(line.split()[0] for line in saved) == ["0", "1"]  # AI-ийн хүн хэвээр, хэрэглэгчийн каск нэмэгдсэн
    assert [b["class_name"] for b in svc.read_boxes(root, "cam_p.jpg")[0]] == ["helmet"]
    svc.write_boxes(root, "cam_p.jpg", [])  # "юу ч байхгүй" ч хүнийг устгахгүй
    assert (root / "datasets/labels/cam_p.txt").read_text().split()[0] == "0"


def test_auto_labels_are_suggestions_until_confirmed(root):
    add_image(root, "cam_2.jpg")
    (root / "datasets/labels_auto").mkdir()
    (root / "datasets/labels_auto/cam_2.txt").write_text("1 0.5 0.5 0.2 0.2\n")
    boxes, source = svc.read_boxes(root, "cam_2.jpg")
    assert source == "auto" and boxes[0]["class_name"] == "helmet"
    assert svc.counts(root)["labeled_count"] == 0  # AI санал нь шошглосонд тооцогдохгүй
    svc.write_boxes(root, "cam_2.jpg", [])  # "юу ч байхгүй" гэж батлав (сөрөг жишээ)
    assert svc.read_boxes(root, "cam_2.jpg") == ([], "manual")
    assert svc.counts(root)["labeled_count"] == 1


@pytest.mark.parametrize(
    "bad",
    [
        {**BOX, "class_name": "cat"},
        {**BOX, "x2": 0.05},  # x2 < x1
        {**BOX, "x1": 0.1, "x2": 0.101},  # хэт жижиг
    ],
)
def test_invalid_boxes_are_rejected(root, bad):
    add_image(root, "cam_3.jpg")
    with pytest.raises(svc.TrainingError):
        svc.write_boxes(root, "cam_3.jpg", [bad])
    assert not (root / "datasets/labels/cam_3.txt").exists()


@pytest.mark.parametrize("name", ["../secret.jpg", "a/b.jpg", "x.png", "", ".jpg", "a b.jpg", "..%2f.jpg", "a" * 130 + ".jpg"])
def test_path_traversal_and_bad_names_are_rejected(root, name):
    with pytest.raises(svc.TrainingError):
        svc.image_path(root, name)
    with pytest.raises(svc.TrainingError):
        svc.write_boxes(root, name, [])


def test_missing_image_is_not_found(root):
    with pytest.raises(FileNotFoundError):
        svc.image_path(root, "nope.jpg")


def test_list_filters_and_orders_newest_first(root):
    add_image(root, "a_1.jpg", 1000)
    add_image(root, "b_2.jpg", 3000)
    add_image(root, "c_3.jpg", 2000)
    svc.write_boxes(root, "c_3.jpg", [BOX])
    total, items = svc.list_images(root, "all", 0, 10)
    assert total == 3 and [i["name"] for i in items] == ["b_2.jpg", "c_3.jpg", "a_1.jpg"]
    assert [i["name"] for i in svc.list_images(root, "unlabeled", 0, 10)[1]] == ["b_2.jpg", "a_1.jpg"]
    assert [i["name"] for i in svc.list_images(root, "labeled", 0, 10)[1]] == ["c_3.jpg"]
    assert [i["name"] for i in svc.list_images(root, "all", 1, 1)[1]] == ["c_3.jpg"]  # хуудаслалт


def test_delete_one_and_delete_all_stay_inside_dataset(root):
    for n in ("a.jpg", "b.jpg"):
        add_image(root, n)
        svc.write_boxes(root, n, [BOX])
    keep = root / "models"
    keep.mkdir()
    (keep / "base-n.pt").write_bytes(b"w")
    svc.delete_image(root, "a.jpg")
    assert not (root / "datasets/raw/a.jpg").exists() and not (root / "datasets/labels/a.txt").exists()
    assert svc.delete_all(root) == 1
    assert svc.counts(root)["image_count"] == 0 and not list((root / "datasets/labels").iterdir())
    assert (keep / "base-n.pt").exists()  # модель устахгүй


def test_training_refuses_without_enough_labels_or_weights(root, tmp_path):
    py = tmp_path / "python"
    py.write_text("")
    script = tmp_path / "train.py"
    script.write_text("")
    with pytest.raises(svc.TrainingError, match="жин олдсонгүй"):
        svc.start_training(root, epochs=10, base="n", python=py, script=script)
    (root / "models").mkdir()
    (root / "models/base-n.pt").write_bytes(b"w")
    with pytest.raises(svc.TrainingError, match="шошглосон"):
        svc.start_training(root, epochs=10, base="n", python=py, script=script)
    with pytest.raises(svc.TrainingError):
        svc.start_training(root, epochs=1, base="n", python=py, script=script)  # epoch хязгаар
    with pytest.raises(svc.TrainingError):
        svc.start_training(root, epochs=10, base="x", python=py, script=script)


def test_dead_training_process_is_reported_failed(root):
    (root / "runs").mkdir()
    (root / "runs/state.json").write_text(json.dumps({"state": "running", "pid": 2**22 + 7, "epochs": 10, "base": "n"}))
    state = svc.read_state(root)
    assert state["state"] == "failed" and "зогссон" in state["message"]
    assert svc.read_state(root)["state"] == "failed"  # хадгалагдсан


def test_progress_is_parsed_from_ultralytics_log(root):
    (root / "runs").mkdir()
    (root / "runs/state.json").write_text(json.dumps({"state": "running", "pid": os.getpid(), "epochs": 40, "base": "n"}))
    (root / "runs/train.log").write_text("      Epoch    GPU_mem\r       3/40      0.0G  1.2 \r       4/40      0.0G  1.1 \n")
    assert svc.read_state(root)["epoch"] == 4
