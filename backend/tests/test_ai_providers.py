"""Provider selection, configuration, fallback, retries, and validation.

No test here performs a network request: the Gemini client and the ADK runner
are injected fakes.
"""

import copy

import pytest

from app.ai.protocols import AnalyzerError
from app.ai.schemas import AnalysisContext
from app.ai.service import (
    build_analyzer,
    gemini_configured,
    run_analysis,
    set_adk_runner_factory,
    set_gemini_client_factory,
)
from app.core.config import Settings
from app.schemas.failure_package import FailurePackage
from tests.conftest import SAMPLE_PACKAGE
from tests.fakes import VALID_RESULT, FakeAdkRunner, FakeGeminiClient


@pytest.fixture()
def pkg() -> FailurePackage:
    return FailurePackage.model_validate(SAMPLE_PACKAGE)


@pytest.fixture(autouse=True)
def clear_injection():
    yield
    set_gemini_client_factory(None)
    set_adk_runner_factory(None)


def settings_for(**overrides) -> Settings:
    base = {
        "analyzer_mode": "deterministic",
        "ai_fallback_enabled": True,
        "gemini_api_key": "",
        "gemini_model": "gemini-3.6-flash",
        "google_genai_use_vertexai": False,
        "google_cloud_project": "",
    }
    return Settings(**{**base, **overrides})


class FakeProviderHttpError(RuntimeError):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


# --- defaults and construction -------------------------------------------


def test_default_mode_is_deterministic():
    s = settings_for()
    assert s.analyzer_mode == "deterministic"
    assert build_analyzer(s).name == "deterministic"


def test_invalid_mode_rejected_by_configuration():
    with pytest.raises(ValueError, match="ANALYZER_MODE"):
        Settings(analyzer_mode="magic")


def test_no_provider_client_is_constructed_at_import_time():
    """Importing the package must never build a client or read credentials."""
    import importlib

    import app.ai.gemini as gemini_module

    importlib.reload(gemini_module)
    analyzer = gemini_module.GeminiAnalyzer(api_key=None, model="gemini-3.6-flash")
    assert analyzer._client is None  # nothing built until analyze() runs


def test_constructing_gemini_analyzer_does_not_dial(pkg):
    from app.ai.gemini import GeminiAnalyzer

    analyzer = GeminiAnalyzer(api_key=None, model="gemini-3.6-flash")
    # no credentials → a safe AnalyzerError, never a network attempt
    with pytest.raises(AnalyzerError) as exc:
        analyzer.analyze(pkg, [], AnalysisContext())
    assert exc.value.code == "unconfigured"


# --- gemini mode with a fake client ---------------------------------------


def test_gemini_mode_returns_validated_result(pkg):
    client = FakeGeminiClient()
    set_gemini_client_factory(lambda: client)
    s = settings_for(analyzer_mode="gemini")

    result = run_analysis(pkg, [], AnalysisContext(), settings=s)

    assert result.provider == "gemini"
    assert result.model_name == "gemini-3.6-flash"
    assert result.analysis.classification == "backend_application_defect"
    assert result.input_tokens == 1234
    assert result.output_tokens == 321
    assert result.fallback_reason is None
    assert result.needs_review() is False
    assert client.calls, "the fake client should have been called"


def test_gemini_uses_json_schema_wire_field(pkg):
    """The Developer API rejects Pydantic ``additionalProperties`` when the
    SDK translates it through the legacy response_schema proto field."""
    from app.ai.gemini import GeminiAnalyzer
    from app.ai.schemas import ModelAnalysis

    client = FakeGeminiClient()
    analyzer = GeminiAnalyzer(
        api_key="placeholder",
        model="gemini-3.6-flash",
        client_factory=lambda: client,
    )

    analyzer.analyze(pkg, [], AnalysisContext())

    config = client.calls[-1]["config"]
    assert config.response_schema is None
    assert config.response_json_schema == ModelAnalysis.model_json_schema()


def test_missing_credentials_falls_back_when_enabled(pkg):
    s = settings_for(analyzer_mode="gemini", ai_fallback_enabled=True)
    result = run_analysis(pkg, [], AnalysisContext(), settings=s)
    assert result.provider == "deterministic_fallback"
    assert result.fallback_reason == "unconfigured"
    # the fallback still produces a real, useful conclusion
    assert result.analysis.classification == "backend_application_defect"


def test_missing_credentials_without_fallback_marks_needs_review(pkg):
    s = settings_for(analyzer_mode="gemini", ai_fallback_enabled=False)
    result = run_analysis(pkg, [], AnalysisContext(), settings=s)
    assert result.provider == "gemini"
    assert result.analysis.classification == "unknown"
    assert result.analysis.requires_human_review is True
    assert result.needs_review() is True
    assert "unconfigured" in (result.fallback_reason or "")


def test_gemini_configured_reports_truthfully():
    assert gemini_configured(settings_for()) is False
    assert gemini_configured(settings_for(gemini_api_key="x")) is True
    assert (
        gemini_configured(settings_for(google_genai_use_vertexai=True, google_cloud_project="p"))
        is True
    )
    assert gemini_configured(settings_for(google_genai_use_vertexai=True)) is False


# --- error handling --------------------------------------------------------


def test_transient_error_is_retried_then_succeeds(pkg):
    client = FakeGeminiClient(raise_times=1, error=RuntimeError("503 unavailable"))
    set_gemini_client_factory(lambda: client)
    s = settings_for(analyzer_mode="gemini")

    result = run_analysis(pkg, [], AnalysisContext(), settings=s)

    assert result.provider == "gemini"
    assert len(client.calls) == 2  # one failure, one retry
    assert [attempt.outcome for attempt in result.provider_attempts] == [
        "retryable_error",
        "success",
    ]
    assert result.provider_attempts[0].error_category == "http_503"


def test_permanent_error_is_not_retried(pkg):
    client = FakeGeminiClient(raise_times=5, error=RuntimeError("permission denied"))
    set_gemini_client_factory(lambda: client)
    s = settings_for(analyzer_mode="gemini")

    result = run_analysis(pkg, [], AnalysisContext(), settings=s)

    assert len(client.calls) == 1  # auth errors must not spin
    assert result.provider == "deterministic_fallback"
    assert result.fallback_reason == "auth_error"
    assert result.provider_error is not None
    assert result.provider_error.error_category == "auth_error"
    assert result.provider_error.attempt_count == 1


def test_retries_are_bounded(pkg):
    client = FakeGeminiClient(raise_times=99, error=RuntimeError("timeout"))
    set_gemini_client_factory(lambda: client)
    s = settings_for(analyzer_mode="gemini", gemini_max_retries=2)

    result = run_analysis(pkg, [], AnalysisContext(), settings=s)

    assert len(client.calls) == 3  # initial + 2 retries, then stop
    assert result.provider == "deterministic_fallback"
    assert result.provider_error is not None
    assert result.provider_error.attempt_count == 3


def test_timeout_error_falls_back_safely(pkg):
    client = FakeGeminiClient(raise_times=99, error=TimeoutError("deadline exceeded"))
    set_gemini_client_factory(lambda: client)
    s = settings_for(analyzer_mode="gemini")
    result = run_analysis(pkg, [], AnalysisContext(), settings=s)
    assert result.provider == "deterministic_fallback"
    assert result.fallback_reason == "timeout"
    assert result.provider_error is not None
    assert result.provider_error.error_category == "timeout"


def test_gemini_failure_without_fallback_keeps_attempted_provider(pkg):
    client = FakeGeminiClient(raise_times=99, error=TimeoutError("deadline exceeded"))
    set_gemini_client_factory(lambda: client)
    s = settings_for(analyzer_mode="gemini", ai_fallback_enabled=False)

    result = run_analysis(pkg, [], AnalysisContext(), settings=s)

    assert result.provider == "gemini"
    assert result.fallback_reason == "timeout"
    assert result.analysis.classification == "unknown"
    assert result.analysis.requires_human_review is True
    assert len(client.calls) == 3
    assert result.provider_error is not None
    assert result.provider_error.error_category == "timeout"
    assert result.provider_error.attempt_count == 3


def test_gemini_failure_with_fallback_runs_deterministic_analyzer(pkg):
    client = FakeGeminiClient(raise_times=99, error=TimeoutError("deadline exceeded"))
    set_gemini_client_factory(lambda: client)
    s = settings_for(analyzer_mode="gemini", ai_fallback_enabled=True)

    result = run_analysis(pkg, [], AnalysisContext(), settings=s)

    assert result.provider == "deterministic_fallback"
    assert result.fallback_reason == "timeout"
    assert result.analysis.classification == "backend_application_defect"
    assert result.analysis.confidence > 0
    assert len(client.calls) == 3
    assert result.provider_error is not None
    assert result.provider_error.error_category == "timeout"


@pytest.mark.parametrize(
    "error,expected_code,expected_category,expected_status",
    [
        (TimeoutError("deadline exceeded"), "timeout", "timeout", None),
        (FakeProviderHttpError(429, "rate limit"), "rate_limit", "rate_limit", 429),
        (FakeProviderHttpError(503, "service unavailable"), "http_error", "http_503", 503),
        (ConnectionError("connection reset by peer"), "connection_error", "connection_reset", None),
    ],
)
def test_retryable_provider_errors_record_attempts(
    pkg, error, expected_code, expected_category, expected_status
):
    client = FakeGeminiClient(raise_times=99, error=error)
    set_gemini_client_factory(lambda: client)
    s = settings_for(
        analyzer_mode="gemini",
        ai_fallback_enabled=False,
        gemini_max_retries=2,
    )

    result = run_analysis(pkg, [], AnalysisContext(), settings=s)

    assert len(client.calls) == 3
    assert result.provider == "gemini"
    assert result.fallback_reason == expected_code
    assert result.provider_error is not None
    assert result.provider_error.error_code == expected_code
    assert result.provider_error.error_category == expected_category
    assert result.provider_error.http_status == expected_status
    assert result.provider_error.attempt_count == 3
    assert [attempt.attempt for attempt in result.provider_error.attempts] == [1, 2, 3]
    assert all(attempt.outcome == "retryable_error" for attempt in result.provider_error.attempts)


def test_permanent_auth_style_error_records_no_retry(pkg):
    client = FakeGeminiClient(
        raise_times=99,
        error=FakeProviderHttpError(401, "authentication failed"),
    )
    set_gemini_client_factory(lambda: client)
    s = settings_for(analyzer_mode="gemini", ai_fallback_enabled=False)

    result = run_analysis(pkg, [], AnalysisContext(), settings=s)

    assert len(client.calls) == 1
    assert result.provider == "gemini"
    assert result.fallback_reason == "auth_error"
    assert result.provider_error is not None
    assert result.provider_error.error_category == "auth_error"
    assert result.provider_error.http_status == 401
    assert result.provider_error.attempt_count == 1


def test_success_after_transient_retry_records_attempt_timeline(pkg):
    client = FakeGeminiClient(raise_times=1, error=FakeProviderHttpError(500, "server error"))
    set_gemini_client_factory(lambda: client)
    s = settings_for(analyzer_mode="gemini", ai_fallback_enabled=False)

    result = run_analysis(pkg, [], AnalysisContext(), settings=s)

    assert result.provider == "gemini"
    assert result.fallback_reason is None
    assert result.provider_error is None
    assert len(result.provider_attempts) == 2
    assert result.provider_attempts[0].error_category == "http_500"
    assert result.provider_attempts[1].outcome == "success"


# --- output validation -----------------------------------------------------


@pytest.mark.parametrize(
    "bad_payload,reason",
    [
        ({**VALID_RESULT, "classification": "totally_made_up"}, "invalid classification"),
        ({**VALID_RESULT, "confidence": 1.4}, "confidence above 1"),
        ({**VALID_RESULT, "confidence": -0.2}, "confidence below 0"),
        ({**VALID_RESULT, "severity": "apocalyptic"}, "invalid severity"),
        ({**VALID_RESULT, "release_risk": "ship_it"}, "invalid release risk"),
        ({**VALID_RESULT, "chain_of_thought": "first I considered..."}, "unknown field"),
        ({**VALID_RESULT, "reasoning": "step by step"}, "reasoning field"),
        ("not json at all", "invalid json"),
        ({"classification": "unknown"}, "missing required fields"),
    ],
)
def test_invalid_model_output_never_reaches_persistence(pkg, bad_payload, reason):
    client = FakeGeminiClient([bad_payload])
    set_gemini_client_factory(lambda: client)
    s = settings_for(analyzer_mode="gemini")

    result = run_analysis(pkg, [], AnalysisContext(), settings=s)

    # the bad response is rejected and the fallback answers instead
    assert result.provider == "deterministic_fallback", reason
    assert result.fallback_reason in ("invalid_schema", "invalid_json"), reason


def test_chain_of_thought_field_is_never_accepted():
    from pydantic import ValidationError

    from app.ai.schemas import ModelAnalysis

    with pytest.raises(ValidationError):
        ModelAnalysis.model_validate({**VALID_RESULT, "chain_of_thought": "..."})


def test_schema_failure_without_fallback_is_conservative(pkg):
    client = FakeGeminiClient([{**VALID_RESULT, "classification": "nope"}])
    set_gemini_client_factory(lambda: client)
    s = settings_for(analyzer_mode="gemini", ai_fallback_enabled=False)

    result = run_analysis(pkg, [], AnalysisContext(), settings=s)

    assert result.analysis.classification == "unknown"
    assert result.analysis.requires_human_review is True


# --- ADK -------------------------------------------------------------------


def test_adk_mode_runs_every_stage_with_a_fake_runner(pkg):
    runner = FakeAdkRunner()
    set_adk_runner_factory(lambda: runner)
    set_gemini_client_factory(lambda: object())  # marks credentials as present
    s = settings_for(analyzer_mode="gemini_adk")

    result = run_analysis(pkg, [], AnalysisContext(), settings=s)

    assert result.provider == "gemini_adk"
    stages = [s.stage for s in result.stage_summaries]
    assert stages == [
        "evidence_normalization",
        "classification",
        "root_cause_synthesis",
        "similarity_correlation",
        "risk_assessment",
        "action_construction",
        "result_validation",
    ]
    assert runner.received, "the fake runner should have been invoked"


def test_production_adk_mode_constructs_real_runner_lazily():
    from app.ai.adk_workflow import GoogleAdkRunner

    analyzer = build_analyzer(
        settings_for(
            analyzer_mode="gemini_adk",
            gemini_api_key="placeholder",
            gemini_request_timeout_seconds=11,
            adk_request_timeout_seconds=91,
        )
    )
    assert analyzer._runner is None
    runner = analyzer._get_runner()
    assert isinstance(runner, GoogleAdkRunner)
    assert runner._timeout == 91


def test_adk_runner_receives_only_sanitized_evidence(pkg):
    secret = "Authorization: Bearer sk-live-secret-value-1234567890"
    poisoned = copy.deepcopy(pkg.model_dump(mode="json"))
    poisoned["failure"]["message"] += f" {secret}"
    package = FailurePackage.model_validate(poisoned)
    runner = FakeAdkRunner()
    set_adk_runner_factory(lambda: runner)

    result = run_analysis(
        package,
        [],
        AnalysisContext(),
        settings=settings_for(analyzer_mode="gemini_adk"),
    )

    assert result.provider == "gemini_adk"
    assert secret not in runner.seen_json
    assert "sk-live-secret-value" not in runner.seen_json
    assert "[REDACTED]" in runner.seen_json


def test_adk_instruction_allows_only_registered_read_only_tools():
    from app.ai.prompts import ADK_SYSTEM_INSTRUCTION

    lowered = ADK_SYSTEM_INSTRUCTION.lower()
    assert "you have no tools" not in lowered
    assert "only the listed read-only" in lowered
    assert "no filesystem" in lowered


def test_adk_risk_is_deterministic_policy_not_model_assertion(pkg):
    """Even if the model claims a low risk, policy decides the release gate."""
    runner = FakeAdkRunner({**VALID_RESULT, "severity": "low", "release_risk": "none"})
    set_adk_runner_factory(lambda: runner)
    set_gemini_client_factory(lambda: object())
    s = settings_for(analyzer_mode="gemini_adk")

    result = run_analysis(pkg, [], AnalysisContext(), settings=s)

    # backend defect ⇒ policy forces high / block_release
    assert result.analysis.severity == "high"
    assert result.analysis.release_risk == "block_release"


def test_adk_invalid_output_is_rejected(pkg):
    runner = FakeAdkRunner({**VALID_RESULT, "classification": "invented"})
    set_adk_runner_factory(lambda: runner)
    set_gemini_client_factory(lambda: object())
    s = settings_for(analyzer_mode="gemini_adk")

    result = run_analysis(pkg, [], AnalysisContext(), settings=s)
    assert result.provider == "deterministic_fallback"
    assert result.fallback_reason == "invalid_schema"


def test_adk_runner_failure_falls_back(pkg):
    runner = FakeAdkRunner(error=RuntimeError("agent exploded"))
    set_adk_runner_factory(lambda: runner)
    set_gemini_client_factory(lambda: object())
    s = settings_for(analyzer_mode="gemini_adk", gemini_max_retries=0)

    result = run_analysis(pkg, [], AnalysisContext(), settings=s)
    assert result.provider == "deterministic_fallback"
    assert result.provider_error is not None
    assert result.provider_error.error_category == "unknown_provider_error"
    assert result.provider_error.attempt_count == 1


def test_adk_retries_a_rate_limit_and_records_attempts(pkg, monkeypatch):
    class RateLimitedOnce:
        def __init__(self):
            self.calls = 0
            self.usage = {"input_tokens": 100, "output_tokens": 20}

        def run(self, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                raise FakeProviderHttpError(429, "resource exhausted")
            return dict(VALID_RESULT)

    runner = RateLimitedOnce()
    set_adk_runner_factory(lambda: runner)
    set_gemini_client_factory(lambda: object())
    monkeypatch.setattr("app.ai.adk_workflow.time.sleep", lambda _seconds: None)

    result = run_analysis(
        pkg,
        [],
        AnalysisContext(),
        settings=settings_for(analyzer_mode="gemini_adk", gemini_max_retries=1),
    )

    assert result.provider == "gemini_adk"
    assert runner.calls == 2
    assert [attempt.outcome for attempt in result.provider_attempts] == [
        "retryable_error",
        "success",
    ]
    assert result.provider_attempts[0].error_category == "rate_limit"


def test_adk_tools_are_read_only():
    """No tool may mutate anything or reach outside supplied data."""
    from app.ai.adk_workflow import READ_ONLY_TOOLS

    names = {tool.__name__ for tool in READ_ONLY_TOOLS}
    assert names == {
        "inspect_network_evidence",
        "inspect_console_evidence",
        "inspect_failure_text",
        "retrieve_similar_cases",
        "calculate_risk",
    }
    forbidden = {"shell", "exec", "write", "delete", "fetch", "http", "github", "env"}
    for name in names:
        assert not any(bad in name for bad in forbidden)


def test_tool_using_adk_agent_has_one_structured_output_path():
    """The ADK owns final-response shaping while the application validates the
    same closed schema again. ``validate_result`` must not also be a tool: two
    schema tools caused Vertex to finish with an empty object.
    """
    from app.ai.adk_workflow import build_adk_agent
    from app.ai.schemas import ModelAnalysis

    agent = build_adk_agent("gemini-3.6-flash")

    assert agent.output_schema is ModelAnalysis
    tool_names = {getattr(tool, "name", getattr(tool, "__name__", "")) for tool in agent.tools}
    assert "validate_result" not in tool_names


# --- persistence of provider metadata --------------------------------------


def test_provider_metadata_is_persisted(client, sample_package):
    inv_id = client.post("/api/v1/investigations", json=sample_package).json()["investigation_id"]
    inv = client.get(f"/api/v1/investigations/{inv_id}").json()
    meta = inv["aiMetadata"]
    assert meta["provider"] == "deterministic"
    assert meta["promptVersion"] == "v2"
    assert meta["analysisSchemaVersion"] == "1.0"
    assert meta["usedFallback"] is False
    assert meta["stageSummaries"]
    # no prompt, no raw response, no reasoning is ever stored
    blob = str(inv).lower()
    assert "chain_of_thought" not in blob
    assert "BEGIN_UNTRUSTED_EVIDENCE".lower() not in blob


def test_gemini_action_history_names_the_real_provider(make_client, sample_package):
    client_provider = FakeGeminiClient()
    set_gemini_client_factory(lambda: client_provider)
    client = make_client(ANALYZER_MODE="gemini", GEMINI_API_KEY="placeholder")

    inv_id = client.post("/api/v1/investigations", json=sample_package).json()[
        "investigation_id"
    ]
    inv = client.get(f"/api/v1/investigations/{inv_id}").json()

    assert inv["aiMetadata"]["provider"] == "gemini"
    assert inv["actionHistory"][-1]["note"] == (
        "Gemini analysis — actions require human approval"
    )
