"""Dataset construction and GROUPED splitting.

Three logically separate datasets:

* ``corpus``     — AI-visible resolved history used for retrieval.
* ``validation`` — used to tune prompts and policy.
* ``holdout``    — touched only for the final accuracy measurement.

Splitting is grouped by scenario *family*, never random by row. Variants
within a family are near-duplicates by construction; a random split would put
sibling cases in both the retrieval corpus and the holdout, and the retriever
would then hand the analyzer a near-copy of the answer. Grouping keeps whole
families on one side of the line.

The expected outcome for every case lives in a SEPARATE oracle file that the
inference path never opens.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.evaluation.generator import GeneratedCase, generate_cases

EVALUATION_DIR = Path(__file__).resolve().parents[2] / "evaluation"
DATASET_DIR = EVALUATION_DIR / "datasets"
ORACLE_DIR = EVALUATION_DIR / "oracle"
RESULTS_DIR = EVALUATION_DIR / "results"

# Families reserved for measurement. Held out whole — no variant of these
# families may appear in the retrieval corpus or the validation set.
HOLDOUT_FAMILIES = ("backend_5xx_inventory", "selector_drift", "dependency_provider")
VALIDATION_FAMILIES = ("performance_budget", "unknown_sparse")


@dataclass(frozen=True)
class SplitResult:
    corpus: list[GeneratedCase]
    validation: list[GeneratedCase]
    holdout: list[GeneratedCase]

    def summary(self) -> dict[str, Any]:
        return {
            "corpus": len(self.corpus),
            "validation": len(self.validation),
            "holdout": len(self.holdout),
            "corpus_families": sorted({c.family for c in self.corpus}),
            "validation_families": sorted({c.family for c in self.validation}),
            "holdout_families": sorted({c.family for c in self.holdout}),
        }


def split_by_family(cases: list[GeneratedCase]) -> SplitResult:
    """Group-aware split. No family appears in more than one partition."""
    corpus, validation, holdout = [], [], []
    for case in cases:
        if case.family in HOLDOUT_FAMILIES:
            holdout.append(case)
        elif case.family in VALIDATION_FAMILIES:
            validation.append(case)
        else:
            corpus.append(case)
    return SplitResult(corpus=corpus, validation=validation, holdout=holdout)


def assert_no_family_leakage(split: SplitResult) -> None:
    """Fail loudly if any family straddles two partitions."""
    corpus_f = {c.family for c in split.corpus}
    validation_f = {c.family for c in split.validation}
    holdout_f = {c.family for c in split.holdout}
    overlaps = (
        ("corpus/holdout", corpus_f & holdout_f),
        ("validation/holdout", validation_f & holdout_f),
        ("corpus/validation", corpus_f & validation_f),
    )
    for label, shared in overlaps:
        if shared:
            raise ValueError(f"family leakage between {label}: {sorted(shared)}")


def to_dataset_records(cases: list[GeneratedCase]) -> list[dict[str, Any]]:
    """AI-visible dataset rows. No expected outcome of any kind."""
    return [
        {
            "case_id": case.case_id,
            "family": case.family,
            "created_at": case.created_at,
            "package": case.package,
        }
        for case in cases
    ]


def to_oracle_records(cases: list[GeneratedCase]) -> dict[str, Any]:
    """The private expected outcomes, keyed by case id. Written to a separate
    file that the analyzer, prompts, and API never read."""
    return {
        "note": (
            "PRIVATE EVALUATION ORACLE — never submit these values to the "
            "analyzer, a prompt, ADK session state, or the investigation store."
        ),
        "cases": {
            case.case_id: {
                "classification": case.expected["classification"],
                "severity": case.expected["severity"],
                "release_risk": case.expected["release_risk"],
                "family": case.family,
            }
            for case in cases
        },
    }


def write_datasets(cases: list[GeneratedCase], seed: int) -> dict[str, Any]:
    """Write datasets and their oracles to disk, in separate directories."""
    split = split_by_family(cases)
    assert_no_family_leakage(split)
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    ORACLE_DIR.mkdir(parents=True, exist_ok=True)

    written: dict[str, Any] = {"seed": seed, **split.summary()}
    for name, subset in (
        ("corpus", split.corpus),
        ("validation", split.validation),
        ("holdout", split.holdout),
    ):
        dataset_path = DATASET_DIR / f"{name}.json"
        dataset_path.write_text(
            json.dumps(
                {
                    "dataset": name,
                    "synthetic": True,
                    "note": "SYNTHETIC BENCHMARK DATA — not production failures.",
                    "seed": seed,
                    "cases": to_dataset_records(subset),
                },
                indent=2,
            )
        )
        (ORACLE_DIR / f"{name}.oracle.json").write_text(
            json.dumps(to_oracle_records(subset), indent=2)
        )
        written[f"{name}_path"] = str(dataset_path)
    return written


def load_dataset(path: str | Path) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text())
    return payload["cases"]


def load_oracle(dataset_path: str | Path) -> dict[str, dict[str, str]]:
    """Load expected outcomes. Called ONLY after predictions exist."""
    name = Path(dataset_path).stem
    oracle_path = ORACLE_DIR / f"{name}.oracle.json"
    if not oracle_path.is_file():
        raise FileNotFoundError(f"No oracle for dataset {name} at {oracle_path}")
    return json.loads(oracle_path.read_text())["cases"]


def build(count: int, seed: int) -> tuple[list[GeneratedCase], dict[str, Any]]:
    cases = generate_cases(count, seed)
    return cases, write_datasets(cases, seed)
