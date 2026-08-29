# Credentials setup

TriageZero runs **fully without credentials**. Everything — the API, the
dashboard, the deterministic analyzer, the test suite, the evaluation harness,
and both Docker images — works with no key present. Follow this guide only when
you want to switch the analyzer from `deterministic` to a Gemini-backed mode.

> **Never paste an API key into a chat, a source file, a commit, a screenshot,
> or an issue.** The only place a real key belongs is `backend/.env`, which is
> gitignored and never built into an image.

## Steps

1. **Create or select a Google AI Studio project** at
   <https://aistudio.google.com/>.
2. **Create a Gemini API key** in that project.
3. **Do not paste it anywhere except step 5.** Not into this repository, not
   into the frontend, not into a prompt, not into a chat window.
4. **Copy the example file:**

   ```bash
   cd backend
   cp .env.example .env
   ```

   `backend/.env` is gitignored. `backend/.env.example` keeps `GEMINI_API_KEY=`
   blank and must stay that way.

5. **Add the key locally**, editing `backend/.env`:

   ```
   GEMINI_API_KEY=<paste your key here, in this file only>
   ```

6. **Select the analyzer mode** in the same file:

   ```
   ANALYZER_MODE=gemini_adk      # or: gemini
   AI_FALLBACK_ENABLED=true      # keep true until you trust the provider
   ```

7. **Restart the backend:**

   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
   ```

8. **Check health.** Before the first provider request it must report
   `unverified`, not `healthy`. After a successful smoke investigation it must
   change to `healthy`:

   ```bash
   curl -s http://localhost:8001/api/v1/health | python3 -m json.tool | grep -A8 '"ai"'
   ```

   | `geminiStatus` | meaning |
   |---|---|
   | `disabled` | that mode is not selected |
   | `unconfigured` | mode selected, but no credentials found |
   | `unverified` | credentials found, but no provider call has succeeded yet |
   | `degraded` | configured, but the last call failed |
   | `healthy` | configured and answering |

   Health never reports a key, a key length, or a key prefix/suffix.

9. **Run one smoke investigation** and confirm the provider is real (not a
   fallback):

   ```bash
   curl -sS -X POST http://localhost:8001/api/v1/investigations \
     -H 'content-type: application/json' \
     --data-binary @- <<'JSON'
   { "schema_version": "1.0", "source": "novacart-playwright",
     "run": {"run_id": "smoke-1", "trigger": "local", "started_at": "2026-08-26T00:00:00Z"},
     "repository": {"name": "novacart-target", "branch": "main", "commit_sha": "abc123"},
     "environment": {"name": "local", "target_url": "http://localhost:5173", "browser": "chromium"},
     "test": {"name": "smoke check", "file": "playwright-tests/tests/smoke.spec.ts", "status": "failed", "retry": 0},
     "failure": {"expected": "201", "actual": "500", "message": "Expected HTTP 201 but received HTTP 500", "stack_trace": "Error\n    at smoke.spec.ts:1:1"},
     "network_evidence": [{"method": "POST", "url": "http://localhost:8000/api/v1/orders", "status": 500}],
     "console_errors": [], "artifacts": {} }
   JSON
   ```

   Then open the investigation and check `aiMetadata.provider`. If it says
   `deterministic_fallback`, the model did **not** run — read
   `aiMetadata.fallbackReason` (`unconfigured`, `auth_error`, `transient_error`,
    `invalid_schema`) rather than assuming success.

   For `ANALYZER_MODE=gemini_adk`, the provider value must be `gemini_adk`.
   The production path creates a real ADK `Agent`, isolated in-memory session,
   and `Runner`; it cannot report `gemini_adk` after using deterministic rules.

### Docker users

`docker compose` loads `backend/.env` as an optional runtime-only environment
file. The file is excluded from Git and the Docker build context. With no file,
the container remains in deterministic mode. After editing it, recreate the
backend with `docker compose up --build -d backend`.

10. **Run the provider evaluation** and compare it against the deterministic
    baseline on identical data:

    ```bash
    cd backend
    python -m app.evaluation.run \
      --provider gemini_adk \
      --dataset evaluation/datasets/holdout.json \
      --output evaluation/results/gemini-adk.json \
      --compare-with evaluation/results/deterministic-baseline.json
    ```

    This is the first step that spends real tokens. Everything before it is free.

## Cost and safety notes

- Start with `ANALYZER_MODE=gemini` (single call per investigation) before
  `gemini_adk` (staged workflow), and keep `AI_FALLBACK_ENABLED=true` so a
  provider outage degrades to deterministic analysis instead of failing ingestion.
- `GEMINI_REQUEST_TIMEOUT_SECONDS` and `GEMINI_MAX_RETRIES` bound the spend per
  investigation. The direct Gemini HTTP client and the ADK workflow both apply
  the request deadline; retries apply only to transient direct-Gemini errors.
- The frontend never receives the key: `VITE_*` variables are the only values
  baked into the bundle, and `GEMINI_API_KEY` is not one of them.
- To use Vertex AI instead of the Gemini Developer API, set
  `GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT`, and
  `GOOGLE_CLOUD_LOCATION`, and authenticate with application default
  credentials instead of an API key.
- To revert at any time: set `ANALYZER_MODE=deterministic` and restart. No key
  is needed and nothing else changes.
