"""Sends frames to MediaMTX with ffmpeg so the dashboard can play IP cameras and webcams over WebRTC.

H.264, no B-frames (WebRTC needs that), very low latency. If ffmpeg is not installed, publishing is skipped.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import time

import numpy as np

logger = logging.getLogger("ai.publisher")
RETRY_START = 5.0  # first wait after a failure
RETRY_MAX = 60.0  # never wait longer than this
STABLE_SECONDS = 30.0  # publishing this long without a failure = healthy again, next failure starts at 5 s


def next_wait(previous: float | None) -> float:
    """5 s, 10 s, 20 s, 40 s, 60 s, 60 s ... — MediaMTX down for long won't spam ffmpeg restarts and logs."""
    return RETRY_START if previous is None else min(previous * 2, RETRY_MAX)


def ffmpeg_command(width: int, height: int, fps: int, url: str) -> list[str]:
    return [
        "ffmpeg", "-loglevel", "error", "-nostdin",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
        "-an", "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency", "-bf", "0",
        "-g", str(fps * 2), "-pix_fmt", "yuv420p",
        "-f", "rtsp", "-rtsp_transport", "tcp", url,
    ]  # fmt: skip


class VideoPublisher:
    _warned_missing = False

    def __init__(self, url: str, fps: int, name: str) -> None:
        self._url, self._fps, self._name = url, fps, name
        self._proc: subprocess.Popen | None = None
        self._size: tuple[int, int] | None = None
        self._retry_at = 0.0
        self._wait: float | None = None  # current backoff, None = healthy
        self._started_at = 0.0

    @staticmethod
    def available() -> bool:
        return shutil.which("ffmpeg") is not None

    def _start(self, width: int, height: int) -> None:
        self._proc = subprocess.Popen(ffmpeg_command(width, height, self._fps, self._url), stdin=subprocess.PIPE)
        self._size = (width, height)
        self._started_at = time.time()
        logger.info("Publishing %s to MediaMTX (%dx%d @ %d fps)", self._name, width, height, self._fps)

    def send(self, frame: np.ndarray) -> None:
        if not self.available():
            if not VideoPublisher._warned_missing:
                logger.warning("ffmpeg not found: video is NOT sent to MediaMTX (detection still works). brew install ffmpeg")
                VideoPublisher._warned_missing = True
            return
        height, width = frame.shape[:2]
        if self._proc is not None:
            if self._proc.poll() is not None:  # ffmpeg died (MediaMTX down?) — wait before trying again
                self._failed("ffmpeg stopped")
            elif self._size != (width, height):  # camera changed resolution — restart now
                self.close()
            elif self._wait is not None and time.time() - self._started_at >= STABLE_SECONDS:
                logger.info("Publishing %s is stable again", self._name)
                self._wait = None
        if self._proc is None:
            if time.time() < self._retry_at:
                return
            self._start(width, height)
        try:
            self._proc.stdin.write(frame.tobytes())
        except (BrokenPipeError, OSError):
            self._failed("MediaMTX publish failed")

    def _failed(self, reason: str) -> None:
        self.close()
        self._wait = next_wait(self._wait)
        self._retry_at = time.time() + self._wait
        logger.warning("%s for %s, retry in %.0fs", reason, self._name, self._wait)

    def close(self) -> None:
        if self._proc is None:
            return
        try:
            self._proc.stdin.close()
            self._proc.wait(timeout=3)
        except Exception:  # noqa: BLE001 — shutting down anyway
            self._proc.kill()
        self._proc = None
