"""Failure-package v1.0 request models — strict contract.

Every model forbids unknown fields: v1.0 is a closed schema, so a package
carrying anything the contract does not define is rejected rather than
silently persisted. Producers that need new data must ship a new
schema_version.

Private-oracle detection is intentionally NOT done here: it runs against the
raw JSON body (see services.evidence.find_forbidden_paths) before Pydantic
parsing, so forbidden keys are reported with their own error code and are
caught even where these models would reject the field for another reason.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_TEXT = 20_000
MAX_SHORT = 500
MAX_LIST = 200

# closed vocabularies, matching the frontend domain types
BrowserName = Literal["chromium", "firefox", "webkit"]
EnvironmentName = Literal["local", "staging", "production"]

STRICT = ConfigDict(extra="forbid")


class RunInfo(BaseModel):
    model_config = STRICT

    run_id: str = Field(min_length=1, max_length=MAX_SHORT)
    trigger: str = Field(default="unknown", max_length=MAX_SHORT)
    started_at: str | None = Field(default=None, max_length=MAX_SHORT)


class RepositoryInfo(BaseModel):
    model_config = STRICT

    name: str = Field(min_length=1, max_length=MAX_SHORT)
    branch: str = Field(min_length=1, max_length=MAX_SHORT)
    commit_sha: str = Field(min_length=1, max_length=MAX_SHORT)


class EnvironmentInfo(BaseModel):
    model_config = STRICT

    name: EnvironmentName
    target_url: str | None = Field(default=None, max_length=2000)
    browser: BrowserName


class TestInfo(BaseModel):
    model_config = STRICT

    name: str = Field(min_length=1, max_length=1000)
    file: str = Field(min_length=1, max_length=1000)
    status: str = Field(min_length=1, max_length=MAX_SHORT)
    retry: int = Field(default=0, ge=0, le=100)

    @field_validator("status")
    @classmethod
    def must_be_failed(cls, v: str) -> str:
        if v != "failed":
            raise ValueError("TriageZero investigates failed tests; test.status must be 'failed'")
        return v


class FailureInfo(BaseModel):
    model_config = STRICT

    expected: str = Field(default="", max_length=2000)
    actual: str = Field(default="", max_length=2000)
    message: str = Field(min_length=1, max_length=5000)
    stack_trace: str = Field(default="", max_length=MAX_TEXT)


class NetworkEvidence(BaseModel):
    model_config = STRICT

    method: str = Field(min_length=1, max_length=16, pattern=r"^[A-Za-z]+$")
    url: str = Field(min_length=1, max_length=2000)
    status: int

    @field_validator("status")
    @classmethod
    def valid_status(cls, v: int) -> int:
        if v != 0 and not 100 <= v <= 599:
            raise ValueError(
                "network status must be a valid HTTP status, or 0 for a connection failure"
            )
        return v


class ArtifactPaths(BaseModel):
    model_config = STRICT

    screenshot_path: str | None = Field(default=None, max_length=2000)
    trace_path: str | None = Field(default=None, max_length=2000)
    video_path: str | None = Field(default=None, max_length=2000)
    console_log_path: str | None = Field(default=None, max_length=2000)
    network_log_path: str | None = Field(default=None, max_length=2000)


class FailurePackage(BaseModel):
    """Top-level v1.0 package. Closed schema — unknown fields are rejected."""

    model_config = STRICT

    schema_version: Literal["1.0"]
    source: str = Field(min_length=1, max_length=MAX_SHORT)
    run: RunInfo
    repository: RepositoryInfo
    environment: EnvironmentInfo
    test: TestInfo
    failure: FailureInfo
    network_evidence: list[NetworkEvidence] = Field(default_factory=list, max_length=MAX_LIST)
    console_errors: list[str] = Field(default_factory=list, max_length=MAX_LIST)
    artifacts: ArtifactPaths | None = None

    @field_validator("console_errors")
    @classmethod
    def cap_console_lines(cls, v: list[str]) -> list[str]:
        return [line[:5000] for line in v]
