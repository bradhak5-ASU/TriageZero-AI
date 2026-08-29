"""Standalone migration entry point.

    python -m app.db.migrate            # uses DATABASE_URL from the environment
    python -m app.db.migrate --url ...  # explicit target
    python -m app.db.migrate --check    # report only, change nothing

Running migrations as their own step - rather than only on app startup - is
what makes a Cloud Run deploy safe. Startup migration still happens (a fresh
instance must be able to create its tables), but a deploy that would fail on
schema changes should fail in a job you can read the logs of, before traffic
is shifted onto the new revision.

Output is counts and index names only. No investigation content, no evidence,
no credentials - this runs in deploy logs, which are widely readable.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.db.base import Base
from app.db.migrations import (
    IDEMPOTENCY_KEY_INDEX,
    SUPPORTED_DIALECTS,
    TABLE,
    index_names,
    run_migrations,
)
from app.db.session import build_engine, normalize_database_url


def _redacted(url: str) -> str:
    """A URL safe to print: scheme and host only, never user:password."""
    scheme, _, rest = url.partition("://")
    host = rest.rpartition("@")[2] if "@" in rest else rest
    return f"{scheme}://{host}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply TriageZero schema migrations.")
    parser.add_argument(
        "--url",
        default=None,
        help="Database URL. Defaults to the configured DATABASE_URL.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report the current schema state and exit without changing anything.",
    )
    args = parser.parse_args(argv)

    url = normalize_database_url(args.url or get_settings().resolved_database_url)
    engine = build_engine(url)
    dialect = engine.dialect.name

    print(f"target:  {_redacted(url)}")
    print(f"dialect: {dialect}")

    if dialect not in SUPPORTED_DIALECTS:
        print(f"ERROR: unsupported dialect {dialect!r}; expected one of {SUPPORTED_DIALECTS}")
        return 2

    try:
        return _apply(engine, args.check)
    except SQLAlchemyError as exc:
        # A deploy log should show one actionable line, not a 30KB traceback -
        # and the traceback of a connection failure can carry the DSN. Only
        # the driver's own message is printed, and never the URL.
        print(f"ERROR: database operation failed: {type(exc).__name__}")
        detail = str(getattr(exc, "orig", exc)).strip().splitlines()
        if detail:
            print(f"       {detail[0]}")
        print(
            "       Check DATABASE_URL, the Cloud SQL connection, "
            "and the database user's grants."
        )
        return 1


def _apply(engine: Engine, check: bool) -> int:
    """The migration itself. Split out so main() can turn any database error
    into one readable line instead of a traceback."""
    if check:
        with engine.connect() as conn:
            if not inspect(conn).has_table(TABLE):
                print(f"table {TABLE!r}: absent (a first deploy will create it)")
                return 0
            names = index_names(conn, TABLE)
            present = "present" if IDEMPOTENCY_KEY_INDEX in names else "MISSING"
            print(f"table {TABLE!r}: present")
            print(f"unique idempotency index: {present}")
            print(f"indexes: {len(names)}")
        return 0

    # create_all() is safe to run against an existing database: it creates
    # missing tables and touches nothing that already exists.
    Base.metadata.create_all(engine)
    report = run_migrations(engine)

    if not report.changed:
        print("schema already up to date; no changes applied")
        return 0

    print("schema migrated:")
    if report.columns_added:
        print(f"  columns added:              {', '.join(report.columns_added)}")
    if report.index_created:
        print(f"  unique index created:       {IDEMPOTENCY_KEY_INDEX}")
    if report.keys_repaired:
        print(f"  duplicate keys repaired:    {report.keys_repaired}")
        print(f"  rows with key cleared:      {report.rows_cleared}")
    if report.secondary_indexes_created:
        print(f"  secondary indexes created:  {', '.join(report.secondary_indexes_created)}")
    if report.legacy_index_dropped:
        print("  legacy index dropped:       yes")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
