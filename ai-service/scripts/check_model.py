"""Is this model ready for our app? Prints its classes, how they map to ours, and what it can / can't detect.

    python -m scripts.check_model                         # checks MODEL_PATH from .env
    python -m scripts.check_model path/to/model.onnx      # checks another file
    python -m scripts.check_model model.pt --image test.jpg   # also runs it once on a picture

Uses CLASS_MAPPING from .env unless you pass --mapping "hardhat:helmet,...".
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from app.detection.classes import CLASSES, parse_mapping, resolve_names
from scripts.export_onnx import mapping_hint

READY, PARTIAL, NOT_USABLE = "READY", "PARTIAL", "NOT USABLE"


def check(names: dict[int, str], mapping: dict[str, str]) -> tuple[str, list[str]]:
    """(verdict, lines to print). Pure function: easy to test without a model file."""
    resolved = resolve_names(names, mapping)
    found = set(resolved.values())
    lines = ["Classes in the model:"]
    for idx, name in sorted(names.items()):
        lines.append(f"  {idx:>3}  {name:<22} -> {resolved.get(idx, '(ignored)')}")

    problems = []
    if "person" not in found:
        problems.append("No 'person' class: nobody can be checked at all.")
    helmet = {"helmet", "no_helmet"} & found
    uniform = {"work_uniform", "no_work_uniform"} & found
    if not helmet:
        problems.append("No helmet classes: helmet is always UNKNOWN (no NO_HELMET violations).")
    elif "no_helmet" not in found:
        problems.append("Only 'helmet' (no 'no_helmet'): a bare head is never reported.")
    if not uniform:
        problems.append("No uniform classes: uniform is always UNKNOWN (no NO_WORK_UNIFORM violations).")
    elif "no_work_uniform" not in found:
        problems.append("Only 'work_uniform' (no 'no_work_uniform'): missing uniforms are never reported.")

    if "person" not in found:
        verdict = NOT_USABLE
    elif "no_helmet" in found and "no_work_uniform" in found:
        verdict = READY
    elif "no_helmet" in found or "no_work_uniform" in found:
        verdict = PARTIAL
    else:
        verdict = NOT_USABLE

    if problems:
        lines += ["", "Problems:"] + [f"  - {p}" for p in problems]
    if verdict != READY and not mapping and len(found) < len(names):
        lines += ["", "If the names just differ from ours, try:", f"  {mapping_hint(names)}"]
    return verdict, lines


def run_on_image(model_path: Path, mapping_text: str, image: Path) -> list[str]:
    import cv2

    from app.detection.model import Detector
    from app.detection.ppe import analyse

    frame = cv2.imread(str(image))
    if frame is None:
        return [f"Cannot read image: {image}"]
    detections = Detector(model_path, mapping_text, conf=0.25, imgsz=640)(frame)
    counts = Counter(d.cls for d in detections)
    lines = ["", f"Test on {image.name}: " + (", ".join(f"{c}={counts[c]}" for c in CLASSES if counts[c]) or "nothing found")]
    for p in analyse(detections, helmet_required=True):
        lines.append(f"  person {p.id}: helmet={p.helmet} uniform={p.uniform}" + ("  <- VIOLATION" if p.violation else ""))
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check if a YOLO model fits the AI service")
    parser.add_argument("model", nargs="?", type=Path, help="model file (default: MODEL_PATH from .env)")
    parser.add_argument("--mapping", help="CLASS_MAPPING to test (default: from .env)")
    parser.add_argument("--image", type=Path, help="also run the model once on this picture")
    args = parser.parse_args(argv)

    from app.config import get_settings

    settings = get_settings()
    model_path = args.model or settings.resolved_model_path
    mapping_text = settings.class_mapping if args.mapping is None else args.mapping
    if not model_path.is_file():
        print(f"Model file not found: {model_path}", file=sys.stderr)
        return 1
    try:
        mapping = parse_mapping(mapping_text)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1

    from ultralytics import YOLO  # heavy import only after the cheap checks

    names = {int(k): str(v) for k, v in YOLO(str(model_path), task="detect").names.items()}
    verdict, lines = check(names, mapping)
    print(f"Model: {model_path}")
    print(f"CLASS_MAPPING: {mapping_text or '(empty)'}\n")
    print("\n".join(lines))
    if args.image:
        print("\n".join(run_on_image(model_path, mapping_text, args.image)))
    print(f"\nResult: {verdict}")
    return 0 if verdict != NOT_USABLE else 2


if __name__ == "__main__":
    sys.exit(main())
