"""Analyzer selection, fallback policy, and provider construction.

The rest of the application calls ``run_analysis`` and gets a validated
``AnalysisResult`` no matter which provider ran. A provider failure never
propagates to the ingestion API: it either falls back to the deterministic
analyzer (when enabled) or produces a conservative needs-review result with a
safe explanation. It never silently pretends the model ran.
"""

import time
from typing import Any

from app.ai.deterministic import DeterministicAnalyzer, classify
from app.ai.protocols import Analyzer, AnalyzerError
from app.ai.schemas import AnalysisContext, AnalysisResult, StageSummary
from app.ai.schemas import ProviderError
from app.ai.telemetry import telemetry
from app.core.config import Settings, get_settings
from app.core.logging import log_event
from app.schemas.failure_package import FailurePackage

VALID_MODES = ("deterministic", "gemini", "gemini_adk")

# Injection points for tests: set to a factory to replace the real provider.
_gemini_factory: Any | None = None
_adk_runner_factory: Any | None = None


def set_gemini_client_factory(factory: Any | None) -> None:
    """Inject a fake Gemini client factory (tests only)."""
    global _gemini_factory
    _gemini_factory = factory


def set_adk_runner_factory(factory: Any | None) -> None:
    """Inject a fake ADK runner factory (tests only)."""
    global _adk_runner_factory
    _adk_runner_factory = factory


def gemini_configured(settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    if _gemini_factory is not None or (
        s.analyzer_mode == "gemini_adk" and _adk_runner_factory is not None
    ):
        return True
    if s.google_genai_use_vertexai:
        return bool(s.google_cloud_project)
    return bool(s.gemini_api_key)


def build_analyzer(settings: Settings | None = None) -> Analyzer:
    """Construct the analyzer for the configured mode.

    Nothing here dials out: the Gemini client and the ADK runner are built
    lazily on first use, so importing or starting the app never touches a
    provider.
    """
    s = settings or get_settings()
    mode = s.analyzer_mode

    if mode == "gemini":
        from app.ai.gemini import GeminiAnalyzer

        return GeminiAnalyzer(
            api_key=s.gemini_api_key or None,
            model=s.gemini_model,
            timeout_seconds=s.gemini_request_timeout_seconds,
            max_retries=s.gemini_max_retries,
            use_vertex=s.google_genai_use_vertexai,
            project=s.google_cloud_project or None,
            location=s.google_cloud_location or None,
            client_factory=_gemini_factory,
        )

    if mode == "gemini_adk":
        from app.ai.adk_workflow import AdkWorkflowAnalyzer, GoogleAdkRunner

        runner_factory = _adk_runner_factory or (
            lambda: GoogleAdkRunner(
                model=s.gemini_model,
                timeout_seconds=s.gemini_request_timeout_seconds,
                api_key=s.gemini_api_key or None,
                use_vertex=s.google_genai_use_vertexai,
                project=s.google_cloud_project or None,
                location=s.google_cloud_location or None,
            )
        )

        return AdkWorkflowAnalyzer(
            model=s.gemini_model,
            runner_factory=runner_factory,
        )

    return DeterministicAnalyzer()


def _fallback_result(
    pkg: FailurePackage,
    similar_cases: list[dict[str, Any]],
    context: AnalysisContext,
    reason: str,
    provider_error: ProviderError | None = None,
) -> AnalysisResult:
    """Deterministic analysis, honestly labeled as a fallback."""
    result = DeterministicAnalyzer(provider_label="deterministic_fallback").analyze(
        pkg, similar_cases, context
    )
    telemetry.record_fallback()
    updates: dict[str, Any] = {"fallback_reason": reason}
    if provider_error is not None:
        updates["provider_error"] = provider_error
        updates["provider_attempts"] = provider_error.attempts
    return result.model_copy(update=updates)


def _conservative_failure(
    pkg: FailurePackage,
    context: AnalysisContext,
    reason: str,
    provider_label: str,
    provider_error: ProviderError | None = None,
) -> AnalysisResult:
    """Fallback disabled: return a needs-review result, never a fake verdict."""
    analysis = classify(pkg).model_copy(
        update={
            "classification": "unknown",
            "confidence": 0.0,
            "release_risk": "moderate",
            "requires_human_review": True,
            "root_cause_summary": (
                "Automated analysis did not complete, so no conclusion is available. "
                "This investigation needs human review."
            ),
            "confidence_explanation": (
                f"The configured AI provider was unavailable ({reason}) and deterministic "
                "fallback is disabled, so no analysis was performed."
            ),
            "recommended_action": "Route to human review — no automated action",
            "action_rationale": "No analysis was produced; a human must triage this failure.",
        }
    )
    return AnalysisResult(
        analysis=analysis,
        provider=provider_label,  # type: ignore[arg-type]
        prompt_version=context.prompt_version,
        stage_summaries=[
            StageSummary(stage="analysis_unavailable", summary=f"Provider error: {reason}.")
        ],
        fallback_reason=reason,
        provider_error=provider_error,
        provider_attempts=list(provider_error.attempts) if provider_error else [],
    )


def _provider_error_from_details(details: dict[str, Any]) -> ProviderError | None:
    if not details:
        return None
    try:
        return ProviderError.model_validate(details)
    except Exception:  # noqa: BLE001 - provider details are best-effort telemetry
        return None


def run_analysis(
    failure_package: FailurePackage,
    similar_cases: list[dict[str, Any]] | None = None,
    context: AnalysisContext | None = None,
    analyzer: Analyzer | None = None,
    settings: Settings | None = None,
) -> AnalysisResult:
    """Analyze one failure package, applying the configured fallback policy."""
    s = settings or get_settings()
    cases = similar_cases or []
    ctx = context or AnalysisContext(
        prompt_version=s.ai_prompt_version, allow_fallback=s.ai_fallback_enabled
    )
    provider = analyzer or build_analyzer(s)
    mode = s.analyzer_mode
    started = time.perf_counter()

    # selected a model provider without credentials → fallback or fail honestly
    if mode in ("gemini", "gemini_adk") and not gemini_configured(s):
        reason = "unconfigured"
        log_event("ai provider unconfigured", mode=mode, fallback=s.ai_fallback_enabled)
        telemetry.record_error(reason)
        if s.ai_fallback_enabled:
            return _fallback_result(failure_package, cases, ctx, reason)
        return _conservative_failure(failure_package, ctx, reason, mode)

    try:
        result = provider.analyze(failure_package, cases, ctx)
        telemetry.record_success(result.provider)
        return result
    except AnalyzerError as exc:
        telemetry.record_error(exc.code)
        provider_error = _provider_error_from_details(exc.details)
        log_event(
            "ai provider error",
            mode=mode,
            error_code=exc.code,  # safe slug only
            error_category=provider_error.error_category if provider_error else None,
            http_status=provider_error.http_status if provider_error else None,
            attempt_count=provider_error.attempt_count if provider_error else None,
            fallback=s.ai_fallback_enabled,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        if s.ai_fallback_enabled:
            return _fallback_result(failure_package, cases, ctx, exc.code, provider_error)
        return _conservative_failure(failure_package, ctx, exc.code, mode, provider_error)
    except Exception:  # noqa: BLE001 - a model failure must never break ingestion
        telemetry.record_error("unexpected_error")
        log_event("ai provider crashed", mode=mode, error_code="unexpected_error")
        if s.ai_fallback_enabled:
            return _fallback_result(failure_package, cases, ctx, "unexpected_error")
        return _conservative_failure(failure_package, ctx, "unexpected_error", mode)
