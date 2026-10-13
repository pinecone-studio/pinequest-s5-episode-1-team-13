"""Бодит Supabase DB дээр (RUN_DB_TESTS=1). Storage-ийг fake-ээр солино."""

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.config import get_settings
from app.database.database import new_session
from app.database.models import Camera, Violation
from app.services.retention import purge_older_than

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DB_TESTS") != "1" or get_settings().startup_problems(),
    reason="set RUN_DB_TESTS=1 with a fully configured backend/.env",
)


def test_old_violations_and_their_images_are_purged_new_ones_kept():
    now = datetime.now(UTC)
    removed = []
    with new_session() as db:
        cam = Camera(name=f"pytest-ret-{uuid.uuid4().hex[:6]}", ip_address="127.0.0.1", username="u")
        db.add(cam)
        db.commit()
        old = Violation(
            camera_id=cam.id, violation_type="NO_HELMET", storage_path="violations/test/old.jpg", detected_at=now - timedelta(hours=3)
        )
        new = Violation(camera_id=cam.id, violation_type="NO_HELMET", storage_path="violations/test/new.jpg", detected_at=now)
        db.add_all([old, new])
        db.commit()
        old_id, new_id, cam_id = old.id, new.id, cam.id
    try:
        count = purge_older_than(now - timedelta(hours=1), lambda paths: removed.extend(paths))
        assert count >= 1 and "violations/test/old.jpg" in removed and "violations/test/new.jpg" not in removed
        with new_session() as db:
            assert db.get(Violation, old_id) is None and db.get(Violation, new_id) is not None
    finally:
        with new_session() as db:
            db.delete(db.get(Camera, cam_id))
            db.commit()


def test_rows_survive_when_storage_removal_fails():
    now = datetime.now(UTC)
    with new_session() as db:
        cam = Camera(name=f"pytest-ret-{uuid.uuid4().hex[:6]}", ip_address="127.0.0.1", username="u")
        db.add(cam)
        db.commit()
        v = Violation(
            camera_id=cam.id, violation_type="NO_HELMET", storage_path="violations/test/x.jpg", detected_at=now - timedelta(hours=3)
        )
        db.add(v)
        db.commit()
        vid, cam_id = v.id, cam.id

    def boom(paths):
        raise RuntimeError("storage down")

    try:
        with pytest.raises(RuntimeError):
            purge_older_than(now - timedelta(hours=1), boom)
        with new_session() as db:
            assert db.get(Violation, vid) is not None  # зураг устгагдаагүй бол мөр устахгүй
    finally:
        with new_session() as db:
            db.delete(db.get(Camera, cam_id))
            db.commit()
