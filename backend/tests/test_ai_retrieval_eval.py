"""Retrieval determinism, corpus eligibility, dataset splitting, and metrics."""

import json

import pytest

from app.ai.retrieval import (
    DeterministicSimilarityIndex,
    RetrievalCandidate,
    console_signature,
    error_terms,
    normalize_endpoint,
    score,
    stack_component,
    status_family,
)
from app.evaluation.datasets import (
    HOLDOUT_FAMILIES,
    VALIDATION_FAMILIES,
    assert_no_family_leakage,
    split_by_family,
)
from app.evaluation.generator import generate_cases
from app.evaluation.metrics import EvaluationMetrics, evaluate_gates
from app.schemas.failure_package import FailurePackage


def candidate(**overrides) -> RetrievalCandidate:
    base = {
        "investigation_id": "INV-1",
        "repository": "novacart-target",
        "test_file": "playwright-tests/tests/checkout.spec.ts",
        "classification": "backend_application_defect",
        "endpoint": "/api/v1/orders",
        "status_family": "5xx",
        "browser": "chromium",
        "environment": "local",
        "error_terms": error_terms("Expected HTTP 201 but received HTTP 500"),
        "stack_component": "checkout.page.ts",
        "console_signature": "TypeError",
        "expected": "201",
        "actual": "500",
        "root_cause_summary": "orders endpoint failed",
        "resolution": "fixed",
        "date": "2026-08-01T00:00:00Z",
    }
    return RetrievalCandidate(**{**base, **overrides})


# --- signal helpers --------------------------------------------------------


def test_endpoint_normalization_collapses_ids():
    assert normalize_endpoint("http://x/api/v1/orders/7781") == "/api/v1/orders/:id"
    assert normalize_endpoint("http://x/api/v1/orders/9002") == "/api/v1/orders/:id"
    assert normalize_endpoint(None) is None


def test_status_family_groups_codes():
    assert status_family(500) == "5xx"
    assert status_family(503) == "5xx"
    assert status_family(404) == "4xx"
    assert status_family(0) == "connection"


def test_console_signature_extracts_error_kind():
    assert console_signature(["TypeError: undefined is not an object"]) == "TypeError"
    assert console_signature(["ReferenceError: x is not defined"]) == "ReferenceError"


def test_stack_component_extracts_file():
    assert stack_component("Error\n    at foo (playwright/pages/checkout.page.ts:88:5)") == (
        "checkout.page.ts"
    )


# --- scoring ---------------------------------------------------------------


def test_identical_candidates_fire_every_signal():
    value, signals = score(candidate(), candidate(investigation_id="INV-2"))
    assert value > 0.9
    for expected in (
        "same_repository",
        "same_test_file",
        "same_endpoint",
        "same_status_family",
        "same_classification",
        "shared_error_terms",
        "same_browser_environment",
        "similar_stack_component",
        "similar_console_signature",
        "similar_expected_actual",
    ):
        assert expected in signals


def test_unrelated_candidates_score_low():
    other = candidate(
        investigation_id="INV-9",
        repository="other-repo",
        test_file="tests/unrelated.spec.ts",
        classification="environment_failure",
        endpoint="/health",
        status_family="connection",
        browser="webkit",
        environment="production",
        error_terms=error_terms("DNS resolution failed entirely"),
        stack_component="smoke.spec.ts",
        console_signature=None,
        expected="",
        actual="",
    )
    value, signals = score(candidate(), other)
    assert value < 0.3
    assert "same_test_file" not in signals


def test_matching_signals_explain_the_score():
    """A partial match scores below a full match, and says which signals fired."""
    partial = candidate(
        investigation_id="INV-3",
        repository="other-repo",
        browser="webkit",
        endpoint="/api/v1/cart",
        stack_component="cart.spec.ts",
        console_signature=None,
    )
    value, signals = score(candidate(), partial)
    assert "same_repository" not in signals
    assert "same_endpoint" not in signals
    assert "same_test_file" in signals
    assert "same_classification" in signals
    full_value, _ = score(candidate(), candidate(investigation_id="INV-2"))
    assert 0 < value < full_value


def test_ranking_is_deterministic_across_runs():
    index = DeterministicSimilarityIndex()
    corpus = [candidate(investigation_id=f"INV-{i}") for i in range(2, 8)]
    query = candidate(investigation_id="INV-1")
    first = [(c.investigation_id, v) for v, _s, c in index.search(query, corpus)]
    for _ in range(5):
        assert [(c.investigation_id, v) for v, _s, c in index.search(query, corpus)] == first


def test_query_never_matches_itself():
    index = DeterministicSimilarityIndex()
    query = candidate(investigation_id="INV-1")
    results = index.search(query, [query])
    assert results == []


# --- corpus eligibility ----------------------------------------------------


def test_only_reviewed_or_synthetic_rows_enter_the_corpus(client, sample_package):
    """An unreviewed AI prediction must never inform a later investigation."""
    first = client.post("/api/v1/investigations", json=sample_package).json()["investigation_id"]
    second_pkg = json.loads(json.dumps(sample_package))
    second_pkg["run"]["run_id"] = "github-run-77777"
    second_pkg["failure"]["message"] = "Expected HTTP 201 but received HTTP 500 (second)"
    second = client.post("/api/v1/investigations", json=second_pkg).json()["investigation_id"]

    assert client.get(f"/api/v1/investigations/{second}").json()["similarFailures"] == []

    client.post(
        f"/api/v1/investigations/{first}/resolution",
        json={
            "classification": "backend_application_defect",
            "severity": "critical",
            "releaseRisk": "block_release",
            "resolutionSummary": "Fixed the orders handler.",
            "responsibleComponent": "novacart-api",
            "resolver": "reviewer",
        },
    )
    client.post(f"/api/v1/investigations/{second}/retry")
    matches = client.get(f"/api/v1/investigations/{second}").json()["similarFailures"]
    assert [m["id"] for m in matches] == [first]
    assert matches[0]["matchingSignals"]


def test_resolution_preserves_the_original_ai_prediction(client, sample_package):
    inv_id = client.post("/api/v1/investigations", json=sample_package).json()["investigation_id"]
    before = client.get(f"/api/v1/investigations/{inv_id}").json()
    predicted = before["classification"]

    after = client.post(
        f"/api/v1/investigations/{inv_id}/resolution",
        json={
            "classification": "test_automation_defect",  # human disagrees
            "severity": "medium",
            "releaseRisk": "low",
            "resolutionSummary": "Actually a stale selector.",
            "responsibleComponent": "qa",
            "resolver": "reviewer",
        },
    ).json()

    assert after["humanResolution"]["classification"] == "test_automation_defect"
    # the model cannot overwrite its own scorecard
    assert after["originalPrediction"]["classification"] == predicted
    assert after["originalPrediction"]["classification"] != "test_automation_defect"


def test_resolution_rejects_invalid_values(client, sample_package):
    inv_id = client.post("/api/v1/investigations", json=sample_package).json()["investigation_id"]
    res = client.post(
        f"/api/v1/investigations/{inv_id}/resolution",
        json={
            "classification": "made_up",
            "severity": "critical",
            "releaseRisk": "block_release",
            "resolutionSummary": "x",
            "resolver": "r",
        },
    )
    assert res.status_code == 422


def test_resolution_audit_trail_records_corrections(client, sample_package):
    inv_id = client.post("/api/v1/investigations", json=sample_package).json()["investigation_id"]
    body = {
        "classification": "backend_application_defect",
        "severity": "critical",
        "releaseRisk": "block_release",
        "resolutionSummary": "First conclusion.",
        "responsibleComponent": "api",
        "resolver": "reviewer-one",
    }
    client.post(f"/api/v1/investigations/{inv_id}/resolution", json=body)
    second = client.post(
        f"/api/v1/investigations/{inv_id}/resolution",
        json={
            **body,
            "classification": "data_integrity_defect",
            "resolutionSummary": "Corrected after review.",
            "resolver": "reviewer-two",
        },
    ).json()
    assert second["humanResolution"]["revision"] == 2
    assert second["humanResolution"]["classification"] == "data_integrity_defect"


# --- dataset splitting -----------------------------------------------------


def test_split_is_grouped_by_family_with_no_leakage():
    cases = generate_cases(240, seed=20260825)
    split = split_by_family(cases)
    assert_no_family_leakage(split)  # raises on overlap

    corpus_f = {c.family for c in split.corpus}
    holdout_f = {c.family for c in split.holdout}
    validation_f = {c.family for c in split.validation}
    assert holdout_f == set(HOLDOUT_FAMILIES)
    assert validation_f == set(VALIDATION_FAMILIES)
    assert not corpus_f & holdout_f
    assert not corpus_f & validation_f


def test_near_duplicate_variants_never_straddle_splits():
    """Two cases from the same family must land in the same partition."""
    cases = generate_cases(240, seed=20260825)
    split = split_by_family(cases)
    partition = {}
    for name, subset in (
        ("corpus", split.corpus),
        ("validation", split.validation),
        ("holdout", split.holdout),
    ):
        for case in subset:
            assert partition.setdefault(case.family, name) == name


def test_family_leakage_is_detected():
    from app.evaluation.datasets import SplitResult

    cases = generate_cases(36, seed=1)
    same_family = [c for c in cases if c.family == "selector_drift"]
    bad = SplitResult(corpus=same_family[:2], validation=[], holdout=same_family[2:4])
    with pytest.raises(ValueError, match="family leakage"):
        assert_no_family_leakage(bad)


def test_generation_is_reproducible_for_a_seed():
    a = generate_cases(40, seed=99)
    b = generate_cases(40, seed=99)
    assert [c.package for c in a] == [c.package for c in b]
    c = generate_cases(40, seed=100)
    assert [x.package for x in a] != [x.package for x in c]


def test_generated_packages_satisfy_the_v1_contract():
    for case in generate_cases(60, seed=20260825):
        FailurePackage.model_validate(case.package)  # raises if invalid


def test_generator_covers_every_scenario_family():
    from app.evaluation.generator import family_distribution
    from app.evaluation.scenarios import TEMPLATES

    dist = family_distribution(generate_cases(240, seed=20260825))
    assert set(dist) == {t.family for t in TEMPLATES}
    assert sum(dist.values()) == 240
    assert min(dist.values()) >= 20  # balanced, not lopsided


# --- metrics ---------------------------------------------------------------


def _add(metrics, actual, predicted, confidence=0.9, **kw):
    metrics.add(
        expected={
            "classification": actual,
            "severity": "critical",
            "release_risk": "block_release",
        },
        predicted={
            "classification": predicted,
            "severity": "critical",
            "release_risk": "block_release",
        },
        confidence=confidence,
        latency_ms=kw.get("latency", 10),
        provider="deterministic",
        schema_valid=kw.get("schema_valid", True),
        abstained=kw.get("abstained", False),
        fallback=kw.get("fallback", False),
        provider_error=False,
    )


def test_confusion_matrix_and_per_class_metrics():
    m = EvaluationMetrics()
    _add(m, "backend_application_defect", "backend_application_defect")
    _add(m, "backend_application_defect", "backend_application_defect")
    _add(m, "backend_application_defect", "unknown", abstained=True)
    _add(m, "test_automation_defect", "test_automation_defect")

    assert m.confusion["backend_application_defect"]["backend_application_defect"] == 2
    assert m.confusion["backend_application_defect"]["unknown"] == 1
    s = m.summary()
    assert s["total_cases"] == 4
    assert s["accuracy"] == 0.75
    backend = next(r for r in s["per_class"] if r["label"] == "backend_application_defect")
    assert backend["support"] == 3
    assert backend["recall"] == pytest.approx(2 / 3, abs=1e-3)
    assert backend["precision"] == 1.0


def test_macro_f1_averages_present_classes():
    m = EvaluationMetrics()
    _add(m, "backend_application_defect", "backend_application_defect")
    _add(m, "test_automation_defect", "test_automation_defect")
    s = m.summary()
    assert s["macro_f1"] == 1.0
    assert s["weighted_f1"] == 1.0


def test_coverage_and_abstention_are_tracked():
    m = EvaluationMetrics()
    _add(m, "backend_application_defect", "backend_application_defect")
    _add(m, "backend_application_defect", "unknown", abstained=True)
    s = m.summary()
    assert s["coverage"] == 0.5
    assert s["unknown_or_needs_review_rate"] == 0.5


def test_brier_score_rewards_calibration():
    confident_right = EvaluationMetrics()
    _add(confident_right, "backend_application_defect", "backend_application_defect", 1.0)
    assert confident_right.summary()["brier_score"] == 0.0

    confident_wrong = EvaluationMetrics()
    _add(confident_wrong, "backend_application_defect", "unknown", 1.0)
    assert confident_wrong.summary()["brier_score"] == 1.0


def test_high_confidence_errors_are_counted():
    m = EvaluationMetrics()
    _add(m, "backend_application_defect", "unknown", 0.95)
    _add(m, "backend_application_defect", "unknown", 0.40)
    s = m.summary()
    assert s["incorrect_high_confidence_count"] == 1


def test_critical_and_block_release_recall():
    m = EvaluationMetrics()
    m.add(
        expected={
            "classification": "backend_application_defect",
            "severity": "critical",
            "release_risk": "block_release",
        },
        predicted={
            "classification": "backend_application_defect",
            "severity": "critical",
            "release_risk": "block_release",
        },
        confidence=0.9,
        latency_ms=5,
        provider="deterministic",
        schema_valid=True,
        abstained=False,
        fallback=False,
        provider_error=False,
    )
    m.add(
        expected={
            "classification": "backend_application_defect",
            "severity": "critical",
            "release_risk": "block_release",
        },
        predicted={"classification": "unknown", "severity": "low", "release_risk": "none"},
        confidence=0.3,
        latency_ms=5,
        provider="deterministic",
        schema_valid=True,
        abstained=True,
        fallback=False,
        provider_error=False,
    )
    s = m.summary()
    assert s["critical_defect_recall"] == 0.5
    assert s["block_release_recall"] == 0.5


def test_quality_gates_report_pass_and_fail_honestly():
    gates = evaluate_gates(
        {
            "structured_output_validity": 1.0,
            "oracle_leakage_count": 0,
            "unauthorized_action_count": 0,
            "prompt_injection_policy_violations": 0,
            "critical_defect_recall": 0.5,
            "block_release_recall": 1.0,
            "accuracy": 0.9,
            "macro_f1": 0.5,
        }
    )
    assert gates["accuracy"]["passed"] is True
    assert gates["critical_defect_recall"]["passed"] is False
    assert gates["macro_f1"]["passed"] is False
    assert gates["oracle_leakage_count"]["passed"] is True


def test_latency_percentiles():
    m = EvaluationMetrics()
    for latency in (1, 2, 3, 4, 100):
        _add(m, "backend_application_defect", "backend_application_defect", latency=latency)
    s = m.summary()
    assert s["latency_p50_ms"] == 3
    assert s["latency_p95_ms"] == 100


def test_evaluation_measures_retrieval_and_injection_probes(tmp_path, monkeypatch):
    from app.evaluation import datasets
    from app.evaluation.datasets import build
    from app.evaluation.run import run_evaluation

    monkeypatch.setattr(datasets, "DATASET_DIR", tmp_path / "datasets")
    monkeypatch.setattr(datasets, "ORACLE_DIR", tmp_path / "oracle")
    build(90, 20260825)
    report = run_evaluation(str(tmp_path / "datasets" / "holdout.json"), "deterministic")
    summary = report["summary"]

    assert summary["prompt_injection_cases_evaluated"] > 0
    assert summary["prompt_injection_policy_violations"] == 0
    assert summary["oracle_leakage_count"] == 0
    assert summary["retrieval_top1_accuracy"] is not None
    assert summary["retrieval_top3_accuracy"] is not None
    assert summary["retrieval_top3_accuracy"] >= summary["retrieval_top1_accuracy"]


def test_evaluation_counts_provider_fallback_as_provider_error(tmp_path, monkeypatch):
    from app.core.config import get_settings
    from app.evaluation import datasets
    from app.evaluation.datasets import build
    from app.evaluation.run import run_evaluation

    monkeypatch.setattr(datasets, "DATASET_DIR", tmp_path / "datasets")
    monkeypatch.setattr(datasets, "ORACLE_DIR", tmp_path / "oracle")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    get_settings.cache_clear()
    build(36, 20260825)
    report = run_evaluation(str(tmp_path / "datasets" / "holdout.json"), "gemini")

    assert report["summary"]["fallback_rate"] == 1.0
    assert report["summary"]["provider_error_rate"] == 1.0
