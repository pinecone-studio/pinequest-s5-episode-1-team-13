from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """Supabase руу SSL заавал (localhost-оос бусад). DATABASE_URL log-д гарахгүй."""
    global _engine, _session_factory
    if _engine is None:
        url = make_url(get_settings().database_url)
        if url.drivername in ("postgresql", "postgres"):
            url = url.set(drivername="postgresql+psycopg2")
        connect_args: dict = {"connect_timeout": 10}
        if url.host not in _LOCAL_HOSTS and "sslmode" not in url.query:
            connect_args["sslmode"] = "require"
        _engine = create_engine(
            url, pool_size=10, max_overflow=10, pool_timeout=10, pool_pre_ping=True, pool_recycle=1800, connect_args=connect_args
        )
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False, autoflush=False)
    return _engine


def get_db() -> Iterator[Session]:
    get_engine()
    assert _session_factory is not None
    db = _session_factory()
    try:
        yield db
    finally:
        db.close()


def new_session() -> Session:
    get_engine()
    assert _session_factory is not None
    return _session_factory()
