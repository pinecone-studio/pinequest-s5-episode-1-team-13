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

    assert make_client(handler).detections("cam-1", [{"id": i} for i in range(80)]) is True
    assert seen["method"] == "PUT" and seen["path"] == "/internal/cameras/cam-1/detections"
    assert len(seen["body"]["people"]) == 50  # backend rejects more than 50


GOOD = {"internal_api_key": "k" * 40, "database_url": "postgresql://u:p@db:5432/x", "camera_secret_key": "f" * 44, "model_path": __file__}


def test_startup_problems():
    assert Settings(_env_file=None, **GOOD).startup_problems() == []
    assert Settings(_env_file=None, **{**GOOD, "internal_api_key": "CHANGE_ME"}).startup_problems() == ["INTERNAL_API_KEY"]
    assert "BACKEND_URL" in Settings(_env_file=None, **GOOD, backend_url="localhost").startup_problems()
    assert "MODEL_PATH (file not found)" in Settings(_env_file=None, **{**GOOD, "model_path": "nope.pt"}).startup_problems()
    assert "DATABASE_URL" in Settings(_env_file=None, **{**GOOD, "database_url": "postgresql://USER:PASSWORD@HOST:5432/DATABASE"}).startup_problems()
