"""Whole AI service in one test: fake camera -> worker -> fake model -> PPE -> rules -> reporter -> backend.

Only the outside world is fake (camera, model, database, storage). Every request the backend receives
is recorded, so we can check what the dashboard would see and in which order.
"""

import json
import threading
import time

import httpx
import numpy as np

from app.backend_client import BackendClient
from app.cameras.models import CameraInfo
from app.cameras.reader import FrameReader
from app.cameras.worker import CameraWorker
from app.config import Settings
from app.detection.pipeline import CameraAI
from app.detection.types import Detection
from app.violations.reporter import ViolationReporter
from app.violations.rules import ViolationRules

CAM = CameraInfo("11111111-2222-3333-4444-555555555555", "Gate", "DAHUA", "10.0.0.5", 554, "admin", "pw", 1, 0, 0,
                 False, True, "FACTORY")  # fmt: skip
PERSON = Detection("person", 0.9, (200, 100, 320, 400), track_id=7)
BARE_HEAD = Detection("no_helmet", 0.85, (230, 85, 290, 140))


class FakeCapture:
    def isOpened(self):
        return True

    def get(self, _):
        return 25.0

    def read(self):
        time.sleep(0.02)
        return True, np.full((480, 640, 3), 120, dtype=np.uint8)

    def release(self):
        pass


class FakeDB:
    def __init__(self):
        self.statuses, self.inserted = [], []
        self.lock = threading.Lock()

    def execute(self, sql, params):
        if "UPDATE cameras" in sql:
            with self.lock:
                self.statuses.append(params[0])

    def fetch(self, sql, params):
        with self.lock:
            self.inserted.append(params)
        return [(f"viol-{len(self.inserted)}",)]


class FakeStorage:
    def __init__(self):
        self.uploads = []

    def upload(self, path, data):
        self.uploads.append((path, data[:3]))
        return True


class Backend:
    """Records every /internal request like the real FastAPI backend would receive it."""

    def __init__(self):
        self.calls = []
        self.lock = threading.Lock()

    def __call__(self, request: httpx.Request):
        assert request.headers["X-Internal-Key"] == "k" * 40
        body = json.loads(request.content) if request.content else None
        with self.lock:
            self.calls.append((request.method, request.url.path, body))
        return httpx.Response(204)

    def paths(self, contains):
        with self.lock:
            return [c for c in self.calls if contains in c[1]]


def wait_for(check, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if check():
            return True
        time.sleep(0.02)
    return False


def test_bare_head_becomes_one_saved_violation_on_the_dashboard():
    backend, db, storage = Backend(), FakeDB(), FakeStorage()
    client = BackendClient("http://backend", "k" * 40, transport=httpx.MockTransport(backend))
    settings = Settings(_env_file=None, internal_api_key="k" * 40, publish_video=False, publish_fps=20)
    reporter = ViolationReporter(db, storage, client)
    ai = CameraAI(client, lambda: (lambda frame: [PERSON, BARE_HEAD]), detect_fps=10,
                  rules=ViolationRules(confirm_seconds=0.5, cooldown_seconds=60), reporter=reporter)  # fmt: skip

    worker = CameraWorker(CAM, settings, db, client, ai=ai)
    worker.reader = FrameReader(0, "test", open_fn=lambda _: FakeCapture())
    worker.start()
    try:
        assert wait_for(lambda: backend.paths("/violations/")), "no violation reached the backend"
        time.sleep(0.5)  # a bit more running: the cooldown must stop a second violation
    finally:
        worker.stop()
        worker.join(timeout=5)
        reporter.close()
        client.close()  # status and boxes are sent in the background: wait for them

    # 1. Camera status went CONNECTING -> STREAMING -> OFFLINE, saved in the DB and announced each time
    assert db.statuses[0] == "CONNECTING" and "STREAMING" in db.statuses and db.statuses[-1] == "OFFLINE"
    assert len(backend.paths("/status")) == len(db.statuses)

    # 2. Live boxes: normalised, with the bare head marked as a violation
    detections = backend.paths("/detections")
    assert detections
    method, path, body = detections[0]
    [person] = body["people"]
    assert method == "PUT" and path == f"/internal/cameras/{CAM.id}/detections"
    assert person["helmet"] == "NO" and person["violation"] is True and person["box"] == [0.3125, 0.2083, 0.5, 0.8333]

    # 3. Exactly one violation: snapshot uploaded, row inserted, backend told — in that order
    assert len(db.inserted) == 1 and len(storage.uploads) == 1
    vtype, person_id, confidence, storage_path, camera_id = db.inserted[0]
    assert (vtype, person_id, camera_id) == ("NO_HELMET", "7", CAM.id) and confidence == 0.85
    assert storage_path == storage.uploads[0][0] and storage.uploads[0][1] == b"\xff\xd8\xff"
    assert [c[1] for c in backend.paths("/violations/")] == ["/internal/violations/viol-1/created"]

    first_box = backend.calls.index(detections[0])
    created = backend.calls.index(backend.paths("/violations/")[0])
    assert first_box < created  # the dashboard sees the red box before the saved violation arrives


def test_ai_disabled_camera_sends_no_boxes_and_saves_nothing():
    backend, db, storage = Backend(), FakeDB(), FakeStorage()
    client = BackendClient("http://backend", "k" * 40, transport=httpx.MockTransport(backend))
    settings = Settings(_env_file=None, internal_api_key="k" * 40, publish_video=False, publish_fps=20)
    reporter = ViolationReporter(db, storage, client)
    calls = []
    ai = CameraAI(client, lambda: (lambda frame: calls.append(1) or [PERSON, BARE_HEAD]), detect_fps=10,
                  rules=ViolationRules(0, 60), reporter=reporter)  # fmt: skip

    off = CameraInfo(**{**CAM.__dict__, "ai_enabled": False})
    worker = CameraWorker(off, settings, db, client, ai=ai)
    worker.reader = FrameReader(0, "test", open_fn=lambda _: FakeCapture())
    worker.start()
    try:
        assert wait_for(lambda: "STREAMING" in db.statuses)
        time.sleep(0.4)
    finally:
        worker.stop()
        worker.join(timeout=5)
        reporter.close()
        client.close()  # status and boxes are sent in the background: wait for them

    assert calls == [] and backend.paths("/detections") == [] and db.inserted == []
