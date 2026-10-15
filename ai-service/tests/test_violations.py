import httpx
import numpy as np

from app.cameras.models import CameraInfo
from app.detection.types import PersonResult
from app.storage import SnapshotStorage, snapshot_path
from app.violations.reporter import ViolationReporter
from app.violations.rules import NO_HELMET, NO_WORK_UNIFORM, ViolationRules
import cv2

from app.violations.snapshot import face_area, make_snapshot


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


def test_reports_again_after_cooldown():
    rules = ViolationRules(confirm_seconds=0, cooldown_seconds=10)
    assert len(rules.update([bare()], 0.0)) == 1
    for t in range(1, 10):
        assert rules.update([bare()], float(t)) == []
    assert len(rules.update([bare()], 10.0)) == 1


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


def noisy(h=300, w=200):
    return np.random.default_rng(0).integers(0, 255, (h, w, 3), dtype=np.uint8)


def decode(data):
    return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)


def detail(image, area):
    x1, y1, x2, y2 = area
    return float(np.abs(np.diff(image[y1:y2, x1:x2].astype(int), axis=1)).mean())


def test_bare_head_face_is_hidden_but_top_of_head_stays():
    person = PersonResult(id=1, box=(20, 20, 180, 290), conf=0.9, helmet="NO", helmet_box=(60, 25, 140, 105))
    x1, y1, x2, y2 = face_area(person)
    assert y1 > 25 + 20 and y2 >= 105  # lower part of the head box only
    frame = noisy()
    blurred = decode(make_snapshot(frame, person, NO_HELMET, quality=100))
    sharp = decode(make_snapshot(frame, person, NO_HELMET, quality=100, blur_faces=False))
    face = (x1 + 4, y1 + 4, x2 - 4, y2 - 4)
    assert detail(blurred, face) < detail(sharp, face) / 3
    top = (70, 30, 130, y1 - 4)  # hair: still there as proof of no helmet
    assert detail(blurred, top) > detail(sharp, top) / 2


def test_helmet_face_is_under_the_helmet_and_inside_the_person():
    person = PersonResult(id=1, box=(20, 20, 180, 290), conf=0.9, helmet="YES", helmet_box=(60, 25, 140, 65))
    x1, y1, x2, y2 = face_area(person)
    assert 55 <= y1 <= 65 < y2 and x1 >= 20 and x2 <= 180


def test_others_in_the_frame_are_hidden_too():
    person = PersonResult(id=1, box=(0, 0, 90, 290), conf=0.9, helmet="NO", helmet_box=(20, 5, 70, 55))
    other = PersonResult(id=2, box=(110, 10, 200, 290), conf=0.9)  # no head box: top of the body box
    frame = noisy()
    x1, y1, x2, y2 = face_area(other)
    area = (x1 + 3, y1 + 3, x2 - 3, y2 - 3)
    sharp = detail(frame, area)
    assert detail(decode(make_snapshot(frame, person, NO_HELMET, quality=100, others=[other])), area) < sharp / 3
    assert detail(decode(make_snapshot(frame, person, NO_HELMET, quality=100)), area) > sharp / 2


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
