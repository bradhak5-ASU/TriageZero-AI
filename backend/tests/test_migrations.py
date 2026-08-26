"""Migration tests for the idempotency-key unique index.

These build a real legacy SQLite database — the milestone-2 schema, which has
a NON-unique index on idempotency_key — and inspect the result with
PRAGMA index_list / index_info rather than trusting repository lookups.
"""

import json
import sqlite3

import pytest
from sqlalchemy import create_engine, text

from app.db.base import Base
from app.db.migrations import (
    IDEMPOTENCY_KEY_INDEX,
    LEGACY_INDEX,
    index_names,
    run_sqlite_migrations,
)
from app.db.models import InvestigationRecord

# The milestone-2 table definition, verbatim in spirit: same columns, but the
# idempotency_key index is not unique.
LEGACY_SCHEMA = """
CREATE TABLE investigations (
    id VARCHAR(32) NOT NULL PRIMARY KEY,
    fingerprint VARCHAR(64) NOT NULL,
    idempotency_key VARCHAR(256),
    status VARCHAR(32) NOT NULL,
    stage VARCHAR(48) NOT NULL,
    retry_count INTEGER,
    repository VARCHAR(500) NOT NULL,
    environment VARCHAR(500) NOT NULL,
    test_name VARCHAR(1000) NOT NULL,
    test_file VARCHAR(1000) NOT NULL,
    classification VARCHAR(64),
    severity VARCHAR(16),
    release_risk VARCHAR(16),
    confidence FLOAT,
    created_at VARCHAR(40) NOT NULL,
    updated_at VARCHAR(40) NOT NULL,
    completed_at VARCHAR(40),
    elapsed_ms INTEGER,
    package_json TEXT NOT NULL,
    doc_json TEXT NOT NULL
);
CREATE UNIQUE INDEX ix_investigations_fingerprint ON investigations (fingerprint);
CREATE INDEX ix_investigations_idempotency_key ON investigations (idempotency_key);
CREATE INDEX ix_investigations_status ON investigations (status);
"""


def legacy_row(inv_id: str, fp: str, key: str | None, created_at: str) -> tuple:
    doc = {"evidence": {"message": f"failure for {inv_id}"}, "timeline": []}
    return (
        inv_id,
        fp,
        key,
        "completed",
        "action_recommendation",
        0,
        "novacart-target",
        "local",
        f"test for {inv_id}",
        "playwright-tests/tests/novacart-baseline.spec.ts",
        "backend_application_defect",
        "critical",
        "block_release",
        0.93,
        created_at,
        created_at,
        created_at,
        45000,
        json.dumps({"schema_version": "1.0", "source": "novacart-playwright"}),
        json.dumps(doc),
    )


def build_legacy_db(path, rows: list[tuple]) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(LEGACY_SCHEMA)
        conn.executemany(
            "INSERT INTO investigations VALUES (" + ",".join(["?"] * 20) + ")", rows
        )
        conn.commit()
    finally:
        conn.close()


def engine_for(path):
    return create_engine(f"sqlite:///{path}")


def pragma_index_list(path) -> dict[str, dict]:
    conn = sqlite3.connect(path)
    try:
        out = {}
        for _seq, name, unique, origin, partial in conn.execute(
            "PRAGMA index_list('investigations')"
        ):
            columns = [
                row[2] for row in conn.execute(f"PRAGMA index_info('{name}')")
            ]
            out[name] = {
                "unique": bool(unique),
                "origin": origin,
                "partial": bool(partial),
                "columns": columns,
            }
        return out
    finally:
        conn.close()


def fetch_rows(path) -> dict[str, dict]:
    conn = sqlite3.connect(path)
    try:
        conn.row_factory = sqlite3.Row
        return {
            row["id"]: dict(row)
            for row in conn.execute("SELECT * FROM investigations")
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# fresh database
# ---------------------------------------------------------------------------


def test_fresh_database_has_named_partial_unique_index(tmp_path):
    db = tmp_path / "fresh.db"
    engine = engine_for(db)
    Base.metadata.create_all(engine)
    report = run_sqlite_migrations(engine)
    engine.dispose()

    indexes = pragma_index_list(db)
    assert IDEMPOTENCY_KEY_INDEX in indexes
    entry = indexes[IDEMPOTENCY_KEY_INDEX]
    assert entry["unique"] is True
    assert entry["partial"] is True
    assert entry["columns"] == ["idempotency_key"]
    # create_all already built it from the model — the migration is a no-op
    assert report.changed is False


def test_fresh_database_schema_matches_migrated_legacy_schema(tmp_path):
    fresh = tmp_path / "fresh.db"
    engine = engine_for(fresh)
    Base.metadata.create_all(engine)
    run_sqlite_migrations(engine)
    engine.dispose()

    legacy = tmp_path / "legacy.db"
    build_legacy_db(legacy, [])
    legacy_engine = engine_for(legacy)
    Base.metadata.create_all(legacy_engine)
    run_sqlite_migrations(legacy_engine)
    legacy_engine.dispose()

    fresh_indexes = pragma_index_list(fresh)
    legacy_indexes = pragma_index_list(legacy)
    assert set(fresh_indexes) == set(legacy_indexes)
    # and the idempotency index has identical properties in both
    assert fresh_indexes[IDEMPOTENCY_KEY_INDEX] == legacy_indexes[IDEMPOTENCY_KEY_INDEX]


# ---------------------------------------------------------------------------
# legacy upgrade
# ---------------------------------------------------------------------------


def test_legacy_database_gains_named_unique_index(tmp_path):
    db = tmp_path / "legacy.db"
    build_legacy_db(
        db,
        [legacy_row("INV-A", "fp-a", "run-1", "2026-08-01T00:00:00Z")],
    )
    before = pragma_index_list(db)
    assert IDEMPOTENCY_KEY_INDEX not in before
    assert before[LEGACY_INDEX]["unique"] is False  # the actual milestone-2 gap

    engine = engine_for(db)
    report = run_sqlite_migrations(engine)
    engine.dispose()

    after = pragma_index_list(db)
    assert after[IDEMPOTENCY_KEY_INDEX]["unique"] is True
    assert after[IDEMPOTENCY_KEY_INDEX]["partial"] is True
    assert LEGACY_INDEX not in after  # redundant index removed
    assert report.index_created is True
    assert report.legacy_index_dropped is True


def test_existing_investigations_survive_migration(tmp_path):
    db = tmp_path / "legacy.db"
    rows = [
        legacy_row("INV-A", "fp-a", "run-1", "2026-08-01T00:00:00Z"),
        legacy_row("INV-B", "fp-b", None, "2026-08-02T00:00:00Z"),
        legacy_row("INV-C", "fp-c", "run-2", "2026-08-03T00:00:00Z"),
    ]
    build_legacy_db(db, rows)
    before = fetch_rows(db)

    engine = engine_for(db)
    run_sqlite_migrations(engine)
    engine.dispose()

    after = fetch_rows(db)
    assert set(after) == {"INV-A", "INV-B", "INV-C"}
    for inv_id, row in after.items():
        original = before[inv_id]
        # every pre-existing column keeps its value; the migration only ADDS
        # columns (which default to NULL/0) and never rewrites stored data
        for column, value in original.items():
            assert row[column] == value, f"{inv_id}.{column}"
        assert row["is_synthetic"] in (0, None)
        assert row["resolution_json"] is None


# ---------------------------------------------------------------------------
# duplicate repair
# ---------------------------------------------------------------------------


def test_duplicate_keys_repaired_deterministically(tmp_path):
    db = tmp_path / "dupes.db"
    build_legacy_db(
        db,
        [
            legacy_row("INV-NEW", "fp-3", "dup", "2026-08-03T00:00:00Z"),
            legacy_row("INV-OLD", "fp-1", "dup", "2026-08-01T00:00:00Z"),
            legacy_row("INV-MID", "fp-2", "dup", "2026-08-02T00:00:00Z"),
            legacy_row("INV-KEEP", "fp-4", "solo", "2026-08-04T00:00:00Z"),
        ],
    )

    engine = engine_for(db)
    report = run_sqlite_migrations(engine)
    engine.dispose()

    rows = fetch_rows(db)
    # oldest by created_at keeps the key; later duplicates are cleared
    assert rows["INV-OLD"]["idempotency_key"] == "dup"
    assert rows["INV-MID"]["idempotency_key"] is None
    assert rows["INV-NEW"]["idempotency_key"] is None
    # an unaffected key is untouched
    assert rows["INV-KEEP"]["idempotency_key"] == "solo"
    # no investigation was deleted
    assert set(rows) == {"INV-OLD", "INV-MID", "INV-NEW", "INV-KEEP"}
    assert report.keys_repaired == 1
    assert report.rows_cleared == 2


def test_duplicate_repair_preserves_investigation_content(tmp_path):
    db = tmp_path / "dupes.db"
    build_legacy_db(
        db,
        [
            legacy_row("INV-OLD", "fp-1", "dup", "2026-08-01T00:00:00Z"),
            legacy_row("INV-NEW", "fp-2", "dup", "2026-08-02T00:00:00Z"),
        ],
    )
    before = fetch_rows(db)

    engine = engine_for(db)
    run_sqlite_migrations(engine)
    engine.dispose()

    after = fetch_rows(db)
    cleared = after["INV-NEW"]
    assert cleared["idempotency_key"] is None
    # everything else about the repaired row is identical
    for field in (
        "id",
        "fingerprint",
        "package_json",
        "doc_json",
        "classification",
        "severity",
        "release_risk",
        "confidence",
        "created_at",
        "completed_at",
        "status",
    ):
        assert cleared[field] == before["INV-NEW"][field], field


def test_ties_on_created_at_are_broken_by_id(tmp_path):
    db = tmp_path / "ties.db"
    same_time = "2026-08-01T00:00:00Z"
    build_legacy_db(
        db,
        [
            legacy_row("INV-ZZZ", "fp-z", "dup", same_time),
            legacy_row("INV-AAA", "fp-a", "dup", same_time),
        ],
    )

    engine = engine_for(db)
    run_sqlite_migrations(engine)
    engine.dispose()

    rows = fetch_rows(db)
    assert rows["INV-AAA"]["idempotency_key"] == "dup"
    assert rows["INV-ZZZ"]["idempotency_key"] is None


# ---------------------------------------------------------------------------
# idempotency of the migration itself
# ---------------------------------------------------------------------------


def test_running_migration_twice_is_safe(tmp_path):
    db = tmp_path / "legacy.db"
    build_legacy_db(
        db,
        [
            legacy_row("INV-OLD", "fp-1", "dup", "2026-08-01T00:00:00Z"),
            legacy_row("INV-NEW", "fp-2", "dup", "2026-08-02T00:00:00Z"),
        ],
    )

    engine = engine_for(db)
    first = run_sqlite_migrations(engine)
    snapshot = fetch_rows(db)
    second = run_sqlite_migrations(engine)
    engine.dispose()

    assert first.changed is True
    # a second run reports zero repairs and changes nothing
    assert second.keys_repaired == 0
    assert second.rows_cleared == 0
    assert second.index_created is False
    assert second.legacy_index_dropped is False
    assert second.changed is False
    assert fetch_rows(db) == snapshot


def test_already_clean_database_upgrade_is_a_noop(tmp_path):
    db = tmp_path / "clean.db"
    engine = engine_for(db)
    Base.metadata.create_all(engine)
    run_sqlite_migrations(engine)
    snapshot = pragma_index_list(db)

    report = run_sqlite_migrations(engine)
    engine.dispose()

    assert report.changed is False
    assert pragma_index_list(db) == snapshot


# ---------------------------------------------------------------------------
# the constraint actually bites after migration
# ---------------------------------------------------------------------------


def _insert(conn, inv_id, fingerprint, key):
    conn.execute(
        text(
            "INSERT INTO investigations (id, fingerprint, idempotency_key, status, "
            "stage, retry_count, repository, environment, test_name, test_file, "
            "created_at, updated_at, package_json, doc_json) VALUES "
            "(:id, :fp, :key, 'received', 'evidence_received', 0, 'r', 'local', "
            "'t', 'f', '2026-08-05T00:00:00Z', '2026-08-05T00:00:00Z', '{}', '{}')"
        ),
        {"id": inv_id, "fp": fingerprint, "key": key},
    )


def test_duplicate_key_insert_fails_after_migration(tmp_path):
    from sqlalchemy.exc import IntegrityError

    db = tmp_path / "legacy.db"
    build_legacy_db(db, [])
    engine = engine_for(db)
    run_sqlite_migrations(engine)

    with engine.begin() as conn:
        _insert(conn, "INV-1", "fp-1", "same-key")

    with pytest.raises(IntegrityError), engine.begin() as conn:
        _insert(conn, "INV-2", "fp-2", "same-key")

    engine.dispose()
    assert set(fetch_rows(db)) == {"INV-1"}


def test_multiple_null_keys_remain_allowed_after_migration(tmp_path):
    db = tmp_path / "legacy.db"
    build_legacy_db(db, [])
    engine = engine_for(db)
    run_sqlite_migrations(engine)

    with engine.begin() as conn:
        _insert(conn, "INV-1", "fp-1", None)
        _insert(conn, "INV-2", "fp-2", None)
        _insert(conn, "INV-3", "fp-3", None)

    engine.dispose()
    assert len(fetch_rows(db)) == 3


def test_fingerprint_uniqueness_still_enforced_after_migration(tmp_path):
    from sqlalchemy.exc import IntegrityError

    db = tmp_path / "legacy.db"
    build_legacy_db(db, [])
    engine = engine_for(db)
    run_sqlite_migrations(engine)

    with engine.begin() as conn:
        _insert(conn, "INV-1", "same-fp", None)

    with pytest.raises(IntegrityError), engine.begin() as conn:
        _insert(conn, "INV-2", "same-fp", None)

    engine.dispose()
    assert set(fetch_rows(db)) == {"INV-1"}


def test_migration_reports_index_via_helper(tmp_path):
    db = tmp_path / "legacy.db"
    build_legacy_db(db, [])
    engine = engine_for(db)
    run_sqlite_migrations(engine)
    with engine.connect() as conn:
        names = index_names(conn, InvestigationRecord.__tablename__)
    engine.dispose()
    assert IDEMPOTENCY_KEY_INDEX in names


# ---------------------------------------------------------------------------
# a migrated legacy row must remain serveable, not just present
# ---------------------------------------------------------------------------


def test_legacy_row_with_partial_document_is_still_serializable(tmp_path, monkeypatch):
    """A row whose stored document predates later fields must not break the
    list endpoint: missing parts fall back to empty values."""
    from fastapi.testclient import TestClient

    from app.core.config import get_settings
    from app.db.session import reset_db_state
    from app.main import create_app

    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(db)
    conn.executescript(LEGACY_SCHEMA)
    row = list(legacy_row("INV-PARTIAL", "fp-p", "k-1", "2026-08-01T00:00:00Z"))
    row[-1] = json.dumps({"evidence": {"message": "only a message"}})  # sparse doc
    conn.execute("INSERT INTO investigations VALUES (" + ",".join(["?"] * 20) + ")", row)
    conn.commit()
    conn.close()

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.setenv("LOCAL_PROCESSING_DELAY_MS", "0")
    get_settings.cache_clear()
    reset_db_state()

    with TestClient(create_app()) as client:
        listing = client.get("/api/v1/investigations")
        assert listing.status_code == 200
        ids = [item["id"] for item in listing.json()]
        assert "INV-PARTIAL" in ids

        detail = client.get("/api/v1/investigations/INV-PARTIAL")
        assert detail.status_code == 200
        payload = detail.json()
        assert payload["evidence"]["message"] == "only a message"
        assert payload["evidence"]["network"] == []
        assert payload["timeline"] == []
        assert payload["branch"] == ""

    reset_db_state()
    get_settings.cache_clear()

    # and the migration still applied its index to that database
    assert IDEMPOTENCY_KEY_INDEX in pragma_index_list(db)
