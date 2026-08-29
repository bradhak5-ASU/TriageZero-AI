# TriageZero backend (local milestone)

FastAPI service that receives Playwright failure packages, validates and sanitizes them, stores investigations in SQLite, runs a deterministic evidence-driven analyzer, and serves the frontend's `Investigation` objects.

Direct Gemini (`google-genai`) is implemented and locally verified against the
live provider. Google ADK (`google-adk`) is implemented but not yet
credential-tested. Production ADK uses a real lazy `Agent` + `Runner` adapter;
offline tests cover its boundary with injected fakes, and the container verifies
the installed SDK API. **Still not connected:**
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
- Blocking provider SDK calls run outside FastAPI's event loop, so list, detail,
  and health requests remain responsive while Gemini is analyzing.
- Optional bearer authentication separates ingestion access from dashboard and
  management access. Staging and production fail closed unless auth is enabled
  with distinct tokens of at least 32 characters; health stays public.
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

Gemini chooses classification, confidence, root cause, and the proposed action.
The application then applies one shared deterministic severity/release-risk
policy, because generated text must not directly control a release gate.
Direct Gemini and ADK use separate deadlines: an agent may require multiple
model/tool turns. Transient ADK provider failures use bounded retries and record
sanitized attempt category/status metadata instead of an opaque fallback.

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

## Datastore

Local development uses SQLite. Nothing needs configuring — the file lives at
`backend/data/triagezero.db`.

The cloud deployment uses **PostgreSQL (Cloud SQL)**, and this is not a
preference. A Cloud Run container's filesystem is ephemeral: a SQLite database
written there is destroyed on every restart, redeploy and scale-to-zero, with
no error to notice. The backend therefore refuses to start with a SQLite URL
when `APP_ENV` is `staging` or `production`.

```bash
pip install -e ".[postgres]"      # psycopg driver, only needed for PostgreSQL
```

`postgres://` and `postgresql://` URLs are rewritten to the psycopg driver
automatically, so a URL copied from a managed service works unchanged.

### Migrations

Schema changes are applied by an explicit command rather than only on startup,
so a deploy fails in a step you can read rather than on a user's request:

```bash
python -m app.db.migrate           # apply
python -m app.db.migrate --check   # report only, change nothing
```

It is idempotent, runs in one transaction, and prints counts and index names
only — never investigation content or credentials.

## Container probes

| Endpoint | Purpose | Touches the database |
|---|---|---|
| `/api/v1/livez` | liveness — the process is up | no |
| `/api/v1/readyz` | readiness — datastore reachable and migrated | yes |
| `/api/v1/health` | the dashboard's rich status view | yes, heavily |

`livez` and `readyz` are unauthenticated because platform probes carry no
credentials, and they disclose nothing beyond a fixed status string.
Point Cloud Run's startup probe at `readyz` and its liveness probe at `livez`;
`/api/v1/health` is for humans, not for probes.

See [`../docs/DEPLOYMENT.md`](../docs/DEPLOYMENT.md) for the full runbook.
