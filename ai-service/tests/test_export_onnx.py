from pathlib import Path

import pytest

from scripts.export_onnx import main, mapping_hint, output_path


def test_output_path():
    assert output_path(Path("models/hat.pt"), None) == Path("models/hat.onnx")
    assert output_path(Path("hat.pt"), "../training/models/ppe.onnx") == Path("../training/models/ppe.onnx")
    with pytest.raises(ValueError):
        output_path(Path("hat.pt"), "ppe.pt")


def test_mapping_hint():
    assert "empty" in mapping_hint({0: "person", 1: "helmet"})
    hint = mapping_hint({0: "Person", 1: "Hardhat"})
    assert "Person:person" in hint and "Hardhat:?" in hint


def test_rejects_missing_or_wrong_file(tmp_path):
    assert main([str(tmp_path / "nope.pt")]) == 1
    onnx = tmp_path / "model.onnx"
    onnx.write_bytes(b"x")
    assert main([str(onnx)]) == 1
