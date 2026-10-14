"""Convert a YOLO .pt model to .onnx (faster on CPU, no PyTorch needed at run time).

Models trained on the web Training page are already .onnx (training/train.py exports them).
Use this for other models, for example a public hard-hat model you downloaded.

    python -m scripts.export_onnx path/to/model.pt              # -> path/to/model.onnx
    python -m scripts.export_onnx model.pt --imgsz 512 --out ../training/models/ppe.onnx

Then set MODEL_PATH in .env to the new file. The script prints the classes and a CLASS_MAPPING hint.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.detection.classes import CLASSES


def output_path(model: Path, out: str | None) -> Path:
    target = Path(out) if out else model.with_suffix(".onnx")
    if target.suffix != ".onnx":
        raise ValueError("--out must end with .onnx")
    return target


def mapping_hint(names: dict[int, str]) -> str:
    """Classes that already match ours map to themselves; the rest are left for the user to fill in."""
    used = [str(n) for n in names.values() if str(n).lower() in CLASSES]
    if len(used) == len(names):
        return "CLASS_MAPPING=   (empty: the model already uses our class names)"
    pairs = ",".join(f"{n}:{n.lower()}" if n.lower() in CLASSES else f"{n}:?" for n in map(str, names.values()))
    return f"CLASS_MAPPING={pairs}\n  (replace each ? with one of: {', '.join(CLASSES)}, or remove that pair to ignore the class)"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export a YOLO .pt model to ONNX")
    parser.add_argument("model", type=Path, help="the .pt file")
    parser.add_argument("--imgsz", type=int, default=640, help="input size (default 640; Training page models use 512)")
    parser.add_argument("--out", help="where to save the .onnx (default: next to the .pt)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.model.suffix != ".pt" or not args.model.is_file():
        print(f"Not a .pt file: {args.model}", file=sys.stderr)
        return 1
    try:
        target = output_path(args.model, args.out)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1

    from ultralytics import YOLO  # heavy import only when really exporting

    model = YOLO(str(args.model))
    # Static size + no simplify: same settings as training/train.py, works on every onnxruntime
    exported = Path(model.export(format="onnx", imgsz=args.imgsz, dynamic=False, simplify=False))
    target.parent.mkdir(parents=True, exist_ok=True)
    if exported.resolve() != target.resolve():
        exported.replace(target)

    print(f"Saved: {target}")
    print(f"Classes: {dict(model.names)}")
    print(mapping_hint(dict(model.names)))
    print(f"In .env:  MODEL_PATH={target}   IMGSZ={args.imgsz}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
