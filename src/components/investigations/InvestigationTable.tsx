import { useNavigate } from 'react-router-dom';
import type { Investigation } from '../../types';
import { formatConfidence, formatRelativeTime } from '../../utils/format';
import {
  ClassificationBadge,
  InvestigationStatusBadge,
  RiskBadge,
  SeverityBadge,
} from '../ui/StatusBadge';

interface InvestigationTableProps {
  items: Investigation[];
  dense?: boolean;
}

export function InvestigationTable({ items, dense = false }: InvestigationTableProps) {
  const navigate = useNavigate();

  const open = (id: string) => navigate(`/investigations/${id}`);

  return (
    <div className="table-wrap">
      <table className="data">
        <thead>
          <tr>
            <th scope="col">Status</th>
            <th scope="col">Test</th>
            <th scope="col">Classification</th>
            <th scope="col">Confidence</th>
            <th scope="col">Severity</th>
            <th scope="col">Release risk</th>
            {!dense && <th scope="col">Repository</th>}
            <th scope="col">Created</th>
            {!dense && <th scope="col">Action taken</th>}
          </tr>
        </thead>
        <tbody>
          {items.map((inv) => (
            <tr
              key={inv.id}
              className="rowlink"
              tabIndex={0}
              onClick={() => open(inv.id)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  open(inv.id);
                }
              }}
              aria-label={`Open investigation ${inv.id}: ${inv.testName}`}
            >
              <td>
                <InvestigationStatusBadge status={inv.status} />
              </td>
              <td style={{ minWidth: 220 }}>
                <div className="cell-main">{inv.testName}</div>
                <div className="cell-sub mono">{inv.id}</div>
              </td>
              <td>
                <ClassificationBadge value={inv.classification} />
              </td>
              <td className="mono">{formatConfidence(inv.confidence)}</td>
              <td>
                <SeverityBadge value={inv.severity} />
              </td>
              <td>
                <RiskBadge value={inv.releaseRisk} />
              </td>
              {!dense && (
                <td>
                  <span className="mono muted">{inv.repository}</span>
                </td>
              )}
              <td className="muted" style={{ whiteSpace: 'nowrap' }}>
                {formatRelativeTime(inv.createdAt)}
              </td>
              {!dense && (
                <td className="muted" style={{ maxWidth: 200 }}>
                  {inv.actionTaken ?? '—'}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
