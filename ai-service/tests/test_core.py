import json
import threading
import time

import httpx

from app.backend_client import BackendClient
from app.config import Settings


def make_client(handler):
    return BackendClient("http://backend", "secret-key", transport=httpx.MockTransport(handler))


def test_heartbeat_sends_internal_key():
    seen = {}

    def handler(request: httpx.Request):
        seen["path"] = request.url.path
        seen["key"] = request.headers.get("X-Internal-Key")
        return httpx.Response(204)

    assert make_client(handler).heartbeat() is True
    assert seen == {"path": "/internal/heartbeat", "key": "secret-key"}


def test_backend_error_does_not_crash():
    assert make_client(lambda r: httpx.Response(401)).heartbeat() is False

    def down(request):
        raise httpx.ConnectError("down")

    assert make_client(down).heartbeat() is False


def test_detections_payload():
    seen = {}

    def handler(request: httpx.Request):
        seen["method"], seen["path"] = request.method, request.url.path
        seen["body"] = __import__("json").loads(request.content)
        return httpx.Response(204)

    client = make_client(handler)
    assert client.detections("cam-1", [{"id": i} for i in range(80)]) is True
    client.close()  # waits for the background send
    assert seen["method"] == "PUT" and seen["path"] == "/internal/cameras/cam-1/detections"
    assert len(seen["body"]["people"]) == 50  # backend rejects more than 50
    assert client.detections("cam-1", []) is False  # closed


def test_slow_backend_never_blocks_the_camera_loop_and_only_newest_boxes_are_sent():
    sent, release = [], threading.Event()

    def slow(request: httpx.Request):
        release.wait(5)  # backend hangs until released
        sent.append(json.loads(request.content)["people"])
        return httpx.Response(204)

    client = make_client(slow)
    started = time.perf_counter()
    for i in range(20):
        assert client.detections("cam-1", [{"id": i}]) is True
    assert time.perf_counter() - started < 0.5  # the camera loop did not wait for the backend
    release.set()
    client.close()
    # the first send was already in flight; everything queued behind it collapsed into the newest boxes
    assert sent[-1] == [{"id": 19}] and len(sent) <= 2


GOOD = {"internal_api_key": "k" * 40, "database_url": "postgresql://u:p@db:5432/x", "camera_secret_key": "f" * 44, "model_path": __file__}


def test_startup_problems():
    assert Settings(_env_file=None, **GOOD).startup_problems() == []
    assert Settings(_env_file=None, **{**GOOD, "internal_api_key": "CHANGE_ME"}).startup_problems() == ["INTERNAL_API_KEY"]
    assert "BACKEND_URL" in Settings(_env_file=None, **GOOD, backend_url="localhost").startup_problems()
    assert "MODEL_PATH (file not found)" in Settings(_env_file=None, **{**GOOD, "model_path": "nope.pt"}).startup_problems()
    assert "DATABASE_URL" in Settings(_env_file=None, **{**GOOD, "database_url": "postgresql://USER:PASSWORD@HOST:5432/DATABASE"}).startup_problems()


def test_every_status_change_is_sent_in_order_but_waiting_boxes_collapse():
    sent, release = [], threading.Event()

    def slow(request: httpx.Request):
        release.wait(5)
        sent.append((request.url.path, json.loads(request.content) if request.content else None))
        return httpx.Response(204)

    client = make_client(slow)
    client.detections("cam-1", [{"id": 0}])  # in flight while the rest queue up
    time.sleep(0.1)
    started = time.perf_counter()
    for i in range(1, 4):
        assert client.camera_status("cam-1") is True
        client.detections("cam-1", [{"id": i}])
    assert time.perf_counter() - started < 0.5
    release.set()
    client.close()
    paths = [p for p, _ in sent]
    assert paths.count("/internal/cameras/cam-1/status") == 3  # none dropped
    assert [b for p, b in sent if p.endswith("/detections")] == [{"people": [{"id": 0}]}, {"people": [{"id": 3}]}]
