import { useCallback, useEffect, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  Gauge,
  Inbox,
  Info,
  RefreshCw,
  XCircle,
} from 'lucide-react';
import { config } from '../app/config';
import { ColumnsChart } from '../components/charts/ColumnsChart';
import { ErrorState, LoadingState } from '../components/ui/States';
import { ServiceStatusBadge } from '../components/ui/StatusBadge';
import { api } from '../services';
import type { EventLevel, SystemHealthSnapshot } from '../types';
import { formatDuration, formatRelativeTime } from '../utils/format';

const levelIcons: Record<EventLevel, React.ReactNode> = {
  info: <Info size={14} style={{ color: 'var(--info)' }} aria-hidden />,
  warn: <AlertTriangle size={14} style={{ color: 'var(--warn)' }} aria-hidden />,
  error: <XCircle size={14} style={{ color: 'var(--crit)' }} aria-hidden />,
};

export function SystemHealth() {
  const [snapshot, setSnapshot] = useState<SystemHealthSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setSnapshot(await api.getHealth());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load system health');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (error && !snapshot) {
    return (
      <div className="card">
        <ErrorState message={error} onRetry={() => void load()} />
      </div>
    );
  }

  if (!snapshot) {
    return (
      <div className="card">
        <LoadingState rows={8} />
      </div>
    );
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1>System Health</h1>
          <p className="sub">
            Overall: <ServiceStatusBadge value={snapshot.overall} />
            {config.useMockApi && (
              <span className="badge badge--ai">Demo data — services not yet deployed</span>
            )}
          </p>
        </div>
        <div className="header-actions">
          <button type="button" className="btn" onClick={() => void load()} disabled={loading}>
            <RefreshCw size={14} aria-hidden />
            Refresh
          </button>
        </div>
      </div>

      {snapshot.incident && (
        <div
          className="card"
          role="status"
          style={{
            marginBottom: 16,
            borderColor: `color-mix(in srgb, var(--${snapshot.incident.level}) 40%, var(--border))`,
          }}
        >
          <div className="card__body" style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
            <AlertTriangle
              size={16}
              style={{ color: `var(--${snapshot.incident.level})`, flexShrink: 0, marginTop: 1 }}
              aria-hidden
            />
            <div>
              <strong style={{ fontSize: 13.5 }}>Active incident: {snapshot.incident.title}</strong>
              <p className="muted" style={{ fontSize: 13, marginTop: 2 }}>
                {snapshot.incident.message}
              </p>
            </div>
          </div>
        </div>
      )}

      <div className="kpi-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))' }}>
        <div className="card kpi">
          <div className="kpi__top">
            <span>Ingestion (last hour)</span>
            <Inbox size={15} aria-hidden style={{ color: 'var(--accent)' }} />
          </div>
          <div className="kpi__value">{snapshot.ingestionLastHour}</div>
          <div className="kpi__meta">failure packages received</div>
        </div>
        <div className="card kpi">
          <div className="kpi__top">
            <span>Queue depth</span>
            <Activity size={15} aria-hidden style={{ color: 'var(--warn)' }} />
          </div>
          <div className="kpi__value">{snapshot.queueDepth}</div>
          <div className="kpi__meta">investigations waiting</div>
        </div>
        <div className="card kpi">
          <div className="kpi__top">
            <span>Worker throughput</span>
            <Gauge size={15} aria-hidden style={{ color: 'var(--ok)' }} />
          </div>
          <div className="kpi__value">{snapshot.workerThroughputPerMin}/min</div>
          <div className="kpi__meta">completed investigations</div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card__header">
          <h2>Service status</h2>
        </div>
        <div className="table-wrap">
          <table className="data" style={{ minWidth: 680 }}>
            <thead>
              <tr>
                <th scope="col">Service</th>
                <th scope="col">Status</th>
                <th scope="col">Latency</th>
                <th scope="col">Last check</th>
                <th scope="col">Region</th>
                <th scope="col">Detail</th>
              </tr>
            </thead>
            <tbody>
              {snapshot.services.map((s) => (
                <tr key={s.id}>
                  <td className="cell-main">{s.name}</td>
                  <td>
                    <ServiceStatusBadge value={s.status} />
                  </td>
                  <td className="mono muted">{s.latencyMs != null ? formatDuration(s.latencyMs) : '—'}</td>
                  <td className="muted" style={{ whiteSpace: 'nowrap' }}>
                    {formatRelativeTime(s.lastCheck)}
                  </td>
                  <td className="mono muted">{s.region}</td>
                  <td className="muted" style={{ maxWidth: 320 }}>{s.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="section-grid" style={{ gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)' }} data-collapse="stack">
        <div className="card">
          <div className="card__header">
            <h2>Recent ingestion volume</h2>
          </div>
          <div className="card__body">
            <ColumnsChart data={snapshot.ingestionVolume} ariaLabel="Failure packages received per hour" />
          </div>
        </div>
        <div className="card">
          <div className="card__header">
            <h2>Recent system events</h2>
          </div>
          <div className="card__body card__body--flush">
            <ul style={{ listStyle: 'none', margin: 0, padding: '6px 0' }}>
              {snapshot.events.map((e) => (
                <li
                  key={e.id}
                  style={{
                    display: 'flex',
                    gap: 10,
                    alignItems: 'flex-start',
                    padding: '9px 16px',
                    borderBottom: '1px solid var(--border)',
                    fontSize: 13,
                  }}
                >
                  {levelIcons[e.level]}
                  <span style={{ flex: 1 }}>{e.message}</span>
                  <span className="faint" style={{ whiteSpace: 'nowrap', fontSize: 12 }}>
                    {formatRelativeTime(e.at)}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </>
  );
}
