"""Response models mirroring the frontend's TypeScript domain types
(src/types/index.ts). Serialized in camelCase — the frontend consumes these
objects verbatim."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

InvestigationStatus = Literal[
    "received", "queued", "analyzing", "completed", "failed", "needs_review"
]
ProcessingStage = Literal[
    "evidence_received",
    "evidence_normalized",
    "classification_complete",
    "similarity_search",
    "risk_assessment",
    "action_recommendation",
]
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
ApprovalState = Literal["proposed", "awaiting_approval", "approved", "executed", "rejected"]
ArtifactKind = Literal["screenshot", "trace", "video", "console_log", "network_log"]


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class NetworkEntryOut(CamelModel):
    method: str
    url: str
    status: int
    duration_ms: int | None = None
    request_headers: dict[str, str] | None = None
    response_summary: str | None = None


class ArtifactOut(CamelModel):
    kind: ArtifactKind
    label: str
    path: str
    size_bytes: int = 0
    available: bool = True


class EvidenceOut(CamelModel):
    expected: str = ""
    actual: str = ""
    message: str = ""
    stack_trace: str = ""
    network: list[NetworkEntryOut] = Field(default_factory=list)
    console_errors: list[str] = Field(default_factory=list)
    artifacts: list[ArtifactOut] = Field(default_factory=list)


class TimelineEventOut(CamelModel):
    id: str
    label: str
    at: str
    detail: str | None = None


class RootCauseOut(CamelModel):
    summary: str
    component: str
    confidence_explanation: str
    next_step: str


class SimilarFailureOut(CamelModel):
    id: str
    similarity: float
    test_name: str
    classification: Classification
    root_cause_summary: str
    date: str
    resolution: str
    issue_ref: str | None = None
    #: names of the weighted signals that matched — shown so a reviewer can
    #: see WHY two failures were considered similar
    matching_signals: list[str] = Field(default_factory=list)
    is_synthetic: bool = False


class RecommendedActionOut(CamelModel):
    action: str
    rationale: str
    issue_title: str
    labels: list[str]
    owner: str
    approval_state: ApprovalState


class ActionRecordOut(CamelModel):
    id: str
    at: str
    actor: str
    action: str
    state: ApprovalState
    note: str | None = None


class StageSummaryOut(CamelModel):
    stage: str
    summary: str
    duration_ms: int = 0


class ProviderAttemptOut(CamelModel):
    attempt: int
    duration_ms: int = 0
    outcome: str
    error_category: str | None = None
    http_status: int | None = None


class ProviderErrorOut(CamelModel):
    error_code: str
    error_category: str
    http_status: int | None = None
    attempt_count: int = 0
    last_attempt_duration_ms: int | None = None
    provider_message_sanitized: str = ""
    attempts: list[ProviderAttemptOut] = Field(default_factory=list)


class AiMetadataOut(CamelModel):
    """Analysis provenance. Conclusions and metrics only — never prompts,
    raw model responses, or reasoning."""

    provider: str
    model_name: str | None = None
    prompt_version: str | None = None
    analysis_schema_version: str | None = None
    duration_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    fallback_reason: str | None = None
    used_fallback: bool = False
    requires_human_review: bool = False
    stage_summaries: list[StageSummaryOut] = Field(default_factory=list)
    provider_error: ProviderErrorOut | None = None
    provider_attempts: list[ProviderAttemptOut] = Field(default_factory=list)
    retrieval_signals: list[str] = Field(default_factory=list)


class HumanResolutionOut(CamelModel):
    classification: Classification
    severity: Severity
    release_risk: ReleaseRisk
    resolution_summary: str
    responsible_component: str = ""
    resolver: str = ""
    resolved_at: str
    revision: int = 1


class OriginalPredictionOut(CamelModel):
    """The AI's prediction, snapshotted before any human edit, so
    prediction-versus-outcome accuracy stays measurable."""

    classification: Classification | None = None
    confidence: float | None = None
    severity: Severity | None = None
    release_risk: ReleaseRisk | None = None
    root_cause_summary: str | None = None
    provider: str | None = None


class InvestigationOut(CamelModel):
    id: str
    status: InvestigationStatus
    stage: ProcessingStage
    test_name: str
    test_file: str
    repository: str
    branch: str
    commit_sha: str
    run_id: str
    run_url: str | None = None
    browser: str
    environment: str
    trigger: str
    created_at: str
    completed_at: str | None = None
    elapsed_ms: int | None = None
    classification: Classification | None = None
    confidence: float | None = None
    severity: Severity | None = None
    release_risk: ReleaseRisk | None = None
    root_cause: RootCauseOut | None = None
    evidence: EvidenceOut
    timeline: list[TimelineEventOut] = Field(default_factory=list)
    similar_failures: list[SimilarFailureOut] = Field(default_factory=list)
    recommended_action: RecommendedActionOut | None = None
    action_history: list[ActionRecordOut] = Field(default_factory=list)
    action_taken: str | None = None
    ai_metadata: AiMetadataOut | None = None
    human_resolution: HumanResolutionOut | None = None
    original_prediction: OriginalPredictionOut | None = None
    is_synthetic: bool = False
