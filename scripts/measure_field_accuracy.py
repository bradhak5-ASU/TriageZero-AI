"""Measure classification accuracy on *real* failures against external ground truth.

Why this exists
---------------
`app/evaluation` scores the deterministic analyzer against a generated holdout.
That is a regression tripwire, not an accuracy claim: the generator builds
scenarios out of the same signal vocabulary the rules encode, so a high score
there is close to tautological.

This script measures something different and much harder to fake. It reads the
investigations the platform actually produced from real Playwright runs against
the deployed application, and labels each one from evidence that exists
independently of the analyzer:

    the browser recorded an HTTP 5xx response from the application

A 5xx is the server admitting it failed. It is captured by Playwright, carried
in the failure package, and is true whether or not TriageZero exists. No rule,
prompt or heuristic in this repository has any say in it. A run whose evidence
contains one is a backend application defect, and any other classification is
wrong.

Runs with no externally decidable label are *excluded*, not guessed. The
catalogue-exhaustion failures are the important case: the tests fail at a
disabled control with no failing request, and "frontend defect" and "data
defect" are both defensible readings. Scoring those either way would be the
experimenter choosing the answer, so they are reported as unlabelled and left
out of the denominator.

Usage
-----
    DATABASE_URL=... python scripts/measure_field_accuracy.py
    python scripts/measure_field_accuracy.py --json exported-investigations.json

The database URL is read from the environment exactly as the backend reads it,
so this runs unchanged against local SQLite or Cloud SQL.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

#: An investigation whose evidence contains a response in this range is, as a
#: matter of external fact, a failure of the application's backend.
SERVER_ERROR_FLOOR = 500
SERVER_ERROR_CEILING = 599

#: The only label this script is willing to assert, and the classification the
#: analyzer must produce for it.
GROUND_TRUTH_LABEL = "backend_application_defect"


@dataclass(frozen=True)
class Case:
    investigation_id: str
    created_at: str
    test_name: str
    provider: str
    predicted: str | None
    confidence: float | None
    truth: str | None
    reason: str

    @property
    def labelled(self) -> bool:
        return self.truth is not None

    @property
    def correct(self) -> bool:
        return self.labelled and self.predicted == self.truth


def _label(evidence: dict) -> tuple[str | None, str]:
    """Derive ground truth from browser-recorded evidence alone."""
    network = evidence.get("network") or []
    server_errors = [
        entry
        for entry in network
        if isinstance(entry.get("status"), int)
        and SERVER_ERROR_FLOOR <= entry["status"] <= SERVER_ERROR_CEILING
    ]
    if server_errors:
        first = server_errors[0]
        method, url, status = first.get("method", "?"), first.get("url", "?"), first["status"]
        return GROUND_TRUTH_LABEL, f"{method} {url} -> {status}"
    return None, "no server error in evidence; not externally decidable"


def _case(row: dict) -> Case:
    doc = row["doc"]
    truth, reason = _label(doc.get("evidence") or {})
    return Case(
        investigation_id=row["id"],
        created_at=row["created_at"],
        test_name=row["test_name"],
        provider=str((doc.get("aiMetadata") or {}).get("provider") or "unknown"),
        predicted=row["classification"],
        confidence=row["confidence"],
        truth=truth,
        reason=reason,
    )


def _rows_from_database(url: str) -> list[dict]:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

    from app.db.models import InvestigationRecord  # noqa: PLC0415
    from app.db.session import build_engine, normalize_database_url  # noqa: PLC0415
    from sqlalchemy import select  # noqa: PLC0415
    from sqlalchemy.orm import Session  # noqa: PLC0415

    engine = build_engine(normalize_database_url(url))
    with Session(engine) as session:
        records = session.scalars(
            select(InvestigationRecord).where(InvestigationRecord.is_synthetic.is_(False))
        ).all()
        return [
            {
                "id": r.id,
                "created_at": r.created_at,
                "test_name": r.test_name,
                "classification": r.classification,
                "confidence": r.confidence,
                "doc": json.loads(r.doc_json),
            }
            for r in records
        ]


def _rows_from_json(path: Path) -> list[dict]:
    payload = json.loads(path.read_text())
    items = payload.get("items", payload) if isinstance(payload, dict) else payload
    return [
        {
            "id": item["id"],
            "created_at": item.get("createdAt", ""),
            "test_name": item.get("testName", ""),
            "classification": item.get("classification"),
            "confidence": item.get("confidence"),
            "doc": item,
        }
        for item in items
    ]


def report(cases: list[Case]) -> int:
    labelled = [c for c in cases if c.labelled]
    excluded = [c for c in cases if not c.labelled]

    print(f"investigations read      : {len(cases)}")
    print(f"externally labelled      : {len(labelled)}")
    print(f"excluded as undecidable  : {len(excluded)}")
    print()

    if not labelled:
        print("no labelled cases — nothing to measure")
        return 1

    by_provider: dict[str, list[Case]] = defaultdict(list)
    for case in labelled:
        by_provider[case.provider].append(case)

    print("accuracy by analysis provider")
    for provider in sorted(by_provider):
        group = by_provider[provider]
        hits = sum(1 for c in group if c.correct)
        print(f"  {provider:<24} {hits:>4}/{len(group):<4} = {hits / len(group):7.2%}")

    hits = sum(1 for c in labelled if c.correct)
    print(f"\noverall{' ' * 19}{hits:>4}/{len(labelled):<4} = {hits / len(labelled):7.2%}")

    wrong = [c for c in labelled if not c.correct]
    print("\ndisagreements")
    if not wrong:
        print("  none")
    for case in wrong:
        print(f"  {case.investigation_id}  predicted {case.predicted}  truth {case.truth}")
        print(f"      {case.test_name}")
        print(f"      evidence: {case.reason}")

    print("\nconfidence")
    for name, group in (("correct", [c for c in labelled if c.correct]), ("incorrect", wrong)):
        scored = [c.confidence for c in group if c.confidence is not None]
        if scored:
            print(f"  {name:<10}: mean {sum(scored) / len(scored):.3f}  n={len(scored)}")
        else:
            print(f"  {name:<10}: none")

    return 0 if not wrong else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json", type=Path, help="read an exported investigation list instead of the database"
    )
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    args = parser.parse_args()

    if args.json:
        rows = _rows_from_json(args.json)
    elif args.database_url:
        rows = _rows_from_database(args.database_url)
    else:
        parser.error("set DATABASE_URL or pass --json")

    return report([_case(row) for row in rows])


if __name__ == "__main__":
    raise SystemExit(main())
