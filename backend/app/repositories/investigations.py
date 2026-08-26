from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models import InvestigationRecord

ACTIVE_STATUSES = ("received", "queued", "analyzing")


def get(session: Session, investigation_id: str) -> InvestigationRecord | None:
    return session.get(InvestigationRecord, investigation_id)


def get_by_fingerprint(session: Session, fingerprint: str) -> InvestigationRecord | None:
    return session.scalar(
        select(InvestigationRecord).where(InvestigationRecord.fingerprint == fingerprint)
    )


def get_by_idempotency_key(session: Session, key: str) -> InvestigationRecord | None:
    return session.scalar(
        select(InvestigationRecord).where(InvestigationRecord.idempotency_key == key)
    )


def list_records(
    session: Session,
    *,
    status: str | None = None,
    classification: str | None = None,
    severity: str | None = None,
    release_risk: str | None = None,
    repository: str | None = None,
    environment: str | None = None,
    search: str | None = None,
    limit: int = 200,
    offset: int = 0,
    sort: str = "newest",
) -> list[InvestigationRecord]:
    query = select(InvestigationRecord)
    if status:
        query = query.where(InvestigationRecord.status == status)
    if classification:
        query = query.where(InvestigationRecord.classification == classification)
    if severity:
        query = query.where(InvestigationRecord.severity == severity)
    if release_risk:
        query = query.where(InvestigationRecord.release_risk == release_risk)
    if repository:
        query = query.where(InvestigationRecord.repository == repository)
    if environment:
        query = query.where(InvestigationRecord.environment == environment)
    if search:
        needle = f"%{search.lower()}%"
        query = query.where(
            or_(
                func.lower(InvestigationRecord.test_name).like(needle),
                func.lower(InvestigationRecord.id).like(needle),
                func.lower(InvestigationRecord.repository).like(needle),
            )
        )
    order = (
        InvestigationRecord.created_at.asc()
        if sort == "oldest"
        else InvestigationRecord.created_at.desc()
    )
    return list(session.scalars(query.order_by(order).limit(limit).offset(offset)))


def others_with_results(
    session: Session, exclude_id: str, limit: int = 200
) -> list[InvestigationRecord]:
    query = (
        select(InvestigationRecord)
        .where(
            InvestigationRecord.id != exclude_id,
            InvestigationRecord.status.in_(("completed", "needs_review")),
        )
        .order_by(InvestigationRecord.created_at.desc())
        .limit(limit)
    )
    return list(session.scalars(query))


def count_active(session: Session) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(InvestigationRecord)
            .where(InvestigationRecord.status.in_(ACTIVE_STATUSES))
        )
        or 0
    )


def created_since(session: Session, iso_cutoff: str) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(InvestigationRecord)
            .where(InvestigationRecord.created_at >= iso_cutoff)
        )
        or 0
    )


def completed_since(session: Session, iso_cutoff: str) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(InvestigationRecord)
            .where(
                InvestigationRecord.completed_at.is_not(None),
                InvestigationRecord.completed_at >= iso_cutoff,
            )
        )
        or 0
    )


def pending_ids(session: Session) -> list[str]:
    return list(
        session.scalars(
            select(InvestigationRecord.id).where(
                InvestigationRecord.status.in_(ACTIVE_STATUSES)
            )
        )
    )


def count_corpus(session: Session) -> int:
    """Investigations eligible for retrieval: seeded synthetic benchmark rows
    plus genuinely human-resolved ones."""
    return (
        session.scalar(
            select(func.count())
            .select_from(InvestigationRecord)
            .where(
                or_(
                    InvestigationRecord.is_synthetic.is_(True),
                    InvestigationRecord.resolution_json.is_not(None),
                )
            )
        )
        or 0
    )


def synthetic_ids(session: Session, family: str | None = None) -> list[str]:
    """Ids of seeded synthetic rows only — never genuine investigations."""
    query = select(InvestigationRecord.id).where(InvestigationRecord.is_synthetic.is_(True))
    if family:
        query = query.where(InvestigationRecord.synthetic_family == family)
    return list(session.scalars(query))
