"""Gemini provider built on the official ``google-genai`` SDK.

Design constraints that matter more than the code:

* **Nothing happens at import time.** The SDK is imported and the client is
  constructed lazily, only when Gemini mode is actually selected, so the
  backend imports, tests, and starts with no credentials present.
* **The model's output is never trusted.** Every response is parsed and
  validated against ``ModelAnalysis`` — a closed schema — before it can reach
  persistence. Unknown fields, bad classifications, or out-of-range confidence
  are provider errors, not data.
* **The model can only produce text.** No tools, no function calling, no file
  or URL access are configured, so an injected instruction has nothing to
  invoke even if the model were to obey it.
"""

import json
import time
from typing import Any

from pydantic import ValidationError

from app.ai.prompts import SYSTEM_INSTRUCTION, build_user_prompt
from app.ai.protocols import Analyzer, AnalyzerError
from app.ai.schemas import (
    AnalysisContext,
    AnalysisResult,
    ModelAnalysis,
    StageSummary,
)
from app.core.logging import log_event
from app.schemas.failure_package import FailurePackage

# Transient conditions worth one bounded retry; everything else fails fast.
_RETRYABLE_MARKERS = (
    "deadline",
    "timeout",
    "unavailable",
    "503",
    "502",
    "500",
    "429",
    "resource_exhausted",
    "rate limit",
    "connection reset",
    "temporarily",
)


def _classify_error(exc: Exception) -> tuple[str, bool]:
    """Map a provider exception to a SAFE code and whether to retry.

    Only the exception's type name and lowercase markers are inspected — the
    message itself is never logged or surfaced, since provider errors can echo
    request contents.
    """
    text = f"{type(exc).__name__}: {exc}".lower()
    if any(marker in text for marker in ("permission", "unauthenticated", "api key", "credential")):
        return "auth_error", False
    if any(marker in text for marker in _RETRYABLE_MARKERS):
        return "transient_error", True
    if "invalid" in text or "argument" in text:
        return "invalid_request", False
    return "provider_error", False


class GeminiAnalyzer(Analyzer):
    """Structured-output analyzer. Construct freely; it dials nothing until
    ``analyze`` is called."""

    name = "gemini"

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        timeout_seconds: int = 30,
        max_retries: int = 2,
        use_vertex: bool = False,
        project: str | None = None,
        location: str | None = None,
        client_factory: Any | None = None,
        provider_label: str = "gemini",
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_seconds
        self._max_retries = max(0, max_retries)
        self._use_vertex = use_vertex
        self._project = project
        self._location = location
        # dependency injection: tests pass a fake, production leaves it None
        self._client_factory = client_factory
        self._client: Any | None = None
        self._label = provider_label

    # -- client ---------------------------------------------------------

    def _build_client(self) -> Any:
        if self._client_factory is not None:
            return self._client_factory()
        if not self._use_vertex and not self._api_key:
            raise AnalyzerError("unconfigured", "No Gemini credentials configured")
        try:
            from google import genai  # imported lazily, never at module import
            from google.genai import types
        except ImportError as exc:  # pragma: no cover - dependency present in image
            raise AnalyzerError("sdk_missing", "google-genai is not installed") from exc
        # google-genai expects milliseconds here. This is an SDK-level HTTP
        # deadline, so a stalled socket cannot outlive the configured bound.
        http_options = types.HttpOptions(timeout=max(1, self._timeout) * 1000)
        if self._use_vertex:
            return genai.Client(
                vertexai=True,
                project=self._project,
                location=self._location,
                http_options=http_options,
            )
        return genai.Client(api_key=self._api_key, http_options=http_options)

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = self._build_client()
        return self._client

    # -- request --------------------------------------------------------

    def _config(self) -> Any:
        """Structured output, no tools. The schema is the contract."""
        try:
            from google.genai import types
        except ImportError:  # pragma: no cover - fakes supply their own config
            return {
                "response_mime_type": "application/json",
                "response_schema": ModelAnalysis.model_json_schema(),
                "system_instruction": SYSTEM_INSTRUCTION,
            }
        return types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=ModelAnalysis,
            temperature=0.0,
            candidate_count=1,
            # deliberately no tools / no function declarations
        )

    @staticmethod
    def _extract_text(response: Any) -> str:
        text = getattr(response, "text", None)
        if isinstance(text, str) and text.strip():
            return text
        parsed = getattr(response, "parsed", None)
        if parsed is not None:
            if isinstance(parsed, ModelAnalysis):
                return parsed.model_dump_json()
            if isinstance(parsed, dict):
                return json.dumps(parsed)
        raise AnalyzerError("empty_response", "Model returned no usable content")

    @staticmethod
    def _usage(response: Any) -> tuple[int | None, int | None]:
        usage = getattr(response, "usage_metadata", None)
        if usage is None:
            return None, None
        return (
            getattr(usage, "prompt_token_count", None),
            getattr(usage, "candidates_token_count", None),
        )

    def _call_model(self, prompt: str) -> Any:
        client = self._get_client()
        last: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                return client.models.generate_content(
                    model=self._model,
                    contents=prompt,
                    config=self._config(),
                )
            except AnalyzerError:
                raise
            except Exception as exc:  # noqa: BLE001 - mapped to a safe code below
                code, retryable = _classify_error(exc)
                last = exc
                if not retryable or attempt == self._max_retries:
                    raise AnalyzerError(code, "Gemini request failed", retryable=retryable) from exc
                # exponential backoff, transient failures only
                time.sleep(min(2**attempt * 0.5, 4.0))
        raise AnalyzerError("provider_error", "Gemini request failed") from last

    # -- analyzer protocol ----------------------------------------------

    def analyze(
        self,
        failure_package: FailurePackage,
        similar_cases: list[dict[str, Any]],
        context: AnalysisContext,
    ) -> AnalysisResult:
        started = time.perf_counter()
        prompt = build_user_prompt(failure_package, similar_cases)

        response = self._call_model(prompt)
        raw = self._extract_text(response)

        try:
            payload = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError as exc:
            raise AnalyzerError("invalid_json", "Model response was not valid JSON") from exc
        if not isinstance(payload, dict):
            raise AnalyzerError("invalid_json", "Model response was not a JSON object")

        try:
            # closed schema: unknown fields (including any smuggled reasoning)
            # and out-of-range values are rejected here, before persistence
            analysis = ModelAnalysis.model_validate(payload)
        except ValidationError as exc:
            log_event(
                "gemini response failed schema validation",
                error_count=len(exc.errors()),
                provider=self._label,
            )
            raise AnalyzerError("invalid_schema", "Model response failed validation") from exc

        duration_ms = int((time.perf_counter() - started) * 1000)
        input_tokens, output_tokens = self._usage(response)
        return AnalysisResult(
            analysis=analysis,
            provider=self._label,  # type: ignore[arg-type]
            model_name=self._model,
            prompt_version=context.prompt_version,
            stage_summaries=[
                StageSummary(
                    stage="gemini_structured_analysis",
                    summary=(
                        f"Model returned a validated result → {analysis.classification} "
                        f"(confidence {analysis.confidence:.2f})."
                    ),
                    duration_ms=duration_ms,
                )
            ],
            duration_ms=duration_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            retrieval_signals=sorted(
                {s for case in similar_cases[:3] for s in (case.get("matchingSignals") or [])}
            )[:20],
        )
