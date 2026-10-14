"""Simple console logging for the AI service."""

from __future__ import annotations

import logging


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )
    # httpx logs every request at INFO; too noisy for a loop that runs many times per second
    logging.getLogger("httpx").setLevel(logging.WARNING)
