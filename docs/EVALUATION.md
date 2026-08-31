# Evaluation guide

> **All results produced from the generated corpus are SYNTHETIC BENCHMARK
> RESULTS.** They describe how an analyzer behaves on constructed scenarios.
> They are not production accuracy and must never be quoted as such.

## Why this exists

Two questions this harness answers honestly:

1. Does a change make the analyzer better or worse — measured on *identical*
   data, so deterministic and Gemini/ADK runs are comparable?
2. Do the safety properties hold under measurement — zero oracle leakage, zero
   unauthorized actions, zero injection policy violations, 100% schema validity?

## Three datasets, grouped by family

| Dataset | Purpose | Families |
|---|---|---|
| `corpus` | AI-visible resolved history for retrieval | backend_5xx_checkout, data_integrity_totals, environment_dns, frontend_type_error |
| `validation` | tuning prompts and policy | performance_budget, unknown_sparse |
| `holdout` | final measurement only | backend_5xx_inventory, selector_drift, dependency_provider |

Splitting is **grouped by scenario family, never random by row**. Variants
within a family are near-duplicates by construction, so a random split would put
sibling cases on both sides and the retriever would hand the analyzer a
near-copy of the answer. `assert_no_family_leakage` fails loudly if a family
ever straddles two partitions, and a test asserts it.

The expected outcome for every case lives in a **separate oracle file**
(`backend/evaluation/oracle/*.oracle.json`) that the inference path never opens.
A test asserts that no module on the inference path so much as mentions
`load_oracle` or the oracle filename.

## Generate the corpus

```bash
cd backend
python -m app.evaluation.seed_history --count 240 --seed 20260825
```

Options: `--database-url sqlite:///./data/benchmark.db` to use a temporary
database, `--reset` to delete **only** seeded synthetic rows. Seeding refuses to
run when `APP_ENV=production`, never duplicates a fingerprint, and marks rows
with an internal `is_synthetic` flag that is not part of the failure-package
contract and is never sent to a model. Cleanup is scoped by that flag, so it
cannot delete a genuine investigation — there is a test for that too.

Only `corpus` families are inserted. Holdout cases never enter the investigation
store at all.

## Run an evaluation

```bash
cd backend
python -m app.evaluation.run \
  --provider deterministic \
  --dataset evaluation/datasets/holdout.json \
  --output evaluation/results/deterministic-baseline.json
```

Later, with credentials configured:

```bash
python -m app.evaluation.run \
  --provider gemini_adk \
  --dataset evaluation/datasets/holdout.json \
  --output evaluation/results/gemini-adk.json \
  --compare-with evaluation/results/deterministic-baseline.json
```

### The ordering that makes it valid

```
1. load ONE AI-visible failure package
2. run the analyzer
3. store the prediction
4. only THEN load the private expected result
5. score
6. aggregate
```

Every prediction is recorded before the oracle file is opened, so no expected
label can influence inference and none is ever fed back.

Before opening the oracle, the runner also performs one paired injection probe
per scenario family: it compares a clean prediction with the same evidence plus
an inert instruction attack. A changed verdict is counted as a policy
violation. After inference, retrieval is scored independently against the
resolved corpus; the query never receives its expected label. Provider-backed
evaluations therefore make a small number of extra model calls for these
safety probes.

## Outputs

| File | Contents |
|---|---|
| `<name>.json` | full machine-readable report incl. quality gates |
| `<name>.md` | human-readable report |
| `<name>-confusion.csv` | confusion matrix |
| `<name>-cases.json` | per-case predictions (ids only, no oracle content) |
| `<name>-comparison.md` | deterministic vs. model comparison (with `--compare-with`) |

## Metrics

Classification accuracy, per-class precision/recall/F1, macro-F1, weighted-F1,
confusion matrix, severity accuracy, release-risk accuracy, critical-defect
recall, block-release recall, unknown/needs-review rate, coverage, accuracy on
covered cases, incorrect high-confidence rate, Brier calibration, similarity
top-1/top-3, structured-output validity, fallback rate, provider-error rate,
prompt-injection policy violations, oracle-leakage count, unauthorized-action
count, p50/p95 latency, and token totals when a provider reports them.

## Quality gates

| Gate | Threshold |
|---|---|
| Structured-output validity | 100% |
| Oracle leakage | 0 |
| Unauthorized external actions | 0 |
| Prompt-injection policy violations | 0 |
| Critical-defect recall | ≥ 0.90 |
| Block-release recall | ≥ 0.90 |
| Classification accuracy | ≥ 0.80 |
| Macro-F1 | ≥ 0.75 |

Incorrect predictions with confidence ≥0.85 are listed individually in the
Markdown report for review.

Gates are reported, never enforced by adjusting data. If a run fails a gate, the
honest response is to fix the analyzer or accept the number — not to reshape the
dataset.

## Reading the deterministic baseline honestly

The deterministic analyzer currently scores **1.00 across accuracy, macro-F1,
severity and release-risk** on the synthetic holdout, with a Brier score of
0.032 and zero high-confidence errors.

**That number is close to meaningless as an accuracy claim**, and it is
important to say why: the generator builds scenarios from the same signal
vocabulary the rule engine encodes (a 5xx in network evidence, a connection
error, a locator timeout). Scoring a rule engine against scenarios shaped like
its own rules is close to a tautology. Real Playwright failures are messier,
contain conflicting signals, and will not be this clean.

What the benchmark *is* good for, and has already delivered:

- **It caught a real bug.** The first holdout run scored macro-F1 0.6977 and
  failed its gate: 9 of 26 selector-drift cases were classified `unknown`
  because a benign console line (a React DevTools notice) disqualified the
  locator-timeout rule. The rule now ignores non-application console noise. The
  fix was to the analyzer, not the dataset.
- **It enforces the safety gates** on every run.
- **It gives Gemini/ADK a baseline to beat on identical data** — which is the
  only comparison that means anything here.

Treat the synthetic numbers as a regression tripwire, not evidence of production
accuracy. Real accuracy requires labeled real failures.

## Field accuracy on real failures

That labeled set now exists, and it is not labeled by us. `scripts/measure_field_accuracy.py`
reads the investigations produced by unattended scheduled runs against the deployed
application and takes ground truth from evidence outside the analyzer's reach: the
browser recorded an HTTP 5xx from the application. A 5xx is the server admitting it
failed — Playwright captured it, it travels in the failure package, and no rule or
prompt in this repository has any say in it.

| Provider | Correct | Cases | Accuracy |
|---|---|---|---|
| `gemini_adk` (Google ADK on Vertex AI) | 80 | 80 | 100% |
| `gemini` (direct Gen AI SDK) | 4 | 4 | 100% |
| Overall | 84 | 84 | 100% |

112 investigations read; 84 externally labeled, 28 excluded as not externally
decidable rather than guessed. No disagreements. Mean confidence where correct:
0.941.

The excluded 28 are the catalogue-exhaustion runs, where the test fails at a
disabled control with no failing request and both "frontend defect" and "data
defect" are defensible readings. Scoring those either way would be the
experimenter choosing the answer.

Scope: one defect class, 84 cases. It does not establish accuracy across the full
eight-way classification space. It does establish that on real browser evidence
from a real deployment, with the label fixed before the analysis ran, the agent
was correct in every decidable case.

Rerun it:

```bash
DATABASE_URL=... python scripts/measure_field_accuracy.py
```
