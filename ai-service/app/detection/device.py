"""Which chip runs the model: Apple GPU (mps), NVIDIA GPU (cuda) or CPU.

DEVICE=auto picks the fastest one available. ONNX models run on ONNX Runtime, which has no Apple GPU
support here, so they use the CPU (ONNX on CPU is already fast).
"""

from __future__ import annotations

from pathlib import Path

CHOICES = ("auto", "mps", "cuda", "cpu")


def pick_device(requested: str, model_path: Path, torch_module=None) -> str:
    requested = requested.lower().strip()
    if requested not in CHOICES:
        raise ValueError(f"DEVICE must be one of {', '.join(CHOICES)} (got '{requested}')")
    if torch_module is None:
        import torch as torch_module  # noqa: PLC0415 — heavy, only when the model is loaded

    cuda_ok = torch_module.cuda.is_available()
    mps_ok = getattr(torch_module.backends, "mps", None) is not None and torch_module.backends.mps.is_available()
    is_onnx = model_path.suffix.lower() == ".onnx"

    if requested == "auto":
        if cuda_ok:
            return "cuda:0"
        return "mps" if mps_ok and not is_onnx else "cpu"
    if requested == "cuda":
        if not cuda_ok:
            raise ValueError("DEVICE=cuda but no NVIDIA GPU was found")
        return "cuda:0"
    if requested == "mps":
        if not mps_ok:
            raise ValueError("DEVICE=mps but the Apple GPU is not available (needs an M-chip Mac)")
        return "cpu" if is_onnx else "mps"
    return "cpu"
