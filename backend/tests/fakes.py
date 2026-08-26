"""Fake providers for AI tests.

Everything here is offline: no test in this suite may contact Gemini, Vertex,
or any network service. These fakes stand in for the real SDK clients and the
ADK runner, and they record what they were sent so tests can assert on the
prompt without a provider.
"""

import json
from typing import Any

from app.ai.schemas import ModelAnalysis

VALID_RESULT: dict[str, Any] = {
    "classification": "backend_application_defect",
    "confidence": 0.91,
    "severity": "critical",
    "release_risk": "block_release",
    "root_cause_summary": "POST /api/v1/orders returned HTTP 500 during checkout.",
    "responsible_component": "novacart-target · API",
    "confidence_explanation": "A deterministic server error accompanies the failing step.",
    "evidence_highlights": ["POST /api/v1/orders returned HTTP 500"],
    "recommended_next_step": "Inspect server logs for the order-creation exception.",
    "recommended_action": "Create GitHub issue and flag release as blocked",
    "action_rationale": "High-confidence backend defect on the checkout path.",
    "proposed_issue_title": "[TriageZero] checkout returns 500",
    "proposed_issue_labels": ["bug", "backend"],
    "requires_human_review": False,
}


class FakeUsage:
    prompt_token_count = 1234
    candidates_token_count = 321


class FakeResponse:
    def __init__(self, payload: Any, *, usage: bool = True) -> None:
        self.text = payload if isinstance(payload, str) else json.dumps(payload)
        self.parsed = None
        self.usage_metadata = FakeUsage() if usage else None


class FakeModels:
    def __init__(self, client: "FakeGeminiClient") -> None:
        self._client = client

    def generate_content(self, *, model: str, contents: str, config: Any) -> FakeResponse:
        self._client.calls.append({"model": model, "prompt": contents, "config": config})
        if self._client.raise_times > 0:
            self._client.raise_times -= 1
            raise self._client.error or RuntimeError("503 service unavailable")
        payload = self._client.payloads.pop(0) if self._client.payloads else VALID_RESULT
        return FakeResponse(payload)


class FakeGeminiClient:
    """Records every prompt; never opens a socket."""

    def __init__(
        self,
        payloads: list[Any] | None = None,
        *,
        raise_times: int = 0,
        error: Exception | None = None,
    ) -> None:
        self.payloads = list(payloads or [])
        self.raise_times = raise_times
        self.error = error
        self.calls: list[dict[str, Any]] = []
        self.models = FakeModels(self)

    @property
    def last_prompt(self) -> str:
        return self.calls[-1]["prompt"] if self.calls else ""

    @property
    def all_prompts(self) -> str:
        return "\n".join(c["prompt"] for c in self.calls)


class FakeAdkRunner:
    """Stands in for an ADK runner. Sees only sanitized inputs."""

    def __init__(self, produced: dict[str, Any] | None = None, error: Exception | None = None):
        self._produced = produced or dict(VALID_RESULT)
        self._error = error
        self.received: list[dict[str, Any]] = []
        self.usage = {"input_tokens": 900, "output_tokens": 210}

    def run(self, *, package: dict, similar_cases: list, signals: dict) -> dict[str, Any]:
        self.received.append(
            {"package": package, "similar_cases": similar_cases, "signals": signals}
        )
        if self._error:
            raise self._error
        return dict(self._produced)

    @property
    def seen_json(self) -> str:
        return json.dumps(self.received)


def valid_model_analysis(**overrides: Any) -> ModelAnalysis:
    return ModelAnalysis.model_validate({**VALID_RESULT, **overrides})
