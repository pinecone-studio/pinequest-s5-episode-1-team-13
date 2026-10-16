import httpx
import numpy as np

from app.cameras.models import CameraInfo
from app.detection.types import PersonResult
from app.storage import SnapshotStorage, snapshot_path
from app.violations.reporter import ViolationReporter
from app.violations.rules import NO_HELMET, NO_WORK_UNIFORM, ViolationRules
from app.violations.snapshot import make_snapshot


def bare(pid=1, helmet_required=True, uniform="YES"):
    return PersonResult(id=pid, box=(10, 10, 60, 160), conf=0.9, helmet="NO", uniform=uniform, helmet_conf=0.8,
                        helmet_box=(20, 5, 50, 35), helmet_required=helmet_required, violation=True)  # fmt: skip


def test_needs_confirm_time_then_reports_once():
    rules = ViolationRules(confirm_seconds=2, cooldown_seconds=60)
    assert rules.update([bare()], 0.0) == []
    assert rules.update([bare()], 1.0) == []
    [(vtype, person)] = rules.update([bare()], 2.0)
    assert vtype == NO_HELMET and person.id == 1
    assert rules.update([bare()], 3.0) == []  # cooldown
    assert rules.update([bare()], 30.0) == []


def test_one_violation_per_visit():
    rules = ViolationRules(confirm_seconds=0, cooldown_seconds=10)
    assert len(rules.update([bare()], 0.0)) == 1
    for t in range(1, 300):  # stays 5 minutes without a helmet: still only one
        assert rules.update([bare()], float(t)) == []


def test_short_gap_is_the_same_visit_long_gap_is_a_new_one():
    rules = ViolationRules(confirm_seconds=0, cooldown_seconds=10)
    assert len(rules.update([bare()], 0.0)) == 1
    assert rules.update([bare()], 6.0) == []  # missed for 6 s (someone walked in front): same visit
    assert rules.update([], 7.0) == []
    assert len(rules.update([bare()], 30.0)) == 1  # gone for 24 s, came back: new visit


def test_new_visit_still_waits_for_the_cooldown():
    rules = ViolationRules(confirm_seconds=0, cooldown_seconds=60)
    assert len(rules.update([bare()], 0.0)) == 1
    assert rules.update([bare()], 20.0) == []  # left at 0 s, back at 20 s: new visit, but cooldown not over
    assert len(rules.update([bare()], 61.0)) == 1


def test_repeat_for_very_long_visits():
    rules = ViolationRules(confirm_seconds=0, cooldown_seconds=10, repeat_seconds=100)
    assert len(rules.update([bare()], 0.0)) == 1
    assert sum(len(rules.update([bare()], float(t))) for t in range(1, 100)) == 0
    assert len(rules.update([bare()], 100.0)) == 1


def test_new_tracker_id_in_the_same_place_is_the_same_person():
    rules = ViolationRules(confirm_seconds=0, cooldown_seconds=60)
    assert len(rules.update([bare(pid=1)], 0.0)) == 1
    moved = PersonResult(id=2, box=(14, 12, 64, 162), conf=0.9, helmet="NO", uniform="YES", helmet_conf=0.8, helmet_required=True)
    assert rules.update([moved], 2.0) == []  # tracker lost #1 and called it #2: not saved twice
    far = PersonResult(id=3, box=(300, 10, 350, 160), conf=0.9, helmet="NO", uniform="YES", helmet_conf=0.8, helmet_required=True)
    assert len(rules.update([moved, far], 3.0)) == 1  # a real second person elsewhere is saved


def test_two_problems_of_one_person_are_two_violations_once_each():
    rules = ViolationRules(confirm_seconds=0, cooldown_seconds=60)
    both = bare(uniform="NO")
    assert sorted(v for v, _ in rules.update([both], 0.0)) == [NO_HELMET, NO_WORK_UNIFORM]
    assert rules.update([both], 5.0) == []


def test_one_frame_glitch_is_ignored():
    rules = ViolationRules(confirm_seconds=2, cooldown_seconds=60)
    rules.update([bare()], 0.0)
    assert rules.update([bare()], 5.0) == []  # gap too long: timer restarted, not confirmed


def test_office_helmet_and_both_types():
    rules = ViolationRules(confirm_seconds=0, cooldown_seconds=60)
    assert rules.update([bare(helmet_required=False)], 0.0) == []
    found = rules.update([bare(pid=2, uniform="NO")], 1.0)
    assert sorted(v for v, _ in found) == [NO_HELMET, NO_WORK_UNIFORM]


def test_snapshot_is_jpeg():
    data = make_snapshot(np.zeros((200, 100, 3), dtype=np.uint8), bare(), NO_HELMET)
    assert data[:3] == b"\xff\xd8\xff"


def test_storage_upload_request():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"], seen["auth"], seen["type"] = str(request.url), request.headers["Authorization"], request.headers["Content-Type"]
        return httpx.Response(200, json={"Key": "x"})

    storage = SnapshotStorage("https://abc.supabase.co", "service-key", "violation-snapshots", transport=httpx.MockTransport(handler))
    path = snapshot_path("cam-1")
    assert storage.upload(path, b"jpg") is True
    assert seen["url"] == f"https://abc.supabase.co/storage/v1/object/violation-snapshots/{path}"
    assert seen["auth"] == "Bearer service-key" and seen["type"] == "image/jpeg"
    assert SnapshotStorage("https://YOUR_PROJECT.supabase.co", "k", "b").enabled is False


class FakeDB:
    def __init__(self):
        self.calls = []

    def fetch(self, sql, params):
        self.calls.append(params)
        return [("viol-1",)]


class FakeStorage:
    def __init__(self, ok):
        self.ok = ok

    def upload(self, path, data):
        return self.ok


class FakeClient:
    def __init__(self):
        self.created = []

    def violation_created(self, vid):
        self.created.append(vid)


CAM = CameraInfo("cam-1", "Gate", "DAHUA", "1.1.1.1", 554, "u", "p", 1, 0, 0, False, True, "FACTORY")


def test_reporter_saves_row_and_notifies():
    db, client = FakeDB(), FakeClient()
    reporter = ViolationReporter(db, FakeStorage(ok=True), client)
    vid = reporter._save(CAM, np.zeros((200, 100, 3), dtype=np.uint8), bare(pid=7), NO_HELMET)
    vtype, person_id, conf, path, camera_id = db.calls[0]
    assert vid == "viol-1" and client.created == ["viol-1"]
    assert (vtype, person_id, conf, camera_id) == ("NO_HELMET", "7", 0.8, "cam-1") and path.startswith("cam-1/")
    reporter.close()


def test_reporter_without_picture_still_saves():
    db = FakeDB()
    reporter = ViolationReporter(db, FakeStorage(ok=False), FakeClient())
    reporter._save(CAM, np.zeros((200, 100, 3), dtype=np.uint8), bare(), NO_HELMET)
    assert db.calls[0][3] is None
    reporter.close()
