"""Keeps one worker per enabled camera in sync with the database.

Every CAMERA_REFRESH_SECONDS: start new cameras, stop removed/disabled ones,
reconnect cameras whose address/login changed, and pass rotation/zone/AI changes to running workers.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from app.cameras.models import CameraInfo

logger = logging.getLogger("ai.manager")


def plan(running: dict[str, CameraInfo], wanted: list[CameraInfo]) -> tuple[list[CameraInfo], list[str], list[CameraInfo]]:
    """Pure logic (easy to test): (to_start, to_stop, to_update). A changed connection = stop + start."""
    wanted_by_id = {c.id: c for c in wanted}
    to_stop = [cid for cid, cam in running.items() if cid not in wanted_by_id or wanted_by_id[cid].connection_key() != cam.connection_key()]
    to_start = [c for c in wanted if c.id not in running or c.id in to_stop]
    to_update = [c for c in wanted if c.id in running and c.id not in to_stop and c != running[c.id]]
    return to_start, to_stop, to_update


class CameraManager:
    def __init__(self, load: Callable[[], list[CameraInfo]], make_worker: Callable[[CameraInfo], object]) -> None:
        self._load = load
        self._make_worker = make_worker
        self.workers: dict = {}

    def sync(self) -> None:
        try:
            wanted = self._load()
        except Exception as exc:  # noqa: BLE001 — DB down: keep the cameras we have
            logger.warning("Could not load cameras: %s", type(exc).__name__)
            return
        running = {cid: w.camera for cid, w in self.workers.items()}
        to_start, to_stop, to_update = plan(running, wanted)
        for cid in to_stop:
            worker = self.workers.pop(cid)
            worker.stop()
            worker.join(timeout=5)  # let it write OFFLINE before a reconnected worker writes CONNECTING
            logger.info("Stopped camera %s", worker.camera.name)
        for cam in to_update:
            self.workers[cam.id].update(cam)
        for cam in to_start:
            try:
                worker = self._make_worker(cam)
            except ValueError as exc:
                logger.error("Camera %s skipped: %s", cam.name, exc)
                continue
            self.workers[cam.id] = worker
            worker.start()
            logger.info("Started camera %s (%s)", cam.name, cam.camera_type)

    def stop_all(self) -> None:
        for worker in self.workers.values():
            worker.stop()
        for worker in self.workers.values():
            worker.join(timeout=5)
        self.workers.clear()
