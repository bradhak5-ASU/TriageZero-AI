"""Investigation domain logic: creation, serialization, similarity,
retries, and recorded action decisions."""

import json
import secrets
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.retrieval import (
    RetrievalCandidate,
    console_signature,
    default_index,
    error_terms,
    normalize_endpoint,
    stack_component,
    status_family,
    to_public,
)
from app.ai.safety import redact
from app.ai.schemas import CLASSIFICATIONS
from app.core.errors import AppError
from app.db.models import InvestigationRecord
from app.repositories import investigations as repo
from app.schemas.failure_package import FailurePackage
from app.services.evidence import (
    build_artifact_metadata,
    package_fingerprint,
    sanitized_package_dict,
)


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def new_investigation_id() -> str:
    """Public IDs are collision-resistant and never sequential."""
    return f"INV-{secrets.token_hex(4).upper()}"


EMPTY_EVIDENCE: dict[str, Any] = {
    "expected": "",
    "actual": "",
    "message": "",
    "stackTrace": "",
    "network": [],
    "consoleErrors": [],
    "artifacts": [],
}


def _doc(record: InvestigationRecord) -> dict[str, Any]:
    return json.loads(record.doc_json)


def _evidence(doc: dict[str, Any]) -> dict[str, Any]:
    """Evidence with every expected key present.

    Rows persisted by an older build may not carry the full document shape;
    one such row must not break the list endpoint, so missing parts fall back
    to empty values rather than raising.
    """
    stored = doc.get("evidence")
    if not isinstance(stored, dict):
        return dict(EMPTY_EVIDENCE)
    return {**EMPTY_EVIDENCE, **stored}


def _save_doc(record: InvestigationRecord, doc: dict[str, Any]) -> None:
    record.doc_json = json.dumps(doc)
    record.updated_at = now_iso()


def append_timeline(doc: dict[str, Any], label: str, detail: str | None = None) -> None:
    doc["timeline"].append(
        {
            "id": f"t{len(doc['timeline'])}",
            "label": label,
            "at": now_iso(),
            **({"detail": detail} if detail else {}),
        }
    )


def create_investigation(
    session: Session, pkg: FailurePackage, idempotency_key: str | None
) -> tuple[InvestigationRecord, bool]:
    """Persist a new investigation, or return the existing one for a
    duplicate package / idempotency key. Returns (record, created)."""
    try:
        artifacts = build_artifact_metadata(pkg)
        sanitized = sanitized_package_dict(pkg)
    except ValueError as exc:
        raise AppError("invalid_artifact_path", str(exc), status_code=422) from exc

    fingerprint = package_fingerprint(sanitized)

    if idempotency_key:
        existing = repo.get_by_idempotency_key(session, idempotency_key)
        if existing:
            # a replay of the same package is idempotent; the same key carrying
            # DIFFERENT evidence is a client error, not a silent no-op
            if existing.fingerprint == fingerprint:
                return existing, False
            raise AppError(
                "idempotency_key_conflict",
                (
                    f"Idempotency-Key '{idempotency_key}' was already used for "
                    f"investigation {existing.id} with different evidence. "
                    "Use a new key for a different failure package."
                ),
                status_code=409,
                details={"investigation_id": existing.id},
            )
    existing = repo.get_by_fingerprint(session, fingerprint)
    if existing:
        # The same package arriving again with a key it did not previously
        # carry: adopt the key so a LATER reuse with different evidence is
        # still detectable as a conflict. A key already on the record wins.
        if idempotency_key and existing.idempotency_key is None:
            existing.idempotency_key = idempotency_key
            try:
                session.commit()
            except IntegrityError:
                session.rollback()  # another record already claimed that key
        return existing, False

    created_at = now_iso()
    doc: dict[str, Any] = {
        "branch": pkg.repository.branch,
        "commitSha": pkg.repository.commit_sha,
        "runId": pkg.run.run_id,
        "browser": pkg.environment.browser,
        "trigger": pkg.run.trigger,
        "evidence": {
            "expected": pkg.failure.expected,
            "actual": pkg.failure.actual,
            "message": pkg.failure.message,
            "stackTrace": pkg.failure.stack_trace,
            "network": [
                {"method": n.method, "url": n.url, "status": n.status}
                for n in pkg.network_evidence
            ],
            "consoleErrors": list(pkg.console_errors),
            "artifacts": artifacts,
        },
        "rootCause": None,
        "recommendedAction": None,
        "actionHistory": [],
        "timeline": [],
        "actionTaken": None,
        "evidenceHighlights": [],
    }
    append_timeline(doc, "Failure received")
    append_timeline(doc, "Evidence validated", "Schema and oracle-separation checks passed")

    record = InvestigationRecord(
        id=new_investigation_id(),
        fingerprint=fingerprint,
        idempotency_key=idempotency_key,
        status="received",
        stage="evidence_received",
        retry_count=0,
        repository=pkg.repository.name,
        environment=pkg.environment.name,
        test_name=pkg.test.name,
        test_file=pkg.test.file,
        created_at=created_at,
        updated_at=created_at,
        package_json=json.dumps(sanitized),
        doc_json=json.dumps(doc),
    )
    session.add(record)
    try:
        session.commit()
    except IntegrityError:
        # another request inserted the same fingerprint or key concurrently —
        # the unique constraints make the database the arbiter
        session.rollback()
        winner = (
            repo.get_by_idempotency_key(session, idempotency_key)
            if idempotency_key
            else None
        ) or repo.get_by_fingerprint(session, fingerprint)
        if winner is None:
            raise
        if idempotency_key and winner.fingerprint != fingerprint:
            raise AppError(
                "idempotency_key_conflict",
                (
                    f"Idempotency-Key '{idempotency_key}' was already used for "
                    f"investigation {winner.id} with different evidence."
                ),
                status_code=409,
                details={"investigation_id": winner.id},
            ) from None
        return winner, False
    return record, True


# ---------------------------------------------------------------------------
# similarity — delegated to the explainable weighted retrieval service
# ---------------------------------------------------------------------------


def _failing_entry(evidence: dict[str, Any]) -> dict[str, Any] | None:
    for entry in evidence.get("network", []) or []:
        status = entry.get("status", 0)
        if status == 0 or status >= 400:
            return entry
    return None


def _to_candidate(record: InvestigationRecord) -> RetrievalCandidate:
    doc = _doc(record)
    evidence = _evidence(doc)
    failing = _failing_entry(evidence) or {}
    root = doc.get("rootCause") or {}
    action = doc.get("recommendedAction") or {}
    resolution = doc.get("humanResolution") or {}
    return RetrievalCandidate(
        investigation_id=record.id,
        repository=record.repository,
        test_file=record.test_file,
        classification=record.classification,
        endpoint=normalize_endpoint(failing.get("url")),
        status_family=status_family(failing.get("status")),
        browser=str(doc.get("browser", "")),
        environment=record.environment,
        error_terms=error_terms(evidence.get("message", "")),
        stack_component=stack_component(evidence.get("stackTrace")),
        console_signature=console_signature(evidence.get("consoleErrors")),
        expected=str(evidence.get("expected", "")),
        actual=str(evidence.get("actual", "")),
        root_cause_summary=(
            resolution.get("resolutionSummary")
            or root.get("summary")
            or "No root-cause summary recorded."
        ),
        resolution=(
            resolution.get("resolutionSummary")
            or action.get("action")
            or "Tracked locally — no external resolution recorded"
        ),
        date=record.completed_at or record.created_at,
        is_synthetic=bool(record.is_synthetic),
    )


def retrieval_corpus(session: Session, exclude_id: str) -> list[RetrievalCandidate]:
    """Investigations eligible to inform a new analysis.

    Only *resolved* history qualifies: a completed investigation that a human
    reviewed, or a seeded synthetic benchmark case. An unreviewed AI prediction
    never becomes "truth" for a later one.
    """
    corpus: list[RetrievalCandidate] = []
    for other in repo.others_with_results(session, exclude_id):
        doc = _doc(other)
        human_reviewed = bool(doc.get("humanResolution"))
        if not (human_reviewed or other.is_synthetic):
            continue
        corpus.append(_to_candidate(other))
    return corpus


def retrieve_similar(session: Session, record: InvestigationRecord) -> list[dict[str, Any]]:
    """Ranked similar historical failures with the signals that matched.

    Usable mid-pipeline: the classification signal simply does not fire until
    this investigation has been classified.
    """
    query = _to_candidate(record)
    matches = default_index.search(query, retrieval_corpus(session, record.id))
    return [to_public(value, fired, candidate) for value, fired, candidate in matches]


def similar_failures(session: Session, record: InvestigationRecord) -> list[dict[str, Any]]:
    """Serialization view — only shown once the investigation has a result."""
    if record.status not in ("completed", "needs_review"):
        return []
    return retrieve_similar(session, record)


# ---------------------------------------------------------------------------
# serialization to the frontend Investigation shape
# ---------------------------------------------------------------------------


def serialize(session: Session, record: InvestigationRecord) -> dict[str, Any]:
    doc = _doc(record)
    return {
        "id": record.id,
        "status": record.status,
        "stage": record.stage,
        "testName": record.test_name,
        "testFile": record.test_file,
        "repository": record.repository,
        "branch": doc.get("branch", ""),
        "commitSha": doc.get("commitSha", ""),
        "runId": doc.get("runId", ""),
        "runUrl": None,
        "browser": doc.get("browser", "chromium"),
        "environment": record.environment,
        "trigger": doc.get("trigger", "unknown"),
        "createdAt": record.created_at,
        "completedAt": record.completed_at,
        "elapsedMs": record.elapsed_ms,
        "classification": record.classification,
        "confidence": record.confidence,
        "severity": record.severity,
        "releaseRisk": record.release_risk,
        "rootCause": doc.get("rootCause"),
        "evidence": _evidence(doc),
        "timeline": doc.get("timeline", []),
        "similarFailures": similar_failures(session, record),
        "recommendedAction": doc.get("recommendedAction"),
        "actionHistory": doc.get("actionHistory", []),
        "actionTaken": doc.get("actionTaken"),
        "aiMetadata": doc.get("aiMetadata"),
        "humanResolution": doc.get("humanResolution"),
        "originalPrediction": doc.get("originalPrediction"),
        "isSynthetic": bool(record.is_synthetic),
    }


# ---------------------------------------------------------------------------
# retries and recorded decisions
# ---------------------------------------------------------------------------


def prepare_retry(session: Session, record: InvestigationRecord) -> None:
    if record.status in repo.ACTIVE_STATUSES:
        raise AppError(
            "retry_conflict",
            f"Investigation {record.id} is actively processing and cannot be retried yet.",
            status_code=409,
        )
    doc = _doc(record)
    doc.setdefault("timeline", [])
    append_timeline(doc, "Retry requested", f"Retry #{record.retry_count + 1} — analysis re-run")
    doc["rootCause"] = None
    doc["recommendedAction"] = None
    doc["actionTaken"] = None
    record.retry_count += 1
    record.status = "received"
    record.stage = "evidence_received"
    record.classification = None
    record.severity = None
    record.release_risk = None
    record.confidence = None
    record.completed_at = None
    record.elapsed_ms = None
    _save_doc(record, doc)
    session.commit()


def record_decision(
    session: Session, record: InvestigationRecord, decision: str
) -> None:
    doc = _doc(record)
    doc.setdefault("actionHistory", [])
    action = doc.get("recommendedAction")
    if not action:
        raise AppError(
            "no_recommended_action",
            f"Investigation {record.id} has no recommended action to decide on.",
            status_code=409,
        )
    state = "approved" if decision == "approve" else "rejected"
    action["approvalState"] = state
    doc["actionHistory"].append(
        {
            "id": f"a{len(doc['actionHistory']) + 1}",
            "at": now_iso(),
            "actor": "local-operator",
            "action": f"{'Approved' if decision == 'approve' else 'Rejected'} recommended action",
            "state": state,
            "note": "Decision recorded locally — no external action executed",
        }
    )
    doc["actionTaken"] = (
        "Approved — execution available after GitHub integration"
        if state == "approved"
        else "Recommendation rejected by operator"
    )
    _save_doc(record, doc)
    session.commit()


# ---------------------------------------------------------------------------
# human-reviewed resolution — the only path by which a case becomes "truth"
# ---------------------------------------------------------------------------

RESOLUTION_TEXT_LIMIT = 2000
RESOLVER_LIMIT = 120


def record_resolution(
    session: Session,
    record: InvestigationRecord,
    *,
    classification: str,
    severity: str,
    release_risk: str,
    resolution_summary: str,
    responsible_component: str,
    resolver: str,
) -> None:
    """Attach a human-reviewed outcome to an investigation.

    The AI's original prediction is snapshotted the first time a human resolves
    the case, so prediction-versus-outcome accuracy stays measurable and the
    model can never overwrite its own scorecard. Corrections append to an audit
    trail rather than replacing history.
    """
    if classification not in CLASSIFICATIONS:
        raise AppError(
            "invalid_resolution",
            f"classification must be one of {', '.join(CLASSIFICATIONS)}",
            status_code=422,
        )
    if severity not in ("critical", "high", "medium", "low"):
        raise AppError("invalid_resolution", "invalid severity", status_code=422)
    if release_risk not in ("block_release", "high", "moderate", "low", "none"):
        raise AppError("invalid_resolution", "invalid release risk", status_code=422)
    summary = (resolution_summary or "").strip()
    if not summary:
        raise AppError("invalid_resolution", "resolution_summary is required", status_code=422)

    doc = _doc(record)
    doc.setdefault("actionHistory", [])
    doc.setdefault("timeline", [])

    # snapshot the AI prediction once, before any human edit
    if "originalPrediction" not in doc or doc["originalPrediction"] is None:
        doc["originalPrediction"] = {
            "classification": record.classification,
            "confidence": record.confidence,
            "severity": record.severity,
            "releaseRisk": record.release_risk,
            "rootCauseSummary": (doc.get("rootCause") or {}).get("summary"),
            "provider": (doc.get("aiMetadata") or {}).get("provider"),
        }

    previous = doc.get("humanResolution")
    resolution = {
        "classification": classification,
        "severity": severity,
        "releaseRisk": release_risk,
        "resolutionSummary": redact(summary[:RESOLUTION_TEXT_LIMIT]),
        "responsibleComponent": redact(responsible_component.strip()[:RESOLVER_LIMIT]),
        "resolver": redact(resolver.strip()[:RESOLVER_LIMIT]) or "local-operator",
        "resolvedAt": now_iso(),
        "revision": (previous or {}).get("revision", 0) + 1,
    }
    doc["humanResolution"] = resolution
    doc.setdefault("resolutionAudit", []).append(
        {
            "at": resolution["resolvedAt"],
            "resolver": resolution["resolver"],
            "classification": classification,
            "severity": severity,
            "releaseRisk": release_risk,
            "revision": resolution["revision"],
            "previousClassification": (previous or {}).get("classification"),
        }
    )
    append_timeline(
        doc,
        "Human resolution recorded",
        f"Reviewed outcome: {classification} (revision {resolution['revision']})",
    )
    record.resolution_json = json.dumps(resolution)
    _save_doc(record, doc)
    session.commit()
