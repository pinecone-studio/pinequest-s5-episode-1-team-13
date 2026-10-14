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


def test_split_uses_contiguous_blocks_and_has_every_part():
    stems = [f"c_{i:04d}" for i in range(100)]
    parts = ds.split(stems)
    assert sorted(sum(parts.values(), [])) == stems                      # хэн ч алдагдаагүй, давхардаагүй
    assert all(parts[k] for k in ("train", "val", "test"))
    assert len(parts["train"]) > len(parts["val"]) > 0 and len(parts["test"]) > 0
    # дараалсан frame-үүд нэг хэсэгт байна (блокоор хуваагдсан)
    test_idx = sorted(int(s.split("_")[1]) for s in parts["test"])
    assert test_idx[:10] == list(range(test_idx[0], test_idx[0] + 10))


def test_split_is_deterministic_and_rejects_tiny_datasets():
    stems = [f"c_{i:04d}" for i in range(45)]
    assert ds.split(stems) == ds.split(list(stems))
    with pytest.raises(ValueError, match="шошглосон"):
        ds.split(stems[:29])
    parts = ds.split(stems[:30])
    assert all(parts[k] for k in parts)  # хамгийн бага хэмжээнд ч val/test хоосон биш


def test_only_images_with_confirmed_labels_are_used(tmp_path):
    make(tmp_path, 40)
    (tmp_path / "datasets/raw/zzz_unlabeled.jpg").write_bytes(b"x")          # шошгогүй => ороход болохгүй
    (tmp_path / "datasets/labels_auto").mkdir()
    (tmp_path / "datasets/labels_auto/zzz_unlabeled.txt").write_text("0 .5 .5 .1 .1\n")  # AI санал ч гэсэн
    assert "zzz_unlabeled" not in ds.labeled_stems(tmp_path) and len(ds.labeled_stems(tmp_path)) == 40


def test_build_writes_yolo_layout_and_reports_missing_classes(tmp_path):
    make(tmp_path, 40, label="0 0.5 0.5 0.4 0.8\n3 0.5 0.6 0.3 0.3\n")
    out = tmp_path / "runs" / "dataset"
    summary = ds.build(tmp_path, out)
    assert sum(summary["images"].values()) == 40
    assert summary["boxes"]["train"]["person"] == summary["images"]["train"]
    assert set(summary["missing_in_train"]) == {"helmet", "no_helmet", "no_work_uniform"}
    yaml = (out / "data.yaml").read_text()
    assert "train: images/train" in yaml and "3: work_uniform" in yaml and f"path: {out.resolve()}" in yaml
    for split in ("train", "val", "test"):
        imgs = sorted(p.stem for p in (out / "images" / split).glob("*.jpg"))
        lbls = sorted(p.stem for p in (out / "labels" / split).glob("*.txt"))
        assert imgs == lbls and imgs
    ds.build(tmp_path, out)  # дахин ажиллуулахад өмнөхийг цэвэрлэнэ


def test_person_is_added_automatically_only_when_missing(tmp_path):
    make(tmp_path, 40, label="3 0.5 0.6 0.3 0.3\n")  # зөвхөн хувцас шошглосон, хүнгүй
    (tmp_path / "datasets/labels/camA_20261009_000000.txt").write_text("3 0.5 0.6 0.3 0.3\n0 0.5 0.5 0.9 0.9\n")  # өөрийн хүнтэй
    calls = []

    def fake_person(image):
        calls.append(image.stem)
        return [(0.4, 0.5, 0.2, 0.8)]

    out = tmp_path / "runs" / "dataset"
    summary = ds.build(tmp_path, out, person_detector=fake_person)
    assert "camA_20261009_000000" not in calls and len(calls) == 39          # хүнтэй шошгонд дахин нэмэхгүй
    assert summary["boxes"]["train"]["person"] >= 1 and "person" not in summary["missing_in_train"]
    some = next((out / "labels" / "train").glob("*.txt")).read_text().splitlines()
    assert any(l.startswith("0 ") for l in some) and any(l.startswith("3 ") for l in some)
    # хэрэглэгчийн анхны шошго өөрчлөгдөөгүй
    assert (tmp_path / "datasets/labels/camA_20261009_000001.txt").read_text() == "3 0.5 0.6 0.3 0.3\n"


# ---------------- хүний хайчилбарын өгөгдөл ----------------
