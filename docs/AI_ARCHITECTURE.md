# AI architecture

## The one rule everything else follows

**A failure package is untrusted input, and a model's output is untrusted
output.** Evidence is attacker-influenceable (a test name or console line can
contain instructions), and a model can be talked into producing anything. So
the design never relies on the model behaving: policy lives outside the
evidence, the result is validated against a closed schema, and no action is
ever executed automatically.

## Provider abstraction

```
backend/app/ai/
├── protocols.py      Analyzer protocol + AnalyzerError (safe error codes)
├── schemas.py        ModelAnalysis (closed) + AnalysisResult (+ provenance)
├── safety.py         redaction, header allowlist, injection-marker counting
├── prompts.py        system instruction + delimited evidence payload
├── retrieval.py      weighted, explainable similarity
├── telemetry.py      counts and safe error codes only
├── deterministic.py  rule engine (default, and the fallback)
├── gemini.py         google-genai structured output, lazy client
├── adk_workflow.py   google-adk staged workflow, read-only tools
└── service.py        mode selection + fallback policy
```

Every provider implements one operation:

```python
analyze(failure_package, similar_cases, context) -> AnalysisResult
```

and all three return the **same validated `AnalysisResult`**, so nothing
downstream branches on which provider ran.

`ModelAnalysis` is the only thing a model may produce. It is `extra="forbid"`,
so a response containing `chain_of_thought`, `reasoning`, or any other
undeclared field is rejected as invalid — reasoning cannot be stored even by
accident. `AnalysisResult` wraps it with provenance the *application* fills in:
provider, model, prompt version, schema version, duration, tokens, fallback
reason, and safe stage summaries.

## Modes

| `ANALYZER_MODE` | Behavior |
|---|---|
| `deterministic` (default) | Local rule engine. No credentials, no network. |
| `gemini` | One structured-output call via `google-genai`. |
| `gemini_adk` | Staged ADK workflow with read-only tools. |

The default never changes on its own. Selecting a model mode without
credentials does not silently pretend the model ran: the service records the
real provider as `deterministic_fallback` with a `fallbackReason`, or — with
`AI_FALLBACK_ENABLED=false` — marks the investigation `needs_review` with a
safe explanation. A model failure can never break ingestion.

## ADK workflow

Seven stages, each with one job:

1. `evidence_normalization` — extract signals from validated evidence
2. `classification` — one label from the closed vocabulary
3. `root_cause_synthesis` — the conclusion, not the reasoning
4. `similarity_correlation` — sanitized historical cases
5. `risk_assessment` — **deterministic policy**, not model assertion
6. `action_construction` — one proposal, always human-approved
7. `result_validation` — closed-schema gate

Tools are read-only pure functions over already-validated data:
`inspect_network_evidence`, `inspect_console_evidence`, `inspect_failure_text`,
`retrieve_similar_cases`, `calculate_risk`, `validate_result`. There is
deliberately **no** tool for shell, filesystem, HTTP, GitHub, database writes,
cloud administration, environment variables, or the evaluation oracle.

Production ADK mode lazily creates a real `Agent`, `Runner`, and isolated
in-memory session. The complete failure package is never passed across that
boundary: tools, session messages, and the model receive the same redacted,
allowlisted, size-bounded evidence representation. If the runner cannot start
or finish before its deadline, the result is honestly labeled
`deterministic_fallback`; ADK is never credited for deterministic output.

Risk is computed by policy on purpose: release risk gates a release, so it must
not be something injected text can talk upward. A model claiming
`release_risk: none` on a backend defect is overridden — there is a test for it.

## Prompt-injection posture

The prompt separates policy from data: the system instruction states the rules,
and evidence is enclosed in `<<<BEGIN_UNTRUSTED_EVIDENCE>>>` … `<<<END…>>>`
with an explicit statement that content inside is quoted data.

That helps, but it is not the guarantee. The guarantees are structural:

- **Output validation** — a hostile verdict still has to satisfy the closed
  schema, and severity/risk come from policy.
- **No tools worth hijacking** — the Gemini path configures no tools at all;
  the ADK path exposes six read-only functions.
- **No automatic actions** — every recommendation ends `awaiting_approval`.
  "Create a GitHub issue immediately" produces, at most, a proposal.

`tests/test_ai_safety.py` runs each documented attack string through every
free-text field and asserts it stays inert.

## Secret hygiene

`safety.py` redacts credential-shaped strings (Google/OpenAI/GitHub keys,
Bearer/Basic headers, JWTs, private-key blocks, `password=`/`token=` pairs) and
blanks sensitive URL query values before any text reaches a provider. If request
headers are forwarded later, only an allowlist survives. Logs carry ids, counts,
and safe error slugs — never prompts, evidence, or responses.

## Retrieval

Deterministic weighted signals over stored investigations — same repository,
test file, normalized endpoint, status family, classification, shared error
terms, browser/environment, stack component, console signature, and
expected-vs-actual shape. Each match reports **which signals fired**, so a
reviewer can see why two failures were linked.

Only **human-reviewed resolutions** and seeded synthetic benchmark rows are
eligible for retrieval. An unreviewed AI prediction never becomes "truth" for a
later investigation. `SimilarityIndex` is the seam where an embedding-backed
index can be added later without changing callers.

## Human-reviewed learning loop

There is no autonomous training. The loop is:

1. The analyzer proposes; a human approves or rejects (recorded, never executed).
2. A human may record a resolution: final classification, severity, release
   risk, summary, component, resolver, timestamp.
3. The AI's original prediction is snapshotted on first resolution, so
   prediction-versus-outcome accuracy stays measurable and the model cannot
   overwrite its own scorecard.
4. Corrections append to an audit trail with a revision number.
5. Only resolved cases enter the retrieval corpus.

See [EVALUATION.md](EVALUATION.md) for how accuracy is measured, and
[CREDENTIALS_SETUP.md](CREDENTIALS_SETUP.md) for enabling a model provider.
