"""One thread per camera: read frames -> publish video -> (later) run AI. Reports status changes to DB + backend."""

from __future__ import annotations

import logging
import threading
import time

import numpy as np

from app.backend_client import BackendClient
from app.cameras import repository
from app.cameras.frames import rotate
from app.cameras.models import CameraInfo
from app.cameras.publisher import VideoPublisher
from app.cameras.reader import FrameReader
from app.cameras.sources import mediamtx_url, source_for
from app.config import Settings
from app.db import Database

logger = logging.getLogger("ai.worker")


class CameraWorker(threading.Thread):
    def __init__(self, camera: CameraInfo, settings: Settings, db: Database, client: BackendClient) -> None:
        super().__init__(name=f"camera-{camera.name}", daemon=True)
        self.camera = camera
        self._settings, self._db, self._client = settings, db, client
        self._stop = threading.Event()
        self._status: str | None = None
        source = source_for(camera, settings.mediamtx_rtsp_url, settings.internal_api_key)
        self.reader = FrameReader(source, camera.name)
        self.publisher = None
        # BROWSER cameras already send their own video to MediaMTX; the AI only reads them
        if settings.publish_video and not camera.is_browser:
            url = mediamtx_url(settings.mediamtx_rtsp_url, camera.id, settings.internal_api_key)
            self.publisher = VideoPublisher(url, settings.publish_fps, camera.name)

    def update(self, camera: CameraInfo) -> None:
        """Rotation / zone / ai_enabled changed: apply without reconnecting."""
        self.camera = camera

    def stop(self) -> None:
        self._stop.set()

    def _report(self, status: str) -> None:
        if status == self._status:
            return
        self._status = status
        try:
            repository.set_status(self._db, self.camera.id, status)
        except Exception as exc:  # noqa: BLE001 — never kill the camera thread because of the DB
            logger.warning("Could not save status for %s: %s", self.camera.name, type(exc).__name__)
            return
        self._client.camera_status(self.camera.id)

    def handle_frame(self, frame: np.ndarray, now: float) -> None:
        """AI processing hook. `frame` is already rotated upright."""

    def run(self) -> None:
        self._report("CONNECTING")
        self.reader.start()
        interval = 1.0 / self._settings.publish_fps
        last_seq = -1
        try:
            while not self._stop.is_set():
                started = time.time()
                frame, seq, _ = self.reader.latest()
                self._report(self.reader.state)
                if frame is not None and seq != last_seq:
                    last_seq = seq
                    if self.publisher is not None:
                        self.publisher.send(frame)  # raw video; the dashboard rotates/mirrors it itself
                    try:
                        self.handle_frame(rotate(frame, self.camera.rotation), started)
                    except Exception:  # noqa: BLE001
                        logger.exception("AI step failed for %s", self.camera.name)
                self._stop.wait(max(0.0, interval - (time.time() - started)))
        finally:
            self.reader.stop()
            if self.publisher is not None:
                self.publisher.close()
            self._report("OFFLINE")
