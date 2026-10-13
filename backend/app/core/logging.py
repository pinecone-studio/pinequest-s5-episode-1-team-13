"""Backend logging: URL доторх `user:password@`-ийг `***` болгоно."""

from __future__ import annotations

import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_CRED = re.compile(r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+.-]*://)(?P<user>[^:/@\s]+):(?P<pw>[^@\s]+)@")
_CONFIGURED = False


class _Redact(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _CRED.sub(r"\g<scheme>\g<user>:***@", record.getMessage())
        record.args = ()
        return True


def setup_logging(level: str, log_dir: Path) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")
    handlers = [
        logging.StreamHandler(sys.stdout),
        RotatingFileHandler(log_dir / "backend.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8"),
    ]
    root = logging.getLogger()
    root.setLevel(level.upper())
    for h in handlers:
        h.setFormatter(fmt)
        h.addFilter(_Redact())
        root.addHandler(h)
    _CONFIGURED = True
