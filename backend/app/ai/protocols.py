"""The analyzer interface every provider implements."""

from typing import Any, Protocol, runtime_checkable

from app.ai.schemas import AnalysisContext, AnalysisResult
from app.schemas.failure_package import FailurePackage


@runtime_checkable
class Analyzer(Protocol):
    """One operation, one validated result type.

    The deterministic analyzer, the Gemini analyzer, and the ADK workflow all
    satisfy this protocol and all return the same ``AnalysisResult``, so the
    rest of the application never branches on which provider ran.
    """

    name: str

    def analyze(
        self,
        failure_package: FailurePackage,
        similar_cases: list[dict[str, Any]],
        context: AnalysisContext,
    ) -> AnalysisResult: ...


class AnalyzerError(Exception):
    """Provider failure carrying a SAFE error code.

    The code is a short slug (``timeout``, ``invalid_schema``, ``unconfigured``)
    that is safe to log and to surface in health output. It never contains
    credentials, prompt contents, or evidence.
    """

    def __init__(self, code: str, message: str = "", *, retryable: bool = False) -> None:
        super().__init__(message or code)
        self.code = code
        self.retryable = retryable
