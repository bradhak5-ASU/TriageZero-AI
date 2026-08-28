"""Structured analysis contracts shared by every analyzer provider.

Two models, deliberately separate:

* ``ModelAnalysis`` is the ONLY thing a language model is allowed to produce.
  It is a closed schema — unknown fields are rejected — and it has no field
  in which reasoning, chain-of-thought, tool calls, or instructions could be
  smuggled back to us.
* ``AnalysisResult`` is what the service returns and persists: a validated
  ``ModelAnalysis`` plus provider/telemetry metadata that the *application*
  fills in, never the model.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ANALYSIS_SCHEMA_VERSION = "1.0"

Classification = Literal[
    "backend_application_defect",
    "frontend_application_defect",
    "test_automation_defect",
    "environment_failure",
    "data_integrity_defect",
    "performance_timing_defect",
    "dependency_failure",
    "unknown",
]
Severity = Literal["critical", "high", "medium", "low"]
ReleaseRisk = Literal["block_release", "high", "moderate", "low", "none"]
Provider = Literal["deterministic", "gemini", "gemini_adk", "deterministic_fallback"]

CLASSIFICATIONS: tuple[str, ...] = (
    "backend_application_defect",
    "frontend_application_defect",
    "test_automation_defect",
    "environment_failure",
    "data_integrity_defect",
    "performance_timing_defect",
    "dependency_failure",
    "unknown",
)

MAX_SUMMARY = 1200
MAX_SHORT = 300


class ModelAnalysis(BaseModel):
    """The conclusion set a provider must return. Closed schema: any extra
    key (including anything resembling reasoning) is a validation error."""

    model_config = ConfigDict(extra="forbid")

    classification: Classification
    confidence: float = Field(ge=0.0, le=1.0)
    severity: Severity
    release_risk: ReleaseRisk
    root_cause_summary: str = Field(min_length=1, max_length=MAX_SUMMARY)
    responsible_component: str = Field(min_length=1, max_length=MAX_SHORT)
    confidence_explanation: str = Field(min_length=1, max_length=MAX_SUMMARY)
    evidence_highlights: list[str] = Field(default_factory=list, max_length=12)
    recommended_next_step: str = Field(min_length=1, max_length=MAX_SUMMARY)
    recommended_action: str = Field(min_length=1, max_length=MAX_SHORT)
    action_rationale: str = Field(min_length=1, max_length=MAX_SUMMARY)
    proposed_issue_title: str = Field(min_length=1, max_length=MAX_SHORT)
    proposed_issue_labels: list[str] = Field(default_factory=list, max_length=10)
    requires_human_review: bool = False

    @field_validator("evidence_highlights", "proposed_issue_labels")
    @classmethod
    def cap_items(cls, v: list[str]) -> list[str]:
        return [item[:MAX_SHORT] for item in v if item]


class StageSummary(BaseModel):
    """A safe, user-facing description of one workflow stage.

    Stage summaries are conclusions ("classified as backend defect"), never
    the model's internal reasoning about how it got there.
    """

    model_config = ConfigDict(extra="forbid")

    stage: str = Field(max_length=80)
    summary: str = Field(max_length=400)
    duration_ms: int = Field(default=0, ge=0)


class ProviderAttempt(BaseModel):
    """Safe provider call telemetry. No prompts, payloads, or credentials."""

    model_config = ConfigDict(extra="forbid")

    attempt: int = Field(ge=1)
    duration_ms: int = Field(default=0, ge=0)
    outcome: str = Field(max_length=80)
    error_category: str | None = Field(default=None, max_length=80)
    http_status: int | None = None


class ProviderError(BaseModel):
    """Sanitized provider failure metadata safe to persist and display."""

    model_config = ConfigDict(extra="forbid")

    error_code: str = Field(max_length=80)
    error_category: str = Field(max_length=80)
    http_status: int | None = None
    attempt_count: int = Field(default=0, ge=0)
    last_attempt_duration_ms: int | None = Field(default=None, ge=0)
    provider_message_sanitized: str = Field(default="", max_length=300)
    attempts: list[ProviderAttempt] = Field(default_factory=list, max_length=10)


class AnalysisResult(BaseModel):
    """Validated conclusions plus application-controlled provenance."""

    model_config = ConfigDict(extra="forbid")

    analysis: ModelAnalysis

    provider: Provider
    model_name: str | None = None
    prompt_version: str = "v1"
    analysis_schema_version: str = ANALYSIS_SCHEMA_VERSION
    stage_summaries: list[StageSummary] = Field(default_factory=list)
    duration_ms: int = Field(default=0, ge=0)
    input_tokens: int | None = None
    output_tokens: int | None = None
    fallback_reason: str | None = Field(default=None, max_length=MAX_SHORT)
    provider_error: ProviderError | None = None
    provider_attempts: list[ProviderAttempt] = Field(default_factory=list, max_length=10)
    retrieval_signals: list[str] = Field(default_factory=list, max_length=20)

    # convenience passthroughs used by the persistence layer
    @property
    def classification(self) -> str:
        return self.analysis.classification

    @property
    def confidence(self) -> float:
        return self.analysis.confidence

    @property
    def severity(self) -> str:
        return self.analysis.severity

    @property
    def release_risk(self) -> str:
        return self.analysis.release_risk

    def needs_review(self) -> bool:
        return self.analysis.requires_human_review or self.analysis.confidence < 0.6


class AnalysisContext(BaseModel):
    """Non-evidence inputs an analyzer may consider."""

    model_config = ConfigDict(extra="forbid")

    investigation_id: str | None = None
    prompt_version: str = "v1"
    allow_fallback: bool = True
