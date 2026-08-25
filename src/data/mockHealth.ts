import type { SystemHealthSnapshot } from '../types';

export function buildHealthSnapshot(): SystemHealthSnapshot {
  const now = Date.now();
  const ago = (s: number) => new Date(now - s * 1000).toISOString();
  const jitter = (base: number, spread: number) =>
    Math.round(base + (Math.random() - 0.5) * spread);

  return {
    overall: 'degraded',
    queueDepth: 3,
    workerThroughputPerMin: 2.4,
    ingestionLastHour: 9,
    ingestionVolume: [
      { label: '-6h', count: 4 },
      { label: '-5h', count: 7 },
      { label: '-4h', count: 3 },
      { label: '-3h', count: 8 },
      { label: '-2h', count: 5 },
      { label: '-1h', count: 11 },
      { label: 'now', count: 9 },
    ],
    services: [
      {
        id: 'ingestion-api',
        name: 'Ingestion API',
        status: 'healthy',
        latencyMs: jitter(42, 14),
        lastCheck: ago(18),
        region: 'us-central1',
        detail: 'Accepting failure packages on /api/v1/investigations',
      },
      {
        id: 'worker',
        name: 'Investigation Worker',
        status: 'healthy',
        latencyMs: jitter(180, 40),
        lastCheck: ago(24),
        region: 'us-central1',
        detail: '2 workers polling; median investigation 2.7m',
      },
      {
        id: 'gemini',
        name: 'Gemini',
        status: 'healthy',
        latencyMs: jitter(890, 220),
        lastCheck: ago(31),
        region: 'us-central1',
        detail: 'gemini-2.0 · classification + root-cause analysis',
      },
      {
        id: 'adk',
        name: 'Google ADK',
        status: 'healthy',
        latencyMs: jitter(120, 30),
        lastCheck: ago(31),
        region: 'us-central1',
        detail: 'Agent runtime orchestrating investigation steps',
      },
      {
        id: 'pubsub',
        name: 'Pub/Sub',
        status: 'degraded',
        latencyMs: jitter(2400, 600),
        lastCheck: ago(12),
        region: 'us-central1',
        detail: 'Elevated publish latency on failure-intake topic',
      },
      {
        id: 'firestore',
        name: 'Firestore',
        status: 'healthy',
        latencyMs: jitter(28, 10),
        lastCheck: ago(15),
        region: 'us-central1',
        detail: 'Investigation store · nam5 multi-region',
      },
      {
        id: 'storage',
        name: 'Cloud Storage',
        status: 'healthy',
        latencyMs: jitter(65, 20),
        lastCheck: ago(20),
        region: 'us-central1',
        detail: 'Artifact bucket · 30-day retention',
      },
      {
        id: 'github',
        name: 'GitHub Integration',
        status: 'disabled',
        lastCheck: ago(3600),
        region: '—',
        detail: 'Issue creation not yet connected in this build',
      },
    ],
    events: [
      {
        id: 'e1',
        at: ago(240),
        level: 'warn',
        message: 'Pub/Sub publish latency above 2s for failure-intake topic',
      },
      {
        id: 'e2',
        at: ago(700),
        level: 'info',
        message: 'Investigation INV-2041 completed — release flagged as blocked',
      },
      {
        id: 'e3',
        at: ago(1500),
        level: 'info',
        message: 'Worker pool scaled 1 → 2 after queue depth exceeded 5',
      },
      {
        id: 'e4',
        at: ago(4200),
        level: 'error',
        message: 'Investigation INV-2036 failed — analysis worker timeout',
      },
      {
        id: 'e5',
        at: ago(6600),
        level: 'info',
        message: 'Nightly similarity-index refresh completed (1,204 embeddings)',
      },
    ],
    incident: {
      title: 'Pub/Sub latency',
      message:
        'Intake events are delayed up to ~30s. Investigations still complete; no data loss.',
      level: 'warn',
    },
  };
}
