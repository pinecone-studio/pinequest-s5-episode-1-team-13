"""Run a .pt model as ONNX when the AI runs on the CPU: same boxes, about 1.7x faster.

Measured on our v2 model, 443 test images, 512 px, 2 CPU cores: PyTorch 143 ms/frame, ONNX Runtime 86 ms/frame,
mAP50 0.892 vs 0.894. The .onnx file is made once and cached outside the models folder (that folder may be
read-only, e.g. mounted into the edge container). If anything fails, the .pt model is used as before.
"""

from __future__ import annotations

import logging
import shutil
import threading
from pathlib import Path

logger = logging.getLogger("ai.model")
_lock = threading.Lock()  # several cameras start at once: export only once


def cached_onnx(model_path: Path, imgsz: int, cache_dir: Path) -> Path | None:
    """Path of an ONNX copy of `model_path` (exported on first use), or None if it cannot be made."""
    if model_path.suffix.lower() != ".pt":
        return None
    stat = model_path.stat()
    target = cache_dir / f"{model_path.stem}-{stat.st_size}-{int(stat.st_mtime)}-{imgsz}.onnx"
    with _lock:
        if target.is_file():
            return target
        try:
            from ultralytics import YOLO  # noqa: PLC0415 — heavy

            work = cache_dir / f"export-{model_path.stem}-{imgsz}"
            work.mkdir(parents=True, exist_ok=True)
            copy = work / model_path.name  # export writes next to the .pt: use a writable copy
            shutil.copy2(model_path, copy)
            logger.info("Making a faster ONNX copy of %s for the CPU (once, ~10 s)...", model_path.name)
            exported = Path(YOLO(str(copy), task="detect").export(format="onnx", imgsz=imgsz, dynamic=False, simplify=False))
            shutil.move(str(exported), target)
            shutil.rmtree(work, ignore_errors=True)
            return target
        except Exception as exc:  # noqa: BLE001 — never block the AI: fall back to the .pt model
            logger.warning("Could not make an ONNX copy (%s): using the .pt model", type(exc).__name__)
            return None
