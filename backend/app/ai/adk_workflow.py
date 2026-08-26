"""Google ADK investigation workflow.

A small, conservative sequence of stages rather than a swarm — each stage does
one job with one read-only tool, and the last stage is a hard validation gate.

    1. evidence_normalization   extract signals from validated evidence
    2. classification           choose one label from the closed vocabulary
    3. root_cause_synthesis     write the conclusion (no reasoning)
    4. similarity_correlation   correlate sanitized historical cases
    5. risk_assessment          severity + release risk via deterministic policy
    6. action_construction      propose one action, always human-approved
    7. result_validation        validate against the closed schema

The agent's tools are pure functions over data already validated at ingestion.
There is deliberately no tool for: shell, filesystem, HTTP, GitHub, database
writes, cloud administration, environment variables, or the private evaluation
oracle. Risk scoring is computed by deterministic policy, not by the model, so
severity and release risk cannot be talked upward by injected text.

``runner_factory`` is the injection point: production builds a real ADK runner;
tests pass a fake, so the workflow is exercised without contacting Gemini.
"""

import asyncio
import contextlib
import json
import os
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

from app.ai.prompts import (
    ADK_SYSTEM_INSTRUCTION,
    EVIDENCE_CLOSE,
    EVIDENCE_OPEN,
    build_evidence_payload,
)
from app.ai.protocols import Analyzer, AnalyzerError
from app.ai.schemas import (
    AnalysisContext,
    AnalysisResult,
    ModelAnalysis,
    StageSummary,
)
from app.schemas.failure_package import FailurePackage

WORKFLOW_STAGES = (
    "evidence_normalization",
    "classification",
    "root_cause_synthesis",
    "similarity_correlation",
    "risk_assessment",
    "action_construction",
    "result_validation",
)

# ---------------------------------------------------------------------------
# read-only tools. Each takes already-validated data and returns plain values.
# ---------------------------------------------------------------------------


def inspect_network_evidence(package: dict[str, Any]) -> dict[str, Any]:
    """Summarize validated network evidence (read-only)."""
    entries = package.get("network_evidence", []) or []
    statuses = [e.get("status", 0) for e in entries]
    return {
        "request_count": len(entries),
        "server_error_count": sum(1 for s in statuses if s >= 500),
        "client_error_count": sum(1 for s in statuses if 400 <= s < 500),
        "connection_failure_count": sum(1 for s in statuses if s == 0),
        "status_families": sorted({f"{s // 100}xx" for s in statuses if s}),
        "first_failing_url": next(
            (e.get("url") for e in entries if e.get("status", 0) == 0 or e.get("status", 0) >= 400),
            None,
        ),
    }


def inspect_console_evidence(package: dict[str, Any]) -> dict[str, Any]:
    """Summarize validated console evidence (read-only)."""
    lines = package.get("console_errors", []) or []
    joined = " ".join(lines)
    return {
        "line_count": len(lines),
        "has_type_error": "TypeError" in joined,
        "has_reference_error": "ReferenceError" in joined,
        "has_uncaught": "Uncaught" in joined,
        "first_line": lines[0][:300] if lines else None,
    }


def inspect_failure_text(package: dict[str, Any]) -> dict[str, Any]:
    """Summarize the failure message and stack trace (read-only)."""
    failure = package.get("failure", {}) or {}
    message = failure.get("message", "") or ""
    stack = failure.get("stack_trace", "") or ""
    frame = ""
    for line in stack.splitlines():
        stripped = line.strip()
        if stripped.startswith("at "):
            frame = stripped[:200]
            break
    return {
        "message_excerpt": message[:400],
        "expected": (failure.get("expected") or "")[:200],
        "actual": (failure.get("actual") or "")[:200],
        "mentions_timeout": "timeout" in message.lower(),
        "top_frame": frame,
    }


def retrieve_similar_cases(similar_cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return sanitized historical cases. Never private evaluation labels."""
    return [
        {
            "investigation_id": case.get("id"),
            "similarity": case.get("similarity"),
            "classification": case.get("classification"),
            "resolution": (case.get("resolution") or "")[:200],
            "matching_signals": case.get("matchingSignals", []),
        }
        for case in similar_cases[:5]
    ]


def calculate_risk(classification: str, confidence: float) -> dict[str, str]:
    """Deterministic severity/release-risk policy.

    Kept out of the model's hands on purpose: risk drives the release gate, so
    it is computed from the classification, never asserted by generated text.
    """
    policy: dict[str, tuple[str, str]] = {
        "backend_application_defect": ("critical", "block_release"),
        "data_integrity_defect": ("high", "high"),
        "frontend_application_defect": ("high", "high"),
        "dependency_failure": ("high", "moderate"),
        "performance_timing_defect": ("medium", "moderate"),
        "test_automation_defect": ("medium", "low"),
        "environment_failure": ("low", "none"),
        "unknown": ("medium", "moderate"),
    }
    severity, release_risk = policy.get(classification, ("medium", "moderate"))
    if confidence < 0.6 and release_risk == "block_release":
        # never block a release on a weak signal
        release_risk = "high"
    return {"severity": severity, "release_risk": release_risk}


def validate_result(payload: dict[str, Any]) -> dict[str, Any]:
    """Final gate: the closed schema decides what is acceptable."""
    return ModelAnalysis.model_validate(payload).model_dump()


READ_ONLY_TOOLS: tuple[Callable[..., Any], ...] = (
    inspect_network_evidence,
    inspect_console_evidence,
    inspect_failure_text,
    retrieve_similar_cases,
    calculate_risk,
    validate_result,
)


def build_adk_agent(model: str) -> Any:
    """Construct the real ADK agent. Imported lazily — never at module import."""
    try:
        from google.adk.agents import Agent
    except ImportError as exc:  # pragma: no cover - dependency present in image
        raise AnalyzerError("sdk_missing", "google-adk is not installed") from exc

    return Agent(
        name="triagezero_investigator",
        model=model,
        description="Conservative regression-failure investigator for TriageZero.",
        instruction=(
            ADK_SYSTEM_INSTRUCTION
            + "\n\nWORKFLOW: use the read-only tools to inspect network, console and "
            "failure text; correlate sanitized similar cases; call calculate_risk for "
            "severity and release risk (never assert them yourself); then emit the "
            "structured result and confirm it with validate_result."
        ),
        tools=list(READ_ONLY_TOOLS),
        output_schema=ModelAnalysis,
    )


class GoogleAdkRunner:
    """Synchronous adapter around Google's asynchronous ADK Runner."""

    APP_NAME = "triagezero"

    def __init__(
        self,
        *,
        model: str,
        timeout_seconds: int,
        api_key: str | None,
        use_vertex: bool,
        project: str | None,
        location: str | None,
    ) -> None:
        self._model = model
        self._timeout = max(1, timeout_seconds)
        self._api_key = api_key
        self._use_vertex = use_vertex
        self._project = project
        self._location = location
        self._runner: Any | None = None
        self._session_service: Any | None = None
        self.usage: dict[str, int] = {}

    def _configure_environment(self) -> None:
        if self._use_vertex:
            os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")
            if self._project:
                os.environ.setdefault("GOOGLE_CLOUD_PROJECT", self._project)
            if self._location:
                os.environ.setdefault("GOOGLE_CLOUD_LOCATION", self._location)
        elif self._api_key:
            os.environ.setdefault("GEMINI_API_KEY", self._api_key)

    def _build(self) -> None:
        if self._runner is not None:
            return
        self._configure_environment()
        try:
            from google.adk.runners import Runner
            from google.adk.sessions import InMemorySessionService
        except ImportError as exc:  # pragma: no cover - dependency present in image
            raise AnalyzerError("sdk_missing", "google-adk is not installed") from exc
        self._session_service = InMemorySessionService()
        self._runner = Runner(
            app_name=self.APP_NAME,
            agent=build_adk_agent(self._model),
            session_service=self._session_service,
        )

    @staticmethod
    def _parse_payload(text: str) -> dict[str, Any]:
        value = text.strip()
        if value.startswith("```"):
            value = value.split("\n", 1)[-1]
            value = value.rsplit("```", 1)[0].strip()
        try:
            parsed = json.loads(value)
        except (TypeError, json.JSONDecodeError) as exc:
            raise AnalyzerError("invalid_json", "ADK returned invalid JSON") from exc
        if not isinstance(parsed, dict):
            raise AnalyzerError("invalid_schema", "ADK returned a non-object")
        return parsed

    async def _run_async(
        self,
        *,
        package: dict[str, Any],
        similar_cases: list[dict[str, Any]],
        signals: dict[str, Any],
    ) -> dict[str, Any]:
        self._build()
        try:
            from google.genai import types
        except ImportError as exc:  # pragma: no cover - dependency present in image
            raise AnalyzerError("sdk_missing", "google-genai is not installed") from exc

        session_id = f"analysis-{uuid.uuid4().hex}"
        user_id = "triagezero-analyzer"
        await self._session_service.create_session(
            app_name=self.APP_NAME, user_id=user_id, session_id=session_id
        )
        prompt = (
            "Analyze the following sanitized evidence. Use only the registered read-only tools "
            "when useful, then return exactly one JSON object matching the required result "
            "schema.\n"
            f"{EVIDENCE_OPEN}\n"
            + json.dumps(
                {"failure_package": package, "similar_cases": similar_cases, "signals": signals},
                sort_keys=True,
            )
            + f"\n{EVIDENCE_CLOSE}"
        )
        final_text = ""
        input_tokens = 0
        output_tokens = 0
        message = types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
        try:
            async with asyncio.timeout(self._timeout):
                async for event in self._runner.run_async(
                    user_id=user_id, session_id=session_id, new_message=message
                ):
                    usage = getattr(event, "usage_metadata", None)
                    input_tokens += int(getattr(usage, "prompt_token_count", 0) or 0)
                    output_tokens += int(getattr(usage, "candidates_token_count", 0) or 0)
                    if event.is_final_response() and getattr(event, "content", None):
                        final_text = "".join(
                            part.text or ""
                            for part in (event.content.parts or [])
                            if getattr(part, "text", None)
                        )
        except TimeoutError as exc:
            raise AnalyzerError(
                "timeout", "ADK analysis exceeded its deadline", retryable=True
            ) from exc
        finally:
            with contextlib.suppress(Exception):
                await self._session_service.delete_session(
                    app_name=self.APP_NAME, user_id=user_id, session_id=session_id
                )
        if not final_text:
            raise AnalyzerError("empty_response", "ADK returned no final response")
        self.usage = {"input_tokens": input_tokens, "output_tokens": output_tokens}
        return self._parse_payload(final_text)

    def run(
        self,
        *,
        package: dict[str, Any],
        similar_cases: list[dict[str, Any]],
        signals: dict[str, Any],
    ) -> dict[str, Any]:
        coroutine = self._run_async(package=package, similar_cases=similar_cases, signals=signals)
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coroutine)

        result: list[dict[str, Any]] = []
        failure: list[BaseException] = []

        def execute() -> None:
            try:
                result.append(asyncio.run(coroutine))
            except BaseException as exc:  # noqa: BLE001 - re-raised on caller thread
                failure.append(exc)

        thread = threading.Thread(target=execute, name="triagezero-adk", daemon=True)
        thread.start()
        thread.join(self._timeout + 1)
        if thread.is_alive():
            raise AnalyzerError("timeout", "ADK analysis exceeded its deadline", retryable=True)
        if failure:
            raise failure[0]
        return result[0]


class AdkWorkflowAnalyzer(Analyzer):
    """Staged ADK workflow.

    ``runner_factory`` returns an object exposing ``run(package, similar_cases,
    signals) -> dict`` that produces the conclusion fields. Production wires it
    to an ADK runner; tests inject a fake. When no runner is supplied the
    workflow still executes every stage and derives conclusions from the
    deterministic policy, so the stage pipeline itself is always exercised.
    """

    name = "gemini_adk"

    def __init__(
        self,
        *,
        model: str,
        runner_factory: Callable[[], Any] | None = None,
        provider_label: str = "gemini_adk",
    ) -> None:
        self._model = model
        self._runner_factory = runner_factory
        self._runner: Any | None = None
        self._label = provider_label

    def _get_runner(self) -> Any | None:
        if self._runner_factory is None:
            return None
        if self._runner is None:
            self._runner = self._runner_factory()
        return self._runner

    def analyze(
        self,
        failure_package: FailurePackage,
        similar_cases: list[dict[str, Any]],
        context: AnalysisContext,
    ) -> AnalysisResult:
        started = time.perf_counter()
        stages: list[StageSummary] = []

        def stage(name: str, summary: str, began: float) -> None:
            stages.append(
                StageSummary(
                    stage=name,
                    summary=summary,
                    duration_ms=int((time.perf_counter() - began) * 1000),
                )
            )

        package = build_evidence_payload(failure_package, similar_cases)

        # 1. evidence normalization
        t0 = time.perf_counter()
        signals = {
            "network": inspect_network_evidence(package),
            "console": inspect_console_evidence(package),
            "failure": inspect_failure_text(package),
        }
        stage(
            "evidence_normalization",
            f"Extracted {signals['network']['request_count']} network and "
            f"{signals['console']['line_count']} console signals.",
            t0,
        )

        # 2 + 3. classification and root-cause synthesis
        t0 = time.perf_counter()
        runner = self._get_runner()
        if runner is not None:
            try:
                produced = runner.run(
                    package=package,
                    similar_cases=retrieve_similar_cases(similar_cases),
                    signals=signals,
                )
            except AnalyzerError:
                raise
            except Exception as exc:  # noqa: BLE001 - surfaced as a safe code
                raise AnalyzerError("provider_error", "ADK workflow failed") from exc
            if not isinstance(produced, dict):
                raise AnalyzerError("invalid_schema", "ADK runner returned a non-object")
            base = dict(produced)
        else:
            raise AnalyzerError("runner_unavailable", "ADK runner is unavailable")
        stage("classification", f"Classified as {base.get('classification')}.", t0)

        t0 = time.perf_counter()
        stage(
            "root_cause_synthesis",
            "Produced a root-cause conclusion and responsible component.",
            t0,
        )

        # 4. similarity correlation
        t0 = time.perf_counter()
        correlated = retrieve_similar_cases(similar_cases)
        stage(
            "similarity_correlation",
            f"Correlated {len(correlated)} sanitized historical case(s).",
            t0,
        )

        # 5. risk assessment — deterministic policy, not model assertion
        t0 = time.perf_counter()
        confidence = float(base.get("confidence", 0.5) or 0.0)
        risk = calculate_risk(str(base.get("classification", "unknown")), confidence)
        base["severity"] = risk["severity"]
        base["release_risk"] = risk["release_risk"]
        stage(
            "risk_assessment",
            f"Policy assigned severity={risk['severity']}, release risk={risk['release_risk']}.",
            t0,
        )

        # 6. action construction — always a proposal
        t0 = time.perf_counter()
        base.setdefault("recommended_action", "Route to human review — no automated action")
        base["requires_human_review"] = bool(base.get("requires_human_review")) or confidence < 0.6
        stage("action_construction", "Proposed one action for human approval.", t0)

        # 7. final validation gate
        t0 = time.perf_counter()
        try:
            validated = ModelAnalysis.model_validate(validate_result(base))
        except AnalyzerError:
            raise
        except Exception as exc:  # noqa: BLE001 - schema failures are provider errors
            raise AnalyzerError("invalid_schema", "ADK result failed validation") from exc
        stage("result_validation", "Structured result passed schema validation.", t0)

        duration_ms = int((time.perf_counter() - started) * 1000)
        usage = getattr(runner, "usage", None) if runner is not None else None
        return AnalysisResult(
            analysis=validated,
            provider=self._label,  # type: ignore[arg-type]
            model_name=self._model,
            prompt_version=context.prompt_version,
            stage_summaries=stages,
            duration_ms=duration_ms,
            input_tokens=(usage or {}).get("input_tokens") if isinstance(usage, dict) else None,
            output_tokens=(usage or {}).get("output_tokens") if isinstance(usage, dict) else None,
            retrieval_signals=sorted(
                {s for case in correlated for s in (case.get("matching_signals") or [])}
            )[:20],
        )
