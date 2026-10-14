"""AI service entry point.

Run:  python -m app.main
"""

from __future__ import annotations

import logging
import signal
import sys
import threading

from app.backend_client import BackendClient
from app.cameras import repository
from app.cameras.manager import CameraManager
from app.cameras.worker import CameraWorker
from app.config import get_settings
from app.crypto import SecretBox
from app.db import Database
from app.detection.classes import parse_mapping
from app.detection.model import Detector
from app.detection.pipeline import CameraAI
from app.logging_setup import setup_logging
from app.storage import SnapshotStorage
from app.violations.reporter import ViolationReporter
from app.violations.rules import ViolationRules

logger = logging.getLogger("ai.main")


def heartbeat_loop(client: BackendClient, every: float, stop: threading.Event) -> None:
    while not stop.is_set():
        client.heartbeat()
        stop.wait(every)


def main() -> int:
    settings = get_settings()
    setup_logging(settings.log_level)

    problems = settings.startup_problems()
    if problems:
        logger.error("Fill these in ai-service/.env first: %s", ", ".join(problems))
        return 1

    try:
        parse_mapping(settings.class_mapping)
    except ValueError as exc:
        logger.error("%s", exc)
        return 1

    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())

    client = BackendClient(settings.backend_base, settings.internal_api_key)
    db = Database(settings.database_url)
    secrets = SecretBox(settings.camera_secret_key)

    def make_detector() -> Detector:
        return Detector(settings.resolved_model_path, settings.class_mapping, settings.conf_threshold, settings.imgsz)

    storage = SnapshotStorage(settings.supabase_url, settings.supabase_service_role_key, settings.supabase_storage_bucket)
    if not storage.enabled:
        logger.warning("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set: violations are saved WITHOUT snapshot pictures")
    reporter = ViolationReporter(db, storage, client)

    def make_ai() -> CameraAI:
        rules = ViolationRules(settings.violation_confirm_seconds, settings.violation_cooldown_seconds)
        return CameraAI(client, make_detector, settings.detect_fps, rules=rules, reporter=reporter)

    manager = CameraManager(
        load=lambda: repository.load_cameras(db, secrets),
        make_worker=lambda cam: CameraWorker(cam, settings, db, client, ai=make_ai()),
    )
    threading.Thread(target=heartbeat_loop, args=(client, settings.heartbeat_seconds, stop), name="heartbeat", daemon=True).start()

    logger.info("AI service started | backend=%s", settings.backend_base)
    try:
        while not stop.is_set():
            manager.sync()
            stop.wait(settings.camera_refresh_seconds)
    finally:
        manager.stop_all()
        reporter.close()
        storage.close()
        db.close()
        client.close()
        logger.info("AI service stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
