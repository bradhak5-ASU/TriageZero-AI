import {
  Activity,
  AlertOctagon,
  AlertTriangle,
  CheckCircle2,
  CircleDashed,
  CircleDot,
  Clock,
  Eye,
  HelpCircle,
  MinusCircle,
  ShieldAlert,
  Sparkles,
  XCircle,
} from 'lucide-react';
import type {
  ApprovalState,
  Classification,
  InvestigationStatus,
  ReleaseRisk,
  ServiceStatus,
  Severity,
} from '../../types';
import {
  APPROVAL_META,
  CLASSIFICATION_META,
  RISK_META,
  SERVICE_STATUS_META,
  SEVERITY_META,
  STATUS_META,
  type Meta,
} from '../../utils/labels';

// every badge pairs color with an icon so state is never color-only
function BaseBadge({ meta, icon }: { meta: Meta; icon?: React.ReactNode }) {
  return (
    <span className={`badge badge--${meta.tone}`}>
      {icon}
      {meta.label}
    </span>
  );
}

const statusIcons: Record<InvestigationStatus, React.ReactNode> = {
  received: <CircleDashed size={12} aria-hidden />,
  queued: <Clock size={12} aria-hidden />,
  analyzing: <Sparkles size={12} aria-hidden />,
  completed: <CheckCircle2 size={12} aria-hidden />,
  failed: <XCircle size={12} aria-hidden />,
  needs_review: <Eye size={12} aria-hidden />,
};

export function InvestigationStatusBadge({ status }: { status: InvestigationStatus }) {
  return <BaseBadge meta={STATUS_META[status]} icon={statusIcons[status]} />;
}

export function ClassificationBadge({ value }: { value?: Classification }) {
  if (!value) return <span className="badge badge--muted">Pending</span>;
  return <BaseBadge meta={CLASSIFICATION_META[value]} icon={<CircleDot size={12} aria-hidden />} />;
}

const severityIcons: Record<Severity, React.ReactNode> = {
  critical: <AlertOctagon size={12} aria-hidden />,
  high: <AlertTriangle size={12} aria-hidden />,
  medium: <Activity size={12} aria-hidden />,
  low: <MinusCircle size={12} aria-hidden />,
};

export function SeverityBadge({ value }: { value?: Severity }) {
  if (!value) return <span className="badge badge--muted">—</span>;
  return <BaseBadge meta={SEVERITY_META[value]} icon={severityIcons[value]} />;
}

const riskIcons: Record<ReleaseRisk, React.ReactNode> = {
  block_release: <ShieldAlert size={12} aria-hidden />,
  high: <AlertTriangle size={12} aria-hidden />,
  moderate: <Activity size={12} aria-hidden />,
  low: <CheckCircle2 size={12} aria-hidden />,
  none: <MinusCircle size={12} aria-hidden />,
};

export function RiskBadge({ value }: { value?: ReleaseRisk }) {
  if (!value) return <span className="badge badge--muted">—</span>;
  return <BaseBadge meta={RISK_META[value]} icon={riskIcons[value]} />;
}

export function ApprovalBadge({ value }: { value: ApprovalState }) {
  const icons: Record<ApprovalState, React.ReactNode> = {
    proposed: <CircleDot size={12} aria-hidden />,
    awaiting_approval: <Clock size={12} aria-hidden />,
    approved: <CheckCircle2 size={12} aria-hidden />,
    executed: <CheckCircle2 size={12} aria-hidden />,
    rejected: <XCircle size={12} aria-hidden />,
  };
  return <BaseBadge meta={APPROVAL_META[value]} icon={icons[value]} />;
}

export function ServiceStatusBadge({ value }: { value: ServiceStatus }) {
  const icons: Record<ServiceStatus, React.ReactNode> = {
    healthy: <CheckCircle2 size={12} aria-hidden />,
    degraded: <AlertTriangle size={12} aria-hidden />,
    offline: <XCircle size={12} aria-hidden />,
    disabled: <HelpCircle size={12} aria-hidden />,
  };
  return <BaseBadge meta={SERVICE_STATUS_META[value]} icon={icons[value]} />;
}
