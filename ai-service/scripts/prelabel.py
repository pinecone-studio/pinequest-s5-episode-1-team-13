"""Turn photos and videos into training pictures, pre-labelled by an AI model, keeping the HARD ones.

    python -m scripts.prelabel ~/Documents/ppe-photos --model ppe-public.pt \\
        --mapping "Worker:person,Hard_hat:helmet,No-Helmet:no_helmet,Vest:work_uniform,No-Vest:no_work_uniform"

    python -m scripts.prelabel walk.mp4 --every 0.5 --only-hard

Saves into the same folders the web Training page reads (DATASET_DIR, default ../training):
    datasets/raw/<name>.jpg           the picture
    datasets/labels_auto/<name>.txt   the model's guess (YOLO format) — you correct it on the Training page

"Hard" = the model is unsure about something (a box with a score between --hard-low and --hard-high).
Labelling those teaches the model the most; easy pictures it already gets right teach it little.
Near-duplicate video frames (almost nothing changed) are skipped.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from app.dataset.collector import _write_atomic, yolo_lines
from app.detection.motion import changed_fraction, small_grey
from app.detection.types import Detection

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
VIDEO_EXT = {".mp4", ".mov", ".avi", ".mkv", ".m4v"}
DUPLICATE_CHANGE = 0.02  # video frames with less than 2 % change since the last kept frame are skipped


@dataclass
class Result:
    seen: int = 0
    saved: int = 0
    hard: int = 0
    skipped_duplicate: int = 0
    skipped_easy: int = 0
    skipped_existing: int = 0


def is_hard(detections: list[Detection], low: float, high: float) -> bool:
    return any(low <= d.conf < high for d in detections)


def stem_for(path: Path, index: int) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", path.stem).strip("-")[:60] or "img"
    return f"{slug}_{index:05d}"


def frames_from(path: Path, every_seconds: float) -> Iterator[tuple[int, np.ndarray]]:
    """(index, frame) for an image (index 0) or every N seconds of a video."""
    if path.suffix.lower() in IMAGE_EXT:
        frame = cv2.imread(str(path))
        if frame is not None:
            yield 0, frame
        return
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    step = max(1, round((fps if 1 <= fps <= 120 else 25.0) * every_seconds))
    index = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if index % step == 0:
                yield index, frame
            index += 1
    finally:
        cap.release()


def collect_files(inputs: list[Path]) -> list[Path]:
    files = []
    for item in inputs:
        if item.is_dir():
            files += sorted(p for p in item.rglob("*") if p.suffix.lower() in IMAGE_EXT | VIDEO_EXT)
        elif item.suffix.lower() in IMAGE_EXT | VIDEO_EXT:
            files.append(item)
    return files


def prelabel(
    files: list[Path],
    detect: Callable[[np.ndarray], list[Detection]],
    dataset_root: Path,
    every_seconds: float = 1.0,
    only_hard: bool = False,
    low: float = 0.3,
    high: float = 0.6,
) -> Result:
    raw, auto = dataset_root / "datasets" / "raw", dataset_root / "datasets" / "labels_auto"
    raw.mkdir(parents=True, exist_ok=True)
    auto.mkdir(parents=True, exist_ok=True)
    result = Result()
    for path in files:
        last_kept = None
        for index, frame in frames_from(path, every_seconds):
            result.seen += 1
            grey = small_grey(frame)
            if last_kept is not None and changed_fraction(last_kept, grey) < DUPLICATE_CHANGE:
                result.skipped_duplicate += 1
                continue
            stem = stem_for(path, index)
            if (raw / f"{stem}.jpg").exists():
                result.skipped_existing += 1
                continue
            detections = detect(frame)
            hard = is_hard(detections, low, high)
            if only_hard and not hard:
                result.skipped_easy += 1
                continue
            ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
            if not ok:
                continue
            lines = yolo_lines(detections, frame.shape[1], frame.shape[0])
            _write_atomic(auto / f"{stem}.txt", ("\n".join(lines) + ("\n" if lines else "")).encode())
            _write_atomic(raw / f"{stem}.jpg", jpg.tobytes())  # picture last, like the live collector
            last_kept = grey
            result.saved += 1
            result.hard += hard
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pre-label photos/videos for the Training page")
    parser.add_argument("inputs", nargs="+", type=Path, help="photos, videos or folders")
    parser.add_argument("--model", type=Path, help="model file (default: MODEL_PATH from .env)")
    parser.add_argument("--mapping", help="CLASS_MAPPING for this model (default: from .env)")
    parser.add_argument("--out", type=Path, help="training folder (default: DATASET_DIR from .env)")
    parser.add_argument("--every", type=float, default=1.0, help="video: one frame every N seconds (default 1)")
    parser.add_argument("--only-hard", action="store_true", help="keep only pictures the model is unsure about")
    parser.add_argument("--hard-low", type=float, default=0.3)
    parser.add_argument("--hard-high", type=float, default=0.6)
    args = parser.parse_args(argv)

    files = collect_files(args.inputs)
    if not files:
        print("No photos or videos found.", file=sys.stderr)
        return 1

    from app.config import get_settings
    from app.detection.model import Detector

    settings = get_settings()
    model = args.model or settings.resolved_model_path
    if not model.is_file():
        print(f"Model not found: {model}", file=sys.stderr)
        return 1
    mapping = settings.class_mapping if args.mapping is None else args.mapping
    # Low confidence on purpose: we WANT the unsure boxes, they are what makes a picture "hard"
    detect = Detector(model, mapping, conf=min(0.25, args.hard_low), imgsz=settings.imgsz, device=settings.device)
    root = args.out or settings.resolved_dataset_dir

    r = prelabel(files, detect, root, args.every, args.only_hard, args.hard_low, args.hard_high)
    print(f"Files: {len(files)} | frames looked at: {r.seen}")
    print(f"Saved: {r.saved} (hard: {r.hard}) -> {root / 'datasets'}")
    print(f"Skipped: {r.skipped_duplicate} near-duplicates, {r.skipped_easy} easy, {r.skipped_existing} already there")
    print("Next: open the web Training page, check the boxes, fix mistakes, then train.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
