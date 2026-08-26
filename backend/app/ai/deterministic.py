"""Deterministic, evidence-driven analyzer.

This is the original rule engine, unchanged in behavior, now expressed behind
the shared ``Analyzer`` protocol. It reads ONLY the submitted package: no
model, no network, no scenario-name matching, no access to the private QA
oracle. Same package in, same result out — which is what makes it a safe
fallback and a meaningful evaluation baseline.
"""

import re
import time
from typing import Any
from urllib.parse import urlparse

from app.ai.protocols import Analyzer
from app.ai.schemas import (
    AnalysisContext,
    AnalysisResult,
    ModelAnalysis,
    StageSummary,
)
from app.schemas.failure_package import FailurePackage

CONNECTION_ERRORS = re.compile(
    r"ERR_NAME_NOT_RESOLVED|ERR_CONNECTION|ECONNREFUSED|ECONNRESET|EAI_AGAIN|"
    r"net::|getaddrinfo|DNS",
    re.IGNORECASE,
)
TIMEOUT = re.compile(r"timeout|timed out", re.IGNORECASE)
PERF_BUDGET = re.compile(
    r"toBeLessThan|within \d+\s*(ms|s|seconds?)|exceeded.*budget|duration|took \d+",
    re.IGNORECASE,
)
DATA_TERMS = re.compile(
    r"count|total|stock|quantity|inventory|balance|decrement|increment|toHaveCount",
    re.IGNORECASE,
)
CONSOLE_APP_ERROR = re.compile(r"TypeError|ReferenceError|Uncaught", re.IGNORECASE)
MESSAGE_5XX = re.compile(r"\b(HTTP\s*)?5\d\d\b")


def _host(url: str) -> str:
    try:
        return urlparse(url).hostname or ""
    except ValueError:
        return ""


def _is_external(url: str, pkg: FailurePackage) -> bool:
    host = _host(url)
    if not host:
        return False
    target_host = _host(pkg.environment.target_url or "")
    local_hosts = {target_host, "localhost", "127.0.0.1", ""}
    return host not in local_hosts and not host.endswith(".internal")


def _action_for(classification: str, release_risk: str, needs_review: bool) -> str:
    if release_risk == "block_release":
        return "Create GitHub issue and flag release as blocked"
    if classification in {"environment_failure", "dependency_failure"}:
        return "Re-run suite and log the incident; no code action"
    if needs_review:
        return "Route to human review — no automated action"
    return "Create GitHub issue for the responsible component"


def _result(
    pkg: FailurePackage,
    *,
    classification: str,
    confidence: float,
    severity: str,
    release_risk: str,
    summary: str,
    component: str,
    explanation: str,
    next_step: str,
    highlights: list[str],
) -> ModelAnalysis:
    needs_review = confidence < 0.6
    action = _action_for(classification, release_risk, needs_review)
    return ModelAnalysis(
        classification=classification,  # type: ignore[arg-type]
        confidence=confidence,
        severity=severity,  # type: ignore[arg-type]
        release_risk=release_risk,  # type: ignore[arg-type]
        root_cause_summary=summary,
        responsible_component=component,
        confidence_explanation=explanation,
        evidence_highlights=highlights,
        recommended_next_step=next_step,
        recommended_action=action,
        action_rationale=explanation,
        proposed_issue_title=(
            f"[TriageZero] {pkg.test.name} — {classification.replace('_', ' ')}"
        )[:300],
        proposed_issue_labels=["triagezero", "auto-triaged"],
        requires_human_review=needs_review,
    )


def classify(pkg: FailurePackage) -> ModelAnalysis:
    """The rule engine. Ordered most-specific signal first."""
    message = pkg.failure.message
    expected, actual = pkg.failure.expected, pkg.failure.actual
    network = pkg.network_evidence
    console = pkg.console_errors

    server_errors = [n for n in network if n.status >= 500]
    connection_failures = [n for n in network if n.status == 0]
    failing_requests = [n for n in network if n.status == 0 or n.status >= 400]

    # 1. correlated 5xx
    if server_errors:
        first = server_errors[0]
        highlights = [f"{n.method} {n.url} returned HTTP {n.status}" for n in server_errors]
        if expected and actual:
            highlights.append(f"Expected {expected}, actual {actual}")
        if _is_external(first.url, pkg):
            return _result(
                pkg,
                classification="dependency_failure",
                confidence=0.85,
                severity="high",
                release_risk="moderate",
                summary=(
                    f"An external dependency returned HTTP {first.status} "
                    f"({first.method} {first.url}) during '{pkg.test.name}'."
                ),
                component=f"External · {_host(first.url)}",
                explanation=(
                    "The failing request targets a host outside the application under "
                    "test; application requests in the same run show no server errors."
                ),
                next_step="Check the provider's status and retry once the dependency recovers.",
                highlights=highlights,
            )
        return _result(
            pkg,
            classification="backend_application_defect",
            confidence=0.93,
            severity="critical",
            release_risk="block_release",
            summary=(
                f"{first.method} {first.url} returned HTTP {first.status} instead of the "
                f"expected result during '{pkg.test.name}'. The server-side handler fails "
                "before producing the expected response."
            ),
            component=f"{pkg.repository.name} · API",
            explanation=(
                "Network evidence shows a deterministic server error on the failing step; "
                "test-side selectors and waits are not implicated."
            ),
            next_step=(
                f"Reproduce {first.method} {first.url} with the captured payload and "
                "inspect server logs for the exception."
            ),
            highlights=highlights,
        )

    # 2. connection-level failure
    if connection_failures or CONNECTION_ERRORS.search(message):
        return _result(
            pkg,
            classification="environment_failure",
            confidence=0.86,
            severity="low",
            release_risk="none",
            summary=(
                "Requests failed at the connection level before reaching the application, "
                "matching an environment or networking outage signature."
            ),
            component=f"{pkg.environment.name} environment",
            explanation=(
                "Connection-level failures affected the run before any application code "
                "path produced the failure."
            ),
            next_step="Re-run the suite once the target environment is reachable.",
            highlights=[message],
        )

    # 3. duration budget exceeded
    if PERF_BUDGET.search(message) and TIMEOUT.search(message) is None:
        return _result(
            pkg,
            classification="performance_timing_defect",
            confidence=0.77,
            severity="medium",
            release_risk="moderate",
            summary=(
                f"'{pkg.test.name}' exceeded its timing budget while the exercised "
                "requests completed successfully — a latency regression rather than a "
                "functional failure."
            ),
            component=f"{pkg.repository.name} · performance",
            explanation=(
                "The assertion is a duration budget and no request or console failure "
                "accompanies it; timing regressions can be environment-sensitive, "
                "which caps confidence."
            ),
            next_step="Profile the slowest request in the flow and compare against baseline.",
            highlights=[message],
        )

    # 4. client-side error with healthy network
    app_console_errors = [line for line in console if CONSOLE_APP_ERROR.search(line)]
    if app_console_errors and not failing_requests:
        return _result(
            pkg,
            classification="frontend_application_defect",
            confidence=0.85,
            severity="high",
            release_risk="high",
            summary=(
                f"A client-side error ('{app_console_errors[0][:120]}') prevented the "
                f"expected UI state in '{pkg.test.name}' while all requests succeeded."
            ),
            component=f"{pkg.repository.name} · frontend",
            explanation=(
                "The console error originates in application code and network evidence "
                "is healthy, isolating the failure to the client."
            ),
            next_step="Open the stack referenced by the console error and guard the failing path.",
            highlights=app_console_errors[:3],
        )

    # 5. business-value mismatch
    if (
        expected
        and actual
        and expected != actual
        and DATA_TERMS.search(message + " " + expected + " " + actual)
        and not MESSAGE_5XX.search(message)
    ):
        return _result(
            pkg,
            classification="data_integrity_defect",
            confidence=0.82,
            severity="high",
            release_risk="high",
            summary=(
                f"'{pkg.test.name}' observed '{actual}' where '{expected}' was expected — "
                "stored business data diverged from the performed operation."
            ),
            component=f"{pkg.repository.name} · data layer",
            explanation=(
                "The mismatch is on business values with no transport or client error, "
                "pointing at persistence or business-logic state."
            ),
            next_step=(
                "Trace the write path for the affected entity and verify transaction boundaries."
            ),
            highlights=[f"Expected {expected}, actual {actual}", message],
        )

    # 6. clean locator timeout.
    # Benign console noise (framework notices, deprecation warnings) is not
    # evidence of an application defect, so only APPLICATION-level console
    # errors disqualify this rule — matching how rule 4 reads the console.
    if TIMEOUT.search(message) and not failing_requests and not app_console_errors:
        return _result(
            pkg,
            classification="test_automation_defect",
            confidence=0.74,
            severity="medium",
            release_risk="low",
            summary=(
                "The failure is a locator/wait timeout with no correlated application "
                "error — most often selector drift or a timing-sensitive assertion in "
                "the test itself."
            ),
            component=f"{pkg.source} · {pkg.test.file}",
            explanation=(
                "No failing requests or console errors accompany the timeout; the "
                "application appears healthy in the captured evidence."
            ),
            next_step=(
                "Review the failing locator against the current DOM; prefer role-based selectors."
            ),
            highlights=[message],
        )

    # 7. message-only 5xx
    if MESSAGE_5XX.search(message):
        return _result(
            pkg,
            classification="backend_application_defect",
            confidence=0.8,
            severity="high",
            release_risk="high",
            summary=(
                f"The failure message reports a server error during '{pkg.test.name}', "
                "but no network capture corroborates it."
            ),
            component=f"{pkg.repository.name} · API",
            explanation=(
                "The 5xx appears only in the assertion message; without network "
                "evidence the confidence is reduced."
            ),
            next_step="Enable network capture for this suite and reproduce the failing call.",
            highlights=[message],
        )

    # 8. insufficient evidence
    return _result(
        pkg,
        classification="unknown",
        confidence=0.5,
        severity="medium",
        release_risk="moderate",
        summary=(
            "The available evidence does not clearly match a known failure signature. "
            "Human review is recommended."
        ),
        component="Undetermined",
        explanation=(
            "Signals are insufficient or conflicting; confidence is below the "
            "automated-action threshold."
        ),
        next_step="Replay the Playwright trace and review the captured evidence manually.",
        highlights=[message] if message else [],
    )


class DeterministicAnalyzer(Analyzer):
    """Rule-engine provider. No network, no credentials, no model."""

    name = "deterministic"

    def __init__(self, provider_label: str = "deterministic") -> None:
        self._label = provider_label

    def analyze(
        self,
        failure_package: FailurePackage,
        similar_cases: list[dict[str, Any]],
        context: AnalysisContext,
    ) -> AnalysisResult:
        started = time.perf_counter()
        analysis = classify(failure_package)
        duration_ms = int((time.perf_counter() - started) * 1000)
        signals: list[str] = []
        for case in similar_cases[:3]:
            signals.extend(case.get("matchingSignals", []) or [])
        return AnalysisResult(
            analysis=analysis,
            provider=self._label,  # type: ignore[arg-type]
            model_name=None,
            prompt_version=context.prompt_version,
            stage_summaries=[
                StageSummary(
                    stage="deterministic_rules",
                    summary=(
                        f"Matched evidence rules → {analysis.classification} "
                        f"(confidence {analysis.confidence:.2f})."
                    ),
                    duration_ms=duration_ms,
                )
            ],
            duration_ms=duration_ms,
            retrieval_signals=sorted(set(signals))[:20],
        )
