"""Historical-pattern retrieval.

Deterministic, explainable, and locally runnable: every match reports which
named signals fired, so a reviewer can see *why* two failures were considered
similar instead of trusting an opaque score. No embeddings, no credentials,
no network.

History is used for retrieval and evaluation only — never to train a model.
The ``SimilarityIndex`` protocol is the seam where a vector-backed index can
be introduced later without changing callers.
"""

import re
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse

WORD = re.compile(r"[a-zA-Z]{4,}")
STACK_COMPONENT = re.compile(r"([\w\-./]+\.(?:ts|tsx|js|jsx|py))")

# Weighted signals. Names are part of the API: they are shown in the UI.
SIGNAL_WEIGHTS: dict[str, float] = {
    "same_repository": 0.08,
    "same_test_file": 0.22,
    "same_endpoint": 0.20,
    "same_status_family": 0.10,
    "same_classification": 0.14,
    "shared_error_terms": 0.10,
    "same_browser_environment": 0.05,
    "similar_stack_component": 0.06,
    "similar_console_signature": 0.05,
    "similar_expected_actual": 0.10,
}

MIN_SCORE = 0.30
MAX_RESULTS = 3


@dataclass(frozen=True)
class RetrievalCandidate:
    """A stored investigation reduced to comparable features."""

    investigation_id: str
    repository: str
    test_file: str
    classification: str | None
    endpoint: str | None
    status_family: str | None
    browser: str
    environment: str
    error_terms: frozenset[str]
    stack_component: str | None
    console_signature: str | None
    expected: str
    actual: str
    root_cause_summary: str
    resolution: str
    date: str
    is_synthetic: bool = False


class SimilarityIndex(Protocol):
    """Seam for a future embedding-backed index."""

    def search(
        self, query: RetrievalCandidate, corpus: list[RetrievalCandidate]
    ) -> list[tuple[float, list[str], RetrievalCandidate]]: ...


def normalize_endpoint(url: str | None) -> str | None:
    """Path only, with numeric and id-like segments collapsed, so
    /api/v1/orders/7781 and /api/v1/orders/9002 compare equal."""
    if not url:
        return None
    try:
        path = urlparse(url).path or url
    except ValueError:
        path = url
    parts = []
    for segment in path.strip("/").split("/"):
        if not segment:
            continue
        if segment.isdigit() or re.fullmatch(r"[0-9a-fA-F-]{8,}", segment):
            parts.append(":id")
        else:
            parts.append(segment.lower())
    return "/" + "/".join(parts) if parts else "/"


def status_family(status: int | None) -> str | None:
    if not status:
        return "connection" if status == 0 else None
    return f"{status // 100}xx"


def error_terms(text: str) -> frozenset[str]:
    return frozenset(WORD.findall((text or "").lower()))


def stack_component(stack: str | None) -> str | None:
    if not stack:
        return None
    match = STACK_COMPONENT.search(stack)
    return match.group(1).split("/")[-1].lower() if match else None


def console_signature(lines: list[str] | None) -> str | None:
    """First error *kind*, not the full message — 'TypeError' matches across
    differently-worded instances of the same class of bug."""
    for line in lines or []:
        match = re.search(r"\b(TypeError|ReferenceError|SyntaxError|RangeError|Uncaught)\b", line)
        if match:
            return match.group(1)
    return (lines or [None])[0][:60] if lines else None


def _mismatch_shape(expected: str, actual: str) -> str | None:
    """Compare the *shape* of a mismatch (numeric vs status vs text)."""
    if not expected and not actual:
        return None
    def shape(value: str) -> str:
        value = value.strip()
        if re.fullmatch(r"\d{3}", value):
            return "http_status"
        if re.fullmatch(r"[\d.,$]+", value):
            return "numeric"
        if not value:
            return "empty"
        return "text"
    return f"{shape(expected)}->{shape(actual)}"


def score(query: RetrievalCandidate, other: RetrievalCandidate) -> tuple[float, list[str]]:
    """Weighted similarity plus the names of the signals that fired."""
    fired: list[str] = []

    if query.repository == other.repository:
        fired.append("same_repository")
    if query.test_file == other.test_file:
        fired.append("same_test_file")
    if query.endpoint and query.endpoint == other.endpoint:
        fired.append("same_endpoint")
    if query.status_family and query.status_family == other.status_family:
        fired.append("same_status_family")
    if query.classification and query.classification == other.classification:
        fired.append("same_classification")

    union = query.error_terms | other.error_terms
    if union and len(query.error_terms & other.error_terms) / len(union) >= 0.3:
        fired.append("shared_error_terms")

    if query.browser == other.browser and query.environment == other.environment:
        fired.append("same_browser_environment")
    if query.stack_component and query.stack_component == other.stack_component:
        fired.append("similar_stack_component")
    if query.console_signature and query.console_signature == other.console_signature:
        fired.append("similar_console_signature")

    query_shape = _mismatch_shape(query.expected, query.actual)
    if query_shape and query_shape == _mismatch_shape(other.expected, other.actual):
        fired.append("similar_expected_actual")

    total = sum(SIGNAL_WEIGHTS[name] for name in fired)
    return min(round(total, 4), 0.97), fired


class DeterministicSimilarityIndex(SimilarityIndex):
    """Exhaustive weighted scan. Ordering is fully deterministic: score
    descending, then investigation id, so repeated runs are identical."""

    def search(
        self, query: RetrievalCandidate, corpus: list[RetrievalCandidate]
    ) -> list[tuple[float, list[str], RetrievalCandidate]]:
        scored: list[tuple[float, list[str], RetrievalCandidate]] = []
        for candidate in corpus:
            if candidate.investigation_id == query.investigation_id:
                continue
            value, fired = score(query, candidate)
            if value >= MIN_SCORE:
                scored.append((value, fired, candidate))
        scored.sort(key=lambda row: (-row[0], row[2].investigation_id))
        return scored[:MAX_RESULTS]


default_index = DeterministicSimilarityIndex()


def to_public(
    value: float, fired: list[str], candidate: RetrievalCandidate
) -> dict[str, Any]:
    """The shape the API and prompt see. Contains no evaluation labels and no
    oracle fields — only sanitized, human-written history."""
    return {
        "id": candidate.investigation_id,
        "similarity": value,
        "matchingSignals": fired,
        "testName": candidate.test_file,
        "classification": candidate.classification or "unknown",
        "rootCauseSummary": candidate.root_cause_summary[:400],
        "resolution": candidate.resolution[:300],
        "date": candidate.date,
        "issueRef": None,
        "isSynthetic": candidate.is_synthetic,
    }
