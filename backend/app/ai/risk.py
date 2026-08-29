"""Application-owned severity and release-risk policy.

Generated text must not directly control a release gate. Providers classify
the evidence and explain the result; this module converts that classification
into a stable, auditable risk decision shared by direct Gemini and ADK.
"""

from app.ai.schemas import ModelAnalysis

RISK_POLICY: dict[str, tuple[str, str]] = {
    "backend_application_defect": ("high", "block_release"),
    "data_integrity_defect": ("high", "block_release"),
    "frontend_application_defect": ("high", "block_release"),
    "dependency_failure": ("high", "moderate"),
    "performance_timing_defect": ("medium", "moderate"),
    "test_automation_defect": ("low", "none"),
    "environment_failure": ("medium", "moderate"),
    "unknown": ("medium", "moderate"),
}


def calculate_risk(classification: str, confidence: float) -> dict[str, str]:
    severity, release_risk = RISK_POLICY.get(classification, ("medium", "moderate"))
    if confidence < 0.6 and release_risk == "block_release":
        # Low-confidence results become needs_review. Keep risk conservative
        # without asserting a definitive hard block from a weak prediction.
        release_risk = "high"
    return {"severity": severity, "release_risk": release_risk}


def apply_risk_policy(analysis: ModelAnalysis) -> ModelAnalysis:
    return analysis.model_copy(
        update=calculate_risk(analysis.classification, analysis.confidence)
    )
