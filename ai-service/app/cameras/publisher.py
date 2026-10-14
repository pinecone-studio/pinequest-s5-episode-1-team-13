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
RETRY_SECONDS = 5.0


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

    @staticmethod
    def available() -> bool:
        return shutil.which("ffmpeg") is not None

    def _start(self, width: int, height: int) -> None:
        self._proc = subprocess.Popen(ffmpeg_command(width, height, self._fps, self._url), stdin=subprocess.PIPE)
        self._size = (width, height)
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
                logger.warning("ffmpeg stopped for %s, retry in %.0fs", self._name, RETRY_SECONDS)
                self.close()
                self._retry_at = time.time() + RETRY_SECONDS
            elif self._size != (width, height):  # camera changed resolution — restart now
                self.close()
        if self._proc is None:
            if time.time() < self._retry_at:
                return
            self._start(width, height)
        try:
            self._proc.stdin.write(frame.tobytes())
        except (BrokenPipeError, OSError):
            logger.warning("MediaMTX publish failed for %s, retry in %.0fs", self._name, RETRY_SECONDS)
            self.close()
            self._retry_at = time.time() + RETRY_SECONDS

    def close(self) -> None:
        if self._proc is None:
            return
        try:
            self._proc.stdin.close()
            self._proc.wait(timeout=3)
        except Exception:  # noqa: BLE001 — shutting down anyway
            self._proc.kill()
        self._proc = None
