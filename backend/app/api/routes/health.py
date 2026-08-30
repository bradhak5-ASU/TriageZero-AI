import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter
from sqlalchemy import select

from app.ai.service import gemini_configured
from app.ai.telemetry import telemetry
from app.api.dependencies import SessionDep
from app.core.config import get_settings
from app.db.models import InvestigationRecord
from app.repositories import investigations as repo
from app.schemas.health import HealthOut

router = APIRouter()

# Adapters that are deliberately not wired up. The details must not describe a
# local SQLite deployment, because this same endpoint serves the Cloud Run
# deployment, where saying "SQLite provides local persistence" is simply false.
DISABLED_SERVICES = [
    ("pubsub", "Pub/Sub", "Not connected — an in-process dispatcher handles queueing"),
    ("firestore", "Firestore", "Not connected — the relational store holds investigations"),
    ("storage", "Cloud Storage", "Not connected — artifacts are recorded as metadata only"),
    ("github", "GitHub Integration", "Not connected — decisions are recorded, no issues created"),
]


def _service_status(state: str) -> str:
    """Map an AI provider state onto the service-status vocabulary."""
    if state == "unverified":
        return "degraded"
    return state if state in ("healthy", "degraded") else "disabled"


def _ai_service_states(settings, telemetry_snapshot: dict) -> tuple[list[dict], str, str]:
    """Truthful Gemini/ADK status.

    Five states, and we never claim more than is true:
      disabled      — this mode is not selected
      unconfigured  — mode selected but no credentials present
      unverified    — configured, but no provider call has completed yet
      degraded      — configured, but the last call failed
      healthy       — configured and the last call succeeded

    No key material, length, prefix, or suffix is ever reported — only whether
    credentials are present at all.
    """
    mode = settings.analyzer_mode
    configured = gemini_configured(settings)
    last_error = telemetry_snapshot.get("last_error_code")
    last_success = telemetry_snapshot.get("last_success_at")

    def state_for(active: bool) -> str:
        if not active:
            return "disabled"
        if not configured:
            return "unconfigured"
        if last_error and not last_success:
            return "degraded"
        if last_error and telemetry_snapshot.get("fallback_count"):
            return "degraded"
        return "healthy" if last_success else "unverified"

    gemini_state = state_for(mode in ("gemini", "gemini_adk"))
    adk_state = state_for(mode == "gemini_adk")

    detail_map = {
        "disabled": f"Not selected — ANALYZER_MODE is '{mode}'",
        "unconfigured": (
            "Mode selected but no credentials are configured; "
            "deterministic analysis is used instead"
        ),
        "degraded": "Configured, but the most recent analysis did not succeed",
        "unverified": "Configured, but no successful provider call has been verified yet",
        "healthy": "Configured and answering",
    }
    return (
        [
            {
                "id": "gemini",
                "name": "Gemini",
                "status": _service_status(gemini_state),
                "lastCheck": None,
                "region": (
                    settings.google_cloud_location if settings.google_genai_use_vertexai else "—"
                ),
                "detail": f"{detail_map[gemini_state]} · model {settings.gemini_model}",
            },
            {
                "id": "adk",
                "name": "Google ADK",
                "status": _service_status(adk_state),
                "lastCheck": None,
                "region": "local",
                "detail": detail_map[adk_state],
            },
        ],
        gemini_state,
        adk_state,
    )


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


@router.get("/health", response_model=HealthOut, response_model_by_alias=True)
def get_health(session: SessionDep) -> HealthOut:
    now = datetime.now(UTC)

    started = time.perf_counter()
    queue_depth = repo.count_active(session)
    db_latency_ms = max(1, int((time.perf_counter() - started) * 1000))

    ingestion_last_hour = repo.created_since(session, _iso(now - timedelta(hours=1)))
    completed_recently = repo.completed_since(session, _iso(now - timedelta(minutes=10)))

    volume = []
    for hours_back in range(6, -1, -1):
        bucket_start = _iso(now - timedelta(hours=hours_back + 1))
        bucket_end = _iso(now - timedelta(hours=hours_back))
        count = repo.created_since(session, bucket_start) - repo.created_since(session, bucket_end)
        volume.append({"label": "now" if hours_back == 0 else f"-{hours_back}h", "count": count})

    recent = list(
        session.scalars(
            select(InvestigationRecord)
            .where(InvestigationRecord.status.in_(("completed", "needs_review", "failed")))
            .order_by(InvestigationRecord.updated_at.desc())
            .limit(8)
        )
    )
    events = [
        {
            "id": f"ev-{r.id}",
            "at": r.completed_at or r.updated_at,
            "level": "error" if r.status == "failed" else "info",
            "message": (
                f"Investigation {r.id} {r.status.replace('_', ' ')}"
                + (f" — {r.classification.replace('_', ' ')}" if r.classification else "")
            ),
        }
        for r in recent
    ]

    failed_last_hour = any(
        r.status == "failed" and (r.completed_at or "") >= _iso(now - timedelta(hours=1))
        for r in recent
    )
    last_check = _iso(now)

    settings = get_settings()
    ai_snapshot = telemetry.snapshot()
    ai_services, gemini_state, adk_state = _ai_service_states(settings, ai_snapshot)
    for entry in ai_services:
        entry["lastCheck"] = last_check

    corpus_size = repo.count_corpus(session)
    dataset_dir = Path(__file__).resolve().parents[3] / "evaluation" / "datasets"
    datasets = sorted(p.name for p in dataset_dir.glob("*.json")) if dataset_dir.is_dir() else []

    # The datastore row must describe the store actually in use. This endpoint
    # previously hardcoded "SQLite Store / Durable local persistence", which is
    # wrong and misleading on the Cloud Run deployment backed by Cloud SQL.
    backend_name = settings.database_backend
    if backend_name == "postgresql":
        store_name = "PostgreSQL Store"
        store_detail = "Managed PostgreSQL — durable across restarts and redeploys"
    elif backend_name == "sqlite":
        store_name = "SQLite Store"
        store_detail = "Local file persistence — for development only"
    else:
        store_name = f"{backend_name} Store"
        store_detail = "Relational persistence for investigations"

    # Cloud Run does not publish its region to the process, so it is injected at
    # deploy time. Reporting "local" everywhere while running in us-central1 was
    # a plain misstatement.
    region = settings.deployment_region or ("local" if settings.app_env == "development" else "—")

    services = [
        {
            "id": "ingestion-api",
            "name": "Ingestion API",
            "status": "healthy",
            # No separate latency probe exists for this service. The database
            # round trip was previously reported here as if it were one, which
            # is why three rows showed an identical figure.
            "lastCheck": last_check,
            "region": region,
            "detail": "Accepting failure packages on /api/v1/investigations",
        },
        {
            "id": "worker",
            "name": "Investigation Worker",
            "status": "healthy",
            "lastCheck": last_check,
            "region": region,
            "detail": f"In-process dispatcher · {queue_depth} active",
        },
        {
            "id": "database",
            "name": store_name,
            "status": "healthy",
            "latencyMs": db_latency_ms,  # the one figure actually measured
            "lastCheck": last_check,
            "region": region,
            "detail": store_detail,
        },
        {
            "id": "analyzer",
            "name": "Deterministic Analyzer",
            "status": "healthy",
            "lastCheck": last_check,
            "region": region,
            "detail": "Evidence-driven rule engine — always available as fallback",
        },
        *ai_services,
        *[
            {
                "id": sid,
                "name": name,
                "status": "disabled",
                "lastCheck": last_check,
                "region": "—",
                "detail": detail,
            }
            for sid, name, detail in DISABLED_SERVICES
        ],
    ]

    # Overall status is derived from the rows themselves. Previously it only
    # considered recently failed investigations, so the banner could read
    # "Healthy" while the table directly below showed a degraded provider.
    any_degraded = any(svc.get("status") == "degraded" for svc in services)
    overall = "degraded" if (failed_last_hour or any_degraded) else "healthy"

    return HealthOut.model_validate(
        {
            "status": "ok",
            "overall": overall,
            "services": services,
            "queueDepth": queue_depth,
            "workerThroughputPerMin": round(completed_recently / 10, 2),
            "ingestionLastHour": ingestion_last_hour,
            "ingestionVolume": volume,
            "events": events,
            "ai": {
                "analyzerMode": settings.analyzer_mode,
                "fallbackEnabled": settings.ai_fallback_enabled,
                "modelName": settings.gemini_model,
                "promptVersion": settings.ai_prompt_version,
                "geminiStatus": gemini_state,
                "adkStatus": adk_state,
                "deterministicStatus": "healthy",
                "lastSuccessAt": ai_snapshot.get("last_success_at"),
                "lastErrorCode": ai_snapshot.get("last_error_code"),
                "fallbackCount": ai_snapshot.get("fallback_count", 0),
                "historicalCorpusSize": corpus_size,
                "evaluationDatasets": datasets,
            },
        }
    )
