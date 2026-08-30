# TriageZero — Google Cloud deployment runbook

Every command here runs on **your Mac**, from the repository root, with the
Google Cloud SDK installed and you signed in. Nothing in this file has been
executed for you: no project, database, service, secret or billing change
exists until you run these yourself.

Read the **Cost** line on each phase before running it. Phase 0 sets a budget
alert first, on purpose.

---

## What gets created

| Resource | Why it is needed | Rough cost while the demo is up |
|---|---|---|
| Cloud SQL for PostgreSQL (`db-f1-micro`) | Durable investigation store. Cloud Run's disk is erased on every restart, so SQLite there loses all data silently. | ~$0.25–0.35/day |
| Cloud Run × 2 (API, dashboard) | Serves the API and the dashboard. | ~$0.30–1.00/day with `min-instances=1` |
| Artifact Registry | Holds the two container images. | pennies |
| Cloud Build | Runs tests, builds, migrates, deploys. | 2,500 free build-minutes/month |
| Firebase Authentication | Human sign-in (email/password). | free at this volume |
| Secret Manager (3 secrets) | Database URL, two API tokens, Gemini key. | ~$0.02/day |
| Vertex AI (Gemini) | AI analysis, via the service account - no API key. | per token; deterministic mode costs nothing |

**Order of magnitude for a 3-day hackathon window: a few US dollars.** These are
approximations, not quotes — list prices change and vary by region. Confirm
against the live pricing pages, and let the budget alert in Phase 0 be the
thing you actually rely on.

If you want the cost floor instead: set `--min-instances=0` on both Cloud Run
services and stop the Cloud SQL instance between sessions. The trade is a cold
start of roughly 5–15 seconds on the first click, which is a bad thing for a
judge to hit. Keep `min-instances=1` for the day of judging.

---

## Phase 0 — project, billing guardrail, APIs

**Cost: none. Do not skip the budget alert.**

```bash
# Use your own values.
export PROJECT_ID="triagezero-demo"          # must be globally unique
export REGION="us-central1"
export BILLING_ACCOUNT="XXXXXX-XXXXXX-XXXXXX"   # gcloud billing accounts list

gcloud projects create "$PROJECT_ID"
gcloud config set project "$PROJECT_ID"
gcloud billing projects link "$PROJECT_ID" --billing-account="$BILLING_ACCOUNT"
```

Set a budget with alerts **before** creating anything billable:

```bash
gcloud billing budgets create \
  --billing-account="$BILLING_ACCOUNT" \
  --display-name="TriageZero demo cap" \
  --budget-amount=25USD \
  --threshold-rule=percent=0.5 \
  --threshold-rule=percent=0.9 \
  --threshold-rule=percent=1.0 \
  --filter-projects="projects/$PROJECT_ID"
```

A budget alert notifies; it does not stop spending. It is a smoke detector, not
a circuit breaker. If you want a hard stop you must disable billing on the
project manually.

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com \
  aiplatform.googleapis.com \
  identitytoolkit.googleapis.com
```

---

## Phase 1 — Cloud SQL (PostgreSQL)

**Cost: this is the first billable step (~$0.25–0.35/day, plus storage).**

```bash
export SQL_INSTANCE="triagezero-db"
export DB_NAME="triagezero"
export DB_USER="tzapp"
export DB_PASSWORD="$(openssl rand -base64 32 | tr -d '/+=' | head -c 32)"

gcloud sql instances create "$SQL_INSTANCE" \
  --database-version=POSTGRES_16 \
  --edition=ENTERPRISE \
  --tier=db-f1-micro \
  --region="$REGION" \
  --storage-size=10GB \
  --storage-auto-increase \
  --no-backup

gcloud sql databases create "$DB_NAME" --instance="$SQL_INSTANCE"
gcloud sql users create "$DB_USER" --instance="$SQL_INSTANCE" --password="$DB_PASSWORD"

export SQL_CONNECTION_NAME="$(gcloud sql instances describe "$SQL_INSTANCE" \
  --format='value(connectionName)')"
echo "connection name: $SQL_CONNECTION_NAME"
```

**`--edition=ENTERPRISE` is not optional.** Cloud SQL now defaults new
PostgreSQL instances to Enterprise Plus, which offers only dedicated
`db-perf-optimized-N-*` machines starting at 2 vCPU - well over $100/month.
Shared-core tiers (`db-f1-micro`, `db-g1-small`) exist only in the Enterprise
edition. Omitting the flag fails with an "Invalid Tier for (ENTERPRISE_PLUS)
Edition" error, which is the good outcome; the bad outcome is accepting the
suggested tier and quietly running a machine 100x the needed size.

If `db-f1-micro` is rejected in your region, `db-g1-small` is the next step up
and still inexpensive.

**On the instance's public IP.** The instance keeps its default public IP, and
that is correct here — Cloud Run's `--add-cloudsql-instances` uses the Cloud SQL
Auth Proxy, which reaches the instance over that IP and authenticates with IAM.
Creating the instance with `--no-assign-ip` would make Cloud Run unable to
connect at all unless you also set up Direct VPC egress or a Serverless VPC
Access connector, which is more moving parts and more cost than this needs.

A public IP is **not** an open database. No authorized networks are added, so
nothing on the internet can reach it; only the IAM-authenticated Auth Proxy can,
and only from principals holding `roles/cloudsql.client`. Verify this after
creation:

```bash
gcloud sql instances describe "$SQL_INSTANCE" \
  --format='value(settings.ipConfiguration.authorizedNetworks)'
```

Empty output is what you want — it means no network is allow-listed.

`--no-backup` is chosen deliberately for a short-lived demo instance: automated
backups cost storage and this database holds nothing that could not be
regenerated by re-running the Playwright suite. For anything real, drop that
flag.

---

## Phase 2 — secrets

**Cost: ~$0.02/day.**

```bash
# The socket form: note the empty host and the ?host= query parameter.
DB_URL="postgresql+psycopg://${DB_USER}:${DB_PASSWORD}@/${DB_NAME}?host=/cloudsql/${SQL_CONNECTION_NAME}"

printf '%s' "$DB_URL"             | gcloud secrets create triagezero-database-url    --data-file=-
openssl rand -hex 32 | tr -d '\n' | gcloud secrets create triagezero-ingestion-token --data-file=-
openssl rand -hex 32 | tr -d '\n' | gcloud secrets create triagezero-dashboard-token --data-file=-
```

**Three secrets, not four — there is no Gemini API key.** Gemini is reached
through Vertex AI with the API service account's own credentials
(`roles/aiplatform.user`, granted in Phase 3), so no key exists to create,
store, rotate or leak. It also means Gemini spend is billed to this project and
shows up in the same budget as everything else, rather than against a separate
API quota you would have to watch independently.

`printf` rather than `echo`: a trailing newline becomes part of the secret and
produces authentication failures that read like a wrong password.

Read the ingestion token back when you configure the Playwright reporter:

```bash
gcloud secrets versions access latest --secret=triagezero-ingestion-token
```

---

## Phase 3 — service accounts (least privilege)

**Cost: none.**

Two service accounts, each holding only what its service actually uses. The
default compute service account is Editor on the whole project — never deploy
with it.

```bash
gcloud iam service-accounts create triagezero-api  --display-name="TriageZero API"
gcloud iam service-accounts create triagezero-web  --display-name="TriageZero dashboard"

API_SA="triagezero-api@${PROJECT_ID}.iam.gserviceaccount.com"

# talk to Cloud SQL
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$API_SA" --role="roles/cloudsql.client"

# call Gemini through Vertex AI
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$API_SA" --role="roles/aiplatform.user"

# NOTE: no Firebase IAM role is granted, deliberately. The backend verifies ID
# tokens locally - it fetches Google's public signing certificates from a public
# endpoint and checks the JWT signature and audience. It never calls a Firebase
# Admin API (verify_id_token is called without check_revoked, which would cost a
# round trip per request). Granting roles/firebaseauth.viewer would be a
# permission the service never exercises.

# read ONLY its own three secrets, not every secret in the project
for S in triagezero-database-url triagezero-ingestion-token \
         triagezero-dashboard-token; do
  gcloud secrets add-iam-policy-binding "$S" \
    --member="serviceAccount:$API_SA" --role="roles/secretmanager.secretAccessor"
done
```

The dashboard service account gets nothing: the frontend is static files and
holds no credential of its own.

---

## Phase 4 — Firebase Authentication

**Cost: none at this volume.**

1. Open the Firebase console and add Firebase to this **existing** GCP project
   (do not create a second project — the backend verifies ID tokens against
   `FIREBASE_PROJECT_ID`, which must be this one).
2. Build → Authentication → Get started → enable **Email/Password**.
3. Project settings → Your apps → Web app → register one → copy the config.
4. Create the demo account judges will use: Authentication → Users → Add user.

The `apiKey`, `authDomain`, `projectId` and `appId` from step 3 are **public**
values — they identify the project to Google and are designed to ship in a
browser bundle. They are not secrets, and they are the only credentials that
ever go into a frontend build arg.

After the dashboard URL exists (Phase 6), add it under Authentication →
Settings → **Authorized domains**, or sign-in fails with
`auth/unauthorized-domain`.

---

## Phase 5 — Artifact Registry, and the first deploy

**Cost: images cost pennies; Cloud Run starts billing here.**

```bash
gcloud artifacts repositories create triagezero \
  --repository-format=docker --location="$REGION"
```

There is a chicken-and-egg here and it is worth naming: the dashboard bundle
needs the API's URL at **build** time, and the API needs the dashboard's origin
for CORS. Neither URL exists until its service is deployed. So the first pass
is deploy-then-rebuild:

```bash
# 1. deploy the API with a placeholder origin, to learn its URL
gcloud builds submit --config=cloudbuild.yaml \
  --substitutions=_SQL_INSTANCE="$SQL_CONNECTION_NAME",_API_URL="https://placeholder.invalid",_WEB_ORIGIN="https://placeholder.invalid",SHORT_SHA=bootstrap

API_URL="$(gcloud run services describe triagezero-api --region="$REGION" --format='value(status.url)')"
WEB_URL="$(gcloud run services describe triagezero-web --region="$REGION" --format='value(status.url)')"
echo "API: $API_URL"
echo "WEB: $WEB_URL"
```

Then run it again with the real values — this is the build that produces the
artifacts you actually demo:

```bash
gcloud builds submit --config=cloudbuild.yaml --substitutions=\
_SQL_INSTANCE="$SQL_CONNECTION_NAME",\
_API_URL="$API_URL",\
_WEB_ORIGIN="$WEB_URL",\
_FIREBASE_API_KEY="<from Phase 4>",\
_FIREBASE_AUTH_DOMAIN="<from Phase 4>",\
_FIREBASE_PROJECT_ID="$PROJECT_ID",\
_FIREBASE_APP_ID="<from Phase 4>",\
SHORT_SHA="$(git rev-parse --short HEAD)"
```

The pipeline runs both test suites before it builds anything, applies schema
migrations as their own step, and only then deploys. A failing test or a
failing migration stops the deploy instead of shipping a broken revision.

---

## Phase 6 — verification (do this before you rely on it)

```bash
# probes: alive, and connected to the real database
curl -sS "$API_URL/api/v1/livez"    # {"status":"alive"}
curl -sS "$API_URL/api/v1/readyz"   # {"status":"ready"}  <- proves Cloud SQL is wired

# schema is actually migrated, not just created
gcloud builds submit --no-source --config=- <<'YAML'
steps:
  - name: 'REPLACE_WITH_API_IMAGE'
    entrypoint: bash
    args: ['-c', 'python -m app.db.migrate --check']
    secretEnv: ['DATABASE_URL']
availableSecrets:
  secretManager:
    - versionName: 'projects/PROJECT/secrets/triagezero-database-url/versions/latest'
      env: DATABASE_URL
YAML

# the dashboard must NOT be open without a credential
curl -s -o /dev/null -w '%{http_code}\n' "$API_URL/api/v1/investigations"   # expect 401

# CORS must name the dashboard exactly, and refuse anything else
curl -sI -H "Origin: $WEB_URL"               "$API_URL/api/v1/health" | grep -i access-control-allow-origin
curl -sI -H "Origin: https://evil.example"   "$API_URL/api/v1/health" | grep -i access-control-allow-origin  # expect nothing
```

Then, in a browser: open `$WEB_URL`, sign in with the demo account, and confirm
the dashboard loads investigations.

**End-to-end, the way a judge will see it** — send a real failure from the
NovaCart Playwright suite with the ingestion token, and watch it appear:

```bash
INGEST_TOKEN="$(gcloud secrets versions access latest --secret=triagezero-ingestion-token)"

# In the TriageZero (NovaCart) repo, from playwright-tests/:
cd ~/Desktop/TriageZero/playwright-tests
TRIAGEZERO_API_URL="$API_URL" \
TRIAGEZERO_API_TOKEN="$INGEST_TOKEN" \
NOVACART_BASE_URL="http://localhost:5173" \
npx playwright test
```

Submission is automatic and requires no manual step: `writeFailureEvidence()`
in `helpers/evidence.ts` calls `submitFailurePackageIfConfigured()`, which
posts the failure package whenever `TRIAGEZERO_API_URL` is set. Each failing
test prints its own line:

```
TriageZero upload: HTTP 202, investigation_id=INV-XXXXXXXX, status=received
```

Setting **no** `TRIAGEZERO_API_URL` is the off switch — the suite then runs
exactly as it does today and uploads nothing. This is what lets a judge run the
suite themselves and watch investigations appear in the dashboard live, with
real evidence from a real failing test.

The reporter uses the **ingestion** token. It never uses a human sign-in, and a
human's ID token cannot be used to impersonate the reporter — the API keeps the
two credential types on separate routes and returns 403, not 401, if one is
presented on the other's route.

---

## Phase 7 — shutting it down

The only step that reliably stops spending:

```bash
gcloud sql instances delete "$SQL_INSTANCE"       # the main cost
gcloud run services delete triagezero-api  --region="$REGION"
gcloud run services delete triagezero-web  --region="$REGION"
```

Or, to keep everything and just stop the meter between sessions:

```bash
gcloud sql instances patch "$SQL_INSTANCE" --activation-policy=NEVER
gcloud run services update triagezero-api --region="$REGION" --min-instances=0
gcloud run services update triagezero-web --region="$REGION" --min-instances=0
```

Deleting the project deletes everything in it, which is the cleanest option
once the hackathon is over.

---

## Things that will bite you

- **`auth/unauthorized-domain` at sign-in** — the Cloud Run dashboard URL is not
  in Firebase's authorized domains (Phase 4, last note).
- **CORS failure with a correct-looking origin** — `FRONTEND_ORIGINS` has a
  trailing slash. Browsers send `https://host` with no path. The backend now
  refuses to start with a trailing slash rather than failing at demo time.
- **`readyz` returns 503** — the API cannot reach Cloud SQL. Check that
  `--add-cloudsql-instances` matches `$SQL_CONNECTION_NAME` exactly and that the
  API service account has `roles/cloudsql.client`.
- **The API starts, then every write fails** — the database user lacks table
  privileges. The migration job creates the schema; make sure it ran, and that
  it ran as the same user the service connects with.
- **The dashboard calls `localhost:8001` in production** — the frontend was
  built without `_API_URL`. Vite bakes it in at build time; changing an
  environment variable on the running container cannot fix it. Rebuild.
- **Investigations vanish after a redeploy** — `DATABASE_URL` is pointing at
  SQLite. The backend refuses to start in production with a SQLite URL for
  exactly this reason; if you see it, something is overriding the secret.
