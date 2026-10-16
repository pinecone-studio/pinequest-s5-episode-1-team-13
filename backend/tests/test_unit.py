import pytest

from app.core.rate_limit import LoginLimiter
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
    verify_password_constant_time,
)
from app.schemas.camera import CameraCreate, CameraOut
from app.services.camera_service import build_rtsp_url


def test_password_hashing():
    h = hash_password("correct horse battery")
    assert h != "correct horse battery" and verify_password("correct horse battery", h)
    assert not verify_password("wrong", h)
    long_pw = "x" * 500  # bcrypt-ийн 72 byte хязгаарт гацахгүй
    assert verify_password(long_pw, hash_password(long_pw)) and not verify_password(long_pw + "y", hash_password(long_pw))
    assert verify_password_constant_time("anything", None) is False


def test_jwt_roundtrip_and_tamper(monkeypatch):
    token = create_access_token("user-1")
    assert decode_access_token(token) == "user-1"
    assert decode_access_token(token[:-2] + "xx") is None
    assert decode_access_token("garbage") is None


def test_fernet_encrypt_roundtrip():
    from app.core.security import decrypt_secret, encrypt_secret

    token = encrypt_secret("p@ss:w/rd")
    assert "p@ss" not in token and decrypt_secret(token) == "p@ss:w/rd"
    assert decrypt_secret("not-a-token") is None


def test_rtsp_url_builder_encodes_credentials():
    assert build_rtsp_url("admin", "p@ss:w/rd", "192.168.1.100", 554, 1, 0) == (
        "rtsp://admin:p%40ss%3Aw%2Frd@192.168.1.100:554/cam/realmonitor?channel=1&subtype=0"
    )
    assert build_rtsp_url("a", "b", "h", 554, 2, 1, "HIKVISION").endswith("/Streaming/Channels/202")
    with pytest.raises(ValueError):
        build_rtsp_url("a", "b", "h", 554, 1, 0, "LOCAL_WEBCAM")


def test_camera_schemas_never_expose_password_or_url():
    assert not {"password", "password_encrypted", "rtsp_url"} & set(CameraOut.model_fields)
    c = CameraCreate(name="c", ip_address="192.168.1.5", username="u", password="secret")
    assert "secret" not in repr(c) and "secret" not in c.model_dump_json()


@pytest.mark.parametrize("bad", ["", "a b", "1.2.3.4; rm -rf /", "http://x", "x" * 300])
def test_camera_host_validation(bad):
    with pytest.raises(ValueError):
        CameraCreate(name="c", ip_address=bad, username="u", password="p")


def test_login_limiter():
    limiter = LoginLimiter(max_failures=3, window_seconds=60)
    for _ in range(3):
        assert limiter.is_locked("k") == 0
        limiter.fail("k")
    assert limiter.is_locked("k") > 0 and limiter.is_locked("other") == 0
    limiter.success("k")
    assert limiter.is_locked("k") == 0


def test_stream_token_is_scoped_to_one_path_and_is_not_a_session_token():
    from app.core.security import create_stream_token, decode_access_token, verify_stream_token

    token = create_stream_token("cam_abc")
    assert verify_stream_token(token, "cam_abc")
    assert not verify_stream_token(token, "cam_other")
    assert not verify_stream_token("garbage", "cam_abc")
    assert decode_access_token(token) is None  # stream токен нэвтрэлтийн session болж чадахгүй
    assert not verify_stream_token(create_access_token("user-1"), "cam_abc")  # session токен stream болж чадахгүй


def test_browser_camera_needs_no_address_or_password():
    cam = CameraCreate(name="Laptop", camera_type="BROWSER", ip_address="whatever")
    assert cam.ip_address == "browser" and cam.username == "-" and cam.password is None


def test_stream_tokens_are_scoped_to_path_and_action():
    from app.core.security import create_stream_token, verify_stream_token

    read, publish = create_stream_token("cam_a"), create_stream_token("cam_a", "publish")
    assert verify_stream_token(read, "cam_a") and not verify_stream_token(read, "cam_a", "publish")
    assert verify_stream_token(publish, "cam_a", "publish") and not verify_stream_token(publish, "cam_a")
    assert not verify_stream_token(publish, "cam_b", "publish")


def test_mediamtx_auth_browser_publish_and_internal_read(monkeypatch):
    from fastapi import HTTPException

    from app.api.mediamtx import AuthRequest, mediamtx_auth
    from app.config import get_settings
    from app.core.security import create_stream_token

    monkeypatch.setattr(get_settings(), "internal_api_key", "k" * 32)
    path = "cam_" + "0" * 8 + "-0000-0000-0000-" + "0" * 12

    def allowed(**kw) -> bool:
        try:
            mediamtx_auth(AuthRequest(path=path, **kw))
            return True
        except HTTPException:
            return False

    assert allowed(action="publish", token=create_stream_token(path, "publish"))
    assert not allowed(action="publish", token=create_stream_token(path))  # үзэх токеноор дамжуулж болохгүй
    assert not allowed(action="api", token=create_stream_token(path, "publish"))
    assert allowed(action="read", user="ai", password="k" * 32)  # ai-service browser камерыг уншина
    assert not allowed(action="read", user="ai", password="wrong")


# ------------------------------------------------------------------ cloud backend: edge tunnel хаяг DB-ээс
def _db_with(value):
    from types import SimpleNamespace

    class Db:
        def get(self, model, key):
            assert key == "mediamtx_edge"
            return None if value is None else SimpleNamespace(value=value)

    return Db()


def _settings(monkeypatch, probe):
    from types import SimpleNamespace

    from app.services import camera_service

    monkeypatch.setattr(
        camera_service, "get_settings", lambda: SimpleNamespace(camera_probe_enabled=probe, mediamtx_public_url="http://localhost:8889/")
    )
    return camera_service


def test_cloud_backend_uses_fresh_edge_tunnel_url_from_db(monkeypatch):
    svc = _settings(monkeypatch, probe=False)
    assert (
        svc.public_media_url(_db_with({"url": "https://abc.trycloudflare.com/", "at": 1000.0}), now=1100.0)
        == "https://abc.trycloudflare.com"
    )


def test_stale_missing_or_unsafe_edge_url_falls_back_to_env(monkeypatch):
    svc = _settings(monkeypatch, probe=False)
    fallback = "http://localhost:8889"
    assert svc.public_media_url(_db_with({"url": "https://abc.trycloudflare.com", "at": 1000.0}), now=1000.0 + 181) == fallback  # хуучирсан
    assert svc.public_media_url(_db_with(None), now=1000.0) == fallback  # байхгүй
    assert svc.public_media_url(_db_with({"url": "http://evil.example", "at": 1000.0}), now=1010.0) == fallback  # зөвхөн https
    assert svc.public_media_url(_db_with({"url": "https://abc.trycloudflare.com"}), now=1010.0) == fallback  # цаггүй
    assert svc.public_media_url(_db_with({"url": "https://abc.trycloudflare.com", "at": 2000.0}), now=1000.0) == fallback  # ирээдүйн цаг
    assert svc.public_media_url(_db_with("not-a-dict"), now=1000.0) == fallback


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("https://abc.trycloudflare.com", "https://abc.trycloudflare.com"),
        (" https://Media.Example.com/ ", "https://media.example.com"),
        ("https://media.example.com:8443", "https://media.example.com:8443"),
        ("https://[2001:db8::1]:8443", "https://[2001:db8::1]:8443"),
        ("http://abc.trycloudflare.com", None),  # зөвхөн https
        ("https://user:pw@abc.trycloudflare.com", None),
        ("https://abc.trycloudflare.com/cam_x/whep", None),
        ("https://abc.trycloudflare.com?x=1", None),
        ("https://abc.trycloudflare.com:99999", None),
        ("https://", None),
        ("javascript:alert(1)", None),
        ("https://" + "a" * 300 + ".com", None),
    ],
)
def test_clean_edge_url(raw, clean):
    from app.services.camera_service import clean_edge_url

    assert clean_edge_url(raw) == clean


def test_edge_announce_endpoint_saves_clean_url(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import internal
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "internal_api_key", "k" * 32)
    saved = []
    monkeypatch.setattr(internal, "_save_edge", saved.append)
    app = FastAPI()
    app.include_router(internal.router)
    client = TestClient(app)

    assert client.put("/internal/edge", json={"url": "https://abc.trycloudflare.com/"}).status_code == 401
    key = {"X-Internal-Key": "k" * 32}
    assert client.put("/internal/edge", headers=key, json={"url": "https://abc.trycloudflare.com/x"}).status_code == 400
    assert client.put("/internal/edge", headers=key, json={}).status_code == 422
    assert saved == []
    assert client.put("/internal/edge", headers=key, json={"url": "https://abc.trycloudflare.com/"}).status_code == 204
    assert saved == ["https://abc.trycloudflare.com"]


def test_local_backend_never_follows_someone_elses_edge(monkeypatch):
    svc = _settings(monkeypatch, probe=True)  # локал backend
    assert svc.public_media_url(_db_with({"url": "https://abc.trycloudflare.com", "at": 1000.0}), now=1010.0) == "http://localhost:8889"


def test_ws_token_is_not_a_session_token_and_vice_versa():
    from app.core.security import create_ws_token, decode_ws_token

    ws, session = create_ws_token("user-1"), create_access_token("user-1")
    assert decode_ws_token(ws) == "user-1" and decode_access_token(ws) is None  # cookie-д хийгээд нэвтэрч болохгүй
    assert decode_ws_token(session) is None


# ------------------------------------------------------------------ WebRTC ICE серверүүд (STUN / TURN)
def _ice(monkeypatch, **overrides):
    from types import SimpleNamespace

    from app.services import camera_service

    values = {
        "webrtc_stun_urls": "stun:stun.l.google.com:19302",
        "turn_urls": "",
        "turn_secret": "",
        "turn_username": "",
        "turn_password": "",
        "turn_credential_ttl_seconds": 86400,
    } | overrides
    monkeypatch.setattr(camera_service, "get_settings", lambda: SimpleNamespace(**values))
    return camera_service


def test_ice_servers_default_is_stun_only(monkeypatch):
    svc = _ice(monkeypatch)
    assert svc.ice_servers() == [{"urls": ["stun:stun.l.google.com:19302"]}]
    assert svc.ice_config_warnings() == []
    assert _ice(monkeypatch, webrtc_stun_urls="").ice_servers() == []


def test_turn_secret_gives_coturn_time_limited_credentials(monkeypatch):
    import base64
    import hashlib
    import hmac

    turn = "turn:turn.example.com:3478?transport=udp, turns:turn.example.com:5349"
    svc = _ice(monkeypatch, turn_urls=turn, turn_secret="s3cret", turn_credential_ttl_seconds=600)
    stun, relay = svc.ice_servers(now=1000.0)
    assert stun == {"urls": ["stun:stun.l.google.com:19302"]}
    assert relay["urls"] == ["turn:turn.example.com:3478?transport=udp", "turns:turn.example.com:5349"]
    assert relay["username"] == "1600:pinequest"
    expected = base64.b64encode(hmac.new(b"s3cret", b"1600:pinequest", hashlib.sha1).digest()).decode()
    assert relay["credential"] == expected and "s3cret" not in str(relay)  # нууц өөрөө browser-т очихгүй


def test_turn_static_credentials_and_missing_credentials(monkeypatch):
    svc = _ice(monkeypatch, turn_urls="turn:t.example.com:3478", turn_username="u", turn_password="p")
    assert svc.ice_servers()[1] == {"urls": ["turn:t.example.com:3478"], "username": "u", "credential": "p"}

    svc = _ice(monkeypatch, turn_urls="turn:t.example.com:3478", turn_username="u")  # нууц үггүй
    assert svc.ice_servers() == [{"urls": ["stun:stun.l.google.com:19302"]}]
    assert any("TURN_SECRET" in w for w in svc.ice_config_warnings())


def test_ice_servers_drop_invalid_urls(monkeypatch):
    svc = _ice(
        monkeypatch,
        webrtc_stun_urls="stun:ok.example.com:3478, http://bad.example.com, ",
        turn_urls="turn.example.com:3478",
        turn_secret="s",
    )
    assert svc.ice_servers() == [{"urls": ["stun:ok.example.com:3478"]}]
    warnings = svc.ice_config_warnings()
    assert any("http://bad.example.com" in w for w in warnings) and any("turn.example.com:3478" in w for w in warnings)


def test_restricted_areas_validation():
    from pydantic import ValidationError

    from app.schemas.camera import RestrictedAreas

    ok = RestrictedAreas(areas=[[(0.5, 0.5), (1, 0.5), (1, 1)]])
    assert ok.areas == [[(0.5, 0.5), (1.0, 0.5), (1.0, 1.0)]]
    assert RestrictedAreas().areas == [] and RestrictedAreas(areas=[]).areas == []
    assert RestrictedAreas(areas=[[(0.123456, 0.5), (1, 0.5), (1, 1)]]).areas[0][0] == (0.1235, 0.5)
    for bad in ([[(0, 0), (1, 1)]], [[(0, 0), (1.5, 0), (1, 1)]], [[(0, 0), (1, 0), (1, 1)]] * 6, [[(0.1, 0.1)] * 31]):
        with pytest.raises(ValidationError):
            RestrictedAreas(areas=bad)


def test_generic_rtsp_full_url():
    from pydantic import ValidationError

    from app.schemas.camera import CameraCreate, CameraUpdate

    base = {"name": "Phone", "rtsp_port": 554, "username": "u", "password": "p", "camera_type": "GENERIC_RTSP"}
    cam = CameraCreate(**base, ip_address=" rtsp://192.168.1.50:8080/h264_ulaw.sdp ")
    assert cam.ip_address == "rtsp://192.168.1.50:8080/h264_ulaw.sdp"
    assert CameraCreate(**base, ip_address="192.168.1.50").ip_address == "192.168.1.50"
    assert CameraUpdate(ip_address="rtsps://cam.local/live").ip_address == "rtsps://cam.local/live"
    bad = ["rtsp://admin:secret@192.168.1.50/live", "rtsp:///nohost", "rtsp://bad host/x", "rtsp://1.2.3.4:99999/x", "http://1.2.3.4/x"]
    for value in bad:
        with pytest.raises(ValidationError):
            CameraCreate(**base, ip_address=value)
    with pytest.raises(ValidationError):  # full URL only for GENERIC_RTSP
        CameraCreate(**{**base, "camera_type": "DAHUA"}, ip_address="rtsp://192.168.1.50/live")


def test_generic_rtsp_url_matches_ai_service():
    assert build_rtsp_url("a b", "p@ss", "rtsp://10.0.0.5:8080/h264.sdp?x=1", 554, 1, 0, "GENERIC_RTSP") == (
        "rtsp://a%20b:p%40ss@10.0.0.5:8080/h264.sdp?x=1"
    )
    assert build_rtsp_url("u", "p", "10.0.0.5", 8554, 1, 0, "GENERIC_RTSP") == "rtsp://u:p@10.0.0.5:8554/"


def test_cloud_backend_reports_offline_edge_instead_of_localhost(monkeypatch):
    svc = _settings(monkeypatch, probe=False)  # cloud (Railway)
    assert svc.media_server_offline("http://localhost:8889")
    assert svc.media_server_offline("http://127.0.0.1:8889")
    assert not svc.media_server_offline("https://abc.trycloudflare.com")
    assert not svc.media_server_offline("https://media.example.com")
    svc = _settings(monkeypatch, probe=True)  # локал: localhost зөв
    assert not svc.media_server_offline("http://localhost:8889")


def test_webrtc_endpoint_returns_503_when_edge_is_offline(monkeypatch):
    import time

    from fastapi import HTTPException

    from app.api import cameras

    _settings(monkeypatch, probe=False)
    with pytest.raises(HTTPException) as exc:
        cameras._media_url_or_503(_db_with(None))
    assert exc.value.status_code == 503 and exc.value.detail == "Video server offline"
    assert cameras._media_url_or_503(_db_with({"url": "https://abc.trycloudflare.com", "at": time.time()})) == (
        "https://abc.trycloudflare.com"
    )
