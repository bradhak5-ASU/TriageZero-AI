"""Process-local AI telemetry.

Counts and safe error codes only — never prompts, evidence, model responses,
or anything derived from credentials. Health reads this; nothing else writes
to it.
"""

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass
class AiTelemetry:
    last_success_at: str | None = None
    last_error_code: str | None = None
    last_error_at: str | None = None
    fallback_count: int = 0
    success_count: int = 0
    error_count: int = 0
    provider_calls: dict[str, int] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record_success(self, provider: str) -> None:
        with self._lock:
            self.success_count += 1
            self.last_success_at = _now()
            self.last_error_code = None
            self.last_error_at = None
            self.provider_calls[provider] = self.provider_calls.get(provider, 0) + 1

    def record_error(self, code: str) -> None:
        with self._lock:
            self.error_count += 1
            self.last_error_code = code
            self.last_error_at = _now()

    def record_fallback(self) -> None:
        with self._lock:
            self.fallback_count += 1

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "last_success_at": self.last_success_at,
                "last_error_code": self.last_error_code,
                "last_error_at": self.last_error_at,
                "fallback_count": self.fallback_count,
                "success_count": self.success_count,
                "error_count": self.error_count,
                "provider_calls": dict(self.provider_calls),
            }

    def reset(self) -> None:
        with self._lock:
            self.last_success_at = None
            self.last_error_code = None
            self.last_error_at = None
            self.fallback_count = 0
            self.success_count = 0
            self.error_count = 0
            self.provider_calls = {}


telemetry = AiTelemetry()
