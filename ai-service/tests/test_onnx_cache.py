from pathlib import Path

from app.detection import onnx_cache


def test_only_pt_models(tmp_path):
    f = tmp_path / "m.onnx"
    f.write_bytes(b"x")
    assert onnx_cache.cached_onnx(f, 512, tmp_path / "cache") is None


def test_reuses_cached_file(tmp_path):
    f = tmp_path / "m.pt"
    f.write_bytes(b"x")
    st = f.stat()
    cache = tmp_path / "cache"
    cache.mkdir()
    ready = cache / f"m-{st.st_size}-{int(st.st_mtime)}-512.onnx"
    ready.write_bytes(b"onnx")
    assert onnx_cache.cached_onnx(f, 512, cache) == ready


def test_export_failure_falls_back(tmp_path):
    f = tmp_path / "broken.pt"
    f.write_bytes(b"not a model")
    assert onnx_cache.cached_onnx(f, 512, tmp_path / "cache") is None
    assert isinstance(tmp_path, Path)
