# TriageZero — Cloud, Firebase Auth, and Production Handoff

**Checkpoint date:** August 29, 2026

**Repository:** `https://github.com/bradhak5-ASU/TriageZero-AI.git`

**Google Cloud project:** `triagezero`

This document is both a project checkpoint and a paste-ready prompt for the next
Claude, ChatGPT, or Codex session. Work directly in the cloned repository. Do
not produce a ZIP or a replacement scaffold.

## Verified checkpoint

TriageZero currently has:

- React, Vite, and TypeScript dashboard frontend.
- FastAPI backend with a strict failure-package v1 API.
- Local SQLite persistence, migrations, idempotency, concurrency protection,
  request-size enforcement, API bearer-token support, and private-oracle
  rejection.
- Deterministic analysis, direct Gemini analysis, and Google ADK analysis.
- Sanitized evidence only is sent to Gemini/Vertex. Credentials, private
  evaluation labels, expected classifications, controlled-defect names, and
  raw artifact contents are excluded.
- Deterministic severity and release-risk policy after AI classification.
- Offline accuracy/evaluation datasets and metrics.
- Dockerfiles for the frontend and backend and a local Docker Compose setup.

The latest live Vertex verification succeeded:

- Investigation: `INV-A83AA8AB`
- Provider: `gemini_adk`
- Model: `gemini-3.6-flash`
- Classification: `backend_application_defect`
- Confidence: `0.925`
- Severity: `high`
- Release risk: `block_release`
- Fallback: `false`
- Usage: 7,857 input tokens and 442 output tokens
- Estimated model cost for that run: about `$0.00755`

The ADK structured-output issue is fixed. The tool-using agent now has one
structured-output mechanism (`ModelAnalysis`) and no duplicate validation tool.
The backend still validates the closed schema again before persistence.

Verification at this checkpoint:

- Backend Ruff: clean.
- Backend pytest: 232 passed.
- Live Vertex ADK end-to-end run: passed without fallback.
- `backend/.env` is ignored by Git.
- No Gemini API key, token, service-account key, or ADC credential is committed.

Cloud preparation already completed by the owner:

- Google Cloud project `triagezero` exists and billing is enabled.
- `aiplatform.googleapis.com` is enabled.
- Google Cloud CLI is installed and authenticated.
- Application Default Credentials work locally with quota project
  `triagezero`.
- Vertex settings are configured locally:
  `GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT=triagezero`, and
  `GOOGLE_CLOUD_LOCATION=global`.
- A cloud budget/alerts were configured. Do not assume a budget automatically
  stops all spending; verify billing controls separately.

## What is not implemented yet

Do not claim these are complete:

- Firebase Authentication and a sign-in screen.
- Firebase ID-token verification in FastAPI.
- Per-user or per-organization workspaces. The intended hackathon experience is
  one shared, sanitized demo workspace after sign-in.
- Production persistence. SQLite is local-only and must not be treated as
  durable storage on Cloud Run.
- Cloud Run services, Artifact Registry images, Secret Manager secrets, or
  Cloud Build deployment triggers.
- Cloud Storage artifact upload/download.
- Pub/Sub processing.
- Automatic Cloud Build execution of the NovaCart Playwright suite.
- Production-domain CORS and Firebase authorized-domain configuration.

## Approved target architecture

Use this minimal architecture for the hackathon:

1. **Frontend:** the existing React application in a Cloud Run frontend service.
2. **Human authentication:** Firebase Authentication. Start with email/password
   sign-up and sign-in. Google sign-in can be added if time permits.
3. **Backend:** the existing FastAPI application in a Cloud Run backend service.
4. **Dashboard authorization:** the frontend sends the signed-in user's Firebase
   ID token as `Authorization: Bearer <ID_TOKEN>`. The backend verifies the ID
   token with Firebase Admin and accepts it only for dashboard/management APIs.
5. **Machine ingestion authorization:** NovaCart/Cloud Build continues to use a
   separate high-entropy ingestion bearer token. Never put this token in the
   browser bundle or failure package.
6. **AI:** Vertex AI through the Cloud Run service account and Application
   Default Credentials. Do not deploy `GEMINI_API_KEY` when using Vertex.
7. **Secrets:** Google Secret Manager for the ingestion token and database
   credentials. Firebase web configuration is public application configuration,
   not a backend secret, but it should still be supplied through documented
   frontend build configuration.
8. **Persistence:** Cloud SQL for PostgreSQL is the recommended first production
   adapter because the application already uses SQLAlchemy and relational
   models. Keep SQLite for local development. Do not deploy Cloud Run with
   SQLite and describe it as durable. Firestore may be considered later, but it
   requires a larger repository-layer rewrite and should not be mixed into the
   first deployment milestone.
9. **Automation:** Cloud Build GitHub triggers. The AI repository trigger builds,
   tests, and deploys TriageZero. The NovaCart repository trigger runs the
   Playwright suite and automatically uploads only failed-test evidence to the
   production TriageZero ingestion endpoint.

The signed-in dashboard is a **shared sanitized demo workspace**: authenticated
demo users may view the same investigations. It must never expose private
evaluation oracle data. Multi-tenancy and organization isolation are explicitly
post-hackathon work.

## Required implementation order

### Phase 1 — Firebase Auth locally

Implement and test authentication before cloud deployment.

Frontend requirements:

- Add the modular Firebase Web SDK.
- Add documented `VITE_FIREBASE_*` configuration placeholders to
  `.env.example`; do not add real private credentials.
- Add an authentication provider/context with loading, signed-in, and signed-out
  states.
- Add a polished sign-up/sign-in page, sign-out action, route protection, and
  clear authentication errors.
- Start with email/password authentication. Do not implement anonymous access.
- Attach the current Firebase ID token to dashboard API requests and refresh it
  through Firebase's supported token flow.
- Never attach the Firebase token to the failure-package JSON.

Backend requirements:

- Add Firebase Admin as a backend dependency.
- Initialize it with Application Default Credentials and the explicit project
  ID; never require a downloaded service-account JSON file in the repository.
- Verify Firebase ID tokens on dashboard/management routes.
- Preserve the existing distinct ingestion-token path for CI/reporters.
- Return consistent `401` for missing/invalid authentication and `403` for an
  authenticated identity that lacks required access.
- Keep local testability: tests must use a fake token verifier and must never
  contact Firebase or Vertex.
- Keep production fail-closed behavior.

Tests required:

- Frontend sign-in, sign-out, auth loading, protected-route redirect, token
  attachment, expired-token refresh/error, and no-token-leak tests.
- Backend valid token, invalid token, expired token, missing token, ingestion
  token separation, and offline-test guard tests.
- Existing suites must remain green.

Stop after Phase 1 and report the exact files changed and verification results.
Do not create cloud resources or deploy without the owner's confirmation.

### Phase 2 — Production persistence

- Add PostgreSQL driver/configuration while retaining SQLite locally.
- Introduce a proper production migration command instead of relying only on
  SQLite startup migration behavior.
- Verify all repository operations, idempotency constraints, timestamps, JSON
  fields, and concurrency behavior on PostgreSQL.
- Add a disposable PostgreSQL integration-test path.
- Prepare Cloud SQL connection configuration for Cloud Run.
- Do not create a paid Cloud SQL instance until the owner confirms region,
  machine size, backup policy, and expected cost.

### Phase 3 — Cloud-ready configuration

- Make both containers comply with Cloud Run's injected `PORT` setting.
- Add health/startup checks.
- Configure exact production CORS origins; never use `*` with authenticated
  requests.
- Keep frontend API-base configuration reproducible at build/deploy time.
- Create least-privilege runtime and build service-account documentation.
- Backend runtime identity needs only the permissions actually used, such as
  Vertex AI invocation, Cloud SQL connection, and access to named secrets.
- Add `cloudbuild.yaml` files only after reviewing every build step and secret
  reference. Never print secrets to logs.

### Phase 4 — Manual first deployment

The owner wants to perform cloud setup interactively. Before executing any
mutating `gcloud` command, show the exact command, explain what it creates and
its likely billing impact, and wait for confirmation.

Deploy in this order:

1. Enable only the required APIs.
2. Create Artifact Registry repository.
3. Create least-privilege service accounts and IAM bindings.
4. Create Secret Manager entries without displaying their values.
5. Create and migrate Cloud SQL PostgreSQL after explicit cost approval.
6. Build and deploy the backend.
7. Configure the backend URL in the frontend build.
8. Build and deploy the frontend.
9. Add the frontend domain to Firebase authorized domains.
10. Configure exact backend CORS origin.
11. Perform production sign-in and authenticated API smoke tests.
12. Run one controlled failed-test upload and confirm a real Vertex
    investigation appears without fallback.

### Phase 5 — Enterprise-style automation

After the manual deployment is proven:

- Connect both GitHub repositories to Cloud Build using the GitHub App/current
  repository connection flow.
- AI repository pull requests: lint, offline backend tests, frontend tests, and
  production build; no deployment and no live Vertex calls.
- AI repository `main`: repeat checks, build immutable images, and deploy only
  after checks pass. Consider manual approval until the demo is stable.
- NovaCart pull requests and `main`: start the target application, seed it, run
  Playwright, and upload a failure package only when a test fails.
- Store the production ingestion token in Secret Manager and expose it only to
  the NovaCart build step that uploads evidence.
- Preserve controlled-defect intent in the private evaluation subsystem, never
  in the submitted evidence or Gemini prompt.
- For the demo, provide a manually invokable Cloud Build trigger so the video
  can show the complete autonomous chain live without editing and pushing code
  on camera.

## Production acceptance checklist

Do not call the system production-ready until all are true:

- Firebase sign-in works and unsigned users cannot open dashboard data.
- FastAPI independently verifies Firebase ID tokens.
- Machine ingestion and human dashboard authentication are separate.
- Real secrets exist only in Secret Manager/local ignored files.
- Cloud Run uses durable production storage, not container-local SQLite.
- Vertex runs through the Cloud Run service account without an API key.
- One production investigation shows `provider=gemini_adk`,
  `usedFallback=false`, token usage, and validated schema output.
- Private oracle fields never appear in evidence, provider prompts, public APIs,
  logs, or the normal dashboard.
- Cloud Build checks are green and do not make accidental billable AI calls.
- Budget alerts, maximum Cloud Run instances, and a post-demo shutdown plan are
  documented.
- The complete NovaCart failure-to-investigation flow is recorded and
  reproducible.

## Paste-ready instruction for the next AI

Read this entire document and inspect the current repository before changing
anything. Work directly in the existing files; do not scaffold a replacement,
make a ZIP, commit credentials, or fabricate verification results. Begin with
Phase 1 only: implement Firebase email/password authentication locally across
the React frontend and FastAPI backend while preserving the separate machine
ingestion token. Use Firebase ID tokens for human dashboard APIs, Firebase Admin
with Application Default Credentials on the backend, fake verifiers in tests,
and a shared sanitized demo workspace. Keep all tests offline. Run lint, all
frontend tests/build, all backend tests, and credential-leak checks. Report the
actual results and stop before creating resources, deploying, changing billing,
or starting Phase 2. If the repository state conflicts with this checkpoint,
report the mismatch instead of guessing.

## Official references

- Firebase web authentication:
  https://firebase.google.com/docs/auth/web/start
- Verify Firebase ID tokens in a custom backend:
  https://firebase.google.com/docs/auth/admin/verify-id-tokens
- Firebase web configuration is public application configuration:
  https://firebase.google.com/docs/projects/learn-more
- Cloud Run deployment options:
  https://docs.cloud.google.com/run/docs/deployment-options-for-services
- Cloud Run service configuration and service identity:
  https://docs.cloud.google.com/run/docs/configuring
- Secret Manager with Cloud Run:
  https://docs.cloud.google.com/run/docs/configuring/services/secrets
- Cloud Run to Cloud SQL for PostgreSQL:
  https://docs.cloud.google.com/sql/docs/postgres/connect-run
- Cloud Build GitHub triggers:
  https://docs.cloud.google.com/build/docs/automating-builds/github/build-repos-from-github
