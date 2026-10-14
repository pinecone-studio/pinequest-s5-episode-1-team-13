"""Reads video in a background thread and keeps only the newest frame (old frames are dropped, so the AI never lags behind)."""

from __future__ import annotations

import logging
import os
import threading
import time

# TCP is more reliable than UDP for RTSP. Must be set BEFORE cv2 is imported.
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from app.cameras.sources import safe_label  # noqa: E402

logger = logging.getLogger("ai.reader")

OPEN_TIMEOUT_MS = 8000
READ_TIMEOUT_MS = 8000
MAX_BACKOFF = 30.0
STALE_SECONDS = 5.0  # no new frame for this long = connection problem

# Same names as the camera_status enum in the database
CONNECTING, STREAMING, RECONNECTING, ERROR = "CONNECTING", "STREAMING", "RECONNECTING", "ERROR"


def open_capture(source: str | int) -> cv2.VideoCapture:
    if isinstance(source, int):
        return cv2.VideoCapture(source)
    return cv2.VideoCapture(
        source, cv2.CAP_FFMPEG, [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, OPEN_TIMEOUT_MS, cv2.CAP_PROP_READ_TIMEOUT_MSEC, READ_TIMEOUT_MS]
    )


class FrameReader(threading.Thread):
    def __init__(self, source: str | int, name: str, open_fn=open_capture) -> None:
        super().__init__(name=f"reader-{name}", daemon=True)
        self._source = source
        self._open = open_fn
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._frame: np.ndarray | None = None
        self._frame_time = 0.0
        self._seq = 0
        self.state = CONNECTING
        self.fps = 0.0

    def latest(self) -> tuple[np.ndarray | None, int, float]:
        """(frame, sequence number, time). Same sequence number = no new frame yet."""
        with self._lock:
            return self._frame, self._seq, self._frame_time

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        backoff = 1.0
        label = safe_label(self._source)
        while not self._stop.is_set():
            cap = self._open(self._source)
            if not cap.isOpened():
                self.state = ERROR if backoff >= MAX_BACKOFF else RECONNECTING
                logger.warning("Cannot open %s, retry in %.0fs", label, backoff)
                cap.release()
                self._stop.wait(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF)
                continue

            fps = cap.get(cv2.CAP_PROP_FPS)
            self.fps = fps if 1 <= fps <= 60 else 15.0
            logger.info("Connected %s (%.0f fps)", label, self.fps)
            backoff = 1.0
            last_ok = time.time()
            while not self._stop.is_set():
                ok, frame = cap.read()
                now = time.time()
                if ok and frame is not None:
                    with self._lock:
                        self._frame, self._frame_time = frame, now
                        self._seq += 1
                    self.state = STREAMING
                    last_ok = now
                elif now - last_ok > STALE_SECONDS:
                    logger.warning("Lost video from %s, reconnecting", label)
                    self.state = RECONNECTING
                    break
                else:
                    time.sleep(0.05)
            cap.release()
