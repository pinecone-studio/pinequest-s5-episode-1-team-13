from pathlib import Path
from types import SimpleNamespace

import pytest

from app.detection.device import pick_device

PT, ONNX = Path("ppe.pt"), Path("ppe.onnx")


def fake_torch(cuda=False, mps=False):
    return SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: cuda), backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: mps)))


def test_auto_picks_fastest():
    assert pick_device("auto", PT, fake_torch(cuda=True, mps=True)) == "cuda:0"
    assert pick_device("auto", PT, fake_torch(mps=True)) == "mps"  # M-chip Mac
    assert pick_device("AUTO", PT, fake_torch()) == "cpu"


def test_onnx_never_uses_apple_gpu():
    assert pick_device("auto", ONNX, fake_torch(mps=True)) == "cpu"
    assert pick_device("mps", ONNX, fake_torch(mps=True)) == "cpu"


def test_asking_for_missing_gpu_is_a_clear_error():
    with pytest.raises(ValueError, match="cuda"):
        pick_device("cuda", PT, fake_torch())
    with pytest.raises(ValueError, match="M-chip"):
        pick_device("mps", PT, fake_torch())
    with pytest.raises(ValueError, match="DEVICE must be"):
        pick_device("gpu", PT, fake_torch())


def test_old_torch_without_mps():
    old = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False), backends=SimpleNamespace())
    assert pick_device("auto", PT, old) == "cpu"
