"""Backwards-compatible entry point for the deterministic analyzer.

The implementation moved to ``app.ai.deterministic`` when the provider
abstraction was introduced. Behavior is unchanged; this module keeps the
original import path working.
"""

from app.ai.deterministic import DeterministicAnalyzer, classify
from app.ai.schemas import ModelAnalysis
from app.schemas.failure_package import FailurePackage

__all__ = ["DeterministicAnalyzer", "analyze", "classify"]


def analyze(pkg: FailurePackage) -> ModelAnalysis:
    """Deterministic classification for one failure package."""
    return classify(pkg)
