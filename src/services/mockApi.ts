import { buildHealthSnapshot } from '../data/mockHealth';
import { mockInvestigations } from '../data/mockInvestigations';
import type {
  ApprovalState,
  ArtifactInfo,
  Classification,
  FailurePackage,
  Investigation,
  InvestigationStatus,
  ProcessingStage,
  ReleaseRisk,
  Severity,
  TimelineEvent,
} from '../types';
import { ApiError } from './apiTypes';
import type {
  ActionDecision,
  CreateInvestigationResponse,
  TriageZeroApi,
} from './apiTypes';

const CREATED_KEY = 'triagezero.created.v1';
const RETRY_KEY = 'triagezero.retries.v1';
const DECISION_KEY = 'triagezero.decisions.v1';

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const latency = () => sleep(200 + Math.random() * 250);

function readJson<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function writeJson(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // storage unavailable — demo state just won't persist
  }
}

interface StoredCreated {
  pkg: FailurePackage;
  id: string;
  createdAt: string;
}

// ---------------------------------------------------------------------------
// Synthesized analysis for user-submitted packages (demo mode).
// A deliberately simple, transparent heuristic standing in for Gemini.
// ---------------------------------------------------------------------------

interface SynthesizedAnalysis {
  classification: Classification;
  confidence: number;
  severity: Severity;
  releaseRisk: ReleaseRisk;
  summary: string;
  component: string;
  explanation: string;
  nextStep: string;
}

function synthesize(pkg: FailurePackage): SynthesizedAnalysis {
  const message = pkg.failure?.message ?? '';
  const server5xx = (pkg.network_evidence ?? []).find((n) => n.status >= 500);
  const netFailed = (pkg.network_evidence ?? []).find((n) => n.status === 0);

  if (server5xx) {
    return {
      classification: 'backend_application_defect',
      confidence: 0.93,
      severity: 'critical',
      releaseRisk: 'block_release',
      summary: `${server5xx.method} ${server5xx.url} returned HTTP ${server5xx.status} during "${pkg.test.name}". The server-side handler fails before the expected response is produced.`,
      component: `${pkg.repository.name} · API`,
      explanation:
        'Network evidence contains a deterministic 5xx response on the failing step while the test-side assertions and selectors are consistent with the captured page state.',
      nextStep: `Reproduce ${server5xx.method} ${server5xx.url} with the captured payload and inspect the server logs for the exception.`,
    };
  }
  if (netFailed || /ERR_NAME_NOT_RESOLVED|ECONNREFUSED/i.test(message)) {
    return {
      classification: 'environment_failure',
      confidence: 0.86,
      severity: 'low',
      releaseRisk: 'none',
      summary:
        'Requests failed at the connection level before reaching the application, matching an environment/networking outage signature.',
      component: `${pkg.environment.name} environment`,
      explanation:
        'Connection-level failures affected the run uniformly; no application code path produced the failure.',
      nextStep: 'Re-run the suite once the target environment is reachable.',
    };
  }
  if (/timeout/i.test(message) && (pkg.network_evidence ?? []).length === 0) {
    return {
      classification: 'test_automation_defect',
      confidence: 0.74,
      severity: 'medium',
      releaseRisk: 'low',
      summary:
        'The failure is a locator timeout with no correlated application error, which most often indicates selector drift or a timing-sensitive assertion in the test.',
      component: `${pkg.source} · ${pkg.test.file}`,
      explanation:
        'No failing network calls or console errors accompany the timeout; the application appears healthy in the captured evidence.',
      nextStep: 'Review the failing locator against the current DOM and prefer role-based selectors.',
    };
  }
  return {
    classification: 'unknown',
    confidence: 0.5,
    severity: 'medium',
    releaseRisk: 'moderate',
    summary:
      'The available evidence does not clearly match a known failure signature. Human review is recommended.',
    component: 'Undetermined',
    explanation:
      'Signals are insufficient or conflicting; confidence is below the automated-action threshold.',
    nextStep: 'Replay the Playwright trace and review the captured evidence manually.',
  };
}

// Demo-mode progression: a freshly created investigation advances through
// the pipeline based on its age, so the UI can show live movement.
const PHASES: Array<{ until: number; status: InvestigationStatus; stage: ProcessingStage }> = [
  { until: 4_000, status: 'received', stage: 'evidence_received' },
  { until: 10_000, status: 'queued', stage: 'evidence_received' },
  { until: 18_000, status: 'analyzing', stage: 'evidence_normalized' },
  { until: 26_000, status: 'analyzing', stage: 'classification_complete' },
  { until: 33_000, status: 'analyzing', stage: 'similarity_search' },
  { until: 39_000, status: 'analyzing', stage: 'risk_assessment' },
  { until: 45_000, status: 'analyzing', stage: 'action_recommendation' },
];

function phaseFor(ageMs: number): { status: InvestigationStatus; stage: ProcessingStage } {
  for (const p of PHASES) {
    if (ageMs < p.until) return { status: p.status, stage: p.stage };
  }
  return { status: 'completed', stage: 'action_recommendation' };
}

function timelineFor(createdAt: string, ageMs: number): TimelineEvent[] {
  const start = new Date(createdAt).getTime();
  const marks: Array<{ at: number; label: string }> = [
    { at: 0, label: 'Failure received' },
    { at: 2_000, label: 'Evidence validated' },
    { at: 5_000, label: 'Investigation queued' },
    { at: 11_000, label: 'Gemini analysis started' },
    { at: 26_000, label: 'Classification completed' },
    { at: 33_000, label: 'Similarity search completed' },
    { at: 39_000, label: 'Release risk calculated' },
    { at: 45_000, label: 'Recommendation produced' },
  ];
  return marks
    .filter((m) => ageMs >= m.at)
    .map((m, i) => ({
      id: `t${i}`,
      label: m.label,
      at: new Date(start + m.at).toISOString(),
    }));
}

function artifactsFromPackage(pkg: FailurePackage): ArtifactInfo[] {
  const out: ArtifactInfo[] = [];
  const a = pkg.artifacts ?? {};
  if (a.screenshot_path) {
    out.push({
      kind: 'screenshot',
      label: 'Failure screenshot',
      path: a.screenshot_path,
      sizeBytes: 240_000,
      available: true,
    });
  }
  if (a.trace_path) {
    out.push({
      kind: 'trace',
      label: 'Playwright trace',
      path: a.trace_path,
      sizeBytes: 4_100_000,
      available: true,
    });
  }
  if (a.video_path) {
    out.push({
      kind: 'video',
      label: 'Test video',
      path: a.video_path,
      sizeBytes: 8_800_000,
      available: true,
    });
  }
  return out;
}

function materialize(stored: StoredCreated): Investigation {
  const { pkg, id, createdAt } = stored;
  const ageMs = Date.now() - new Date(createdAt).getTime();
  const { status, stage } = phaseFor(ageMs);
  const done = status === 'completed';
  const analysis = synthesize(pkg);
  const needsReview = done && analysis.confidence < 0.6;

  const inv: Investigation = {
    id,
    status: needsReview ? 'needs_review' : status,
    stage,
    testName: pkg.test.name,
    testFile: pkg.test.file,
    repository: pkg.repository.name,
    branch: pkg.repository.branch,
    commitSha: pkg.repository.commit_sha,
    runId: pkg.run.run_id,
    browser: (['chromium', 'firefox', 'webkit'].includes(pkg.environment.browser)
      ? pkg.environment.browser
      : 'chromium') as Investigation['browser'],
    environment: (['local', 'staging', 'production'].includes(pkg.environment.name)
      ? pkg.environment.name
      : 'local') as Investigation['environment'],
    trigger: pkg.run.trigger,
    createdAt,
    evidence: {
      expected: pkg.failure.expected,
      actual: pkg.failure.actual,
      message: pkg.failure.message,
      stackTrace: pkg.failure.stack_trace,
      network: (pkg.network_evidence ?? []).map((n) => ({
        method: n.method,
        url: n.url,
        status: n.status,
      })),
      consoleErrors: pkg.console_errors ?? [],
      artifacts: artifactsFromPackage(pkg),
    },
    timeline: timelineFor(createdAt, ageMs),
    similarFailures: [],
    actionHistory: [],
  };

  if (done) {
    inv.completedAt = new Date(new Date(createdAt).getTime() + 45_000).toISOString();
    inv.elapsedMs = 45_000;
    inv.classification = analysis.classification;
    inv.confidence = analysis.confidence;
    inv.severity = analysis.severity;
    inv.releaseRisk = analysis.releaseRisk;
    inv.rootCause = {
      summary: analysis.summary,
      component: analysis.component,
      confidenceExplanation: analysis.explanation,
      nextStep: analysis.nextStep,
    };
    inv.actionTaken =
      analysis.releaseRisk === 'block_release'
        ? 'Release-block proposed — awaiting approval'
        : 'Recommendation produced';
    inv.recommendedAction = {
      action:
        analysis.releaseRisk === 'block_release'
          ? 'Create GitHub issue and flag release as blocked'
          : 'Create GitHub issue for the responsible component',
      rationale: analysis.explanation,
      issueTitle: `[TriageZero] ${pkg.test.name} — ${analysis.classification.replaceAll('_', ' ')}`,
      labels: ['triagezero', 'auto-triaged'],
      owner: analysis.component,
      approvalState: 'awaiting_approval',
    };
    inv.actionHistory = [
      {
        id: 'a1',
        at: inv.completedAt,
        actor: 'TriageZero agent',
        action: 'Proposed recommended action',
        state: 'awaiting_approval',
        note: 'Demo mode — actions are simulated and never executed externally',
      },
    ];
    inv.aiMetadata = {
      provider: 'deterministic',
      modelName: null,
      promptVersion: 'v1',
      analysisSchemaVersion: '1.0',
      durationMs: 45,
      inputTokens: null,
      outputTokens: null,
      fallbackReason: null,
      usedFallback: false,
      requiresHumanReview: analysis.confidence < 0.6,
      stageSummaries: [
        {
          stage: 'deterministic_rules',
          summary: `Matched evidence rules → ${analysis.classification} (confidence ${analysis.confidence.toFixed(2)}).`,
          durationMs: 45,
        },
      ],
      retrievalSignals: [],
    };
    inv.similarFailures = [
      {
        id: 'INV-1893',
        similarity: 0.81,
        testName: 'successful checkout shows confirmation page',
        classification: analysis.classification,
        rootCauseSummary: 'Closest match from the historical index (demo).',
        date: new Date(Date.now() - 9 * 24 * 3600_000).toISOString(),
        resolution: 'Resolved by the owning team.',
        issueRef: '#412',
      },
    ];
  }
  return inv;
}

function applyRetry(inv: Investigation): Investigation {
  const retries = readJson<Record<string, string>>(RETRY_KEY, {});
  const at = retries[inv.id];
  if (!at) return inv;
  const age = Date.now() - new Date(at).getTime();
  if (age > 45_000) return inv;
  const { status, stage } = phaseFor(Math.max(age, 10_001));
  return { ...inv, status, stage };
}

interface StoredDecision {
  state: ApprovalState;
  at: string;
}

function applyDecision(inv: Investigation): Investigation {
  const decisions = readJson<Record<string, StoredDecision>>(DECISION_KEY, {});
  const decision = decisions[inv.id];
  if (!decision || !inv.recommendedAction) return inv;
  return {
    ...inv,
    recommendedAction: { ...inv.recommendedAction, approvalState: decision.state },
    actionTaken:
      decision.state === 'approved'
        ? 'Approved — simulated locally in demo mode'
        : 'Recommendation rejected (demo mode)',
    actionHistory: [
      ...inv.actionHistory,
      {
        id: `local-${decision.at}`,
        at: decision.at,
        actor: 'you (demo)',
        action:
          decision.state === 'approved'
            ? 'Approved recommended action'
            : 'Rejected recommended action',
        state: decision.state,
        note: 'Recorded locally — demo mode never executes external actions',
      },
    ],
  };
}

function allInvestigations(): Investigation[] {
  const created = readJson<StoredCreated[]>(CREATED_KEY, []).map(materialize);
  return [...created, ...mockInvestigations]
    .map(applyRetry)
    .map(applyDecision)
    .sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1));
}

export const mockApi: TriageZeroApi = {
  async getHealth() {
    await latency();
    return buildHealthSnapshot();
  },

  async listInvestigations() {
    await latency();
    return allInvestigations();
  },

  async getInvestigation(id: string) {
    await latency();
    const found = allInvestigations().find((i) => i.id === id);
    if (!found) throw new ApiError(`Investigation ${id} not found`, 404);
    return found;
  },

  async createInvestigation(pkg: FailurePackage): Promise<CreateInvestigationResponse> {
    await latency();
    const created = readJson<StoredCreated[]>(CREATED_KEY, []);
    const id = `INV-${2100 + created.length + Math.floor(Math.random() * 40)}`;
    created.unshift({ pkg, id, createdAt: new Date().toISOString() });
    writeJson(CREATED_KEY, created.slice(0, 25));
    return { id, status: 'received' };
  },

  async retryInvestigation(id: string) {
    await latency();
    const created = readJson<StoredCreated[]>(CREATED_KEY, []);
    const own = created.find((c) => c.id === id);
    if (own) {
      own.createdAt = new Date().toISOString();
      writeJson(CREATED_KEY, created);
      return materialize(own);
    }
    const inv = mockInvestigations.find((i) => i.id === id);
    if (!inv) throw new ApiError(`Investigation ${id} not found`, 404);
    const retries = readJson<Record<string, string>>(RETRY_KEY, {});
    retries[id] = new Date().toISOString();
    writeJson(RETRY_KEY, retries);
    return applyRetry(inv);
  },

  async decideAction(id: string, decision: ActionDecision) {
    await latency();
    const inv = allInvestigations().find((i) => i.id === id);
    if (!inv) throw new ApiError(`Investigation ${id} not found`, 404);
    if (!inv.recommendedAction) {
      throw new ApiError(`Investigation ${id} has no recommended action`, 409);
    }
    const decisions = readJson<Record<string, StoredDecision>>(DECISION_KEY, {});
    decisions[id] = {
      state: decision === 'approve' ? 'approved' : 'rejected',
      at: new Date().toISOString(),
    };
    writeJson(DECISION_KEY, decisions);
    return applyDecision(inv);
  },
};
