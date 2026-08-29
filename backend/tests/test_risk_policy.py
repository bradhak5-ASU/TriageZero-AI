import pytest

from app.ai.risk import apply_risk_policy, calculate_risk
from tests.fakes import valid_model_analysis


@pytest.mark.parametrize(
    "classification,severity,release_risk",
    [
        ("backend_application_defect", "high", "block_release"),
        ("data_integrity_defect", "high", "block_release"),
        ("frontend_application_defect", "high", "block_release"),
        ("dependency_failure", "high", "moderate"),
        ("performance_timing_defect", "medium", "moderate"),
        ("test_automation_defect", "low", "none"),
        ("environment_failure", "medium", "moderate"),
        ("unknown", "medium", "moderate"),
    ],
)
def test_risk_policy_is_stable_for_every_classification(
    classification, severity, release_risk
):
    assert calculate_risk(classification, 0.9) == {
        "severity": severity,
        "release_risk": release_risk,
    }


def test_provider_supplied_risk_cannot_override_release_policy():
    provider_result = valid_model_analysis(
        classification="test_automation_defect",
        severity="critical",
        release_risk="block_release",
    )
    normalized = apply_risk_policy(provider_result)
    assert normalized.severity == "low"
    assert normalized.release_risk == "none"


def test_low_confidence_hard_block_is_reduced_and_sent_to_review():
    assert calculate_risk("backend_application_defect", 0.4)["release_risk"] == "high"
