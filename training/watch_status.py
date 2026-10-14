"""training/watch.sh-ийн тусламж: сургалтын төлөвийг нэг удаа хэвлэнэ."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent

try:
    s = json.loads((ROOT / "runs" / "state.json").read_text())
    print(f"төлөв: {s.get('state')} | epoch: {s.get('epochs')} | суурь: {s.get('base')}")
    if s.get("message"):
        print("мессеж:", s["message"])
    m = s.get("metrics")
    if m:
        print(f"\nTEST үнэлгээ: mAP50={m['map50']}  mAP50-95={m['map50_95']}")
        for c, v in m["per_class"].items():
            print(f"  {c:16s} нарийвчлал={v['precision']}  илрүүлэлт={v['recall']}  mAP50={v['map50']}")
        if s.get("model_file"):
            print("\nМодель:", s["model_file"])
except Exception as exc:
    print("төлөв уншиж чадсангүй:", exc)

log = ROOT / "runs" / "train.log"
if log.is_file():
    tail = log.read_bytes()[-6000:].decode("utf-8", errors="replace").replace("\r", "\n")
    rows = [l for l in tail.splitlines() if re.match(r"^\s*\d+/\d+\s", l)]
    if rows:
        print("\n" + rows[-1][:100])

csv = ROOT / "runs" / "run" / "results.csv"
if csv.is_file():
    print("\nepoch, секунд, val_mAP50, val_mAP50-95")
    for line in csv.read_text().splitlines()[-12:]:
        p = line.split(",")
        print(", ".join(p[i] for i in (0, 1, 7, 8) if i < len(p)))
