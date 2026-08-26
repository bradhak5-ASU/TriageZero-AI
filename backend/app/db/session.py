from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.migrations import run_sqlite_migrations

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def build_engine(database_url: str) -> Engine:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args)


def init_db() -> None:
    """Create the engine/session factory from settings, ensure tables exist,
    and bring an older database up to the current schema.

    create_all() only creates missing tables — it never alters existing ones —
    so the migration step runs immediately afterwards, before any request or
    pending-investigation recovery touches the data.
    """
    global _engine, _session_factory
    settings = get_settings()
    _engine = build_engine(settings.resolved_database_url)
    _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    Base.metadata.create_all(_engine)
    run_sqlite_migrations(_engine)


def reset_db_state() -> None:
    """Dispose the engine (used by tests to point at a fresh database)."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


def new_session() -> Session:
    if _session_factory is None:
        init_db()
    assert _session_factory is not None
    return _session_factory()


def get_session() -> Iterator[Session]:
    session = new_session()
    try:
        yield session
    finally:
        session.close()
