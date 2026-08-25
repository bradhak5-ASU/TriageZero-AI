import type {
  ApprovalState,
  Classification,
  InvestigationStatus,
  ProcessingStage,
  ReleaseRisk,
  ServiceStatus,
  Severity,
} from '../types';

// tone maps onto the design-token status palette
export type Tone = 'ok' | 'warn' | 'crit' | 'info' | 'ai' | 'muted';

export interface Meta {
  label: string;
  tone: Tone;
}

export const STATUS_META: Record<InvestigationStatus, Meta> = {
  received: { label: 'Received', tone: 'muted' },
  queued: { label: 'Queued', tone: 'info' },
  analyzing: { label: 'Analyzing', tone: 'ai' },
  completed: { label: 'Completed', tone: 'ok' },
  failed: { label: 'Failed', tone: 'crit' },
  needs_review: { label: 'Needs Review', tone: 'warn' },
};

export const CLASSIFICATION_META: Record<Classification, Meta> = {
  backend_application_defect: { label: 'Backend Defect', tone: 'crit' },
  frontend_application_defect: { label: 'Frontend Defect', tone: 'warn' },
  test_automation_defect: { label: 'Test Automation', tone: 'info' },
  environment_failure: { label: 'Environment', tone: 'muted' },
  data_integrity_defect: { label: 'Data Integrity', tone: 'crit' },
  performance_timing_defect: { label: 'Performance / Timing', tone: 'warn' },
  dependency_failure: { label: 'Dependency', tone: 'warn' },
  unknown: { label: 'Unknown', tone: 'muted' },
};

export const SEVERITY_META: Record<Severity, Meta> = {
  critical: { label: 'Critical', tone: 'crit' },
  high: { label: 'High', tone: 'warn' },
  medium: { label: 'Medium', tone: 'info' },
  low: { label: 'Low', tone: 'muted' },
};

export const RISK_META: Record<ReleaseRisk, Meta> = {
  block_release: { label: 'Block Release', tone: 'crit' },
  high: { label: 'High Risk', tone: 'warn' },
  moderate: { label: 'Moderate', tone: 'info' },
  low: { label: 'Low', tone: 'ok' },
  none: { label: 'None', tone: 'muted' },
};

export const STAGE_META: Record<ProcessingStage, string> = {
  evidence_received: 'Evidence received',
  evidence_normalized: 'Evidence normalized',
  classification_complete: 'Classification complete',
  similarity_search: 'Similarity search',
  risk_assessment: 'Risk assessment',
  action_recommendation: 'Action recommendation',
};

export const STAGE_ORDER: ProcessingStage[] = [
  'evidence_received',
  'evidence_normalized',
  'classification_complete',
  'similarity_search',
  'risk_assessment',
  'action_recommendation',
];

export const APPROVAL_META: Record<ApprovalState, Meta> = {
  proposed: { label: 'Proposed', tone: 'info' },
  awaiting_approval: { label: 'Awaiting Approval', tone: 'warn' },
  approved: { label: 'Approved', tone: 'ok' },
  executed: { label: 'Executed', tone: 'ok' },
  rejected: { label: 'Rejected', tone: 'muted' },
};

export const SERVICE_STATUS_META: Record<ServiceStatus, Meta> = {
  healthy: { label: 'Healthy', tone: 'ok' },
  degraded: { label: 'Degraded', tone: 'warn' },
  offline: { label: 'Offline', tone: 'crit' },
  disabled: { label: 'Disabled', tone: 'muted' },
};

export function stageProgress(stage: ProcessingStage): number {
  const idx = STAGE_ORDER.indexOf(stage);
  return (idx + 1) / STAGE_ORDER.length;
}

export function confidenceTone(value?: number): Tone {
  if (value == null) return 'muted';
  if (value >= 0.85) return 'ok';
  if (value >= 0.6) return 'warn';
  return 'crit';
}
