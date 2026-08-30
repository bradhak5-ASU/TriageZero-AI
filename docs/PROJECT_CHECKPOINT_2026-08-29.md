# TriageZero — Project Checkpoint

**Date:** August 29, 2026
**Prepared for:** project management / architecture review
**Prepared by:** the implementation session (Claude, Cowork)
**Repository:** https://github.com/bradhak5-ASU/TriageZero-AI
**Head commit at checkpoint:** `d9b3279` (pushed to `origin/main`, working tree clean)

## How to read this document

Sections 1–4 are context. Section 5 is what actually exists. Section 6 is the
evidence, with method, so you can judge how much to trust it. Sections 7–10 are
the parts a reviewer should push back on: the checklist, honest observations,
an explicit opinion, and the risk register. Section 11 is the exact pickup point.

Throughout, **verified** means a command was run and its output observed in this
session. **Asserted** means it follows from code review but was not executed.
Where something was not verified, it says so.

---

## 1. What the project is

TriageZero is an autonomous regression-test failure investigation platform. A
Playwright suite running against a target application (NovaCart) captures a
structured failure package on every failing test and submits it. TriageZero
ingests it, classifies the failure, produces a root-cause hypothesis with a
confidence explanation, assesses release risk, retrieves similar historical
failures, and recommends an action for a human to approve.

**Submission target:** Google "All Things Agentic" Hackathon, Devpost,
Taskmaster track.
**Deadline:** August 31, 2026. **Two days remain from this checkpoint.**

## 2. Repositories and boundaries

| Repository | Role | Editable |
|---|---|---|
| `~/Desktop/TriageZero-AI` | The investigation platform: React dashboard + FastAPI backend. All work happens here. | Yes |
| `~/Desktop/TriageZero` | NovaCart target app + Playwright suite. Produces the failure packages. | **No — read-only by owner instruction** |

The read-only constraint on the NovaCart repo held throughout. Nothing in it was
modified. This was checked at the end and confirmed: the integration works
without touching it (see §5.6).

## 3. Binding constraints set by the owner

These are the standing requirements every decision was held against. They are
recorded verbatim in intent because they should survive into the next session.

1. **No fabricated demo data.** *"During demo or post that whenever the panel
   wants to run it should not show cooked invalid values. It must use real
   values and it must do what its asked without manual interference."* Judges
   must be able to run the system themselves, against real evidence, with no
   hidden manual steps.
2. **Do not manipulate the dataset to make evaluation pass.** When the
   deterministic analyzer failed its accuracy gate, the fix had to be to the
   analyzer, not the benchmark. This was honoured (see §8.2).
3. **No credentials in the repository.** No real secrets committed at any point.
4. **Security is required**, because the system is being deployed publicly.
5. **Do not commit or push without explicit approval.** Honoured — the three
   commits in this checkpoint were made only after direct instruction.

## 4. Architecture in one paragraph

A React 18 / Vite 8 / TypeScript dashboard talks to a FastAPI backend over a
strict, closed-schema v1 failure-package contract. The backend validates and
sanitises the package, rejects private QA-oracle fields at any nesting depth
*before* Pydantic parsing, fingerprints it for idempotency, persists it, and
runs an analyzer. The analyzer is an abstraction with three interchangeable
providers — `deterministic` (rule engine, no credentials, no network),
`gemini` (Google Gen AI SDK), and `gemini_adk` (Google Agent Development Kit
workflow) — all returning one validated `AnalysisResult`. Deterministic is the
default and the fallback. Persistence is SQLite locally and PostgreSQL
(Cloud SQL) in the cloud.

---

## 5. What exists today

### 5.1 Frontend dashboard — complete
Six pages (Command Center, Investigations, Investigation Detail, Ingest,
Settings, Not Found), custom design-token CSS, demo/mock mode, React Router 7,
Context API state. 65 TypeScript/TSX source files. No chatbot UI, by design —
this is an operations console, not an assistant.

### 5.2 Backend API — complete
51 Python modules. Strict v1 validation with `extra="forbid"` and `Literal`
enums; recursive private-oracle rejection; SHA-256 fingerprint idempotency with
an `Idempotency-Key` header and a partial unique index; request-size enforcement
on both `Content-Length` and actual bytes received (chunked requests carry no
`Content-Length`); structured JSON logging that never emits evidence or secrets.

### 5.3 AI layer — complete
Provider abstraction over deterministic / Gemini / Gemini-ADK. Prompt-injection
defence: untrusted evidence is delimited, the model gets no tools, output is
schema-validated, and risk policy is computed deterministically rather than
taken from the model. A synthetic benchmark generator, grouped-by-family dataset
splitting (never a random row split, which would leak near-duplicates across the
split), oracle loaded only after inference, and a metrics/gate harness. A
human-review loop records the only outcome allowed to become "truth".

### 5.4 Human sign-in — complete, this session
Firebase email/password authentication for humans, verified server-side as
Firebase ID tokens. Machine reporters continue to use `INGESTION_API_TOKEN`.
The two are verified independently and are not interchangeable: a recognised
credential presented on a route it may not use returns **403, not 401**.
Firebase is disabled by default, so local development, CI and the test suite
need no Firebase project.

### 5.5 PostgreSQL support — complete, this session
Dialect-aware migrations covering both SQLite and PostgreSQL, converging on an
identical schema. `python -m app.db.migrate` runs migrations as a standalone,
idempotent, single-transaction step with a `--check` mode. The backend now
**refuses to start on SQLite when `APP_ENV` is staging or production**, because
Cloud Run's filesystem is ephemeral and a SQLite database there is erased on
every restart — silently, with no error.

### 5.6 Cloud Run readiness — complete, this session
`/api/v1/livez` (liveness, touches nothing) and `/api/v1/readyz` (readiness,
proves the datastore answers and the schema exists), both unauthenticated
because platform probes carry no credentials, and both disclosing nothing
beyond a fixed status string. Injected `PORT` honoured by both images. nginx
template for the frontend. Production CORS validation rejecting wildcards,
plaintext origins, and trailing slashes. A `cloudbuild.yaml` that runs both
test suites, then builds, then migrates, then deploys. A 353-line deployment
runbook (`docs/DEPLOYMENT.md`).

### 5.7 NovaCart integration — already working, verified this session
`writeFailureEvidence()` in the NovaCart repo's `helpers/evidence.ts` already
calls `submitFailurePackageIfConfigured()`, which posts the failure package
automatically whenever `TRIAGEZERO_API_URL` is set, printing:

```
TriageZero upload: HTTP 202, investigation_id=INV-XXXXXXXX, status=received
```

**This directly satisfies constraint 3.1.** A judge sets two environment
variables, runs `npx playwright test`, and watches real investigations appear
in the dashboard. No manual step, no seeded data, and no edit to the NovaCart
repo. Setting no `TRIAGEZERO_API_URL` is the off switch.

---

## 6. Verification evidence

Everything below was executed and its output observed. Method is stated so the
strength of each claim is visible.

| Check | Result | Method |
|---|---|---|
| Backend suite, SQLite | **279 passed, 5 skipped** | `pytest` on the owner's machine |
| Backend suite, **live PostgreSQL 16** | **284 passed, 0 skipped** | Real `postgres` server started in a Linux container; the 5 skips are the Postgres integration tests, which then run |
| Ruff lint | clean | `ruff check .` |
| Frontend suite | **59 passed / 11 files** | `vitest run` on the owner's Mac |
| TypeScript build | clean | `tsc -b` |
| ESLint | clean | `eslint .` |
| Production build | succeeds, 445.77 kB (132 kB gzip) | `vite build` |
| Secret scan across all 3 commits | clean | grep for key patterns; only intentional test fakes |

**Production-shape integration test.** The API was run with `APP_ENV=production`,
an injected `PORT`, a real PostgreSQL database, and authentication enabled:

- migration applied as its own step, as Cloud Build does — succeeded
- `/livez` → `{"status":"alive"}`; `/readyz` → `{"status":"ready"}`
- unauthenticated dashboard request → **401**
- dashboard token → **200**
- ingestion token on a dashboard route → **403** (scope separation holds)
- CORS echoed the exact configured origin; `https://evil.example` → no header
- a real failure package ingested → analysed → classified
  `backend_application_defect`, severity `critical`, row confirmed present in
  PostgreSQL
- **the process was killed and restarted; the investigation survived** — the
  entire justification for Cloud SQL, demonstrated rather than argued

**nginx template.** Rendered with the same `envsubst` mechanism the nginx image
uses, then actually served: `listen 8080` substituted, `$uri` preserved,
`/healthz` → `ok`, SPA fallback → 200, security headers present.

**Migration CLI.** Exercised against real PostgreSQL: `--check` on an empty
database, apply, apply again (idempotent), `--check` after. A connection failure
prints one actionable line and exits 1, with **zero occurrences of the password**
in the output.

---

## 7. Progress checklist

### Complete
- [x] Frontend dashboard, 6 pages, demo mode
- [x] Backend API with strict v1 contract and oracle separation
- [x] SQLite persistence, migrations, idempotency, concurrency handling
- [x] Security hardening pass (dependency CVEs, chunked-size bypass, idempotency conflicts, closed schema)
- [x] Node runtime enforcement (`engines`, `engine-strict`, `.nvmrc`)
- [x] AI layer: provider abstraction, Gemini, ADK, safety controls, retrieval
- [x] Synthetic benchmark, grouped evaluation splits, metrics, human-review loop
- [x] **Firebase human sign-in with machine/human credential separation**
- [x] **PostgreSQL support + standalone migration command**
- [x] **Cloud Run readiness: probes, PORT, CORS validation, nginx template**
- [x] **`cloudbuild.yaml` + 353-line deployment runbook**
- [x] Local toolchain repaired (Node 20 → 22.23.2; corrupted `node_modules` rebuilt)
- [x] Three commits pushed to `origin/main`

### Deployment — Phases 0–3 complete (August 30)
- [x] Phase 0: project `triagezero` (pre-existing, billing enabled), APIs enabled
- [x] Phase 0: budget confirmed — $20/month, alerts at 50/90/100%
- [x] Phase 1: Cloud SQL `triagezero-db`, POSTGRES_16, ENTERPRISE, `db-f1-micro`
- [x] Phase 2: three secrets (database URL, ingestion token, dashboard token)
- [x] Phase 3: two least-privilege service accounts, verified at exactly two roles

### Deployment — remaining
- [ ] Phase 4: Firebase Authentication + demo account + authorized domains
- [ ] Phase 5: Artifact Registry + **two** Cloud Build runs (deploy-then-rebuild)
- [ ] Phase 6: Post-deploy verification, including the end-to-end Playwright run
- [ ] **Verify the Gemini path against deployed Cloud Run** (see §8.3)
- [ ] Devpost submission: writeup, demo video, repository link

**Correction to an earlier version of this document.** It previously stated that
no GCP project existed. That was wrong — the project `triagezero` had existed
with billing enabled since an earlier session, and Vertex AI already worked
locally against it. The claim was written without checking, and the owner caught
it. It mattered: acting on it would have meant running `gcloud projects create`
and producing a second project, which would have broken Firebase ID-token
verification (the backend validates the audience against one project ID).

**Still true:** no Cloud Run service, container image, or deployed revision
exists. Nothing serves traffic yet.

### Corrections found *during* deployment (§8.8)
Five errors in the runbook were found and fixed while executing it, each before
it caused damage. They are listed in §8.8; the repository is correct, and any
memory of the original runbook is not.

---

## 8. Observation points

### 8.1 A test caught a real defect class, and the code was already correct
While building the PostgreSQL suite, a test appeared to expose an idempotency
bug: a key supplied on a fingerprint-duplicate seemed to be silently dropped.
On investigation the working copy used for that run was stale — the fix already
existed in the repository. The correct code was **not** modified. Recorded here
because the instinct to "fix" a passing-in-reality system on the strength of a
failing test is a real failure mode, and avoiding it was deliberate.

### 8.2 The AI accuracy number is the weakest part of the story
The deterministic analyzer scores **1.00 across accuracy, macro-F1, severity and
release risk** on the synthetic holdout. `docs/EVALUATION.md` states plainly that
this number *"is close to meaningless as an accuracy claim"*, because the
generator builds scenarios from the same signal vocabulary the rule engine
encodes — scoring a rule engine against scenarios shaped like its own rules is
close to a tautology.

What the benchmark genuinely delivered: it **caught a real bug**. The first
holdout run scored macro-F1 0.6977 and failed its gate because a benign React
DevTools console line disqualified the locator-timeout rule in 9 of 26
selector-drift cases. **The fix was to the analyzer, not the dataset** — per
constraint 3.2.

**Recommendation to the architect: do not put "1.00 accuracy" in the Devpost
writeup.** It invites exactly the question that undermines it. The honest
framing — a regression tripwire that caught a real bug, plus a baseline for
Gemini to beat on identical data — is both true and more credible.

### 8.3 One capability is genuinely unverified
Everything run in production shape used `ANALYZER_MODE=deterministic`. The
Gemini path has **not** been observed working against deployed Cloud Run with a
Secret Manager key. It was verified in an earlier session locally, but that is
not the same thing.

This matters more than it looks: `AI_FALLBACK_ENABLED=true` means a bad or
missing key degrades **quietly** to the deterministic analyzer rather than
erroring. The system will appear to work while the AI differentiator is silently
switched off. This must be explicitly checked in Phase 6 by confirming an
investigation shows Gemini provenance.

### 8.4 The local toolchain was broken and is now fixed
Two independent problems, both resolved this session:

- **`node_modules` corruption.** 295 entries carried `" 2"` / `" 3"` suffixes —
  the signature of Finder or a cloud-sync agent resolving name collisions, not
  a shell copy. Rolldown could not resolve its native binding, so every `npm`
  command failed. Source files were unaffected (zero corrupted files outside
  `node_modules`). **The suspected cause — iCloud syncing of `~/Desktop` — was
  not confirmed.** If it is syncing, this will recur; moving the repo out of
  `~/Desktop` would prevent it.
- **Wrong Node version.** The Mac was running Node 20.19.5 from a hardcoded
  Homebrew path at line 1 of `.zshrc`, while the project requires `^22.22.2`.
  Now on **22.23.2**, matching `.nvmrc`, the Docker image and Cloud Build exactly.

### 8.5 `package-lock.json` was out of sync and would have broken Cloud Build
`package.json` required `firebase@^12.5.0` with no corresponding lockfile entry.
`npm ci` — which `cloudbuild.yaml` runs — fails outright on that mismatch. Found
before the first deploy rather than during it. The regenerated lockfile is
committed.

### 8.6 A documented cost estimate was overstated and corrected
An earlier session characterised Cloud SQL as a cost risk. On investigation that
was wrong: it is roughly **$0.25–0.35/day**, about **$1 for a three-day
hackathon window**. The real cost of Cloud SQL is *setup time*, not money. The
correction is recorded because the original claim influenced planning.

### 8.8 Five runbook errors surfaced during execution
Written up because they say something about how much a written runbook should be
trusted before it has been run once:

1. **`--no-assign-ip` on Cloud SQL was wrong.** Cloud Run's `--add-cloudsql-instances`
   uses the Auth Proxy, which reaches the instance over its public IP with IAM
   authentication. With no public IP and no VPC connector, Cloud Run could not
   have connected at all. Public IP with **zero authorized networks** is the
   secure pattern, and was verified empty after creation.
2. **`--edition=ENTERPRISE` is mandatory.** Cloud SQL now defaults new PostgreSQL
   instances to Enterprise Plus, which offers only dedicated machines starting
   at 2 vCPU — well over $100/month against a $20 budget. The creation failed
   loudly, which was the good outcome.
3. **No Gemini API key is needed.** The owner questioned why one was required
   when the architecture already specified Vertex AI. Correct: the code takes
   `genai.Client(vertexai=True, ...)` using ADC, so the service account's
   `roles/aiplatform.user` grant is the whole credential. One fewer secret, and
   Gemini spend now lands inside the project budget rather than a separate API
   quota where it would have been invisible.
4. **`roles/firebaseauth.viewer` was an unnecessary grant.** The backend verifies
   ID tokens locally against Google's public certificates and never calls a
   Firebase Admin API (`verify_id_token` is called without `check_revoked`).
   Granting it would have contradicted the least-privilege claim.
5. **The Cloud Build migration step could never have worked.** The DATABASE_URL
   uses the Cloud SQL socket form, and that socket exists only where the Auth
   Proxy runs — inside Cloud Run, not in a build worker. Removed; the app
   migrates on startup (idempotent, single transaction) and `/readyz` returns
   503 until the schema exists, so the gate moved into the readiness check
   rather than vanishing.

### 8.7 Minor, deliberately deferred
`eslint@9.39.5` reports as no longer supported. It lints correctly. Bumping it
two days before the deadline risks new rule violations across the codebase for
zero demo value. **Recommend leaving it**; worth one line in a known-issues
section.

---

## 9. Assessment

**The code is in good shape. The remaining risk is almost entirely execution
risk, not engineering risk.** 284 backend tests pass against a real PostgreSQL
server, the full production shape has been exercised end to end including
survival across a restart, and the frontend is clean on the owner's own machine.
What has not happened is a single `gcloud` command.

**The strongest asset for judging is not the AI.** It is the closed loop: a
judge sets two environment variables, runs the NovaCart Playwright suite, and
watches real investigations from real failing tests appear in a live dashboard,
with no seeded data and no manual step. That is rare in a hackathon submission
and it directly answers the owner's own constraint. It should be the centrepiece
of the demo.

**The second-strongest asset is the safety posture**, and it is under-sold:
oracle separation enforced before parsing, prompt-injection defences with
schema-validated output and no model tool access, risk policy computed
deterministically rather than trusted from the model, machine and human
credentials that cannot substitute for each other, and a deterministic fallback
that means the system degrades rather than fails. For an *agentic* hackathon
track, "this agent cannot be talked into a bad action" is a stronger story than
an accuracy number.

**The main scheduling judgement: deploy today, not on the 31st.** Every
remaining unknown is in deployment, first deploys reliably surface
misconfiguration, and the failure modes are concentrated in ordering and console
steps rather than code. A failed deploy on the 29th costs an afternoon; the same
failure on the 31st costs the submission. My recommendation is to complete
Phases 0–6 today and treat the 30th as buffer plus writeup and video.

**On whether two days is enough: yes, comfortably, if deployment starts now.**
The runbook is written and the code is verified. Realistic estimate for
Phases 0–6 is 60–90 minutes including console clicks and one typo.

---

## 10. Risk register

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Gemini silently falls back to deterministic in cloud; AI story evaporates unnoticed | Medium | **High** | Explicit provenance check in Phase 6 (§8.3) |
| R2 | Frontend built without `_API_URL`; dashboard calls `localhost:8001` | Medium | High | Phase 5 is deliberately deploy-then-rebuild; cannot be fixed post-build, Vite bakes it in |
| R3 | Firebase `auth/unauthorized-domain` at sign-in | Medium | Medium | Add Cloud Run URL to Firebase authorized domains (Phase 4) |
| R4 | Cost overrun | Low | Medium | Budget alert in Phase 0 — note it *notifies*, it does not stop spending |
| R5 | Cold start on a judge's first click | Medium | Low | `min-instances=1` for judging day |
| R6 | `node_modules` corruption recurs mid-deploy | Low | Medium | Move repo off `~/Desktop` if iCloud sync is confirmed (§8.4) |
| R7 | Deploy attempted on Aug 31 and fails | — | **Critical** | Deploy Aug 29; see §9 |

---

## 11. Pickup point for the next session

**State:** `origin/main` at `d9b3279`, working tree clean, all local checks green,
nothing deployed.

**Next action:** execute `docs/DEPLOYMENT.md` Phase 0, on the owner's Mac.
The three prerequisites to gather first:

1. Billing account ID — `gcloud billing accounts list`
2. A Gemini API key (a placeholder is acceptable; the backend falls back rather
   than erroring — but see R1)
3. A globally unique GCP project ID

**Two ordering traps, restated because they are the ones that actually bite:**
- Phase 0's budget alert goes in **before** anything billable.
- Phase 5 requires **two** `gcloud builds submit` runs. The first exists only to
  learn the two Cloud Run URLs; the second is the build that gets demoed.

**Division of labour:** the implementation session cannot run `gcloud`, cannot
reach GitHub credentials, and cannot make billing changes. All cloud execution
is the owner's. The implementation session can write code, run both test suites,
run a real PostgreSQL, and commit.

### Decisions needed from the architect
1. **Does the Devpost writeup lead with the closed-loop demo or with the AI?**
   Recommendation in §9: the closed loop, with the AI as the mechanism.
2. **Is "1.00 accuracy" going in the writeup?** Recommendation in §8.2: no.
3. **`min-instances=1` (≈$0.30–1.00/day, no cold start) or `0` (cheaper, 5–15s
   first click)?** Recommendation: `1` for judging day.
4. **Is the demo account credential being shared with judges, or do they create
   their own?** Not yet decided; affects Phase 4.

---

## Appendix — file map

| Path | Purpose |
|---|---|
| `docs/DEPLOYMENT.md` | The runbook to execute. 353 lines, Phases 0–7. |
| `docs/EVALUATION.md` | Benchmark method and the honest accuracy caveat. |
| `docs/AI_ARCHITECTURE.md` | Provider abstraction, safety controls. |
| `docs/CREDENTIALS_SETUP.md` | Local credential configuration. |
| `docs/NOVACART_INTEGRATION.md` | Failure-package contract. |
| `docs/CLOUD_FIREBASE_DEPLOYMENT_HANDOFF.md` | **Superseded.** Kept as record of what was planned. |
| `cloudbuild.yaml` | Test → build → migrate → deploy pipeline. |
| `backend/app/db/migrate.py` | Standalone migration command. |
| `backend/app/api/routes/probes.py` | `/livez`, `/readyz`. |
| `backend/app/core/firebase_auth.py` | ID-token verification. |

**Commits in this checkpoint**

```
d9b3279  Make both services Cloud Run ready and add the deployment runbook
df0d2b3  Support PostgreSQL and add an explicit migration step
62dd0bd  Add Firebase human sign-in alongside machine ingestion tokens
```
