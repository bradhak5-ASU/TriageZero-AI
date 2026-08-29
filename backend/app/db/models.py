from sqlalchemy import Boolean, Float, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

#: Stable name shared by the model and the SQLite migration.
IDEMPOTENCY_KEY_INDEX = "ux_investigations_idempotency_key"


class InvestigationRecord(Base):
    """One investigation. Scalar columns exist for filtering/sorting; the
    full structured payloads live in JSON text columns:

    - package_json: the sanitized original failure package (audit trail)
    - doc_json: everything needed to rebuild the frontend Investigation object
      (evidence, root cause, recommended action, action history, timeline, …)
    """

    __tablename__ = "investigations"

    # Concurrent submissions carrying the same Idempotency-Key must race in the
    # database rather than creating duplicate investigations. The index is
    # partial so that the many rows with no key (the normal case) stay allowed.
    # `sqlite_where` and `postgresql_where` are dialect-specific spellings of
    # the same partial index. Both are declared so a fresh database gets the
    # identical constraint whichever backend it runs on — SQLite locally,
    # PostgreSQL in the cloud — and so app.db.migrations has one shape to
    # reconcile an existing database against.
    __table_args__ = (
        Index(
            IDEMPOTENCY_KEY_INDEX,
            "idempotency_key",
            unique=True,
            sqlite_where=text("idempotency_key IS NOT NULL"),
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # uniqueness is declared as the named partial index in __table_args__ so
    # that fresh databases and databases upgraded by app.db.migrations end up
    # with exactly the same schema
    idempotency_key: Mapped[str | None] = mapped_column(String(256), nullable=True)

    status: Mapped[str] = mapped_column(String(32), index=True)
    stage: Mapped[str] = mapped_column(String(48))
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    repository: Mapped[str] = mapped_column(String(500), index=True)
    environment: Mapped[str] = mapped_column(String(500), index=True)
    test_name: Mapped[str] = mapped_column(String(1000))
    test_file: Mapped[str] = mapped_column(String(1000))

    classification: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    severity: Mapped[str | None] = mapped_column(String(16), index=True, nullable=True)
    release_risk: Mapped[str | None] = mapped_column(String(16), index=True, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[str] = mapped_column(String(40), index=True)
    updated_at: Mapped[str] = mapped_column(String(40))
    completed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    elapsed_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    package_json: Mapped[str] = mapped_column(Text)
    doc_json: Mapped[str] = mapped_column(Text)

    # Internal-only provenance. Never part of the failure-package contract and
    # never sent to a model: seeded benchmark rows must be distinguishable from
    # genuine user investigations so cleanup can never touch real data.
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    synthetic_family: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # Human-reviewed outcome (JSON) — the only thing allowed to become "truth".
    resolution_json: Mapped[str | None] = mapped_column(Text, nullable=True)
