# TriageZero

**Autonomous Failure Intelligence** — the engineering dashboard for an AI-driven regression-test failure investigation platform.

When a Playwright test fails in the NovaCart repository, the test harness captures evidence (network calls, console errors, stack traces, screenshots, traces) and submits a structured failure package to TriageZero. The platform then uses Gemini and Google ADK to classify the failure, assess confidence, severity, and release risk, identify the likely root cause, find similar historical failures, and recommend a conservative engineering action. This repository contains the complete frontend for that system.

The backend (Gemini, Google ADK, Pub/Sub, Firestore, Cloud Run) is not part of this repo yet — the app runs fully in **demo mode** with realistic mock data until it is connected.

## Architecture

```
NovaCart repo (separate)                     This repo
┌──────────────────────┐   failure package   ┌───────────────────────────┐
│ Playwright suite      │ ──────────────────▶ │ TriageZero frontend       │
│ evidence capture      │  POST /api/v1/...   │  React + Vite + TS        │
└──────────────────────┘                     │  mock API ⇄ real API       │
                                             └───────────────────────────┘
                     future backend: ingestion API → Pub/Sub → worker
                     (Gemini + Google ADK) → Firestore → this dashboard
```

The frontend talks to a single API abstraction (`src/services`). `VITE_USE_MOCK_API` selects between the mock implementation (local data + localStorage, simulated pipeline progression) and the real HTTP client. Visual components never call the API directly — data flows through React contexts.

## Directory structure

```
src/
├── app/            config, App root, routes
├── components/
│   ├── layout/     sidebar, topbar, breadcrumbs, shell
│   ├── ui/         badges, cards, tabs, states, modal, copy button
│   ├── charts/     lightweight CSS/SVG charts
│   ├── investigations/  table + card views
│   └── evidence/   evidence tabs, network inspector, artifacts
├── context/        settings, toasts, investigations state
├── data/           mock investigations, health snapshot, sample package
├── hooks/          useLocalStorage
├── pages/          the six routes + 404
├── services/       API contract, HTTP client, mock client
├── types/          all domain types
├── utils/          formatters, label metadata, package validation
└── styles/         design tokens + global stylesheet
```

## Installation

```bash
npm install
npm run dev        # http://localhost:5173
```

## Environment configuration

Copy `.env.example` to `.env` (never commit `.env`):

```
VITE_API_BASE_URL=http://localhost:8000
VITE_USE_MOCK_API=true
```

All configuration is read once in `src/app/config.ts` — no URLs are hardcoded in components.

## Demo mode

With `VITE_USE_MOCK_API=true` (the default):

- 14 realistic investigations across repositories, browsers, and outcomes are provided.
- Submitting a valid failure package on the Ingest page creates a local investigation (status `received`), persists it in localStorage, and simulates the pipeline: received → queued → analyzing (stage by stage) → completed, with a synthesized classification.
- System Health shows representative demo values and is labeled as such.
- Recommended actions are never executed externally; approvals are recorded locally and labeled as simulated.

## Routes

| Route | Page |
|---|---|
| `/` | Command Center — KPIs, latest critical failure, queue, recent investigations, summaries |
| `/investigations` | Search, filters, sorting, table/card views, JSON export |
| `/investigations/:id` | Full investigation: decision summary, root cause, evidence, timeline, similar failures, recommended action, audit log |
| `/ingest` | Manual failure-package ingestion (fallback for local testing/demos) |
| `/system` | Service health, queue metrics, events |
| `/settings` | Locally persisted preferences |

## API contract

The frontend is built against these endpoints:

```
GET  /api/v1/health
GET  /api/v1/investigations
POST /api/v1/investigations
GET  /api/v1/investigations/:investigationId
POST /api/v1/investigations/:investigationId/retry
```

Set `VITE_USE_MOCK_API=false` to use them via `src/services/httpApi.ts`.

## Testing

```bash
npm run lint
npm test
```

Tests cover: Command Center rendering, investigation filtering, investigation detail (classification + evidence), package validation and submission in mock mode, rejection of private-oracle fields, settings/theme persistence, and the 404 route.

## Production build

```bash
npm run build      # type-check + bundle to dist/
npm run preview
```

## Current limitations

- All AI analysis is mock/synthesized; Gemini and Google ADK are not wired up.
- Artifact downloads, GitHub Actions links, and GitHub issue links are honest placeholders until integrations exist.
- Approvals on recommended actions are recorded locally only.
- System Health values are demo data while `VITE_USE_MOCK_API=true`.

## Next milestone: backend integration

1. Stand up the ingestion API (`POST /api/v1/investigations`) and health endpoint.
2. Point `VITE_API_BASE_URL` at it and set `VITE_USE_MOCK_API=false`.
3. Replace synthesized analysis with real Gemini + Google ADK investigation results.
4. Connect artifact storage (Cloud Storage) and the GitHub integration for issue creation.

## Security note: private QA-oracle separation

The evaluation harness for this project knows the *expected* classification of each controlled defect. That oracle data must never reach the AI investigator. The Ingest page rejects packages containing oracle fields (`expected_classification`, `expected_severity`, `expected_release_risk`, `expected_action`, `private_oracle`, `oracle`, `controlled_defect`, `defect_scenario`, `scenario_name`) at any nesting depth and explains why. This UI check demonstrates the safeguard — the backend enforces the real boundary. The frontend also never displays model chain-of-thought: only stage names, conclusions, and evidence.
