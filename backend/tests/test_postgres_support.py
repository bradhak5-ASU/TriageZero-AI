"""PostgreSQL support: URL handling, engine tuning, and real migrations.

Two layers:

1. Tests that always run and need no server - URL normalization, pool tuning,
   the production durability guard, and the DDL the partial unique index
   compiles to on the PostgreSQL dialect.

2. Tests gated on ``TRIAGEZERO_TEST_POSTGRES_URL``, which run the migration
   path and the whole ingestion flow against a real PostgreSQL server. These
   are what actually prove the cloud store works; the compile-only checks
   would happily pass on SQL PostgreSQL rejects.

Set TRIAGEZERO_TEST_POSTGRES_URL to a throwaway database to enable layer 2.
It is skipped rather than failed when unset so the default suite stays offline.
"""

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateIndex

from app.core.config import Settings
from app.db.migrations import (
    IDEMPOTENCY_KEY_INDEX,
    LEGACY_INDEX,
    TABLE,
    index_names,
    run_migrations,
)
from app.db.models import InvestigationRecord
from app.db.session import build_engine, normalize_database_url

POSTGRES_URL = os.environ.get("TRIAGEZERO_TEST_POSTGRES_URL", "")

# SQLAlchemy imports the DBAPI when the engine is created, so even building a
# PostgreSQL engine needs psycopg installed. It ships in the `postgres` extra
# (and in the cloud image); the default dev install does not carry it, so these
# tests skip rather than fail there.
try:  # pragma: no cover - import probe
    import psycopg  # noqa: F401

    HAS_PSYCOPG = True
except ImportError:  # pragma: no cover
    HAS_PSYCOPG = False

requires_psycopg = pytest.mark.skipif(
    not HAS_PSYCOPG, reason="psycopg is not installed (pip install '.[postgres]')"
)
requires_postgres = pytest.mark.skipif(
    not (POSTGRES_URL and HAS_PSYCOPG),
    reason="set TRIAGEZERO_TEST_POSTGRES_URL (and install the postgres extra)",
)

DURABLE_URL = "postgresql+psycopg://u:p@db.internal:5432/triagezero"


# --- URL normalization ------------------------------------------------------


@pytest.mark.parametrize(
    "given,expected",
    [
        # Managed services hand out these two forms; neither resolves to a
        # driver this project ships, so both must be rewritten.
        ("postgres://u:p@h:5432/db", "postgresql+psycopg://u:p@h:5432/db"),
        ("postgresql://u:p@h:5432/db", "postgresql+psycopg://u:p@h:5432/db"),
        # An explicit driver choice is respected, not overridden.
        ("postgresql+psycopg://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("postgresql+psycopg2://u:p@h/db", "postgresql+psycopg2://u:p@h/db"),
        # SQLite is untouched.
        ("sqlite:///./data/x.db", "sqlite:///./data/x.db"),
        ("sqlite:////abs/x.db", "sqlite:////abs/x.db"),
    ],
)
def test_database_url_is_normalized_to_a_driver_we_ship(given, expected):
    assert normalize_database_url(given) == expected


def test_cloud_sql_unix_socket_url_survives_normalization():
    """Cloud SQL connects over a Unix socket passed as a `host` query param.
    The rewrite must not disturb the query string."""
    given = (
        "postgresql://user:pw@/triagezero"
        "?host=/cloudsql/my-project:us-central1:tz-db"
    )
    out = normalize_database_url(given)
    assert out.startswith("postgresql+psycopg://")
    assert out.endswith("?host=/cloudsql/my-project:us-central1:tz-db")


# --- engine tuning ----------------------------------------------------------


@requires_psycopg
def test_postgres_engine_pre_pings_and_recycles_connections():
    """Cloud Run instances idle and Cloud SQL closes idle connections, so a
    pooled connection is often dead on reuse. Without pre-ping that surfaces
    as a failed request rather than a transparent reconnect."""
    engine = build_engine(DURABLE_URL)
    assert engine.pool._pre_ping is True
    assert engine.pool._recycle == 1800
    assert engine.dialect.name == "postgresql"
    assert engine.dialect.driver == "psycopg"


def test_sqlite_engine_keeps_its_threading_argument():
    engine = build_engine("sqlite:///:memory:")
    assert engine.dialect.name == "sqlite"
    assert engine.url.database == ":memory:"


# --- schema shape on the PostgreSQL dialect ---------------------------------


def test_idempotency_index_is_partial_and_unique_on_postgres():
    """The uniqueness guarantee must survive the move to PostgreSQL. Without
    `postgresql_where` the index would be built over every row, and the many
    investigations with no Idempotency-Key would collide on NULL semantics
    differing from what the code assumes."""
    index = next(
        i for i in InvestigationRecord.__table__.indexes if i.name == IDEMPOTENCY_KEY_INDEX
    )
    ddl = str(CreateIndex(index).compile(dialect=postgresql.dialect()))
    assert "UNIQUE INDEX" in ddl
    assert "WHERE idempotency_key IS NOT NULL" in ddl


# --- production durability guard --------------------------------------------


@pytest.mark.parametrize("env", ["production", "staging", "PRODUCTION"])
def test_production_refuses_an_ephemeral_sqlite_database(env):
    """Cloud Run's disk is thrown away on restart. SQLite there loses every
    investigation silently, so this must fail at startup, not at 2am."""
    with pytest.raises(ValueError, match="durable database"):
        Settings(
            app_env=env,
            database_url="sqlite:///./data/triagezero.db",
            frontend_origins="https://tz.example.com",
            api_auth_required=True,
            ingestion_api_token="i" * 40,
            dashboard_api_token="d" * 40,
        )


def test_production_accepts_postgres():
    settings = Settings(
        app_env="production",
        database_url=DURABLE_URL,
        frontend_origins="https://tz.example.com",
        api_auth_required=True,
        ingestion_api_token="i" * 40,
        dashboard_api_token="d" * 40,
    )
    assert settings.database_backend == "postgresql"


def test_local_development_still_uses_sqlite_with_no_configuration():
    settings = Settings(app_env="development")
    assert settings.database_backend == "sqlite"


def test_migration_cli_never_prints_database_credentials(capsys):
    from app.db.migrate import _redacted

    printed = _redacted("postgresql+psycopg://tzuser:sup3rs3cret@10.1.2.3:5432/triagezero")
    assert "sup3rs3cret" not in printed
    assert "tzuser" not in printed
    assert "10.1.2.3:5432/triagezero" in printed


# --- real PostgreSQL --------------------------------------------------------


@pytest.fixture()
def pg_engine():  # noqa: PT004
    """A live engine with the investigations table dropped beforehand, so each
    test starts from a known schema state."""
    engine = build_engine(POSTGRES_URL)
    with engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {TABLE} CASCADE"))
    yield engine
    engine.dispose()


@requires_postgres
def test_fresh_postgres_database_gets_the_unique_index(pg_engine):
    from app.db.base import Base

    Base.metadata.create_all(pg_engine)
    run_migrations(pg_engine)
    with pg_engine.connect() as conn:
        assert IDEMPOTENCY_KEY_INDEX in index_names(conn, TABLE)


@requires_postgres
def test_unique_index_actually_rejects_a_duplicate_key_on_postgres(pg_engine):
    from app.db.base import Base

    Base.metadata.create_all(pg_engine)
    run_migrations(pg_engine)

    def insert(inv_id: str, key: str | None) -> None:
        with pg_engine.begin() as conn:
            conn.execute(
                text(
                    f"INSERT INTO {TABLE} (id, fingerprint, idempotency_key, status, "
                    "stage, retry_count, repository, environment, test_name, test_file, "
                    "created_at, updated_at, package_json, doc_json, is_synthetic) "
                    "VALUES (:id, :fp, :key, 'completed', 'done', 0, 'r', 'e', 't', 'f', "
                    "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', '{}', '{}', FALSE)"
                ),
                {"id": inv_id, "fp": f"fp-{inv_id}", "key": key},
            )

    insert("INV-A", "shared-key")
    with pytest.raises(IntegrityError):
        insert("INV-B", "shared-key")

    # the index is partial, so any number of rows without a key remain legal
    insert("INV-C", None)
    insert("INV-D", None)


@requires_postgres
def test_legacy_postgres_database_is_migrated_without_losing_rows(pg_engine):
    """Simulates a database created before the unique index existed: missing
    later columns, a non-unique legacy index, and duplicate keys that would
    block the unique index. Nothing may be deleted."""
    with pg_engine.begin() as conn:
        conn.execute(
            text(
                f"""CREATE TABLE {TABLE} (
                    id VARCHAR(32) PRIMARY KEY,
                    fingerprint VARCHAR(64) NOT NULL UNIQUE,
                    idempotency_key VARCHAR(256),
                    status VARCHAR(32) NOT NULL,
                    stage VARCHAR(48) NOT NULL,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    repository VARCHAR(500) NOT NULL,
                    environment VARCHAR(500) NOT NULL,
                    test_name VARCHAR(1000) NOT NULL,
                    test_file VARCHAR(1000) NOT NULL,
                    classification VARCHAR(64),
                    severity VARCHAR(16),
                    release_risk VARCHAR(16),
                    confidence DOUBLE PRECISION,
                    created_at VARCHAR(40) NOT NULL,
                    updated_at VARCHAR(40) NOT NULL,
                    completed_at VARCHAR(40),
                    elapsed_ms INTEGER,
                    package_json TEXT NOT NULL,
                    doc_json TEXT NOT NULL
                )"""
            )
        )
        conn.execute(text(f"CREATE INDEX {LEGACY_INDEX} ON {TABLE} (idempotency_key)"))
        for n, (inv_id, key, created) in enumerate(
            [
                ("INV-OLD1", "dup", "2026-01-01T00:00:00Z"),
                ("INV-OLD2", "dup", "2026-01-02T00:00:00Z"),
                ("INV-OLD3", "unique", "2026-01-03T00:00:00Z"),
                ("INV-OLD4", None, "2026-01-04T00:00:00Z"),
            ]
        ):
            conn.execute(
                text(
                    f"INSERT INTO {TABLE} (id, fingerprint, idempotency_key, status, stage, "
                    "repository, environment, test_name, test_file, created_at, updated_at, "
                    "package_json, doc_json) VALUES (:id, :fp, :key, 'completed', 'done', "
                    "'r', 'e', 't', 'f', :created, :created, '{}', '{}')"
                ),
                {"id": inv_id, "fp": f"fp-{n}", "key": key, "created": created},
            )

    report = run_migrations(pg_engine)

    assert report.dialect == "postgresql"
    assert set(report.columns_added) == {"is_synthetic", "synthetic_family", "resolution_json"}
    assert report.index_created is True
    assert report.keys_repaired == 1
    assert report.rows_cleared == 1
    assert report.legacy_index_dropped is True

    with pg_engine.connect() as conn:
        names = index_names(conn, TABLE)
        assert IDEMPOTENCY_KEY_INDEX in names
        assert LEGACY_INDEX not in names

        # every investigation survives; only the duplicate key was cleared,
        # and the OLDEST row of the group keeps it
        rows = dict(
            conn.execute(
                text(f"SELECT id, idempotency_key FROM {TABLE} ORDER BY id")
            ).all()
        )
        assert set(rows) == {"INV-OLD1", "INV-OLD2", "INV-OLD3", "INV-OLD4"}
        assert rows["INV-OLD1"] == "dup"
        assert rows["INV-OLD2"] is None
        assert rows["INV-OLD3"] == "unique"


@requires_postgres
def test_postgres_migration_is_idempotent(pg_engine):
    from app.db.base import Base

    Base.metadata.create_all(pg_engine)
    run_migrations(pg_engine)
    second = run_migrations(pg_engine)
    assert second.changed is False


@requires_postgres
def test_full_ingestion_flow_against_postgres(make_client, sample_package):
    """The real proof: the whole API works on PostgreSQL, including the
    idempotency conflict that depends on the partial unique index."""
    engine = build_engine(POSTGRES_URL)
    with engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {TABLE} CASCADE"))
    engine.dispose()

    client = make_client(DATABASE_URL=POSTGRES_URL)

    created = client.post("/api/v1/investigations", json=sample_package)
    assert created.status_code == 202
    inv_id = created.json()["investigation_id"]

    fetched = client.get(f"/api/v1/investigations/{inv_id}")
    assert fetched.status_code == 200
    assert fetched.json()["testName"] == sample_package["test"]["name"]

    # identical package replays to the same investigation
    replay = client.post("/api/v1/investigations", json=sample_package)
    assert replay.json()["investigation_id"] == inv_id

    # same key, different evidence -> conflict, not a silent wrong answer
    key = {"Idempotency-Key": f"pg-{uuid.uuid4()}"}
    first = client.post("/api/v1/investigations", json=sample_package, headers=key)
    assert first.status_code == 202
    altered = dict(sample_package)
    altered["failure"] = dict(sample_package["failure"], message="A different failure")
    conflict = client.post("/api/v1/investigations", json=altered, headers=key)
    assert conflict.status_code == 409
