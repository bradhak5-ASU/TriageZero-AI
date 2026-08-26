"""Prompt-injection and secret-leak defenses.

Every byte of a failure package is untrusted attacker-influenceable data: a
test name, a console line, or a URL can contain instructions aimed at the
model. Two rules follow, and this module enforces both:

1. Evidence is *quoted data*, never instructions. It is delimited, labeled,
   and the system instruction tells the model to treat it as inert.
2. Nothing sensitive leaves the process. Secrets are redacted before any
   text reaches a provider, and logs carry ids and counts only.

The real guarantee is not the prompt — it is that the model's output is
validated against a closed schema and cannot trigger any action. Even a model
that fully obeys an injected instruction can only produce a proposal a human
must approve.
"""

import re
from typing import Any

REDACTED = "[REDACTED]"

# Patterns are intentionally broad: over-redacting evidence is safe, leaking is not.
_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Google API keys
    (re.compile(r"\b(AIza[0-9A-Za-z_\-]{10,})"), REDACTED),
    # generic secret keys
    (re.compile(r"\b(sk-[A-Za-z0-9]{10,})"), REDACTED),
    # GitHub tokens
    (re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{10,})"), REDACTED),
    (re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{8,}", re.IGNORECASE), f"Bearer {REDACTED}"),
    (re.compile(r"\bBasic\s+[A-Za-z0-9+/=]{8,}", re.IGNORECASE), f"Basic {REDACTED}"),
    (
        re.compile(
            r"(?i)\b(authorization|x-api-key|api[_-]?key|secret|password|passwd|token"
            r"|cookie|set-cookie)\b\s*[:=]\s*[^\s,;{}\"']+"
        ),
        r"\1: " + REDACTED,
    ),
    (
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
        REDACTED,
    ),
    # JWT
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"), REDACTED),
]

# Query parameters whose VALUE is dropped even if the name looks harmless.
_SENSITIVE_QUERY_KEYS = {
    "key", "api_key", "apikey", "token", "access_token", "id_token", "refresh_token",
    "secret", "client_secret", "password", "pwd", "signature", "sig", "auth",
    "session", "sessionid", "code",
}

# Only these request headers may ever be forwarded, if headers are added later.
HEADER_ALLOWLIST = frozenset({"accept", "content-type", "user-agent", "referer"})

_QUERY_RE = re.compile(r"([?&])([^=&#\s]+)=([^&#\s]*)")


def redact_urls(text: str) -> str:
    """Blank the values of sensitive query parameters inside any URL."""

    def _sub(match: re.Match[str]) -> str:
        sep, key, _value = match.groups()
        if key.lower() in _SENSITIVE_QUERY_KEYS:
            return f"{sep}{key}={REDACTED}"
        return match.group(0)

    return _QUERY_RE.sub(_sub, text)


def redact(text: str) -> str:
    """Remove credential-shaped substrings from a piece of evidence."""
    if not text:
        return text
    cleaned = redact_urls(text)
    for pattern, replacement in _SECRET_PATTERNS:
        cleaned = pattern.sub(replacement, cleaned)
    return cleaned


def redact_value(value: Any) -> Any:
    """Recursively redact strings inside evidence structures."""
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_value(item) for key, item in value.items()}
    return value


def filter_headers(headers: dict[str, str] | None) -> dict[str, str]:
    """Allowlist request headers and redact whatever survives."""
    if not headers:
        return {}
    return {
        name: redact(value)
        for name, value in headers.items()
        if name.lower() in HEADER_ALLOWLIST
    }


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"… [truncated, {len(text)} chars total]"


# Phrases that indicate evidence is trying to steer the model. Their presence
# does NOT change how the evidence is treated — it is always inert data — but
# counting them gives us an auditable signal for the evaluation harness.
_INJECTION_MARKERS = re.compile(
    r"(ignore (all )?(previous|prior|above) instructions"
    r"|disregard (the )?(above|previous|system)"
    r"|you are now"
    r"|system prompt"
    r"|print (the )?environment"
    r"|env(ironment)? variables?"
    r"|reveal (your|the) (prompt|instructions|key)"
    r"|read .{0,30}oracle"
    r"|expected_(classification|severity|release_risk|action)"
    r"|create (a )?github issue"
    r"|run (a )?(shell|bash|command)"
    r"|execute .{0,20}(command|script)"
    r"|confidence (of )?1\.0"
    r"|mark this as)",
    re.IGNORECASE,
)


def count_injection_markers(text: str) -> int:
    """How many steering attempts appear in this evidence (audit signal only)."""
    return len(_INJECTION_MARKERS.findall(text or ""))
