#!/usr/bin/env bash
# Entry point for the scheduled test run.
#
# The critical detail: this exits 0 even when tests fail.
#
# A failing test is the EXPECTED outcome here - it is the input TriageZero
# exists to process. If the container exited non-zero, Cloud Run would treat a
# perfectly healthy run as a crashed job, retry it, and eventually mark the
# schedule as failing. The job's success means "the suite ran and reported",
# not "the application under test is healthy". That distinction is the whole
# point of the system.
#
# A genuine infrastructure failure - the suite not running at all - still
# surfaces, because Playwright's own exit codes are logged before we swallow
# the test result.
set -uo pipefail

echo "=== TriageZero scheduled run $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo "target:   ${NOVACART_BASE_URL:-<unset>}"
echo "reporting to: ${TRIAGEZERO_API_URL:-<unset>}"
echo "defect scenario: ${NOVACART_DEFECT_SCENARIO:-<none>}"
echo "token present: $([ -n "${TRIAGEZERO_API_TOKEN:-}" ] && echo yes || echo NO)"

if [ -z "${TRIAGEZERO_API_URL:-}" ] || [ -z "${TRIAGEZERO_API_TOKEN:-}" ]; then
  echo "ERROR: TriageZero URL or token missing - failures would be discarded."
  exit 1   # a real misconfiguration; this SHOULD fail the job
fi

npx playwright test
STATUS=$?

echo "=== playwright exit code: $STATUS ==="
if [ "$STATUS" -eq 0 ]; then
  echo "All tests passed - nothing to investigate this run."
else
  echo "Tests failed - failure packages were submitted to TriageZero."
fi
echo "=== run complete ==="
exit 0
