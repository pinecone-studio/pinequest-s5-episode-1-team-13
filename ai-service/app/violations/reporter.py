"""Saves a violation: upload snapshot -> insert DB row -> tell the backend (dashboard gets VIOLATION_CREATED).

Runs in a small background pool so a slow upload never freezes the camera video.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from app.backend_client import BackendClient
from app.cameras.models import CameraInfo
from app.db import Database
from app.detection.types import PersonResult
from app.storage import SnapshotStorage, snapshot_path
from app.violations.rules import NO_HELMET
from app.violations.snapshot import make_snapshot

logger = logging.getLogger("ai.violations")

INSERT_SQL = """
INSERT INTO violations (camera_id, zone_id, violation_type, person_id, confidence, storage_path)
SELECT c.id, c.zone_id, %s::violation_type, %s, %s, %s FROM cameras c WHERE c.id = %s
RETURNING id::text
"""


class ViolationReporter:
    def __init__(
        self, db: Database, storage: SnapshotStorage, client: BackendClient, workers: int = 2, blur_faces: bool = True
    ) -> None:
        self._db, self._storage, self._client = db, storage, client
        self._blur_faces = blur_faces
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="violation")

    def submit(
        self, camera: CameraInfo, frame: np.ndarray, person: PersonResult, vtype: str, others: Sequence[PersonResult] = ()
    ) -> None:
        """others = everyone else in the frame (their faces are hidden in the picture too)."""
        self._pool.submit(self._save, camera, frame, person, vtype, tuple(others))

    def _save(
        self, camera: CameraInfo, frame: np.ndarray, person: PersonResult, vtype: str, others: Sequence[PersonResult] = ()
    ) -> str | None:
        try:
            path = snapshot_path(camera.id)
            picture = make_snapshot(frame, person, vtype, others=others, blur_faces=self._blur_faces)
            if not self._storage.upload(path, picture):
                path = None  # still save the violation, just without a picture
            confidence = person.helmet_conf if vtype == NO_HELMET else person.uniform_conf
            person_id = str(person.id) if person.id is not None else None
            rows = self._db.fetch(INSERT_SQL, (vtype, person_id, round(confidence, 4) or None, path, camera.id))
            if not rows:
                logger.warning("Camera %s was deleted, violation dropped", camera.name)
                return None
            violation_id = rows[0][0]
            self._client.violation_created(violation_id)
            logger.info("Violation %s | camera=%s person=%s", vtype, camera.name, person_id or "?")
            return violation_id
        except Exception:  # noqa: BLE001 — log and keep the service alive
            logger.exception("Could not save violation for %s", camera.name)
            return None

    def close(self) -> None:
        self._pool.shutdown(wait=True)
