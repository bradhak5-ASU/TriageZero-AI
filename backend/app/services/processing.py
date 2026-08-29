"""Processing lifecycle for investigations.

The dispatcher is deliberately a small interface: the local implementation
runs the pipeline in-process (synchronously when the configured delay is 0,
as a background task otherwise). A Pub/Sub-backed dispatcher can replace it
later without touching routes or services.
"""

import asyncio
import json
from typing import Protocol

from app.ai.schemas import AnalysisContext, AnalysisResult
from app.ai.service import run_analysis
from app.core.config import get_settings
from app.core.logging import log_event, logger
from app.db.session import new_session
from app.repositories import investigations as repo
from app.schemas.failure_package import FailurePackage
from app.services.investigations import append_timeline, now_iso, retrieve_similar

# (stage, timeline label) in pipeline order; analysis runs at classification.
PIPELINE_STEPS = [
    ("evidence_received", "Investigation queued"),
    ("evidence_normalized", "Analysis started"),
    ("classification_complete", "Classification completed"),
    ("similarity_search", "Similarity search completed"),
    ("risk_assessment", "Release risk calculated"),
    ("action_recommendation", "Recommendation produced"),
]


class Dispatcher(Protocol):
    def dispatch(self, investigation_id: str) -> None: ...


class LocalDispatcher:
    """Runs the pipeline in-process. Zero delay (tests) → synchronous;
    otherwise an asyncio background task so the frontend can watch the
    stages advance. Works from async routes and from sync routes running
    in the threadpool (via the loop bound at startup)."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def dispatch(self, investigation_id: str) -> None:
        delay_ms = get_settings().local_processing_delay_ms
        if delay_ms <= 0:
            process_investigation(investigation_id, delay_ms=0)
            return
        try:
            asyncio.get_running_loop().create_task(
                _process_async(investigation_id, delay_ms)
            )
            return
        except RuntimeError:
            pass  # called from a worker thread — fall through to the bound loop
        if self._loop is not None and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                _process_async(investigation_id, delay_ms), self._loop
            )
        else:
            process_investigation(investigation_id, delay_ms=0)


dispatcher: Dispatcher = LocalDispatcher()


async def _process_async(investigation_id: str, delay_ms: int) -> None:
    for step_index in range(len(PIPELINE_STEPS)):
        await asyncio.sleep(delay_ms / 1000)
        # Provider SDK calls are synchronous. Run each database/pipeline step
        # in a worker thread so a slow model request or bounded retry cannot
        # block the FastAPI event loop, health checks, or dashboard reads.
        done = await asyncio.to_thread(_advance, investigation_id, step_index)
        if done:
            return


def process_investigation(investigation_id: str, delay_ms: int = 0) -> None:
    """Synchronous pipeline run (zero-delay path and tests)."""
    for step_index in range(len(PIPELINE_STEPS)):
        if _advance(investigation_id, step_index):
            return


def _analyze(pkg: FailurePackage, cases: list, investigation_id: str) -> AnalysisResult:
    """Run the configured analyzer. Never raises: the service applies the
    fallback policy and always returns a validated result."""
    settings = get_settings()
    return run_analysis(
        pkg,
        cases,
        AnalysisContext(
            investigation_id=investigation_id,
            prompt_version=settings.ai_prompt_version,
            allow_fallback=settings.ai_fallback_enabled,
        ),
        settings=settings,
    )


def _apply_analysis(record, doc: dict, result: AnalysisResult) -> None:
    """Persist conclusions and provenance. Only safe, user-facing fields are
    stored — never prompts, raw model responses, or reasoning."""
    analysis = result.analysis
    record.classification = analysis.classification
    record.confidence = analysis.confidence
    record.severity = analysis.severity
    record.release_risk = analysis.release_risk
    doc["rootCause"] = {
        "summary": analysis.root_cause_summary,
        "component": analysis.responsible_component,
        "confidenceExplanation": analysis.confidence_explanation,
        "nextStep": analysis.recommended_next_step,
    }
    doc["evidenceHighlights"] = list(analysis.evidence_highlights)
    doc["recommendedAction"] = {
        "action": analysis.recommended_action,
        "rationale": analysis.action_rationale,
        "issueTitle": analysis.proposed_issue_title,
        "labels": list(analysis.proposed_issue_labels),
        "owner": analysis.responsible_component,
        "approvalState": "awaiting_approval",
    }
    doc["aiMetadata"] = {
        "provider": result.provider,
        "modelName": result.model_name,
        "promptVersion": result.prompt_version,
        "analysisSchemaVersion": result.analysis_schema_version,
        "durationMs": result.duration_ms,
        "inputTokens": result.input_tokens,
        "outputTokens": result.output_tokens,
        "fallbackReason": result.fallback_reason,
        "usedFallback": result.provider == "deterministic_fallback",
        "requiresHumanReview": result.needs_review(),
        "stageSummaries": [s.model_dump() for s in result.stage_summaries],
        "providerError": (
            result.provider_error.model_dump() if result.provider_error is not None else None
        ),
        "providerAttempts": [attempt.model_dump() for attempt in result.provider_attempts],
        "retrievalSignals": list(result.retrieval_signals),
    }


def _advance(investigation_id: str, step_index: int) -> bool:
    """Apply one pipeline step. Returns True when processing is finished
    (successfully or not)."""
    session = new_session()
    try:
        record = repo.get(session, investigation_id)
        if record is None or record.status in ("completed", "needs_review", "failed"):
            return True

        doc = json.loads(record.doc_json)
        stage, label = PIPELINE_STEPS[step_index]
        record.stage = stage
        record.status = "queued" if step_index == 0 else "analyzing"
        append_timeline(doc, label)

        if stage == "classification_complete":
            pkg = FailurePackage.model_validate(json.loads(record.package_json))
            # retrieval runs first so the analyzer can correlate history
            cases = retrieve_similar(session, record)
            result = _analyze(pkg, cases, record.id)
            _apply_analysis(record, doc, result)

        if stage == "action_recommendation":
            needs_review = bool(doc.get("aiMetadata", {}).get("requiresHumanReview"))
            provider = str(doc.get("aiMetadata", {}).get("provider") or "unknown")
            provider_label = {
                "deterministic": "Deterministic",
                "deterministic_fallback": "Deterministic fallback",
                "gemini": "Gemini",
                "gemini_adk": "Gemini ADK",
            }.get(provider, "TriageZero")
            record.status = "needs_review" if needs_review else "completed"
            record.completed_at = now_iso()
            elapsed = _elapsed_ms(record.created_at, record.completed_at)
            record.elapsed_ms = elapsed
            doc["actionTaken"] = (
                "Flagged for human review"
                if record.status == "needs_review"
                else "Recommendation produced — awaiting approval"
            )
            doc["actionHistory"].append(
                {
                    "id": f"a{len(doc['actionHistory']) + 1}",
                    "at": record.completed_at,
                    "actor": "TriageZero analyzer",
                    "action": "Proposed recommended action",
                    "state": "awaiting_approval",
                    "note": f"{provider_label} analysis — actions require human approval",
                }
            )
            log_event(
                "investigation completed",
                investigation_id=record.id,
                classification=record.classification,
                status=record.status,
                duration_ms=elapsed,
            )

        record.doc_json = json.dumps(doc)
        record.updated_at = now_iso()
        session.commit()
        return stage == "action_recommendation"
    except Exception:
        session.rollback()
        _mark_failed(session, investigation_id)
        logger.exception(
            "investigation processing failed",
            extra={"event": {"investigation_id": investigation_id, "error": "processing_error"}},
        )
        return True
    finally:
        session.close()


def _mark_failed(session, investigation_id: str) -> None:
    try:
        record = repo.get(session, investigation_id)
        if record is None:
            return
        doc = json.loads(record.doc_json)
        append_timeline(doc, "Investigation failed", "Processing raised an error — retry available")
        record.status = "failed"
        record.completed_at = now_iso()
        record.doc_json = json.dumps(doc)
        record.updated_at = record.completed_at
        session.commit()
    except Exception:
        session.rollback()


def _elapsed_ms(start_iso: str, end_iso: str) -> int:
    from datetime import datetime

    start = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
    end = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
    return max(0, int((end - start).total_seconds() * 1000))


def recover_pending() -> int:
    """On startup, resume investigations left mid-pipeline by a previous
    process. Returns how many were re-dispatched."""
    session = new_session()
    try:
        ids = repo.pending_ids(session)
    finally:
        session.close()
    for investigation_id in ids:
        dispatcher.dispatch(investigation_id)
    if ids:
        log_event("recovered pending investigations", count=len(ids))
    return len(ids)
