import time
from dataclasses import replace

import numpy as np
from cryptography.fernet import Fernet

from app.cameras.frames import rotate
from app.cameras.manager import plan
from app.cameras.models import CameraInfo
from app.cameras.publisher import ffmpeg_command
from app.cameras.reader import STREAMING, FrameReader
from app.cameras.sources import mediamtx_url, safe_label, source_for, stream_path
from app.crypto import SecretBox

CAM = CameraInfo(
    id="11111111-2222-3333-4444-555555555555", name="Gate", camera_type="DAHUA", ip_address="192.168.1.10",
    rtsp_port=554, username="admin", password="p@ss/1", channel=1, subtype=0, rotation=0, mirror=False,
    ai_enabled=True, zone_type="FACTORY",
)  # fmt: skip


def test_dahua_and_hikvision_urls_match_backend():
    assert source_for(CAM, "rtsp://m:8554", "k") == "rtsp://admin:p%40ss%2F1@192.168.1.10:554/cam/realmonitor?channel=1&subtype=0"
    hik = replace(CAM, camera_type="HIKVISION", channel=2, subtype=1)
    assert source_for(hik, "rtsp://m:8554", "k").endswith("/Streaming/Channels/202")


def test_webcam_browser_and_generic():
    assert source_for(replace(CAM, camera_type="LOCAL_WEBCAM", ip_address="0"), "rtsp://m:8554", "k") == 0
    browser = source_for(replace(CAM, camera_type="BROWSER"), "rtsp://mediamtx:8554", "key/1")
    assert browser == f"rtsp://ai:key%2F1@mediamtx:8554/{stream_path(CAM.id)}"
    full = replace(CAM, camera_type="GENERIC_RTSP", ip_address="rtsp://10.0.0.5:8554/live", username="u", password="p")
    assert source_for(full, "rtsp://m:8554", "k") == "rtsp://u:p@10.0.0.5:8554/live"


def test_logs_never_show_password():
    label = safe_label(source_for(CAM, "rtsp://m:8554", "k"))
    assert "p%40ss" not in label and "admin" not in label
    assert "secret" not in safe_label(mediamtx_url("rtsp://m:8554", CAM.id, "secret"))


def test_secret_box_roundtrip():
    key = Fernet.generate_key().decode()
    token = Fernet(key.encode()).encrypt(b"camera-pass").decode()
    assert SecretBox(key).decrypt(token) == "camera-pass"
    assert SecretBox(Fernet.generate_key().decode()).decrypt(token) is None  # wrong key
    assert SecretBox(key).decrypt(None) is None


def test_rotate_clockwise():
    frame = np.zeros((2, 4, 3), dtype=np.uint8)
    frame[0, 0] = 255  # top-left
    turned = rotate(frame, 90)
    assert turned.shape == (4, 2, 3)
    assert turned[0, 1].tolist() == [255, 255, 255]  # top-left goes to top-right
    assert rotate(frame, 0) is frame


def test_plan_start_stop_update():
    other = replace(CAM, id="b", name="B")
    start, stop, update = plan({CAM.id: CAM}, [replace(CAM, rotation=90), other])
    assert [c.id for c in start] == ["b"] and stop == [] and update[0].rotation == 90

    start, stop, update = plan({CAM.id: CAM}, [replace(CAM, ip_address="192.168.1.99")])
    assert stop == [CAM.id] and start[0].ip_address == "192.168.1.99" and update == []

    assert plan({CAM.id: CAM}, []) == ([], [CAM.id], [])


def test_publisher_uses_webrtc_friendly_h264():
    cmd = ffmpeg_command(640, 480, 15, "rtsp://ai:k@m:8554/cam_x")
    assert cmd[cmd.index("-bf") + 1] == "0" and "zerolatency" in cmd and cmd[-1].endswith("cam_x")


class FakeCapture:
    def __init__(self):
        self.reads = 0

    def isOpened(self):
        return True

    def get(self, _):
        return 25.0

    def read(self):
        self.reads += 1
        return True, np.full((4, 4, 3), self.reads % 256, dtype=np.uint8)

    def release(self):
        pass


def test_reader_keeps_only_newest_frame():
    reader = FrameReader(0, "test", open_fn=lambda _: FakeCapture())
    reader.start()
    deadline = time.time() + 2
    while reader.latest()[1] < 3 and time.time() < deadline:
        time.sleep(0.01)
    reader.stop()
    frame, seq, _ = reader.latest()
    assert reader.state == STREAMING and seq >= 3 and frame is not None
