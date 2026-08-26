"""Seeded generator for synthetic failure packages.

Reproducible: the same ``seed`` always yields the same corpus, so evaluation
runs are comparable. Every generated package must satisfy failure-package
v1.0, and none of them may contain a private-oracle field name — the expected
outcome travels separately, in the oracle file.
"""

import hashlib
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.evaluation.scenarios import (
    BROWSERS,
    ENVIRONMENTS,
    REPOSITORIES,
    TEMPLATES,
    ScenarioTemplate,
)

# Names that must never appear in generated, AI-visible data.
from app.services.evidence import FORBIDDEN_ORACLE_FIELDS

BASE_TIME = datetime(2026, 8, 1, 9, 0, 0, tzinfo=UTC)


@dataclass(frozen=True)
class GeneratedCase:
    """One synthetic case: the AI-visible package, plus the private expected
    outcome that is stored separately and read only after inference."""

    case_id: str
    family: str
    package: dict[str, Any]
    expected: dict[str, str]
    root_cause: str
    resolution: str
    created_at: str


def _sha(rng: random.Random) -> str:
    return hashlib.sha1(str(rng.random()).encode()).hexdigest()  # noqa: S324 - not security


def _build_case(
    template: ScenarioTemplate, index: int, rng: random.Random
) -> GeneratedCase:
    status = rng.choice(template.statuses) if template.statuses else 200
    expected_value = rng.choice(template.expected_values)
    actual_value = rng.choice(template.actual_values)
    message = (
        rng.choice(template.messages)
        .replace("{status}", str(status))
        .replace("{expected}", expected_value)
        .replace("{actual}", actual_value)
    )
    component = rng.choice(template.stack_components)
    test_name = rng.choice(template.test_names)
    test_file = rng.choice(template.test_files)
    repository = rng.choice(REPOSITORIES)
    browser = rng.choice(BROWSERS)
    environment = rng.choice(ENVIRONMENTS)
    created = BASE_TIME + timedelta(hours=index * 7 + rng.randint(0, 6))

    network: list[dict[str, Any]] = []
    if template.endpoints:
        endpoint = rng.choice(template.endpoints)
        url = endpoint if endpoint.startswith("http") else f"http://localhost:8000{endpoint}"
        network.append(
            {"method": rng.choice(template.methods), "url": url, "status": status}
        )
        # noise: an unrelated successful request, as a real capture would contain
        if rng.random() < 0.5:
            network.insert(
                0,
                {"method": "GET", "url": "http://localhost:8000/api/v1/session", "status": 200},
            )

    console = list(template.console_lines) and [rng.choice(template.console_lines)] or []
    if rng.random() < 0.3:
        console.append(rng.choice(template.noise_console))

    package = {
        "schema_version": "1.0",
        "source": "novacart-playwright",
        "run": {
            "run_id": f"github-run-{rng.randint(10000, 99999)}",
            "trigger": rng.choice(["ci", "local", "scheduled"]),
            "started_at": created.isoformat().replace("+00:00", "Z"),
        },
        "repository": {
            "name": repository,
            "branch": rng.choice(["main", "develop", "release/2.4", "feat/checkout"]),
            "commit_sha": _sha(rng),
        },
        "environment": {
            "name": environment,
            "target_url": "http://localhost:5173",
            "browser": browser,
        },
        "test": {
            "name": test_name,
            "file": test_file,
            "status": "failed",
            "retry": rng.choice([0, 0, 0, 1]),
        },
        "failure": {
            "expected": expected_value,
            "actual": actual_value,
            "message": message,
            "stack_trace": (
                f"Error: {message}\n    at assertion ({component}:{rng.randint(10, 300)}:"
                f"{rng.randint(1, 60)})\n    at {test_file}:{rng.randint(10, 200)}:3"
            ),
        },
        "network_evidence": network,
        "console_errors": console,
        "artifacts": {
            "screenshot_path": f"test-results/run-{index}/test-failed-1.png",
            "trace_path": f"test-results/run-{index}/trace.zip",
        },
    }

    return GeneratedCase(
        case_id=f"SYN-{template.family}-{index:04d}",
        family=template.family,
        package=package,
        expected={
            "classification": template.expected_classification,
            "severity": template.expected_severity,
            "release_risk": template.expected_release_risk,
        },
        root_cause=rng.choice(template.root_causes),
        resolution=rng.choice(template.resolutions),
        created_at=created.isoformat().replace("+00:00", "Z"),
    )


def assert_no_oracle_fields(payload: Any, path: str = "") -> None:
    """Generated AI-visible data must never carry an oracle field NAME."""
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in FORBIDDEN_ORACLE_FIELDS:
                raise ValueError(f"generated package contains oracle field at {path}.{key}")
            assert_no_oracle_fields(value, f"{path}.{key}")
    elif isinstance(payload, list):
        for i, item in enumerate(payload):
            assert_no_oracle_fields(item, f"{path}[{i}]")


def generate_cases(count: int, seed: int) -> list[GeneratedCase]:
    """Produce ``count`` cases spread evenly across every family.

    Seeding is explicit — there is no ambient default — so a corpus can always
    be reproduced from the recorded (count, seed) pair.
    """
    rng = random.Random(seed)
    cases: list[GeneratedCase] = []
    per_family = max(1, count // len(TEMPLATES))
    index = 0
    while len(cases) < count:
        for template in TEMPLATES:
            for _ in range(per_family):
                if len(cases) >= count:
                    break
                case = _build_case(template, index, rng)
                assert_no_oracle_fields(case.package)
                cases.append(case)
                index += 1
    return cases[:count]


def family_distribution(cases: list[GeneratedCase]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for case in cases:
        counts[case.family] = counts.get(case.family, 0) + 1
    return dict(sorted(counts.items()))
