from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

ServiceStatus = Literal["healthy", "degraded", "offline", "disabled"]
EventLevel = Literal["info", "warn", "error"]


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ServiceHealthOut(CamelModel):
    id: str
    name: str
    status: ServiceStatus
    latency_ms: int | None = None
    last_check: str
    region: str
    detail: str


class SystemEventOut(CamelModel):
    id: str
    at: str
    level: EventLevel
    message: str


class VolumeBucketOut(CamelModel):
    label: str
    count: int


class AiHealthOut(CamelModel):
    """Truthful AI provider state. Contains no key material, no key length,
    and no prefix/suffix — only whether credentials are present."""

    analyzer_mode: str
    fallback_enabled: bool
    model_name: str
    prompt_version: str
    gemini_status: Literal["disabled", "unconfigured", "unverified", "healthy", "degraded"]
    adk_status: Literal["disabled", "unconfigured", "unverified", "healthy", "degraded"]
    deterministic_status: Literal["healthy", "degraded", "disabled"]
    last_success_at: str | None = None
    last_error_code: str | None = None
    fallback_count: int = 0
    historical_corpus_size: int = 0
    evaluation_datasets: list[str] = Field(default_factory=list)


class HealthOut(CamelModel):
    """Matches the frontend SystemHealthSnapshot type, plus a top-level
    `status` field for simple liveness checks."""

    status: Literal["ok"] = "ok"
    overall: ServiceStatus
    services: list[ServiceHealthOut]
    queue_depth: int
    worker_throughput_per_min: float
    ingestion_last_hour: int
    ingestion_volume: list[VolumeBucketOut] = Field(default_factory=list)
    events: list[SystemEventOut] = Field(default_factory=list)
    ai: AiHealthOut
