"""Deterministic analyzer: evidence-driven classification, no oracle access."""


def create(client, pkg):
    inv_id = client.post("/api/v1/investigations", json=pkg).json()["investigation_id"]
    return client.get(f"/api/v1/investigations/{inv_id}").json()


def test_http_500_classified_as_backend_defect(client, sample_package):
    inv = create(client, sample_package)
    assert inv["status"] == "completed"
    assert inv["classification"] == "backend_application_defect"
    assert inv["severity"] == "critical"
    assert inv["releaseRisk"] == "block_release"
    assert inv["confidence"] >= 0.9
    assert inv["recommendedAction"]["approvalState"] == "awaiting_approval"


def test_connection_failure_classified_as_environment(client, sample_package):
    sample_package["failure"]["message"] = (
        "page.goto: net::ERR_NAME_NOT_RESOLVED at staging.novacart.internal"
    )
    sample_package["network_evidence"] = [
        {"method": "GET", "url": "https://staging.novacart.internal/", "status": 0}
    ]
    sample_package["console_errors"] = []
    inv = create(client, sample_package)
    assert inv["classification"] == "environment_failure"
    assert inv["releaseRisk"] == "none"


def test_locator_timeout_without_app_errors_is_test_automation(client, sample_package):
    sample_package["failure"] = {
        "expected": "result card visible",
        "actual": "locator matched 0 elements",
        "message": 'Timeout 15000ms waiting for locator("[data-test=result-card]")',
        "stack_trace": "TimeoutError at search.spec.ts:44",
    }
    sample_package["network_evidence"] = [
        {"method": "GET", "url": "http://localhost:8000/api/v1/search", "status": 200}
    ]
    sample_package["console_errors"] = []
    inv = create(client, sample_package)
    assert inv["classification"] == "test_automation_defect"
    assert inv["status"] == "completed"


def test_insufficient_evidence_becomes_needs_review(client, sample_package):
    sample_package["failure"] = {
        "expected": "",
        "actual": "",
        "message": "assertion mismatch",
        "stack_trace": "",
    }
    sample_package["network_evidence"] = []
    sample_package["console_errors"] = []
    inv = create(client, sample_package)
    assert inv["classification"] == "unknown"
    assert inv["status"] == "needs_review"
    assert inv["confidence"] < 0.6


def test_analyzer_is_deterministic():
    from app.schemas.failure_package import FailurePackage
    from app.services.analyzer import analyze
    from tests.conftest import SAMPLE_PACKAGE

    pkg = FailurePackage.model_validate(SAMPLE_PACKAGE)
    first, second = analyze(pkg), analyze(pkg)
    assert first == second


def test_analyzer_uses_only_submitted_evidence(client, sample_package):
    """Same evidence, different test name → same classification: nothing is
    keyed off scenario/test names."""
    inv_a = create(client, sample_package)
    sample_package["test"]["name"] = "a completely different name"
    sample_package["run"]["run_id"] = "github-run-99999"
    inv_b = create(client, sample_package)
    assert inv_a["classification"] == inv_b["classification"]
    assert inv_a["confidence"] == inv_b["confidence"]
