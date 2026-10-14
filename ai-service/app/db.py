"""Direct PostgreSQL access (same Supabase database as the backend).

The AI reads cameras and writes camera status. One connection, reconnects once if it was dropped.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Sequence
from typing import Any

import psycopg2

logger = logging.getLogger("ai.db")


class Database:
    def __init__(self, url: str) -> None:
        self._url = url
        self._conn = None
        self._lock = threading.Lock()  # psycopg2 connections are not safe to share between threads at the same time

    def _connect(self):
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(self._url, connect_timeout=10)
            self._conn.autocommit = True
        return self._conn

    def _run(self, sql: str, params: Sequence[Any] = (), fetch: bool = False):
        with self._lock:
            for attempt in (1, 2):
                try:
                    with self._connect().cursor() as cur:
                        cur.execute(sql, params)
                        return cur.fetchall() if fetch else None
                except (psycopg2.OperationalError, psycopg2.InterfaceError):
                    self.close()
                    if attempt == 2:
                        raise
                    logger.warning("Database connection lost, reconnecting")

    def fetch(self, sql: str, params: Sequence[Any] = ()) -> list[tuple]:
        return self._run(sql, params, fetch=True)

    def execute(self, sql: str, params: Sequence[Any] = ()) -> None:
        self._run(sql, params)

    def close(self) -> None:
        if self._conn is not None and not self._conn.closed:
            self._conn.close()
        self._conn = None
