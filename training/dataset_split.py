"""Шошглосон зургийг train / val / test болгон хуваана (сургалтын өмнөх бэлтгэл).

Хуваалт нь **дараалсан frame-үүдийг блок болгон** (санамсаргүй биш) хийгддэг. Нэг камерын ойролцоо хугацааны frame-үүд бараг ижил
тул санамсаргүй хуваавал ижил дүр зураг train болон test-д давхар орж, үнэлгээг хуурамч өндөр харуулна. Блокоор нь хуваавал
test нь модельд "шинэ" дүр зураг болно.
"""

from __future__ import annotations

import shutil
from collections import Counter
from pathlib import Path

CLASSES = ("person", "helmet", "no_helmet", "work_uniform", "no_work_uniform")
MIN_LABELED = 30
# 10 блокийн 7 нь train, 2 нь val, 1 нь test
BUCKETS = ("train",) * 7 + ("val",) * 2 + ("test",)


def labeled_stems(root: Path) -> list[str]:
    """datasets/raw/<x>.jpg ба datasets/labels/<x>.txt хоёулаа байгаа нэрс (нэрээр эрэмбэлсэн => камер, цагаар)."""
    raw, labels = root / "datasets" / "raw", root / "datasets" / "labels"
    if not raw.is_dir() or not labels.is_dir():
        return []
    return sorted(p.stem for p in raw.glob("*.jpg") if (labels / f"{p.stem}.txt").is_file())


def split(stems: list[str]) -> dict[str, list[str]]:
    if len(stems) < MIN_LABELED:
        raise ValueError(f"Дор хаяж {MIN_LABELED} шошглосон зураг хэрэгтэй (одоо {len(stems)})")
    size = max(1, min(20, len(stems) // 10))
    out: dict[str, list[str]] = {"train": [], "val": [], "test": []}
    for g, start in enumerate(range(0, len(stems), size)):
        out[BUCKETS[g % len(BUCKETS)]].extend(stems[start:start + size])
    return out


def count_boxes(label_file: Path) -> Counter:
    c: Counter = Counter()
    for line in label_file.read_text().splitlines():
        parts = line.split()
        if parts and parts[0].isdigit() and int(parts[0]) < len(CLASSES):
            c[CLASSES[int(parts[0])]] += 1
    return c


def boxes_without_person(label_file: Path) -> bool:
    return not any(line.split()[:1] == ["0"] for line in label_file.read_text().splitlines())


def build(root: Path, out_dir: Path, person_detector=None) -> dict:
    """out_dir-д YOLO бүтэц (images/<split>, labels/<split>) + data.yaml үүсгэнэ. Хураангуйг буцаана.

    Хүн (person) ангийг хэрэглэгч шошглодоггүй. Шошгонд хүн байхгүй зургуудад `person_detector(зургийн_зам)` (COCO модель)
    -оор олсон хүнийг нэмнэ: [(cx, cy, w, h), ...] нормчилсон. Хэрэглэгчийн шошгын файлыг өөрчлөхгүй, зөвхөн хуулбарт нэмнэ.
    """
    stems = labeled_stems(root)
    parts = split(stems)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    boxes: dict[str, Counter] = {}
    for name, items in parts.items():
        (out_dir / "images" / name).mkdir(parents=True)
        (out_dir / "labels" / name).mkdir(parents=True)
        boxes[name] = Counter()
        for stem in items:
            shutil.copy2(root / "datasets" / "raw" / f"{stem}.jpg", out_dir / "images" / name / f"{stem}.jpg")
            label = root / "datasets" / "labels" / f"{stem}.txt"
            target = out_dir / "labels" / name / f"{stem}.txt"
            shutil.copy2(label, target)
            if person_detector and boxes_without_person(label):
                extra = [f"0 {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}" for cx, cy, w, h in person_detector(root / "datasets" / "raw" / f"{stem}.jpg")]
                if extra:
                    with open(target, "a") as f:
                        f.write(("" if target.read_text().endswith("\n") or not target.read_text() else "\n") + "\n".join(extra) + "\n")
            boxes[name] += count_boxes(target)
    names = "\n".join(f"  {i}: {n}" for i, n in enumerate(CLASSES))
    (out_dir / "data.yaml").write_text(
        f"path: {out_dir.resolve()}\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n{names}\n"
    )
    return {
        "images": {k: len(v) for k, v in parts.items()},
        "boxes": {k: dict(v) for k, v in boxes.items()},
        "data_yaml": str(out_dir / "data.yaml"),
        "missing_in_train": [c for c in CLASSES if boxes["train"][c] == 0],
    }
