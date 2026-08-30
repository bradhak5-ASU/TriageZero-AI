// Single source of truth for environment configuration.
// Components never read import.meta.env directly.

export const config = {
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8001',
  useMockApi: (import.meta.env.VITE_USE_MOCK_API ?? 'true') !== 'false',
  appName: 'TriageZero',
  tagline: 'Autonomous Failure Intelligence',
  version: '0.1.0',
  // artifactRetentionDays was here and was displayed as "30 days (configured
  // server-side)". The frontend has no way to know the server's retention
  // policy, so it was simply asserting a number. Removed rather than guessed.
} as const;
