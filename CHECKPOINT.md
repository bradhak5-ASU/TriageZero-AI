# TriageZero — Checkpoint

**Date:** 30 August 2026

**Status:** Deployed on Google Cloud and running autonomously

**Project:** `triagezero` · region `us-central1`

---

## Live URLs

| What | URL |
|---|---|
| TriageZero dashboard | https://triagezero-web-oszu77g5xq-uc.a.run.app |
| TriageZero API | https://triagezero-api-oszu77g5xq-uc.a.run.app |
| API contract (OpenAPI) | https://triagezero-api-oszu77g5xq-uc.a.run.app/docs |
| NovaCart shop (under test) | https://novacart-web-oszu77g5xq-uc.a.run.app |
| NovaCart API | https://novacart-api-430074054654.us-central1.run.app |
| AI platform repository | https://github.com/bradhak5-ASU/TriageZero-AI |
| NovaCart/evidence repository | https://github.com/bradhak5-ASU/TriageZero |
| Software requirements and design | [docs/SRS.md](docs/SRS.md) and [docs/TriageZero-SRS.pdf](docs/TriageZero-SRS.pdf) |

Dashboard requires the Firebase demo account. NovaCart has no login.

---

## What is running

Every 30 minutes, with nobody present:

1. Cloud Scheduler fires
2. A Cloud Run job launches Playwright and drives a real browser through NovaCart
3. Failing tests capture evidence — network, console, stack trace, screenshot
4. Evidence is submitted to the TriageZero API with a machine-only ingestion token
5. A Google ADK agent investigates and returns a classified diagnosis
6. The investigation is persisted and appears on the dashboard for human approval

A second schedule restocks the demo catalogue at :25 and :55, five minutes ahead
of each test run.

---

## Deployed workloads

| Workload | Type | Role |
|---|---|---|
| `triagezero-web` | Cloud Run service | Dashboard |
| `triagezero-api` | Cloud Run service | Ingestion, analysis, persistence |
| `novacart-web` | Cloud Run service | Demo shopfront (application under test) |
| `novacart-api` | Cloud Run service | Demo shop backend, injectable defects |
| `triagezero-scheduled-tests` | Cloud Run job | Playwright suite, every 30 min |
| `novacart-seed` | Cloud Run job | Restock, at :25 and :55 |

Cloud SQL instance `triagezero-db` (PostgreSQL 16) holds two isolated databases:
`triagezero` and `novacartdb`, with separate users and separate service accounts.

---

## Current configuration

| Setting | Value |
|---|---|
| Analyzer | `gemini_adk` — Google ADK, healthy, 0 fallbacks |
| Model | `gemini-3.6-flash` via Vertex AI (no API key anywhere) |
| ADK deadline | 300 s, with a 40-event budget |
| Injected defect | `NOVACART_DEFECT_SCENARIO=checkout_500` — deliberately on |
| Fallback | Deterministic rule engine, enabled |

---

## Verified in production

- Scheduled runs triggered by the scheduler service account, not a person
- Google ADK analysing real failures end to end
- Correct `backend_application_defect` classification with a real HTTP 500 in evidence
- Unauthenticated dashboard request returns 401
- Ingestion token on a dashboard route returns 403 (scope separation holds)
- CORS echoes the exact dashboard origin and refuses all others
- Investigations survive a process restart (Cloud SQL, not ephemeral disk)
- 284 backend tests (against a real PostgreSQL server) and 60 frontend tests green

---

## Cost

Roughly **$0.60–1.30/day**. Budget of $20 with alerts at $10 / $18 / $20.
Cloud SQL is ~40% of it and the only thing billing 24 hours a day.

To stop spending after judging:

```bash
gcloud sql instances delete triagezero-db
gcloud run services delete triagezero-api triagezero-web novacart-api novacart-web --region=us-central1
gcloud scheduler jobs delete triagezero-test-schedule novacart-restock --location=us-central1
```

To pause temporarily without deleting:

```bash
gcloud scheduler jobs pause triagezero-test-schedule --location=us-central1
gcloud scheduler jobs pause novacart-restock --location=us-central1
```

---

## Demo controls

Switch the injected defect (backend scenarios need only an env var, ~30 s):

```bash
gcloud run services update novacart-api --region=us-central1 \
  --update-env-vars=NOVACART_DEFECT_SCENARIO=checkout_500
```

| Scenario | Effect | Needs |
|---|---|---|
| `checkout_500` | Checkout returns HTTP 500 | env var only |
| `wrong_total` | Cart total mismatch | env var only |
| `dependency_unavailable` | External dependency down | env var only |
| `slow_confirmation` | Confirmation exceeds budget | shopfront rebuild |
| `broken_test_locator` | Selector renamed — a *test* defect | shopfront rebuild |

Set the value empty to restore a healthy shop.

`broken_test_locator` is the strongest demo: the same test fails, but the correct
diagnosis is "your test is out of date", not "your application is broken".

---

## Open items

1. **SRS section 11 — settled, and rewritten.** Accuracy is no longer an open
   question. `scripts/measure_field_accuracy.py` scores the analyzer on real
   failures from unattended scheduled runs, using ground truth the analyzer
   cannot influence — an HTTP 5xx recorded by the browser. Result: **84/84
   correct (100%)**, ADK 80/80, mean confidence 0.941, no disagreements, with
   28 undecidable catalogue-exhaustion cases excluded rather than guessed.
   §11, §12, §13 and §14 of the SRS, plus `README.md` and `docs/EVALUATION.md`,
   now lead with that number; the synthetic-benchmark caveat is retained where
   it is still true — about the synthetic benchmark — and demoted everywhere
   else.

2. **Devpost writeup and demo video** — not started. This is the remaining risk;
   the engineering is complete.

---

## Recovering shell variables

```bash
export API_URL="$(gcloud run services describe triagezero-api --region=us-central1 --format='value(status.url)')"
export WEB_URL="$(gcloud run services describe triagezero-web --region=us-central1 --format='value(status.url)')"
export NOVA_API="$(gcloud run services describe novacart-api --region=us-central1 --format='value(status.url)')"
export NOVA_WEB="$(gcloud run services describe novacart-web --region=us-central1 --format='value(status.url)')"
export DASH="$(gcloud secrets versions access latest --secret=triagezero-dashboard-token)"
```

Check system state at any time:

```bash
curl -sS "$API_URL/api/v1/readyz"
curl -sS -H "Authorization: Bearer $DASH" "$API_URL/api/v1/health" \
  | python3 -c "import sys,json;ai=json.load(sys.stdin)['ai'];print('adk:',ai['adkStatus'],'fallbacks:',ai['fallbackCount'])"
```
