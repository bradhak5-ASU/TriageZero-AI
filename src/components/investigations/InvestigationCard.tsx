import { Link } from 'react-router-dom';
import { GitBranch, Globe } from 'lucide-react';
import type { Investigation } from '../../types';
import { formatConfidence, formatRelativeTime } from '../../utils/format';
import {
  ClassificationBadge,
  InvestigationStatusBadge,
  RiskBadge,
  SeverityBadge,
} from '../ui/StatusBadge';

export function InvestigationCard({ inv }: { inv: Investigation }) {
  return (
    <Link
      to={`/investigations/${inv.id}`}
      className="card"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        padding: 14,
        color: 'inherit',
        textDecoration: 'none',
      }}
      aria-label={`Open investigation ${inv.id}: ${inv.testName}`}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <InvestigationStatusBadge status={inv.status} />
        <span className="cell-sub mono">{inv.id}</span>
      </div>
      <div className="cell-main" style={{ fontSize: 13.5 }}>
        {inv.testName}
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        <ClassificationBadge value={inv.classification} />
        <SeverityBadge value={inv.severity} />
        <RiskBadge value={inv.releaseRisk} />
      </div>
      <div className="kpi__meta" style={{ justifyContent: 'space-between' }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
          <GitBranch size={11} aria-hidden />
          <span className="mono">{inv.repository}</span>
        </span>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
          <Globe size={11} aria-hidden />
          {inv.environment}
        </span>
        <span>conf {formatConfidence(inv.confidence)}</span>
        <span>{formatRelativeTime(inv.createdAt)}</span>
      </div>
    </Link>
  );
}
