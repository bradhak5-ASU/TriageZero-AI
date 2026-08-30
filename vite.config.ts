/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// TriageZero runs on 5174 so it never collides with the NovaCart target app (5173).
const DEV_PORT = 5174;

export default defineConfig({
  plugins: [react()],
  server: { port: DEV_PORT, strictPort: true },
  preview: { port: DEV_PORT, strictPort: true },
  test: {
    environment: 'jsdom',
    globals: true,
    // Playwright suites are staged under deploy/.runner-build when the Cloud
    // Run test-job image is assembled. Keep Vitest scoped to dashboard unit
    // and component tests so generated end-to-end specs are never collected.
    include: ['src/test/**/*.{test,spec}.{ts,tsx}'],
    setupFiles: './src/test/setup.ts',
    css: false,
  },
});
