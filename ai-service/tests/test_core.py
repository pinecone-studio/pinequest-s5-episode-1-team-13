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


def test_startup_problems():
    assert Settings(_env_file=None, internal_api_key="CHANGE_ME").startup_problems() == ["INTERNAL_API_KEY"]
    assert Settings(_env_file=None, internal_api_key="k" * 40).startup_problems() == []
    assert "BACKEND_URL" in Settings(_env_file=None, internal_api_key="k", backend_url="localhost").startup_problems()
