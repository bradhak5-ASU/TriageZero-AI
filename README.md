# TriageZero

**Autonomous Failure Intelligence** — an AI-driven regression-test failure investigation platform.

When a Playwright test fails in the NovaCart repository, the harness captures evidence (network calls, console errors, stack traces, artifact metadata) and submits a structured failure package to TriageZero. TriageZero validates and stores it, analyzes the evidence, classifies the failure, assesses confidence, severity, and release risk, finds similar historical failures, and recommends a conservative engineering action that always requires human approval.

This repository contains the complete **local milestone**: the React dashboard,
a working FastAPI backend with durable persistence, a deterministic analyzer,
and optional production adapters for Gemini and Google ADK. Google Cloud
deployment remains a later milestone; everything here still runs with **zero
credentials**.

## Architecture (local milestone)

```
NovaCart repo (separate)                This repo
┌────────────────────┐  failure pkg   ┌─────────────────────────────────────┐
│ Playwright suite    │ ─────────────▶ │ backend/  FastAPI                   │
│ evidence capture    │  POST /api/v1/ │  validate → sanitize → store (SQLite)│
└────────────────────┘  investigations │  → staged pipeline → deterministic  │
                                       │    analyzer → structured result     │
                                       └──────────────┬──────────────────────┘
                                                      │ camelCase Investigation JSON
                                       ┌──────────────▼──────────────────────┐
                                       │ src/  React + Vite + TS dashboard   │
                                       │  mock mode (default) or real API    │
                                       └─────────────────────────────────────┘
```

Responsibilities: the **backend** owns validation, the private-oracle security boundary, persistence, analysis, similarity, retries, and recorded action decisions. The **frontend** owns presentation, filtering, and the demo/mock mode; its HTTP adapter translates the external ingestion receipt (`investigation_id`) into the internal `id`. Analysis logic is not duplicated in the frontend for real mode.

## Directory structure

```
├── src/                 frontend (see below)
│   ├── app/ components/ context/ data/ hooks/ pages/ services/ types/ utils/ styles/
├── backend/             FastAPI service (see backend/README.md)
│   ├── app/{api,core,db,repositories,schemas,services}/
│   └── tests/
├── Dockerfile.frontend  production frontend image (nginx)
├── nginx.conf
└── docker-compose.yml   full local stack
```

## Prerequisites

- **Node 22.23.2 is the recommended frontend runtime.** It is pinned in `.nvmrc` and `.node-version`, and it is the version the Docker frontend image builds with.
- **Node 20 is not supported by the current test toolchain.** jsdom 30 / Undici require Node APIs that Node 20 does not provide, so the test suite fails while loading, before any test runs. `package.json` declares `engines.node` and `.npmrc` sets `engine-strict=true`, so an unsupported runtime fails clearly during `npm ci` instead of producing confusing test errors later.
- **Python 3.11 or newer is required for the backend** (it uses `datetime.UTC` and 3.11-era typing).
- **Docker is an alternative** that avoids installing Node and Python locally — see [Docker](#docker) below.

## Manual setup

Terminal 1 — backend:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

Terminal 2 — frontend against the real backend:

```bash
nvm install     # installs the version in .nvmrc (22.23.2)
nvm use
npm ci          # clean, lockfile-exact install
VITE_USE_MOCK_API=false VITE_API_BASE_URL=http://localhost:8001 npm run dev
```

Use `npm ci` rather than `npm install` on a fresh clone: it installs exactly what the lockfile pins, so you get the hardened dependency versions. An existing `node_modules` from an earlier milestone can otherwise keep serving stale packages (React Router 6 / Vite 5 / Vitest 2).

Verify the runtime and the resolved dependency versions before reporting a problem:

```bash
node --version
npm ls react-router-dom vite vitest jsdom --depth=0
```

(`npm run verify:runtime` runs both.) Expect Node v22.23.2 with react-router-dom 7.18.2, vite 8.2.2, vitest 4.1.11, and jsdom 30.0.1.

Or keep the frontend in demo mode (no backend needed): `npm run dev`.

## Docker

```bash
docker compose up --build
```

Frontend at http://localhost:5174, backend at http://localhost:8001, API docs at http://localhost:8001/docs. These ports are offset from NovaCart (5173/8000) so the target app and the investigation system run side by side — see [docs/NOVACART_INTEGRATION.md](docs/NOVACART_INTEGRATION.md). Investigations persist in the `triagezero-data` volume across restarts. Note the variable split: `VITE_*` values are **build-time** (baked into the frontend bundle via build args), while backend variables are **runtime** environment.

## Environment variables

Frontend (`.env.example`): `VITE_API_BASE_URL` (default `http://localhost:8001`), `VITE_USE_MOCK_API` (default `true`).

Backend (`backend/.env.example`): `APP_ENV`, `APP_HOST`, `APP_PORT`, `DATABASE_URL` (SQLite, default `backend/data/triagezero.db`), `FRONTEND_ORIGINS` (comma-separated CORS allowlist, default `http://localhost:5174`), `MAX_REQUEST_BYTES`, `LOCAL_PROCESSING_DELAY_MS`, `LOG_LEVEL`, plus the AI settings (`ANALYZER_MODE`, `AI_FALLBACK_ENABLED`, `GEMINI_API_KEY` — blank in all committed files —, `GEMINI_MODEL`, `GEMINI_REQUEST_TIMEOUT_SECONDS`, `GEMINI_MAX_RETRIES`, `GOOGLE_GENAI_USE_VERTEXAI`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `AI_PROMPT_VERSION`). Never commit a real `.env`; no secrets exist in this milestone.

## API

```
GET  /api/v1/health                                system health snapshot (+ status: ok)
GET  /api/v1/investigations                        list (filters: status, classification,
                                                   severity, release_risk, repository,
                                                   environment, search, limit, offset, sort)
POST /api/v1/investigations                        ingest failure package → 202
GET  /api/v1/investigations/{id}                   full investigation
POST /api/v1/investigations/{id}/retry             re-run analysis (409 while active)
POST /api/v1/investigations/{id}/actions/approve   record decision (never executes)
POST /api/v1/investigations/{id}/actions/reject    record decision
```

Ingestion returns `{"investigation_id": "INV-…", "status": "received", "received_at": …}`. Investigation objects use the frontend's camelCase domain types verbatim (`src/types/index.ts`).

**Idempotency.** Re-submitting an identical package (SHA-256 canonical fingerprint) returns the existing investigation. An optional `Idempotency-Key` header does the same for a replay of the *same* package; reusing a key with **different** evidence returns `409 idempotency_key_conflict` naming the original investigation rather than silently returning stale results. Both the key and the fingerprint are unique columns, so concurrent duplicate submissions race in the database and resolve to a single investigation.

**Failure-package v1.0 is a closed contract** — see `src/data/samplePackage.ts`, enforced by `backend/app/schemas/failure_package.py`. `schema_version` must be `"1.0"`; the test must be `failed`; `environment.browser` ∈ {`chromium`, `firefox`, `webkit`} and `environment.name` ∈ {`local`, `staging`, `production`}; network statuses must be valid HTTP statuses (or 0 for connection failures); sizes, list lengths, and text lengths are capped; artifact paths must be safe relative paths (no traversal, absolute paths, home paths, or `file://`). **Unknown fields are rejected at every level** so unexpected data is never persisted — producers needing new fields must ship a new `schema_version`. The request-size cap is enforced on bytes actually received, so a chunked request without `Content-Length` cannot bypass it.

**Database upgrades.** Startup automatically brings an older local SQLite database up to the current schema and **preserves existing investigations** — you never need to delete `backend/data/triagezero.db`. `create_all()` only creates missing tables, so a database from an earlier milestone would otherwise keep its old indexes; `backend/app/db/migrations.py` closes that gap. It creates the named partial unique index `ux_investigations_idempotency_key` (so the concurrency guarantee is actually enforced after an upgrade, not just declared in the model), backfills any other model-declared index the old table lacks, and drops the superseded non-unique index. If a legacy database already contains duplicate non-null idempotency keys — which the old schema allowed — the key is kept on the **oldest** investigation of each group (ordered by `created_at`, then `id`) and cleared to `NULL` on the later rows. No investigation is deleted, and fingerprints, evidence, analysis results, timelines, and public investigation IDs are never modified. Only counts are logged. The migration is idempotent: a second startup performs and reports zero changes.

**Docker volumes need no manual reset.** The `triagezero-data` volume is migrated in place on the next `docker compose up`, with the same guarantees.

## Security: private QA-oracle separation

The evaluation harness knows each controlled defect's expected outcome. That oracle must never reach the analyzer. The backend rejects — recursively, at any nesting depth, against the raw request body — any package containing `expected_classification`, `expected_severity`, `expected_release_risk`, `expected_action`, `private_oracle`, `oracle`, `controlled_defect`, `defect_scenario`, or `scenario_name`. Rejected packages are not persisted, forbidden values are never logged or echoed, and the analyzer is never invoked. The analyzer never reads `playwright-tests/evaluation/expected-results.json` or any external file; it infers conclusions from submitted evidence only. The frontend's Ingest-page validation demonstrates the same rule but is not the security boundary — the server is.

## AI analysis

Three analyzer modes share one interface and one validated result type:

| `ANALYZER_MODE` | Behavior |
|---|---|
| `deterministic` (default) | Local rule engine — no credentials, no network |
| `gemini` | One structured-output call via `google-genai` |
| `gemini_adk` | Staged Google ADK workflow with read-only tools |

**The default never changes on its own, and nothing here needs credentials.**
Selecting a model mode without a key does not pretend the model ran: the
provider is recorded as `deterministic_fallback` with a reason, or — with
`AI_FALLBACK_ENABLED=false` — the investigation is marked `needs_review`.

Model output is validated against a closed schema, so a response carrying
reasoning, an invalid classification, or an out-of-range confidence is rejected
before it can be persisted. Severity and release risk come from deterministic
policy, not from generated text. No recommendation is ever executed: approval
and rejection are recorded local decisions.

See [docs/AI_ARCHITECTURE.md](docs/AI_ARCHITECTURE.md) for the design and the
prompt-injection posture, [docs/EVALUATION.md](docs/EVALUATION.md) for how
accuracy is measured, and [docs/CREDENTIALS_SETUP.md](docs/CREDENTIALS_SETUP.md)
for enabling a provider later.

## Deterministic analyzer

A transparent rule engine stands in for Gemini and returns the same structured result shape: correlated HTTP 5xx → backend defect (external host → dependency failure); connection-level failures → environment; duration-budget failures → performance/timing; client console errors with healthy network → frontend defect; business-value mismatches → data integrity; locator timeouts without app errors → test-automation defect; otherwise `unknown` with low confidence → `needs_review`. Same package in, same result out. Recommended actions are always `awaiting_approval`; nothing executes externally.

## Testing

```bash
cd backend && pytest && ruff check .   # backend tests, fully offline
npm test && npm run lint               # 42 frontend tests
npm audit                              # expected: 0 vulnerabilities
```

## Production build

```bash
npm run build && npm run preview
```

## Synthetic benchmark results

The deterministic analyzer currently scores 1.00 accuracy / 1.00 macro-F1 on the
78-case synthetic holdout (Brier 0.032, zero high-confidence errors, all quality
gates met). **That is a synthetic benchmark number, not production accuracy** —
the generator builds scenarios from the same signal vocabulary the rules encode,
so a high score is close to tautological. Its real value: it caught a genuine
analyzer bug (benign console noise was suppressing the locator-timeout rule,
macro-F1 0.6977 before the fix), it enforces the safety gates on every run, and
it gives Gemini/ADK a baseline to beat on identical data.
See [docs/EVALUATION.md](docs/EVALUATION.md).

## Current limitations

- Gemini and ADK are implemented but **unverified against the live services** —
  no credentials were used, so every AI test runs against injected fakes.
- Synthetic benchmark numbers do not predict production accuracy.
- Artifacts are metadata only (no upload/download until Cloud Storage).
- GitHub Actions links and issue creation are honest placeholders; decisions are recorded, never executed.
- Local processing uses an in-process dispatcher (Pub/Sub replaces it later).
- Retrieval is deterministic keyword/signal matching; embeddings are a later step.

## Next milestone: cloud integration

1. Supply credentials and verify Gemini / ADK against the live services
   ([docs/CREDENTIALS_SETUP.md](docs/CREDENTIALS_SETUP.md)), then compare against
   the deterministic baseline on identical data.
2. Swap the local dispatcher for Pub/Sub and SQLite for Firestore.
3. Add Cloud Storage artifact uploads (artifacts are metadata-only today).
4. Deploy to Cloud Run; connect NovaCart CI to submit packages automatically
   ([docs/NOVACART_INTEGRATION.md](docs/NOVACART_INTEGRATION.md)).
