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
        build_rtsp_url("a", "b", "h", 554, 1, 0, "GENERIC_RTSP")


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


def test_local_backend_never_follows_someone_elses_edge(monkeypatch):
    svc = _settings(monkeypatch, probe=True)  # локал backend
    assert svc.public_media_url(_db_with({"url": "https://abc.trycloudflare.com", "at": 1000.0}), now=1010.0) == "http://localhost:8889"


def test_ws_token_is_not_a_session_token_and_vice_versa():
    from app.core.security import create_ws_token, decode_ws_token

    ws, session = create_ws_token("user-1"), create_access_token("user-1")
    assert decode_ws_token(ws) == "user-1" and decode_access_token(ws) is None  # cookie-д хийгээд нэвтэрч болохгүй
    assert decode_ws_token(session) is None
