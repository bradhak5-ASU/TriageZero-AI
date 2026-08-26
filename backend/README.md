# TriageZero backend (local milestone)

FastAPI service that receives Playwright failure packages, validates and sanitizes them, stores investigations in SQLite, runs a deterministic evidence-driven analyzer, and serves the frontend's `Investigation` objects.

**Implemented but not credential-tested:** Gemini (`google-genai`) and Google
ADK (`google-adk`). Production ADK uses a real lazy `Agent` + `Runner` adapter;
offline tests cover its boundary with injected fakes, and the container verifies
the installed SDK API. No credentials were used. **Still not connected:**
Pub/Sub, Firestore, Cloud Storage, GitHub issue creation. The whole backend runs
with zero credentials.

## Run

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

Docs at http://localhost:8001/docs (TriageZero uses 8001 so it does not collide with the NovaCart target app on 8000). Configuration comes from environment variables (see `.env.example`); copy it to `.env` to override locally. Never commit a real `.env`.

## Layout

```
app/
├── api/routes/       health + investigations endpoints
├── core/             config (pydantic-settings), errors, JSON logging
├── db/               SQLAlchemy models + session (SQLite, durable)
├── repositories/     query layer
├── schemas/          failure-package (snake_case in) + investigation (camelCase out)
└── services/
    ├── evidence.py   oracle rejection, artifact-path safety, fingerprint
    ├── analyzer.py   deterministic rule engine (Gemini stand-in)
    ├── investigations.py  creation, similarity, retries, decisions
    └── processing.py staged pipeline + dispatcher interface
```

## Key behaviors

- `POST /api/v1/investigations` → 202 `{investigation_id, status, received_at}`. An identical package (SHA-256 canonical fingerprint), or a replay of the same package under the same `Idempotency-Key`, returns the existing investigation; reusing a key with different evidence returns `409 idempotency_key_conflict`. Both columns are unique, so concurrent duplicates race in the database and the loser resolves to the winning investigation.
- The failure-package schema is **closed**: unknown fields are rejected at every level, `environment.browser` and `environment.name` use fixed vocabularies, and the request-size cap is enforced against bytes actually received (a chunked body cannot bypass the `Content-Length` fast-fail in middleware).
- Private QA-oracle keys (`expected_classification`, `private_oracle`, `controlled_defect`, …) are rejected recursively against the raw body before parsing; nothing is persisted, values are never logged or echoed. This is the real security boundary. The analyzer never reads `playwright-tests/evaluation/expected-results.json` or any file outside the submitted package.
- Artifact paths are metadata only: relative paths enforced, traversal/absolute/`file://`/home paths rejected.
- Processing advances received → queued → analyzing (six stages) → completed / needs_review (confidence < 0.6) / failed, with configurable delays (`LOCAL_PROCESSING_DELAY_MS`, 0 in tests = synchronous). Pending investigations are recovered on startup.
- Action decisions (`/actions/approve|reject`) are recorded only — no external action is ever executed.
- Similarity is a transparent local ranker (same test file / failing endpoint / classification / repository / shared error terms) over stored investigations; no vector database.

## Tests & lint

```bash
pytest       # deterministic, no network access required
ruff check .
```

## AI modes

`ANALYZER_MODE` selects the analyzer: `deterministic` (default, local rules),
`gemini`, or `gemini_adk`. All three return the same validated `AnalysisResult`.
No provider client is constructed at import time, and a model failure never
breaks ingestion — the service falls back to deterministic analysis (or marks
the case `needs_review` when `AI_FALLBACK_ENABLED=false`) and records the real
provider, never a pretended one.

See `../docs/AI_ARCHITECTURE.md`, `../docs/EVALUATION.md`, and
`../docs/CREDENTIALS_SETUP.md`.

## Benchmarking

```bash
python -m app.evaluation.seed_history --count 240 --seed 20260825
python -m app.evaluation.run --provider deterministic \
  --dataset evaluation/datasets/holdout.json \
  --output evaluation/results/deterministic-baseline.json
```

`evaluation/` is gitignored and excluded from the Docker image — the private
oracle must never ship in a runtime container.
