"""Хүн бүрийн хайчилбар дээр PPE модель сургах өгөгдөл бэлтгэнэ.

Яагаад: бодит шинжилгээ 2 шаттай. (1) COCO yolo26 хүнийг олно, (2) хүн бүрийг хайчилж томруулаад PPE модель каск / каскгүй /
ажлын хувцас / ажлын хувцасгүй гэж дүгнэнэ. Тиймээс PPE моделийг мөн л ХҮНИЙ ХАЙЧИЛБАР дээр (бодит шинжилгээтэй ижил геометр,
ижил масштаб) сургана; бүтэн frame дээр биш.

- Хүний хайрцгийг шошгоос биш бодит шинжилгээнд ашиглах хүн ологчоор (person_detector) авна => сургалт, шинжилгээний тархалт ижил.
- Нэг хүнээс хэд хэдэн хувилбар: 0 = үндсэн хайчилбар, 1.. = margin өөрчилсөн + хол байгааг дуурайлгаж (бууруулаад дахин томруулсан).
- Хайчилбар доторх PPE хайрцгийг хайчилбарын координатад хөрвүүлнэ. Хүнд хамаарахгүй (шүүгээн дээрх, гарт барьсан) каск орохгүй.
- Зургийг нэр, цагаар нь дараалуулан блокоор train/val/test болгоно (dataset_split.split), нэг зургийн бүх хайчилбар нэг хэсэгт.
"""

from __future__ import annotations

import random
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import dataset_split as ds  # noqa: E402
from person_crops import MARGIN_X, MARGIN_Y, MIN_PERSON_PX, crop_region, scale_for  # noqa: E402

PPE_CLASSES = ("helmet", "no_helmet", "work_uniform", "no_work_uniform")
SRC_TO_NEW = {1: 0, 2: 1, 3: 2, 4: 3}  # шошгоны файлын id (dataset_split.CLASSES) -> PPE моделийн id
FAR_PERSON_PX = (90, 240)  # хол байгааг дуурайлгах: хүний үзэгдэх өндөр (px)

PersonDetectorFn = Callable[[Path], list[tuple[float, float, float, float]]]  # зураг -> нормчилсон (x1,y1,x2,y2)


def read_labels(label_file: Path) -> tuple[list[tuple[int, float, float, float, float]], list[tuple[float, float, float, float]]]:
    """(PPE хайрцгууд [(шинэ id, x1,y1,x2,y2)], шошгонд байгаа хүний хайрцгууд) — нормчилсон."""
    ppe, persons = [], []
    for line in label_file.read_text().splitlines():
        p = line.split()
        if len(p) < 5 or not p[0].isdigit():
            continue
        cid, cx, cy, w, h = int(p[0]), *map(float, p[1:5])
        box = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
        if cid in SRC_TO_NEW:
            ppe.append((SRC_TO_NEW[cid], *box))
        elif cid == 0:
            persons.append(box)
    return ppe, persons


def _degrade(crop: np.ndarray, factor: float, rng: random.Random) -> np.ndarray:
    """Хүнийг холоос авсан мэт: багасгаад (мэдээлэл алдагдана), JPEG шахалт нэмнэ."""
    h, w = crop.shape[:2]
    small = cv2.resize(crop, (max(8, int(w * factor)), max(8, int(h * factor))), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, rng.randint(55, 90)])
    return cv2.imdecode(buf, cv2.IMREAD_COLOR) if ok else small


def crop_one(im: np.ndarray, person_px: tuple[float, float, float, float], ppe: list, variant: int, rng: random.Random):
    """(зураг, шошгоны мөрүүд) эсвэл None. person_px = (x1,y1,x2,y2) пиксел."""
    height, width = im.shape[:2]
    x1, y1, x2, y2 = person_px
    if y2 - y1 < MIN_PERSON_PX or x2 - x1 < 8:
        return None
    mx, my = (MARGIN_X, MARGIN_Y) if variant == 0 else (MARGIN_X * rng.uniform(0.6, 1.4), MARGIN_Y * rng.uniform(0.6, 1.4))
    cx1, cy1, cx2, cy2 = crop_region(x1, y1, x2, y2, width, height, mx, my)
    crop = im[cy1:cy2, cx1:cx2]
    cw, ch = crop.shape[1], crop.shape[0]
    if cw < 16 or ch < 16:
        return None
    if variant >= 1:
        target = rng.uniform(*FAR_PERSON_PX)
        factor = target / max(1.0, y2 - y1)
        if factor < 1.0:
            crop = _degrade(crop, factor, rng)
    k = scale_for(cw, ch)
    fw, fh = max(8, round(cw * k)), max(8, round(ch * k))
    out = cv2.resize(crop, (fw, fh), interpolation=cv2.INTER_CUBIC if k > 1 else cv2.INTER_AREA)

    lines = []
    for cid, bx1, by1, bx2, by2 in ppe:
        b = (bx1 * width, by1 * height, bx2 * width, by2 * height)
        mxc, myc = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        if not (x1 <= mxc <= x2 and y1 <= myc <= y2):
            continue  # энэ хүнд хамаарахгүй (шүүгээн дээрх каск, өөр хүн)
        ix1, iy1, ix2, iy2 = max(b[0], cx1), max(b[1], cy1), min(b[2], cx2), min(b[3], cy2)
        area = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
        if ix2 <= ix1 or iy2 <= iy1 or (ix2 - ix1) * (iy2 - iy1) < 0.5 * area:
            continue
        lines.append(f"{cid} {((ix1 + ix2) / 2 - cx1) / cw:.6f} {((iy1 + iy2) / 2 - cy1) / ch:.6f} "
                     f"{(ix2 - ix1) / cw:.6f} {(iy2 - iy1) / ch:.6f}")
    return out, lines


def build_crops(root: Path, out_dir: Path, person_detector: PersonDetectorFn, variants: int = 2, seed: int = 0) -> dict:
    stems = ds.labeled_stems(root)
    parts = ds.split(stems)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    rng = random.Random(seed)
    crops, boxes = Counter(), {}
    unmatched = no_person = 0
    for split, items in parts.items():
        (out_dir / "images" / split).mkdir(parents=True)
        (out_dir / "labels" / split).mkdir(parents=True)
        boxes[split] = Counter()
        for stem in items:
            image_path = root / "datasets" / "raw" / f"{stem}.jpg"
            im = cv2.imread(str(image_path))
            if im is None:
                continue
            height, width = im.shape[:2]
            ppe, label_persons = read_labels(root / "datasets" / "labels" / f"{stem}.txt")
            persons = list(person_detector(image_path)) or label_persons
            if not persons:
                no_person += 1
            used = 0
            for j, pb in enumerate(persons):
                px = (pb[0] * width, pb[1] * height, pb[2] * width, pb[3] * height)
                for v in range(variants):
                    res = crop_one(im, px, ppe, v, rng)
                    if res is None:
                        continue
                    img, lines = res
                    if not lines and ppe:
                        continue  # зургийн бусад хүн дээр PPE шошготой, энэ хүнд үгүй => шошголоогүй байж магадгүй, сөрөг гэж үзэхгүй
                    name = f"{stem}_p{j}_v{v}"
                    cv2.imwrite(str(out_dir / "images" / split / f"{name}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
                    (out_dir / "labels" / split / f"{name}.txt").write_text("\n".join(lines) + ("\n" if lines else ""))
                    crops[split] += 1
                    used += len(lines) if v == 0 else 0
                    for ln in lines:
                        boxes[split][PPE_CLASSES[int(ln.split()[0])]] += 1
            unmatched += max(0, len(ppe) - used)
    names = "\n".join(f"  {i}: {n}" for i, n in enumerate(PPE_CLASSES))
    (out_dir / "data.yaml").write_text(
        f"path: {out_dir.resolve()}\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n{names}\n"
    )
    return {
        "images": {k: len(v) for k, v in parts.items()},
        "crops": dict(crops),
        "boxes": {k: dict(v) for k, v in boxes.items()},
        "images_without_person": no_person,
        "ppe_boxes_without_person": unmatched,
        "data_yaml": str(out_dir / "data.yaml"),
        "missing_in_train": [c for c in PPE_CLASSES if boxes["train"][c] == 0],
    }
