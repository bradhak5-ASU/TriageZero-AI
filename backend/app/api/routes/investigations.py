import json
from typing import Annotated, Literal

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.api.dependencies import SessionDep
from app.core.config import get_settings
from app.core.errors import AppError, OracleFieldsError
from app.core.logging import log_event
from app.repositories import investigations as repo
from app.schemas.actions import IngestAccepted
from app.schemas.failure_package import FailurePackage
from app.schemas.investigation import InvestigationOut
from app.schemas.resolution import ResolutionRequest
from app.services import processing
from app.services.evidence import find_forbidden_paths
from app.services.investigations import (
    create_investigation,
    now_iso,
    prepare_retry,
    record_decision,
    record_resolution,
    serialize,
)

router = APIRouter()


def _get_or_404(session, investigation_id: str):
    record = repo.get(session, investigation_id)
    if record is None:
        raise AppError(
            "not_found", f"Investigation {investigation_id} not found", status_code=404
        )
    return record


async def _read_body_limited(request: Request) -> bytes:
    """Read the request body while enforcing the size limit on the actual
    bytes received — a chunked request without Content-Length cannot bypass
    the cap (the header check in middleware is only a fast-fail)."""
    max_bytes = get_settings().max_request_bytes
    received = bytearray()
    async for chunk in request.stream():
        received.extend(chunk)
        if len(received) > max_bytes:
            raise AppError(
                "request_too_large",
                f"Request exceeds the configured maximum of {max_bytes} bytes.",
                status_code=413,
            )
    return bytes(received)


@router.post("/investigations", status_code=202, response_model=IngestAccepted)
async def ingest_failure(
    request: Request,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> IngestAccepted | JSONResponse:
    # oracle detection runs against the RAW body, before any model parsing,
    # so forbidden keys are caught even where Pydantic would drop them
    try:
        raw = json.loads(await _read_body_limited(request))
    except json.JSONDecodeError as exc:
        raise AppError("invalid_json", f"Request body is not valid JSON: {exc}", 400) from exc

    forbidden = find_forbidden_paths(raw)
    if forbidden:
        log_event(
            "package rejected: private oracle fields",
            outcome="rejected",
            forbidden_field_count=len(forbidden),
        )
        raise OracleFieldsError(forbidden)

    try:
        pkg = FailurePackage.model_validate(raw)
    except ValidationError as exc:
        details = [
            {"field": ".".join(str(p) for p in err["loc"]), "message": err["msg"]}
            for err in exc.errors()
        ]
        raise AppError(
            "validation_error",
            "Failure package failed validation.",
            status_code=422,
            details=details,
        ) from None

    record, created = create_investigation(session, pkg, idempotency_key)
    if created:
        processing.dispatcher.dispatch(record.id)
        log_event(
            "investigation created",
            investigation_id=record.id,
            outcome="accepted",
            repository=record.repository,
            test_file=record.test_file,
        )
    else:
        log_event(
            "duplicate package deduplicated",
            investigation_id=record.id,
            outcome="deduplicated",
        )
    return IngestAccepted(
        investigation_id=record.id,
        status="received",
        received_at=record.created_at if not created else now_iso(),
    )


@router.get(
    "/investigations",
    response_model=list[InvestigationOut],
    response_model_by_alias=True,
)
def list_investigations(
    session: SessionDep,
    status: Annotated[
        str | None,
        Query(pattern="^(received|queued|analyzing|completed|failed|needs_review)$"),
    ] = None,
    classification: Annotated[str | None, Query(max_length=64)] = None,
    severity: Annotated[str | None, Query(pattern="^(critical|high|medium|low)$")] = None,
    release_risk: Annotated[
        str | None, Query(pattern="^(block_release|high|moderate|low|none)$")
    ] = None,
    repository: Annotated[str | None, Query(max_length=500)] = None,
    environment: Annotated[str | None, Query(max_length=500)] = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
    sort: Annotated[Literal["newest", "oldest"], Query()] = "newest",
) -> list[dict]:
    records = repo.list_records(
        session,
        status=status,
        classification=classification,
        severity=severity,
        release_risk=release_risk,
        repository=repository,
        environment=environment,
        search=search,
        limit=limit,
        offset=offset,
        sort=sort,
    )
    return [serialize(session, r) for r in records]


@router.get(
    "/investigations/{investigation_id}",
    response_model=InvestigationOut,
    response_model_by_alias=True,
)
def get_investigation(investigation_id: str, session: SessionDep) -> dict:
    return serialize(session, _get_or_404(session, investigation_id))


@router.post(
    "/investigations/{investigation_id}/retry",
    response_model=InvestigationOut,
    response_model_by_alias=True,
)
def retry_investigation(investigation_id: str, session: SessionDep) -> dict:
    record = _get_or_404(session, investigation_id)
    prepare_retry(session, record)
    processing.dispatcher.dispatch(record.id)
    log_event(
        "investigation retry",
        investigation_id=record.id,
        outcome="requeued",
        retry_count=record.retry_count,
    )
    session.refresh(record)
    return serialize(session, record)


@router.post(
    "/investigations/{investigation_id}/actions/{decision}",
    response_model=InvestigationOut,
    response_model_by_alias=True,
)
def decide_action(
    investigation_id: str,
    decision: Literal["approve", "reject"],
    session: SessionDep,
) -> dict:
    record = _get_or_404(session, investigation_id)
    record_decision(session, record, decision)
    log_event(
        "action decision recorded",
        investigation_id=record.id,
        outcome=decision,
    )
    return serialize(session, record)


@router.post(
    "/investigations/{investigation_id}/resolution",
    response_model=InvestigationOut,
    response_model_by_alias=True,
)
def submit_resolution(
    investigation_id: str,
    body: ResolutionRequest,
    session: SessionDep,
) -> dict:
    """Record a human-reviewed outcome.

    This is the only way a case becomes eligible for the historical retrieval
    corpus — an unreviewed AI prediction never becomes "truth". The original
    prediction is preserved separately so prediction-versus-outcome accuracy
    stays measurable.

    Local mode has no user system; the resolver is supplied by the caller and
    recorded verbatim (sanitized). Wire real authorization before exposing this
    endpoint outside localhost.
    """
    record = _get_or_404(session, investigation_id)
    record_resolution(
        session,
        record,
        classification=body.classification,
        severity=body.severity,
        release_risk=body.release_risk,
        resolution_summary=body.resolution_summary,
        responsible_component=body.responsible_component,
        resolver=body.resolver,
    )
    log_event(
        "human resolution recorded",
        investigation_id=record.id,
        outcome=body.classification,
    )
    return serialize(session, record)
