import hashlib

from app.core import leaked_keys


def test_detects_leaked_values_by_hash(monkeypatch):
    fake = {"INTERNAL_API_KEY": {hashlib.sha256(b"old-key").hexdigest()}, "DATABASE_URL": {hashlib.sha256(b"pw1").hexdigest()}}
    monkeypatch.setattr(leaked_keys, "LEAKED_SHA256", fake)
    assert leaked_keys.leaked_names({"INTERNAL_API_KEY": "old-key", "DATABASE_URL": "postgresql://u:pw1@h:5432/db"}) == [
        "INTERNAL_API_KEY",
        "DATABASE_URL",
    ]
    assert leaked_keys.leaked_names({"INTERNAL_API_KEY": "new-key", "DATABASE_URL": "postgresql://u:pw2@h/db"}) == []
    assert leaked_keys.leaked_names({"INTERNAL_API_KEY": "", "DATABASE_URL": "postgresql://h/db", "OTHER": "old-key"}) == []


def test_settings_expose_all_checked_names():
    from app.config import Settings

    assert set(Settings().secret_values()) == set(leaked_keys.LEAKED_SHA256)
