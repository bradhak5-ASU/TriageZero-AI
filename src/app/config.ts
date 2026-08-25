// Single source of truth for environment configuration.
// Components never read import.meta.env directly.

export const config = {
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000',
  useMockApi: (import.meta.env.VITE_USE_MOCK_API ?? 'true') !== 'false',
  appName: 'TriageZero',
  tagline: 'Autonomous Failure Intelligence',
  version: '0.1.0',
  build: 'frontend-demo',
  artifactRetentionDays: 30,
} as const;
