import type { FailurePackage } from '../types';

// The canonical example package Playwright submits from the NovaCart repo.
export const sampleFailurePackage: FailurePackage = {
  schema_version: '1.0',
  source: 'novacart-playwright',
  run: {
    run_id: `github-run-${10000 + Math.floor(Math.random() * 90000)}`,
    trigger: 'local',
    started_at: new Date().toISOString(),
  },
  repository: {
    name: 'novacart-target',
    branch: 'main',
    commit_sha: 'abc123def4567890abc123def4567890abc123de',
  },
  environment: {
    name: 'local',
    target_url: 'http://localhost:5173',
    browser: 'chromium',
  },
  test: {
    name: 'successful checkout shows confirmation page',
    file: 'playwright-tests/tests/novacart-baseline.spec.ts',
    status: 'failed',
    retry: 0,
  },
  failure: {
    expected: '201',
    actual: '500',
    message: 'Expected HTTP 201 but received HTTP 500',
    stack_trace:
      'Error: Expected HTTP 201 but received HTTP 500\n    at expectOrderCreated (playwright-tests/tests/novacart-baseline.spec.ts:214:11)\n    at NovacartCheckoutPage.submitOrder (playwright-tests/pages/checkout.page.ts:88:5)',
  },
  network_evidence: [
    {
      method: 'POST',
      url: 'http://localhost:8000/api/v1/orders',
      status: 500,
    },
  ],
  console_errors: [
    'Failed to load resource: the server responded with status 500',
  ],
  artifacts: {
    screenshot_path: 'test-results/run/test-failed-1.png',
    trace_path: 'test-results/run/trace.zip',
  },
};
