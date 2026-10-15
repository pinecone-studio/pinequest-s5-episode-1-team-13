from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.sql.dml import Update

from scripts import rotate_camera_key as script
from scripts.rotate_camera_key import rotate_tokens


def _keys():
    return Fernet.generate_key().decode(), Fernet.generate_key().decode()


def test_rotate_tokens_reencrypts_with_new_key():
    old, new = _keys()
    tokens = {1: Fernet(old).encrypt(b"cam-pass-1").decode(), 2: Fernet(old).encrypt(b"cam-pass-2").decode()}
    rotated = rotate_tokens(tokens, old, new)
    assert {k: Fernet(new).decrypt(v.encode()) for k, v in rotated.items()} == {1: b"cam-pass-1", 2: b"cam-pass-2"}
    assert rotate_tokens(rotated, old, new).keys() == rotated.keys()  # дахин ажиллуулахад (аль хэдийн шинэ) асуудалгүй


def test_rotate_tokens_wrong_old_key_changes_nothing():
    old, new = _keys()
    other = Fernet.generate_key().decode()
    tokens = {1: Fernet(old).encrypt(b"ok").decode(), 2: Fernet(other).encrypt(b"x").decode()}
    with pytest.raises(ValueError, match="1 камерын"):
        rotate_tokens(tokens, old, new)


def test_rotate_tokens_empty():
    assert rotate_tokens({}, *_keys()) == {}


class FakeDB:
    """cameras: {id: token}. UPDATE нь commit хийгдсэн үед л cameras-д бичигдэнэ."""

    def __init__(self, cameras):
        self.cameras, self.pending, self.commits = cameras, {}, 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, stmt):
        if isinstance(stmt, Update):
            params = stmt.compile().params
            self.pending[params["id_1"]] = params["password_encrypted"]
            return None
        return SimpleNamespace(all=lambda: list(self.cameras.items()))

    def commit(self):
        self.cameras.update(self.pending)
        self.commits += 1


def _run(monkeypatch, old, new, cameras, argv):
    db = FakeDB(cameras)
    monkeypatch.setattr(script, "get_settings", lambda: SimpleNamespace(camera_secret_key=old))
    monkeypatch.setattr(script, "new_session", lambda: db)
    monkeypatch.setenv("NEW_CAMERA_SECRET_KEY", new)
    return script.main(argv), db


def test_main_dry_run_and_rotate(monkeypatch, capsys):
    old, new = _keys()
    cameras = {1: Fernet(old).encrypt(b"pw").decode()}
    before = dict(cameras)

    code, db = _run(monkeypatch, old, new, cameras, ["--dry-run"])
    assert (code, db.commits, cameras) == (0, 0, before)

    code, db = _run(monkeypatch, old, new, cameras, [])
    assert (code, db.commits) == (0, 1)
    assert Fernet(new).decrypt(cameras[1].encode()) == b"pw"
    out = capsys.readouterr().out
    assert old not in out and new not in out  # түлхүүрийг хэвлэхгүй


def test_main_rejects_bad_or_same_key_and_wrong_old_key(monkeypatch):
    old, new = _keys()
    assert _run(monkeypatch, old, "not-a-key", {}, [])[0] == 2
    assert _run(monkeypatch, old, old, {}, [])[0] == 2
    cameras = {1: Fernet(Fernet.generate_key()).encrypt(b"pw").decode()}
    before = dict(cameras)
    code, db = _run(monkeypatch, old, new, cameras, [])
    assert (code, db.commits, cameras) == (1, 0, before)
