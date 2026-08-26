"""Evidence handling: private-oracle detection, artifact-path safety,
package sanitization, and the idempotency fingerprint.

This module is the server-side security boundary for oracle separation.
The deterministic analyzer never reads the private QA oracle
(playwright-tests/evaluation/expected-results.json) or any file outside the
submitted package — nothing in this backend opens files from the test repo.
"""

import hashlib
import json
import posixpath
import re
from typing import Any

from app.schemas.failure_package import FailurePackage

FORBIDDEN_ORACLE_FIELDS = frozenset(
    {
        "expected_classification",
        "expected_severity",
        "expected_release_risk",
        "expected_action",
        "private_oracle",
        "oracle",
        "controlled_defect",
        "defect_scenario",
        "scenario_name",
    }
)

ARTIFACT_KINDS: dict[str, tuple[str, str]] = {
    "screenshot_path": ("screenshot", "Failure screenshot"),
    "trace_path": ("trace", "Playwright trace"),
    "video_path": ("video", "Test video"),
    "console_log_path": ("console_log", "Console log"),
    "network_log_path": ("network_log", "Network log"),
}

_WINDOWS_ABS = re.compile(r"^[a-zA-Z]:[\\/]")


def find_forbidden_paths(value: Any, path: str = "") -> list[str]:
    """Recursively find private QA-oracle keys at any depth in the raw body.
    Returns key paths only — never values."""
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_path = f"{path}.{key}" if path else str(key)
            if key in FORBIDDEN_ORACLE_FIELDS:
                found.append(key_path)
            found.extend(find_forbidden_paths(child, key_path))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            found.extend(find_forbidden_paths(item, f"{path}[{i}]"))
    return found


def sanitize_artifact_path(raw: str) -> str:
    """Validate and normalize an artifact path. Artifacts are metadata only in
    this milestone — the backend never opens them — but unsafe paths are
    rejected so nothing dangerous is ever persisted or displayed.
    Raises ValueError for unsafe paths."""
    path = raw.strip()
    if not path:
        raise ValueError("artifact path is empty")
    lowered = path.lower()
    if lowered.startswith("file://"):
        raise ValueError("file:// artifact URLs are not allowed")
    normalized = path.replace("\\", "/")
    if normalized.startswith(("/", "~")) or _WINDOWS_ABS.match(path):
        raise ValueError("artifact paths must be relative")
    normalized = posixpath.normpath(normalized)
    if normalized.startswith("..") or "/../" in f"/{normalized}/":
        raise ValueError("artifact paths must not traverse directories")
    if normalized.startswith(("/", "~")):
        raise ValueError("artifact paths must be relative")
    return normalized


def build_artifact_metadata(pkg: FailurePackage) -> list[dict[str, Any]]:
    """Turn artifact paths into the frontend's artifact cards. Unsafe paths
    raise ValueError (the whole package is rejected — tested explicitly)."""
    artifacts: list[dict[str, Any]] = []
    if pkg.artifacts is None:
        return artifacts
    for field, (kind, label) in ARTIFACT_KINDS.items():
        raw = getattr(pkg.artifacts, field, None)
        if raw:
            artifacts.append(
                {
                    "kind": kind,
                    "label": label,
                    "path": sanitize_artifact_path(raw),
                    "sizeBytes": 0,  # metadata only; sizes arrive with Cloud Storage later
                    "available": True,
                }
            )
    return artifacts


def sanitized_package_dict(pkg: FailurePackage) -> dict[str, Any]:
    """The audit copy of the package: validated fields (plus preserved safe
    extras) with artifact paths normalized."""
    data = pkg.model_dump(mode="json")
    if pkg.artifacts is not None:
        for field in ARTIFACT_KINDS:
            raw = data.get("artifacts", {}).get(field)
            if raw:
                data["artifacts"][field] = sanitize_artifact_path(raw)
    return data


def package_fingerprint(sanitized: dict[str, Any]) -> str:
    """Deterministic SHA-256 over the canonicalized sanitized package.
    Volatile run metadata (started_at) is excluded so an identical failure
    re-submitted by the same run is deduplicated."""
    canonical = json.loads(json.dumps(sanitized))
    if isinstance(canonical.get("run"), dict):
        canonical["run"].pop("started_at", None)
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
