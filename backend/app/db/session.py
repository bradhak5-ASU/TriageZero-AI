"""Engine and session management for both supported backends.

SQLite is the local/default store. PostgreSQL (Cloud SQL) is the cloud store,
because a Cloud Run container's filesystem is ephemeral: a SQLite file written
there disappears on every restart, redeploy and scale-to-zero, which would
silently erase every investigation between demo runs.
"""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.migrations import run_migrations

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None

#: Driver used for PostgreSQL. psycopg 3 is the current driver and is what
#: Cloud SQL connections are tested against here.
POSTGRES_DRIVER = "postgresql+psycopg"


def normalize_database_url(url: str) -> str:
    """Return a URL SQLAlchemy can open with the driver we actually ship.

    Managed PostgreSQL services hand out `postgres://` or `postgresql://` URLs.
    Bare `postgresql://` resolves to psycopg2 (which is not a dependency here)
    and `postgres://` is not a scheme SQLAlchemy accepts at all, so both are
    rewritten to the psycopg 3 driver rather than failing at first connect -
    in production that failure would land on a request, not on a deploy.
    """
    for prefix in ("postgresql+psycopg://", "postgresql+psycopg2://", "postgresql+asyncpg://"):
        if url.startswith(prefix):
            return url  # an explicit driver choice is respected
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return f"{POSTGRES_DRIVER}://{url[len(prefix):]}"
    return url


def build_engine(database_url: str) -> Engine:
    """Create an engine tuned for the backend in the URL.

    PostgreSQL settings exist because of how Cloud Run behaves: instances idle
    and are recycled, and Cloud SQL closes connections that have been idle,
    so a pooled connection is frequently dead by the time it is reused.
    `pool_pre_ping` checks it instead of failing the request, and
    `pool_recycle` retires connections before the server does. The pool is
    deliberately small - each Cloud Run instance holds its own pool, and Cloud
    SQL instance connection limits are shared across all of them.
    """
    url = normalize_database_url(database_url)

    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False})

    if url.startswith("postgresql"):
        return create_engine(
            url,
            pool_pre_ping=True,
            pool_recycle=1800,
            pool_size=5,
            max_overflow=2,
            pool_timeout=30,
        )

    return create_engine(url)


def init_db() -> None:
    """Create the engine/session factory from settings, ensure tables exist,
    and bring an older database up to the current schema.

    create_all() only creates missing tables - it never alters existing ones -
    so the migration step runs immediately afterwards, before any request or
    pending-investigation recovery touches the data.
    """
    global _engine, _session_factory
    settings = get_settings()
    _engine = build_engine(settings.resolved_database_url)
    _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    Base.metadata.create_all(_engine)
    run_migrations(_engine)


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
