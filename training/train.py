#!/usr/bin/env python3
"""Шошглосон зургаар PPE модель сургана → models/ppe-trained-<цаг>.onnx

Ихэвчлэн dashboard → Сургалт → «Сургах» товчоор ажиллана (backend дуудна). Гараар:

    cd training && python train.py --epochs 40 --base models/base-n.pt

Нууцлал: ultralytics-ийн анонимоор статистик илгээх (sync) унтраалттай, дутуу сан автоматаар суулгахгүй,
суурь жин локал файл байх ёстой (интернэтээс юу ч татахгүй).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("YOLO_AUTOINSTALL", "False")

from crops import build_crops  # noqa: E402

STATE = ROOT / "runs" / "state.json"


def update_state(**fields) -> None:
    try:
        state = json.loads(STATE.read_text()) if STATE.is_file() else {}
    except ValueError:
        state = {}
    state.update(fields)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False))
    tmp.replace(STATE)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def pick_device(requested: str) -> str:
    if requested != "auto":
        return requested
    import torch

    if torch.cuda.is_available():
        return "0"
    return "mps" if torch.backends.mps.is_available() else "cpu"


def coco_person_detector(conf: float = 0.30, imgsz: int = 960):
    """Бодит шинжилгээний 1-р шаттай ЯГ ИЖИЛ хүн ологч (COCO yolo26, models/base-n.pt). Нормчилсон (x1,y1,x2,y2) буцаана."""
    import cv2
    from person_detector import PersonDetector

    weights = ROOT / "models" / "base-n.pt"
    if not weights.is_file():
        raise SystemExit(f"Хүн олох модель олдсонгүй: {weights}")
    det = PersonDetector(weights, conf, imgsz, device="cpu")  # сургалтын GPU-г өрсөлдөхгүйн тулд CPU
    det.load()

    def detect(image: Path) -> list[tuple[float, float, float, float]]:
        im = cv2.imread(str(image))
        h, w = im.shape[:2]
        return [(x1 / w, y1 / h, x2 / w, y2 / h) for x1, y1, x2, y2, _ in det.detect(im)]

    return detect


def evaluate(model_path: Path, data_yaml: str, device: str, imgsz: int) -> dict:
    from ultralytics import YOLO

    m = YOLO(str(model_path)).val(data=data_yaml, split="test", imgsz=imgsz, device=device, plots=False, verbose=False)
    per_class = {}
    for i, cls_idx in enumerate(m.box.ap_class_index):
        per_class[m.names[int(cls_idx)]] = {
            "precision": round(float(m.box.p[i]), 3), "recall": round(float(m.box.r[i]), 3), "map50": round(float(m.box.ap50[i]), 3),
        }
    return {"map50": round(float(m.box.map50), 3), "map50_95": round(float(m.box.map), 3), "per_class": per_class}


def run(args: argparse.Namespace) -> None:
    from ultralytics import YOLO, settings

    settings.update({"sync": False})  # анонимоор ч гэсэн статистик илгээхгүй
    base = Path(args.base)
    if not base.is_file():
        raise SystemExit(f"Суурь жин олдсонгүй: {base}")

    summary = build_crops(ROOT, ROOT / "runs" / "dataset", person_detector=coco_person_detector())
    print(f"Өгөгдөл: зураг {summary['images']} -> хүний хайчилбар {summary['crops']} | хайрцаг (train): {summary['boxes']['train']}", flush=True)
    if summary["ppe_boxes_without_person"]:
        print(f"АНХААР: {summary['ppe_boxes_without_person']} PPE хайрцаг хүнд хамаарсангүй (хүн олдсонгүй эсвэл хүнээс гадна)", flush=True)
    if summary["missing_in_train"]:
        print(f"АНХААР: train-д эдгээр ангилал огт байхгүй (сурахгүй): {', '.join(summary['missing_in_train'])}", flush=True)

    device = pick_device(args.device)
    print(f"Төхөөрөмж: {device} | суурь: {base.name} | epoch: {args.epochs}", flush=True)
    model = YOLO(str(base))
    model.train(
        data=summary["data_yaml"], epochs=args.epochs, imgsz=args.imgsz, batch=args.batch, device=device,
        project=str(ROOT / "runs"), name="run", exist_ok=True, patience=max(15, args.epochs // 3), workers=2, plots=False, amp=False, seed=0,
    )

    best = ROOT / "runs" / "run" / "weights" / "best.pt"
    if not best.is_file():
        raise RuntimeError("best.pt үүссэнгүй")
    stamp = time.strftime("%Y%m%d_%H%M")
    (ROOT / "models").mkdir(exist_ok=True)
    kept_pt = ROOT / "models" / f"ppe-trained-{stamp}.pt"
    kept_pt.write_bytes(best.read_bytes())  # дараагийн сургалтад суурь болгож болно

    metrics = evaluate(kept_pt, summary["data_yaml"], device, args.imgsz)
    print(f"Test үнэлгээ: mAP50={metrics['map50']} mAP50-95={metrics['map50_95']}", flush=True)

    exported = Path(YOLO(str(kept_pt)).export(format="onnx", imgsz=args.imgsz, simplify=False, dynamic=False))
    onnx = ROOT / "models" / f"ppe-trained-{stamp}.onnx"
    exported.replace(onnx)
    update_state(state="done", finished_at=now(), metrics={**metrics, "images": summary["crops"]},
                 model_file=f"training/models/{onnx.name}", message="Сургалт амжилттай дууслаа")
    print(f"Бэлэн: {onnx}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", required=True, help="Суурь жин (.pt), жишээ models/base-n.pt")
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--imgsz", type=int, default=512)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--device", default="auto", help="auto | cpu | mps | 0")
    args = parser.parse_args()
    try:
        run(args)
        return 0
    except SystemExit as exc:
        update_state(state="failed", finished_at=now(), message=str(exc.code))
        raise
    except Exception as exc:  # алдааг хэрэглэгчид ойлгомжтой харуулна, дэлгэрэнгүй нь логт
        import traceback

        traceback.print_exc()
        update_state(state="failed", finished_at=now(), message=f"{type(exc).__name__}: {str(exc)[:200]}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
