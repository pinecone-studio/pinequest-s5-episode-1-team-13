import asyncio
import json
import logging
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from app.database.models import CameraStatus
from app.services import alerts
from app.services.alerts import Monitor, Problem, check_all, send_alert, webhook_payload, webhook_problem


@pytest.mark.parametrize(
    ("url", "post_url", "body"),
    [
        (
            "https://discord.com/api/webhooks/1/abc",
            "https://discord.com/api/webhooks/1/abc",
            {"content": "hi", "allowed_mentions": {"parse": []}},
        ),
        ("https://hooks.slack.com/services/T/B/x", "https://hooks.slack.com/services/T/B/x", {"text": "hi"}),
        ("https://api.telegram.org/bot123:abc/sendMessage?chat_id=-100", "https://api.telegram.org/bot123:abc/sendMessage", {"chat_id": "-100", "text": "hi"}),
        ("https://chat.example.com/hooks/x", "https://chat.example.com/hooks/x", {"text": "hi"}),
    ],
)
def test_webhook_payload_by_url(url, post_url, body):
    assert webhook_payload(url, "hi") == (post_url, body)


def test_webhook_payload_truncates_long_text():
    _, body = webhook_payload("https://hooks.slack.com/services/x", "a" * 5000)
    assert len(body["text"]) == alerts.MAX_TEXT


def test_webhook_problem():
    assert webhook_problem("https://discord.com/api/webhooks/1/abc") is None
    assert webhook_problem("https://api.telegram.org/bot1:x/sendMessage?chat_id=5") is None
    assert "chat_id" in webhook_problem("https://api.telegram.org/bot1:x/sendMessage")
    assert "https" in webhook_problem("http://hooks.slack.com/services/x")
    assert "https" in webhook_problem("not a url")


def _p(key):
    return Problem(key, key.upper(), "down")


def test_monitor_baseline_is_silent_and_its_recovery_too():
    m = Monitor()
    assert m.update([_p("cam")]) == []  # суурь: аль хэдийн унтарсан
    assert m.update([_p("cam")]) == []
    assert m.update([]) == []  # суурийн зүйл сэргэхэд чимээгүй
    assert m.update([_p("cam")]) == []  # дахин унтарвал ердийн журмаар (1 дэх удаа)
    assert m.update([_p("cam")]) == ["[АСУУДАЛ] CAM: down"]


def test_monitor_alerts_after_threshold_once_and_on_recovery():
    m = Monitor()
    assert m.update([]) == []
    assert m.update([_p("ai")]) == []  # 1 удаа: тасалдал байж болно
    assert m.update([_p("ai")]) == ["[АСУУДАЛ] AI: down"]
    assert m.update([_p("ai")]) == []  # давтахгүй
    assert m.update([]) == ["[СЭРГЭЛЭЭ] AI"]
    assert m.update([]) == []


def test_monitor_single_blip_resets():
    m = Monitor()
    m.update([])
    assert m.update([_p("db")]) == []
    assert m.update([]) == []
    assert m.update([_p("db")]) == []  # тоолуур дахин эхэлсэн


class FakeDB:
    def __init__(self, cameras=(), edge=None, fail=False):
        self.cameras, self.edge, self.fail = list(cameras), edge, fail

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, _stmt):
        if self.fail:
            raise ConnectionError("db down")
        return SimpleNamespace(all=lambda: self.cameras)

    def get(self, _model, _key):
        return self.edge


def _setup(monkeypatch, db, probe=True, ai_alive=True):
    monkeypatch.setattr(alerts, "new_session", lambda: db)
    monkeypatch.setattr(alerts, "get_settings", lambda: SimpleNamespace(camera_probe_enabled=probe))
    monkeypatch.setattr(alerts, "ai_heartbeat", SimpleNamespace(alive=ai_alive))


def test_check_all_db_down_reports_only_db(monkeypatch):
    _setup(monkeypatch, FakeDB(fail=True), probe=False, ai_alive=False)
    assert [p.key for p in check_all()] == ["db"]


def test_check_all_reports_ai_cameras_and_stale_edge(monkeypatch):
    bad, ok = uuid.uuid4(), uuid.uuid4()
    cameras = [(bad, "Gate 1", CameraStatus.OFFLINE), (ok, "Gate 2", CameraStatus.STREAMING)]
    edge = SimpleNamespace(value={"url": "https://media.example.com", "at": 1000.0})
    _setup(monkeypatch, FakeDB(cameras, edge), probe=False, ai_alive=False)
    problems = check_all(now=1000.0 + 181)
    assert [p.key for p in problems] == ["ai", f"camera:{bad}", "edge"]
    assert problems[1].label == "Камер 'Gate 1'" and problems[1].detail == "OFFLINE"


def test_check_all_healthy(monkeypatch):
    edge = SimpleNamespace(value={"url": "https://media.example.com", "at": 1000.0})
    _setup(monkeypatch, FakeDB([(uuid.uuid4(), "Gate", CameraStatus.ONLINE)], edge), probe=False)
    assert check_all(now=1010.0) == []
    _setup(monkeypatch, FakeDB(), probe=True)  # локал backend: edge шалгахгүй
    assert check_all() == []


@pytest.mark.parametrize("url", ["", "http://hooks.example.com/SECRET-TOKEN", "https://api.telegram.org/botSECRET-TOKEN/sendMessage"])
def test_alert_loop_disabled_without_valid_url(monkeypatch, caplog, url):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(alerts, "get_settings", lambda: SimpleNamespace(alert_webhook_url=url, alert_check_seconds=60))
    assert asyncio.run(asyncio.wait_for(alerts.alert_loop(), timeout=2)) is None
    assert "Alert унтраалттай" in caplog.text
    assert "SECRET-TOKEN" not in caplog.text


def _server(status_code):
    received = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            received.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            self.send_response(status_code)
            self.send_header("Content-Length", "0")
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, received


def test_send_alert_posts_and_never_logs_the_url(caplog):
    caplog.set_level(logging.DEBUG)
    server, received = _server(204)
    url = f"http://127.0.0.1:{server.server_address[1]}/hook/SECRET-TOKEN"
    try:
        assert asyncio.run(send_alert(url, "test")) is True
        assert received == [("/hook/SECRET-TOKEN", {"text": "test"})]
    finally:
        server.shutdown()

    server, _ = _server(500)
    url = f"http://127.0.0.1:{server.server_address[1]}/hook/SECRET-TOKEN"
    try:
        assert asyncio.run(send_alert(url, "test")) is False
    finally:
        server.shutdown()
    assert asyncio.run(send_alert(url, "test")) is False  # сервер унтарсан: холбогдохгүй
    assert "HTTP 500" in caplog.text
    assert "SECRET-TOKEN" not in caplog.text
