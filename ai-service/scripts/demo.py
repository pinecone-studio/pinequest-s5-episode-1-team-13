"""Run the AI on a photo or a video file and save a copy with boxes drawn on it.

Your backup for the pitch: no camera, backend or database needed — only the model.

    python -m scripts.demo factory.jpg                  # -> factory_demo.jpg
    python -m scripts.demo walk.mp4                     # -> walk_demo.mp4 + a summary
    python -m scripts.demo walk.mp4 --office --max-seconds 20

Colours: green = OK, red = violation, grey = can't tell (UNKNOWN).
For videos it also counts violations with the same rules as the live system (2 s to confirm, 60 s cooldown).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

from app.detection.ppe import analyse
from app.detection.types import PersonResult
from app.violations.rules import ViolationRules

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
GREEN, RED, GREY, WHITE = (60, 180, 75), (40, 40, 230), (150, 150, 150), (255, 255, 255)


def colour(person: PersonResult) -> tuple[int, int, int]:
    if person.violation:
        return RED
    if person.helmet == "UNKNOWN" and person.uniform == "UNKNOWN":
        return GREY
    return GREEN


def label(person: PersonResult) -> str:
    parts = [f"#{person.id}" if person.id is not None else "?"]
    if person.helmet_required or person.helmet != "UNKNOWN":
        parts.append(f"helmet:{person.helmet}")
    parts.append(f"uniform:{person.uniform}")
    return " ".join(parts)


def draw(frame: np.ndarray, people: list[PersonResult]) -> np.ndarray:
    out = frame.copy()
    thick = max(2, out.shape[1] // 500)
    scale = max(0.45, out.shape[1] / 1800)
    for p in people:
        c = colour(p)
        x1, y1, x2, y2 = (int(v) for v in p.box)
        cv2.rectangle(out, (x1, y1), (x2, y2), c, thick)
        if p.helmet_box:
            hx1, hy1, hx2, hy2 = (int(v) for v in p.helmet_box)
            cv2.rectangle(out, (hx1, hy1), (hx2, hy2), RED if p.helmet == "NO" else GREEN, max(1, thick - 1))
        text = label(p)
        (tw, th), base = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
        ty = max(y1, th + base + 4)
        cv2.rectangle(out, (x1, ty - th - base - 4), (x1 + tw + 6, ty), c, -1)
        cv2.putText(out, text, (x1 + 3, ty - base - 2), cv2.FONT_HERSHEY_SIMPLEX, scale, WHITE, 1, cv2.LINE_AA)
    return out


def demo_image(path: Path, out: Path, detect, helmet_required: bool, no_conf: float = 0.0) -> list[PersonResult]:
    frame = cv2.imread(str(path))
    if frame is None:
        raise ValueError(f"Cannot read image: {path}")
    people = analyse(detect(frame), helmet_required=helmet_required, no_conf=no_conf)
    cv2.imwrite(str(out), draw(frame, people))
    return people


class VideoOut:
    """H.264 with ffmpeg when installed (plays everywhere), otherwise OpenCV's mp4v."""

    def __init__(self, path: Path, fps: float, size: tuple[int, int]) -> None:
        width, height = size
        self._proc = None
        self._writer = None
        if shutil.which("ffmpeg"):
            cmd = ["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{width}x{height}",
                   "-r", f"{fps:.3f}", "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path)]  # fmt: skip
            self._proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        else:
            self._writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, size)

    def write(self, frame: np.ndarray) -> None:
        if self._proc is not None:
            self._proc.stdin.write(frame.tobytes())
        else:
            self._writer.write(frame)

    def close(self) -> None:
        if self._proc is not None:
            self._proc.stdin.close()
            self._proc.wait()
        else:
            self._writer.release()


def demo_video(path: Path, out: Path, detect, helmet_required: bool, max_seconds: float | None = None, no_conf: float = 0.0) -> dict:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {path}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    fps = fps if 1 <= fps <= 120 else 25.0
    rules = ViolationRules(confirm_seconds=2, cooldown_seconds=60)
    writer = None
    frames, ids, saved = 0, set(), Counter()
    try:
        while True:
            ok, frame = cap.read()
            if not ok or (max_seconds is not None and frames / fps >= max_seconds):
                break
            people = analyse(detect(frame), helmet_required=helmet_required, no_conf=no_conf)
            ids.update(p.id for p in people if p.id is not None)
            for vtype, _ in rules.update(people, frames / fps):
                saved[vtype] += 1
            if writer is None:
                writer = VideoOut(out, fps, (frame.shape[1], frame.shape[0]))
            writer.write(draw(frame, people))
            frames += 1
    finally:
        cap.release()
        if writer is not None:
            writer.close()
    return {"frames": frames, "seconds": round(frames / fps, 1), "people": len(ids), "violations": dict(saved)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run PPE detection on a photo or video file")
    parser.add_argument("file", type=Path)
    parser.add_argument("--out", type=Path, help="output file (default: <name>_demo.<ext>)")
    parser.add_argument("--model", type=Path, help="model file (default: MODEL_PATH from .env)")
    parser.add_argument("--mapping", help="CLASS_MAPPING (default: from .env)")
    parser.add_argument("--conf", type=float, default=0.35)
    parser.add_argument("--office", action="store_true", help="OFFICE zone: helmet not required")
    parser.add_argument("--max-seconds", type=float, help="only the first N seconds of a video")
    args = parser.parse_args(argv)

    if not args.file.is_file():
        print(f"File not found: {args.file}", file=sys.stderr)
        return 1
    is_image = args.file.suffix.lower() in IMAGE_EXT
    out = args.out or args.file.with_name(f"{args.file.stem}_demo{args.file.suffix if is_image else '.mp4'}")

    from app.config import get_settings
    from app.detection.model import Detector

    settings = get_settings()
    model = args.model or settings.resolved_model_path
    if not model.is_file():
        print(f"Model not found: {model} (set MODEL_PATH in .env or pass --model)", file=sys.stderr)
        return 1
    detect = Detector(model, settings.class_mapping if args.mapping is None else args.mapping, args.conf, settings.imgsz)
    helmet_required = not args.office

    if is_image:
        people = demo_image(args.file, out, detect, helmet_required, settings.no_conf_threshold)
        bad = sum(p.violation for p in people)
        print(f"Saved: {out}\nPeople: {len(people)} | violations: {bad}")
        for p in people:
            print(f"  {label(p)}" + ("  <- VIOLATION" if p.violation else ""))
    else:
        summary = demo_video(args.file, out, detect, helmet_required, args.max_seconds, settings.no_conf_threshold)
        print(f"Saved: {out}")
        print(f"{summary['seconds']} s, {summary['frames']} frames | different people: {summary['people']}")
        print(f"Violations the live system would save: {summary['violations'] or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
