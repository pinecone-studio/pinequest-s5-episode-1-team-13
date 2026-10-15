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
from app.dataset.collector import CollectionConfig, DatasetCollector, ImageCounter
from app.db import Database
from app.detection.classes import parse_mapping
from app.detection.device import pick_device
from app.detection.model import Detector
from app.detection.motion import MotionGate
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
        logger.info("AI device: %s", pick_device(settings.device, settings.resolved_model_path))
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
        return Detector(settings.resolved_model_path, settings.class_mapping, settings.conf_threshold, settings.imgsz, settings.device)

    storage = SnapshotStorage(settings.supabase_url, settings.supabase_service_role_key, settings.supabase_storage_bucket)
    if not storage.enabled:
        logger.warning("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set: violations are saved WITHOUT snapshot pictures")
    reporter = ViolationReporter(db, storage, client)
    collection = CollectionConfig(db)
    dataset_root = settings.resolved_dataset_dir
    image_counter = ImageCounter(dataset_root / "datasets" / "raw")

    def make_ai() -> CameraAI:
        rules = ViolationRules(settings.violation_confirm_seconds, settings.violation_cooldown_seconds)
        collector = DatasetCollector(dataset_root, collection, image_counter)
        motion = MotionGate(settings.motion_threshold, settings.motion_max_skip_seconds) if settings.motion_skip else None
        return CameraAI(
            client, make_detector, settings.detect_fps, rules=rules, reporter=reporter, collector=collector, motion=motion,
            min_brightness=settings.min_brightness, min_sharpness=settings.min_sharpness,
            no_conf=settings.no_conf_threshold, smooth_window=settings.smooth_window,
        )  # fmt: skip

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
