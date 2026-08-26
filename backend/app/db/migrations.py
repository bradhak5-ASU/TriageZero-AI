"""Schema migrations for the local SQLite store.

`Base.metadata.create_all()` creates missing tables but never alters existing
ones, so a database created by an earlier milestone keeps its old schema even
after the model changes. The uniqueness guarantee behind Idempotency-Key
handling is therefore not actually enforced on an upgraded database unless we
apply it explicitly — that is what this module does.

Everything here is idempotent: running it on a fresh database, on an already
migrated database, or repeatedly, performs no further changes.
"""

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from app.core.logging import log_event
from app.db.models import IDEMPOTENCY_KEY_INDEX, InvestigationRecord

TABLE = InvestigationRecord.__tablename__

# Index SQLAlchemy auto-created for the previous `index=True` column. On a
# milestone-2 database it is non-unique; it is redundant once the named partial
# unique index exists, and dropping it makes upgraded schemas match fresh ones.
LEGACY_INDEX = "ix_investigations_idempotency_key"


@dataclass(frozen=True)
class MigrationReport:
    """Counts only — never package contents or private evidence."""

    columns_added: tuple[str, ...] = ()
    keys_repaired: int = 0
    rows_cleared: int = 0
    index_created: bool = False
    legacy_index_dropped: bool = False
    secondary_indexes_created: tuple[str, ...] = ()

    @property
    def changed(self) -> bool:
        return bool(
            self.columns_added
            or self.keys_repaired
            or self.rows_cleared
            or self.index_created
            or self.legacy_index_dropped
            or self.secondary_indexes_created
        )


def _table_exists(conn: Connection, table: str) -> bool:
    row = conn.execute(
        text("SELECT name FROM sqlite_master WHERE type = 'table' AND name = :t"),
        {"t": table},
    ).first()
    return row is not None


def index_names(conn: Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(text(f"PRAGMA index_list('{table}')"))}


# Columns added after the first release, with the DDL to create them.
# ALTER TABLE ... ADD COLUMN is the only schema change SQLite supports well,
# and it preserves every existing row.
LATER_COLUMNS: tuple[tuple[str, str], ...] = (
    ("is_synthetic", "BOOLEAN DEFAULT 0"),
    ("synthetic_family", "VARCHAR(64)"),
    ("resolution_json", "TEXT"),
)


def _column_names(conn: Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(text(f"PRAGMA table_info(\'{table}\')"))}


def _add_missing_columns(conn: Connection) -> tuple[str, ...]:
    """Add columns introduced after this database was created."""
    existing = _column_names(conn, TABLE)
    added: list[str] = []
    for name, ddl in LATER_COLUMNS:
        if name not in existing:
            conn.execute(text(f"ALTER TABLE {TABLE} ADD COLUMN {name} {ddl}"))
            added.append(name)
    return tuple(added)


def _create_missing_secondary_indexes(conn: Connection) -> tuple[str, ...]:
    """Create any other model-declared index the table is missing.

    A table that already exists is skipped wholesale by create_all(), so an
    upgraded database can also lack the secondary indexes added since it was
    created. Reconciling them here keeps fresh and upgraded schemas identical.
    """
    existing = index_names(conn, TABLE)
    created: list[str] = []
    for index in sorted(InvestigationRecord.__table__.indexes, key=lambda i: i.name or ""):
        if index.name == IDEMPOTENCY_KEY_INDEX or index.name in existing:
            continue  # the unique key index is handled explicitly above
        index.create(bind=conn)
        created.append(str(index.name))
    return tuple(created)


def _duplicate_keys(conn: Connection) -> list[str]:
    rows = conn.execute(
        text(
            f"SELECT idempotency_key FROM {TABLE} "
            "WHERE idempotency_key IS NOT NULL "
            "GROUP BY idempotency_key HAVING COUNT(*) > 1"
        )
    )
    return [row[0] for row in rows]


def _repair_duplicate_keys(conn: Connection) -> tuple[int, int]:
    """Clear duplicate non-null idempotency keys, keeping the key on the oldest
    investigation of each group.

    Ordering is (created_at, id) so the outcome is deterministic even when two
    rows share a timestamp. Investigations are never deleted and nothing else
    about them is touched — only the duplicate key is set to NULL, which is the
    state a request without an Idempotency-Key would have produced.
    """
    keys = _duplicate_keys(conn)
    rows_cleared = 0
    for key in keys:
        ids = [
            row[0]
            for row in conn.execute(
                text(
                    f"SELECT id FROM {TABLE} WHERE idempotency_key = :k "
                    "ORDER BY created_at ASC, id ASC"
                ),
                {"k": key},
            )
        ]
        losers = ids[1:]  # ids[0] is the oldest — it keeps the key
        for loser in losers:
            conn.execute(
                text(f"UPDATE {TABLE} SET idempotency_key = NULL WHERE id = :id"),
                {"id": loser},
            )
        rows_cleared += len(losers)
    return len(keys), rows_cleared


def run_sqlite_migrations(engine: Engine) -> MigrationReport:
    """Bring an existing SQLite database up to the current intended schema.

    Applied in one transaction: repair duplicate keys first (a unique index
    cannot be built over duplicates), then create the named partial unique
    index, then drop the redundant legacy index.
    """
    if engine.dialect.name != "sqlite":
        return MigrationReport()

    with engine.begin() as conn:
        if not _table_exists(conn, TABLE):
            return MigrationReport()

        columns_added = _add_missing_columns(conn)

        existing = index_names(conn, TABLE)
        needs_index = IDEMPOTENCY_KEY_INDEX not in existing

        keys_repaired = rows_cleared = 0
        if needs_index:
            keys_repaired, rows_cleared = _repair_duplicate_keys(conn)
            conn.execute(
                text(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS {IDEMPOTENCY_KEY_INDEX} "
                    f"ON {TABLE} (idempotency_key) WHERE idempotency_key IS NOT NULL"
                )
            )

        secondary = _create_missing_secondary_indexes(conn)

        drop_legacy = LEGACY_INDEX in existing
        if drop_legacy:
            conn.execute(text(f"DROP INDEX IF EXISTS {LEGACY_INDEX}"))

        report = MigrationReport(
            columns_added=columns_added,
            keys_repaired=keys_repaired,
            rows_cleared=rows_cleared,
            index_created=needs_index,
            legacy_index_dropped=drop_legacy,
            secondary_indexes_created=secondary,
        )

    if report.changed:
        log_event(
            "sqlite schema migrated",
            index_created=report.index_created,
            legacy_index_dropped=report.legacy_index_dropped,
            columns_added=len(report.columns_added),
            duplicate_keys_repaired=report.keys_repaired,
            rows_key_cleared=report.rows_cleared,
            secondary_indexes_created=len(report.secondary_indexes_created),
        )
    return report
