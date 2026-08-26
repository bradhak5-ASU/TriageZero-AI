# NovaCart → TriageZero integration

Two separate systems run side by side on one machine.

| | Repository | Role | Frontend | Backend |
|---|---|---|---|---|
| **NovaCart** | separate repo | the **target application** under test, plus its Playwright suite | `http://localhost:5173` | `http://localhost:8000` |
| **TriageZero** | this repo | the **investigation system** that receives and analyzes failures | `http://localhost:5174` | `http://localhost:8001` |

The ports are deliberately offset so both stacks can run at the same time. **Never change NovaCart's ports** — TriageZero moved instead.

## Where Playwright submits failure packages

**Playwright running directly on macOS** (the normal case):

```
POST http://localhost:8001/api/v1/investigations
```

**Playwright running inside a Docker container on macOS** — `localhost` there means the *container*, not the host, so use Docker Desktop's host alias:

```
POST http://host.docker.internal:8001/api/v1/investigations
```

Make this configurable in the NovaCart harness rather than hardcoding it, e.g.:

```ts
const TRIAGEZERO_URL =
  process.env.TRIAGEZERO_URL ?? 'http://localhost:8001';
await fetch(`${TRIAGEZERO_URL}/api/v1/investigations`, {
  method: 'POST',
  headers: {
    'content-type': 'application/json',
    'Idempotency-Key': `${runId}:${testId}`, // optional; see below
  },
  body: JSON.stringify(failurePackage),
});
```

On Linux CI, `host.docker.internal` does not exist by default — either run with `--add-host=host.docker.internal:host-gateway` or point `TRIAGEZERO_URL` at the service name on a shared Docker network.

## Responses the harness must handle

| Status | Meaning | Harness action |
|---|---|---|
| `202` | accepted — body is `{"investigation_id", "status", "received_at"}` | log the id; continue |
| `409` | `Idempotency-Key` reused with *different* evidence | use a new key per distinct failure |
| `413` | package exceeds the configured size cap | trim the stack trace / console lines |
| `422` | contract violation — body names the offending field paths | fix the producer; do not retry unchanged |

An `Idempotency-Key` is optional but recommended (`<run_id>:<test_id>`): resubmitting the *same* package under the same key is a no-op, which makes CI retries safe.

## The contract must match exactly

TriageZero enforces failure-package **v1.0 as a closed schema** — see `src/data/samplePackage.ts` for the canonical example and `backend/app/schemas/failure_package.py` for the enforced rules:

- `schema_version` must be `"1.0"` and `test.status` must be `"failed"`.
- `environment.browser` ∈ `chromium` | `firefox` | `webkit`.
- `environment.name` ∈ `local` | `staging` | `production`.
- Network `status` must be a valid HTTP status, or `0` for a connection failure.
- Artifact paths must be **relative** — no absolute paths, `..` traversal, `~`, or `file://` URLs.
- **Unknown fields are rejected at every level.** If the harness needs to send something new, bump `schema_version`; do not bolt fields onto v1.0.

Text lengths and list sizes are capped, and the whole request has a byte cap enforced on the bytes actually received (a chunked upload cannot bypass it).

## Private evaluation-oracle fields must never be submitted

NovaCart's evaluation harness knows each controlled defect's expected outcome. That knowledge is the **oracle**, and it must never reach the investigator — otherwise TriageZero would be grading itself against its own inputs.

These keys are rejected recursively, at any nesting depth, with HTTP `422` and error code `private_oracle_fields`:

```
expected_classification   expected_severity   expected_release_risk
expected_action           private_oracle      oracle
controlled_defect         defect_scenario     scenario_name
```

Rejected packages are not persisted, the analyzer is never invoked, and the offending values are never logged or echoed back — only the key paths are reported.

Keep the oracle in the NovaCart repository, in a file the failure-package builder does not read (e.g. `playwright-tests/evaluation/expected-results.json`). TriageZero never reads that file, and nothing in this repository imports it.
