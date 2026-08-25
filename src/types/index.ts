export type EnvironmentName = 'local' | 'staging' | 'production';

export type InvestigationStatus =
  | 'received'
  | 'queued'
  | 'analyzing'
  | 'completed'
  | 'failed'
  | 'needs_review';

export type Classification =
  | 'backend_application_defect'
  | 'frontend_application_defect'
  | 'test_automation_defect'
  | 'environment_failure'
  | 'data_integrity_defect'
  | 'performance_timing_defect'
  | 'dependency_failure'
  | 'unknown';

export type Severity = 'critical' | 'high' | 'medium' | 'low';

export type ReleaseRisk = 'block_release' | 'high' | 'moderate' | 'low' | 'none';

export type ProcessingStage =
  | 'evidence_received'
  | 'evidence_normalized'
  | 'classification_complete'
  | 'similarity_search'
  | 'risk_assessment'
  | 'action_recommendation';

export type ApprovalState =
  | 'proposed'
  | 'awaiting_approval'
  | 'approved'
  | 'executed'
  | 'rejected';

export type BrowserName = 'chromium' | 'firefox' | 'webkit';

export interface NetworkEntry {
  method: string;
  url: string;
  status: number;
  durationMs?: number;
  requestHeaders?: Record<string, string>;
  responseSummary?: string;
}

export type ArtifactKind =
  | 'screenshot'
  | 'trace'
  | 'video'
  | 'console_log'
  | 'network_log';

export interface ArtifactInfo {
  kind: ArtifactKind;
  label: string;
  path: string;
  sizeBytes: number;
  available: boolean;
}

export interface TimelineEvent {
  id: string;
  label: string;
  at: string;
  detail?: string;
}

export interface SimilarFailure {
  id: string;
  similarity: number; // 0..1
  testName: string;
  classification: Classification;
  rootCauseSummary: string;
  date: string;
  resolution: string;
  issueRef?: string;
}

export interface RecommendedAction {
  action: string;
  rationale: string;
  issueTitle: string;
  labels: string[];
  owner: string;
  approvalState: ApprovalState;
}

export interface ActionRecord {
  id: string;
  at: string;
  actor: string;
  action: string;
  state: ApprovalState;
  note?: string;
}

export interface RootCause {
  summary: string;
  component: string;
  confidenceExplanation: string;
  nextStep: string;
}

export interface Evidence {
  expected: string;
  actual: string;
  message: string;
  stackTrace: string;
  network: NetworkEntry[];
  consoleErrors: string[];
  artifacts: ArtifactInfo[];
}

export interface Investigation {
  id: string;
  status: InvestigationStatus;
  stage: ProcessingStage;
  testName: string;
  testFile: string;
  repository: string;
  branch: string;
  commitSha: string;
  runId: string;
  runUrl?: string;
  browser: BrowserName;
  environment: EnvironmentName;
  trigger: string;
  createdAt: string;
  completedAt?: string;
  elapsedMs?: number;
  classification?: Classification;
  confidence?: number; // 0..1
  severity?: Severity;
  releaseRisk?: ReleaseRisk;
  rootCause?: RootCause;
  evidence: Evidence;
  timeline: TimelineEvent[];
  similarFailures: SimilarFailure[];
  recommendedAction?: RecommendedAction;
  actionHistory: ActionRecord[];
  actionTaken?: string;
}

export interface FailurePackage {
  schema_version: string;
  source: string;
  run: {
    run_id: string;
    trigger: string;
    started_at: string;
  };
  repository: {
    name: string;
    branch: string;
    commit_sha: string;
  };
  environment: {
    name: string;
    target_url: string;
    browser: string;
  };
  test: {
    name: string;
    file: string;
    status: string;
    retry: number;
  };
  failure: {
    expected: string;
    actual: string;
    message: string;
    stack_trace: string;
  };
  network_evidence?: Array<{
    method: string;
    url: string;
    status: number;
  }>;
  console_errors?: string[];
  artifacts?: {
    screenshot_path?: string;
    trace_path?: string;
    video_path?: string;
  };
}

export type ServiceStatus = 'healthy' | 'degraded' | 'offline' | 'disabled';

export interface ServiceHealth {
  id: string;
  name: string;
  status: ServiceStatus;
  latencyMs?: number;
  lastCheck: string;
  region: string;
  detail: string;
}

export type EventLevel = 'info' | 'warn' | 'error';

export interface SystemEvent {
  id: string;
  at: string;
  level: EventLevel;
  message: string;
}

export interface SystemHealthSnapshot {
  overall: ServiceStatus;
  services: ServiceHealth[];
  queueDepth: number;
  workerThroughputPerMin: number;
  ingestionLastHour: number;
  ingestionVolume: Array<{ label: string; count: number }>;
  events: SystemEvent[];
  incident?: { title: string; message: string; level: 'warn' | 'error' };
}

export type ThemeName = 'dark' | 'light';

export interface NotificationPrefs {
  blockRelease: boolean;
  needsReview: boolean;
  completed: boolean;
}

export interface AppSettings {
  theme: ThemeName;
  defaultEnvironment: EnvironmentName;
  refreshIntervalSec: number;
  notifications: NotificationPrefs;
  confirmDangerousActions: boolean;
}
