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
from app.logging_setup import setup_logging

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

    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())

    client = BackendClient(settings.backend_base, settings.internal_api_key)
    db = Database(settings.database_url)
    secrets = SecretBox(settings.camera_secret_key)
    manager = CameraManager(
        load=lambda: repository.load_cameras(db, secrets),
        make_worker=lambda cam: CameraWorker(cam, settings, db, client),
    )
    threading.Thread(target=heartbeat_loop, args=(client, settings.heartbeat_seconds, stop), name="heartbeat", daemon=True).start()

    logger.info("AI service started | backend=%s", settings.backend_base)
    try:
        while not stop.is_set():
            manager.sync()
            stop.wait(settings.camera_refresh_seconds)
    finally:
        manager.stop_all()
        db.close()
        client.close()
        logger.info("AI service stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
