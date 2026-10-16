import hashlib

from app import leaked_keys
from app.config import Settings


def test_detects_leaked_values_by_hash(monkeypatch):
    monkeypatch.setattr(leaked_keys, "LEAKED_SHA256", {"INTERNAL_API_KEY": {hashlib.sha256(b"old").hexdigest()}})
    assert leaked_keys.leaked_names({"INTERNAL_API_KEY": "old"}) == ["INTERNAL_API_KEY"]
    assert leaked_keys.leaked_names({"INTERNAL_API_KEY": "new"}) == []


def test_same_hashes_as_backend_and_names_exist():
    assert set(Settings().secret_values()) <= set(leaked_keys.LEAKED_SHA256)
