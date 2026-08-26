"""Seed the synthetic historical retrieval corpus.

    python -m app.evaluation.seed_history --count 240 --seed 20260825

Only *corpus* cases are inserted — holdout and validation families never enter
the investigation store, so retrieval can never hand the analyzer a sibling of
a case it is about to be measured on.

Seeded rows are marked ``is_synthetic`` internally. That marker is database
metadata only: it is not part of the failure-package contract and is never
sent to a model. Cleanup is scoped to those rows, so genuine investigations
cannot be deleted by this tool.
"""

import argparse
import json
import sys

from app.ai.deterministic import classify
from app.core.config import get_settings
from app.db.session import init_db, new_session, reset_db_state
from app.evaluation.datasets import build, split_by_family
from app.evaluation.generator import GeneratedCase
from app.repositories import investigations as repo
from app.schemas.failure_package import FailurePackage
from app.services.evidence import package_fingerprint, sanitized_package_dict
from app.services.investigations import new_investigation_id, now_iso


def _record_for(case: GeneratedCase):
    from app.db.models import InvestigationRecord

    pkg = FailurePackage.model_validate(case.package)
    sanitized = sanitized_package_dict(pkg)
    analysis = classify(pkg)

    doc = {
        "branch": pkg.repository.branch,
        "commitSha": pkg.repository.commit_sha,
        "runId": pkg.run.run_id,
        "browser": pkg.environment.browser,
        "trigger": pkg.run.trigger,
        "evidence": {
            "expected": pkg.failure.expected,
            "actual": pkg.failure.actual,
            "message": pkg.failure.message,
            "stackTrace": pkg.failure.stack_trace,
            "network": [
                {"method": n.method, "url": n.url, "status": n.status}
                for n in pkg.network_evidence
            ],
            "consoleErrors": list(pkg.console_errors),
            "artifacts": [],
        },
        # historical cases are RESOLVED cases: the summary is the human-reviewed
        # outcome, which is what makes them eligible for retrieval
        "rootCause": {
            "summary": case.root_cause,
            "component": analysis.responsible_component,
            "confidenceExplanation": "Recorded from the resolved historical case.",
            "nextStep": case.resolution,
        },
        "recommendedAction": {
            "action": case.resolution,
            "rationale": "Historical resolution recorded by a reviewer.",
            "issueTitle": f"[history] {pkg.test.name}",
            "labels": ["history", "synthetic-benchmark"],
            "owner": analysis.responsible_component,
            "approvalState": "executed",
        },
        "humanResolution": {
            "classification": case.expected["classification"],
            "severity": case.expected["severity"],
            "releaseRisk": case.expected["release_risk"],
            "resolutionSummary": case.resolution,
            "responsibleComponent": analysis.responsible_component,
            "resolver": "synthetic-benchmark",
            "resolvedAt": case.created_at,
            "revision": 1,
        },
        "actionHistory": [],
        "timeline": [{"id": "t0", "label": "Historical case imported", "at": case.created_at}],
        "actionTaken": "Historical synthetic benchmark case",
        "evidenceHighlights": [],
        "aiMetadata": None,
        "isSyntheticBenchmark": True,
    }

    return InvestigationRecord(
        id=new_investigation_id(),
        fingerprint=package_fingerprint(sanitized),
        idempotency_key=None,
        status="completed",
        stage="action_recommendation",
        retry_count=0,
        repository=pkg.repository.name,
        environment=pkg.environment.name,
        test_name=pkg.test.name,
        test_file=pkg.test.file,
        classification=case.expected["classification"],
        severity=case.expected["severity"],
        release_risk=case.expected["release_risk"],
        confidence=None,
        created_at=case.created_at,
        updated_at=now_iso(),
        completed_at=case.created_at,
        elapsed_ms=None,
        package_json=json.dumps(sanitized),
        doc_json=json.dumps(doc),
        is_synthetic=True,
        synthetic_family=case.family,
        resolution_json=json.dumps(doc["humanResolution"]),
    )


def seed(count: int, seed_value: int, *, database_url: str | None = None) -> dict:
    settings = get_settings()
    if settings.app_env.lower() in ("production", "prod"):
        raise SystemExit(
            "Refusing to seed synthetic data in production mode (APP_ENV=production)."
        )
    if database_url:
        import os

        os.environ["DATABASE_URL"] = database_url
        get_settings.cache_clear()
        reset_db_state()

    cases, written = build(count, seed_value)
    corpus = split_by_family(cases).corpus

    init_db()
    session = new_session()
    inserted = skipped = 0
    try:
        for case in corpus:
            record = _record_for(case)
            if repo.get_by_fingerprint(session, record.fingerprint):
                skipped += 1  # never duplicate a fingerprint
                continue
            session.add(record)
            session.commit()
            inserted += 1
    finally:
        session.close()

    return {**written, "inserted": inserted, "skipped_duplicates": skipped}


def reset_synthetic(*, database_url: str | None = None) -> int:
    """Delete ONLY seeded synthetic rows. Genuine investigations are never
    touched: the delete is scoped by the internal is_synthetic marker."""
    if database_url:
        import os

        os.environ["DATABASE_URL"] = database_url
        get_settings.cache_clear()
        reset_db_state()
    init_db()
    session = new_session()
    try:
        ids = repo.synthetic_ids(session)
        for investigation_id in ids:
            record = repo.get(session, investigation_id)
            if record is not None and record.is_synthetic:
                session.delete(record)
        session.commit()
        return len(ids)
    finally:
        session.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed the synthetic historical corpus.")
    parser.add_argument("--count", type=int, default=240)
    parser.add_argument("--seed", type=int, required=False, default=20260825)
    parser.add_argument("--database-url", type=str, default=None,
                        help="Temporary database path, e.g. sqlite:///./data/benchmark.db")
    parser.add_argument("--reset", action="store_true",
                        help="Delete seeded synthetic rows only, then exit.")
    args = parser.parse_args(argv)

    if args.reset:
        removed = reset_synthetic(database_url=args.database_url)
        print(json.dumps({"removed_synthetic_rows": removed}, indent=2))
        return 0

    summary = seed(args.count, args.seed, database_url=args.database_url)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
