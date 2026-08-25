import { useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  Activity,
  ArrowRight,
  BrainCircuit,
  CheckCheck,
  GitBranch,
  GitCommitHorizontal,
  Globe,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  Timer,
  Zap,
} from 'lucide-react';
import { useInvestigations } from '../context/InvestigationsContext';
import { useSettings } from '../context/SettingsContext';
import { BarList } from '../components/charts/BarList';
import { ColumnsChart } from '../components/charts/ColumnsChart';
import { StackBar } from '../components/charts/StackBar';
import { InvestigationTable } from '../components/investigations/InvestigationTable';
import { KpiCard } from '../components/ui/KpiCard';
import { EmptyState, ErrorState, LoadingState } from '../components/ui/States';
import {
  ClassificationBadge,
  InvestigationStatusBadge,
  RiskBadge,
  SeverityBadge,
} from '../components/ui/StatusBadge';
import { topFailingComponents, weeklyTrend } from '../data/mockInvestigations';
import {
  formatConfidence,
  formatDuration,
  formatRelativeTime,
  shortSha,
} from '../utils/format';
import { CLASSIFICATION_META, STAGE_META, stageProgress } from '../utils/labels';
import type { Classification, ReleaseRisk } from '../types';

const ACTIVE_STATUSES = ['received', 'queued', 'analyzing'] as const;

export function CommandCenter() {
  const { items, loading, error, lastUpdated, refresh } = useInvestigations();
  const { environment } = useSettings();
  const navigate = useNavigate();

  const stats = useMemo(() => {
    const startOfDay = new Date();
    startOfDay.setHours(0, 0, 0, 0);
    const today = items.filter((i) => new Date(i.createdAt) >= startOfDay);
    const processing = items.filter((i) =>
      (ACTIVE_STATUSES as readonly string[]).includes(i.status),
    );
    const blockers = items.filter((i) => i.releaseRisk === 'block_release');
    const confidences = items.map((i) => i.confidence).filter((c): c is number => c != null);
    const avgConfidence =
      confidences.length > 0
        ? confidences.reduce((a, b) => a + b, 0) / confidences.length
        : undefined;
    const times = items.map((i) => i.elapsedMs).filter((t): t is number => t != null);
    const meanTime =
      times.length > 0 ? times.reduce((a, b) => a + b, 0) / times.length : undefined;
    const executed = items.reduce(
      (sum, i) => sum + i.actionHistory.filter((a) => a.state === 'executed').length,
      0,
    );
    return { today, processing, blockers, avgConfidence, meanTime, executed };
  }, [items]);

  const featured = useMemo(
    () =>
      items.find(
        (i) =>
          i.releaseRisk === 'block_release' ||
          (i.severity === 'critical' && i.status === 'completed'),
      ),
    [items],
  );

  const queue = useMemo(
    () => items.filter((i) => (ACTIVE_STATUSES as readonly string[]).includes(i.status)),
    [items],
  );

  const recent = useMemo(() => items.slice(0, 8), [items]);

  const classificationCounts = useMemo(() => {
    const counts = new Map<Classification, number>();
    for (const i of items) {
      if (i.classification) {
        counts.set(i.classification, (counts.get(i.classification) ?? 0) + 1);
      }
    }
    return [...counts.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([cls, count]) => ({ name: CLASSIFICATION_META[cls].label, count }));
  }, [items]);

  const riskSegments = useMemo(() => {
    const order: Array<{ key: ReleaseRisk; name: string; color: string }> = [
      { key: 'block_release', name: 'Block release', color: 'var(--crit)' },
      { key: 'high', name: 'High', color: 'var(--warn)' },
      { key: 'moderate', name: 'Moderate', color: 'var(--info)' },
      { key: 'low', name: 'Low', color: 'var(--ok)' },
      { key: 'none', name: 'None', color: 'var(--text-faint)' },
    ];
    return order.map((o) => ({
      name: o.name,
      color: o.color,
      count: items.filter((i) => i.releaseRisk === o.key).length,
    }));
  }, [items]);

  if (error && items.length === 0) {
    return (
      <div className="card">
        <ErrorState message={error} onRetry={() => void refresh()} />
      </div>
    );
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Command Center</h1>
          <p className="sub">
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
              <Globe size={13} aria-hidden /> {environment}
            </span>
            <span aria-hidden>·</span>
            <span>
              Last updated{' '}
              {lastUpdated ? formatRelativeTime(new Date(lastUpdated).toISOString()) : '—'}
            </span>
            <span className="health-pill">
              <span className="pulse pulse--ok" aria-hidden />
              Live
            </span>
          </p>
        </div>
        <div className="header-actions">
          <button type="button" className="btn" onClick={() => void refresh()} disabled={loading}>
            <RefreshCw size={14} aria-hidden className={loading ? 'spin' : undefined} />
            Refresh
          </button>
          <Link to="/ingest" className="btn btn--primary" style={{ textDecoration: 'none' }}>
            <Zap size={14} aria-hidden />
            Ingest failure
          </Link>
        </div>
      </div>

      <div className="kpi-grid">
        <KpiCard
          label="Investigations today"
          value={String(stats.today.length)}
          caption="since midnight"
          tooltip="Failure packages received and investigated since local midnight."
          icon={<Activity size={15} aria-hidden style={{ color: 'var(--accent)' }} />}
          trend={{ direction: 'up', text: '+3', positive: false }}
        />
        <KpiCard
          label="Currently processing"
          value={String(stats.processing.length)}
          caption="in pipeline"
          tooltip="Investigations currently received, queued, or under analysis."
          icon={<Sparkles size={15} aria-hidden style={{ color: 'var(--ai)' }} />}
          trend={{ direction: 'flat', text: 'steady' }}
        />
        <KpiCard
          label="Block-release failures"
          value={String(stats.blockers.length)}
          caption="require sign-off"
          tooltip="Open investigations whose release risk is assessed as block_release."
          icon={<ShieldAlert size={15} aria-hidden style={{ color: 'var(--crit)' }} />}
          trend={{ direction: 'up', text: '+1', positive: false }}
        />
        <KpiCard
          label="Average confidence"
          value={formatConfidence(stats.avgConfidence)}
          caption="across classified"
          tooltip="Mean model confidence across investigations with a classification."
          icon={<BrainCircuit size={15} aria-hidden style={{ color: 'var(--ai)' }} />}
          trend={{ direction: 'up', text: '+2pts', positive: true }}
        />
        <KpiCard
          label="Mean investigation time"
          value={formatDuration(stats.meanTime)}
          caption="receipt → recommendation"
          tooltip="Average wall-clock time from failure receipt to recommendation."
          icon={<Timer size={15} aria-hidden style={{ color: 'var(--info)' }} />}
          trend={{ direction: 'down', text: '-14s', positive: true }}
        />
        <KpiCard
          label="Automated actions"
          value={String(stats.executed)}
          caption="executed after approval"
          tooltip="Actions executed by the agent after passing the approval policy."
          icon={<CheckCheck size={15} aria-hidden style={{ color: 'var(--ok)' }} />}
          trend={{ direction: 'up', text: '+2', positive: true }}
        />
      </div>

      {featured && (
        <div
          className="card"
          style={{
            borderColor: 'color-mix(in srgb, var(--crit) 35%, var(--border))',
            marginBottom: 16,
          }}
        >
          <div className="card__header">
            <h2>
              <ShieldAlert size={16} style={{ color: 'var(--crit)' }} aria-hidden />
              Latest critical failure
            </h2>
            <InvestigationStatusBadge status={featured.status} />
          </div>
          <div className="card__body" style={{ display: 'grid', gap: 14 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
              <div style={{ minWidth: 0 }}>
                <div className="cell-main" style={{ fontSize: 15 }}>
                  {featured.testName}
                </div>
                <div className="cell-sub" style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 6 }}>
                  <span className="mono" style={{ display: 'inline-flex', gap: 4, alignItems: 'center' }}>
                    <GitBranch size={12} aria-hidden />
                    {featured.repository} · {featured.branch}
                  </span>
                  <span className="mono" style={{ display: 'inline-flex', gap: 4, alignItems: 'center' }}>
                    <GitCommitHorizontal size={12} aria-hidden />
                    {shortSha(featured.commitSha)}
                  </span>
                  <span>received {formatRelativeTime(featured.createdAt)}</span>
                </div>
              </div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'flex-start' }}>
                <ClassificationBadge value={featured.classification} />
                <SeverityBadge value={featured.severity} />
                <RiskBadge value={featured.releaseRisk} />
                <span className="badge badge--ai">conf {formatConfidence(featured.confidence)}</span>
              </div>
            </div>
            {featured.rootCause && (
              <p className="muted" style={{ fontSize: 13.5, maxWidth: 860 }}>
                {featured.rootCause.summary}
              </p>
            )}
            <div>
              <button
                type="button"
                className="btn btn--primary"
                onClick={() => navigate(`/investigations/${featured.id}`)}
              >
                Open investigation
                <ArrowRight size={14} aria-hidden />
              </button>
            </div>
          </div>
        </div>
      )}

      <div
        className="section-grid"
        style={{ gridTemplateColumns: 'minmax(0, 2fr) minmax(0, 1fr)', marginBottom: 16 }}
        data-collapse="stack"
      >
        <div className="card">
          <div className="card__header">
            <h2>Recent investigations</h2>
            <Link to="/investigations" style={{ fontSize: 12.5, fontWeight: 600 }}>
              View all
            </Link>
          </div>
          {loading && items.length === 0 ? (
            <LoadingState rows={5} />
          ) : recent.length === 0 ? (
            <EmptyState
              title="No investigations yet"
              message="Submit a failure package from the Ingest page to see TriageZero at work."
            />
          ) : (
            <InvestigationTable items={recent} dense />
          )}
        </div>

        <div className="card">
          <div className="card__header">
            <h2>
              <Sparkles size={15} style={{ color: 'var(--ai)' }} aria-hidden />
              Investigation queue
            </h2>
            <span className="count-chip">{queue.length} active</span>
          </div>
          <div className="card__body" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {queue.length === 0 ? (
              <EmptyState title="Queue is clear" message="No investigations are currently processing." />
            ) : (
              queue.map((q) => (
                <Link
                  key={q.id}
                  to={`/investigations/${q.id}`}
                  style={{ color: 'inherit', textDecoration: 'none', display: 'grid', gap: 6, minWidth: 0, maxWidth: '100%', overflow: 'hidden' }}
                  aria-label={`Open queued investigation ${q.id}`}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center', minWidth: 0 }}>
                    <span className="cell-main" style={{ fontSize: 12.5, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {q.testName}
                    </span>
                    <InvestigationStatusBadge status={q.status} />
                  </div>
                  <div className="progress" aria-hidden>
                    <span style={{ width: `${stageProgress(q.stage) * 100}%` }} />
                  </div>
                  <div className="kpi__meta" style={{ justifyContent: 'space-between' }}>
                    <span>{STAGE_META[q.stage]}</span>
                    <span>{formatRelativeTime(q.createdAt)}</span>
                  </div>
                </Link>
              ))
            )}
          </div>
        </div>
      </div>

      <div
        className="section-grid"
        style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))' }}
      >
        <div className="card">
          <div className="card__header">
            <h2>Failure classifications</h2>
          </div>
          <div className="card__body">
            {classificationCounts.length === 0 ? (
              <p className="muted">No classified investigations yet.</p>
            ) : (
              <BarList items={classificationCounts} ariaLabel="Failure classification counts" />
            )}
          </div>
        </div>
        <div className="card">
          <div className="card__header">
            <h2>Release-risk distribution</h2>
          </div>
          <div className="card__body">
            <StackBar segments={riskSegments} ariaLabel="Release risk distribution" />
          </div>
        </div>
        <div className="card">
          <div className="card__header">
            <h2>7-day investigation trend</h2>
          </div>
          <div className="card__body">
            <ColumnsChart data={weeklyTrend} ariaLabel="Investigations per day over the last week" />
          </div>
        </div>
        <div className="card">
          <div className="card__header">
            <h2>Top failing components</h2>
          </div>
          <div className="card__body">
            <BarList
              items={topFailingComponents.map((c) => ({ ...c, color: 'var(--warn)' }))}
              ariaLabel="Most frequently implicated components"
            />
          </div>
        </div>
      </div>
    </>
  );
}
