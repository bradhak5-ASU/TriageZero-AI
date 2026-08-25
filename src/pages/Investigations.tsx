import { useMemo, useState } from 'react';
import {
  Download,
  FilterX,
  LayoutGrid,
  RefreshCw,
  Rows3,
  Search,
} from 'lucide-react';
import { InvestigationCard } from '../components/investigations/InvestigationCard';
import { InvestigationTable } from '../components/investigations/InvestigationTable';
import { EmptyState, ErrorState, LoadingState } from '../components/ui/States';
import { useInvestigations } from '../context/InvestigationsContext';
import { useToast } from '../context/ToastContext';
import {
  CLASSIFICATION_META,
  RISK_META,
  SEVERITY_META,
  STATUS_META,
} from '../utils/labels';
import { downloadJson } from '../utils/download';
import type {
  Classification,
  EnvironmentName,
  InvestigationStatus,
  ReleaseRisk,
  Severity,
} from '../types';

const PAGE_SIZE = 10;

type SortKey = 'newest' | 'oldest' | 'confidence' | 'severity';

const severityRank: Record<Severity, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
};

const dateWindows = {
  all: { label: 'Any time', ms: Infinity },
  '24h': { label: 'Last 24 hours', ms: 24 * 3600_000 },
  '7d': { label: 'Last 7 days', ms: 7 * 24 * 3600_000 },
  '30d': { label: 'Last 30 days', ms: 30 * 24 * 3600_000 },
} as const;

export function Investigations() {
  const { items, loading, error, refresh } = useInvestigations();
  const { pushToast } = useToast();

  const [search, setSearch] = useState('');
  const [status, setStatus] = useState<InvestigationStatus | 'all'>('all');
  const [classification, setClassification] = useState<Classification | 'all'>('all');
  const [severity, setSeverity] = useState<Severity | 'all'>('all');
  const [risk, setRisk] = useState<ReleaseRisk | 'all'>('all');
  const [repo, setRepo] = useState<string>('all');
  const [env, setEnv] = useState<EnvironmentName | 'all'>('all');
  const [window_, setWindow] = useState<keyof typeof dateWindows>('all');
  const [sort, setSort] = useState<SortKey>('newest');
  const [view, setView] = useState<'table' | 'cards'>('table');
  const [visible, setVisible] = useState(PAGE_SIZE);

  const repos = useMemo(
    () => [...new Set(items.map((i) => i.repository))].sort(),
    [items],
  );

  const hasFilters =
    search !== '' ||
    status !== 'all' ||
    classification !== 'all' ||
    severity !== 'all' ||
    risk !== 'all' ||
    repo !== 'all' ||
    env !== 'all' ||
    window_ !== 'all';

  const clearFilters = () => {
    setSearch('');
    setStatus('all');
    setClassification('all');
    setSeverity('all');
    setRisk('all');
    setRepo('all');
    setEnv('all');
    setWindow('all');
    setVisible(PAGE_SIZE);
  };

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    const cutoff = Date.now() - dateWindows[window_].ms;
    const result = items.filter((i) => {
      if (q && !(
        i.testName.toLowerCase().includes(q) ||
        i.id.toLowerCase().includes(q) ||
        i.repository.toLowerCase().includes(q) ||
        i.branch.toLowerCase().includes(q)
      )) return false;
      if (status !== 'all' && i.status !== status) return false;
      if (classification !== 'all' && i.classification !== classification) return false;
      if (severity !== 'all' && i.severity !== severity) return false;
      if (risk !== 'all' && i.releaseRisk !== risk) return false;
      if (repo !== 'all' && i.repository !== repo) return false;
      if (env !== 'all' && i.environment !== env) return false;
      if (window_ !== 'all' && new Date(i.createdAt).getTime() < cutoff) return false;
      return true;
    });

    result.sort((a, b) => {
      switch (sort) {
        case 'oldest':
          return a.createdAt.localeCompare(b.createdAt);
        case 'confidence':
          return (b.confidence ?? -1) - (a.confidence ?? -1);
        case 'severity':
          return (
            (a.severity ? severityRank[a.severity] : 9) -
            (b.severity ? severityRank[b.severity] : 9)
          );
        default:
          return b.createdAt.localeCompare(a.createdAt);
      }
    });
    return result;
  }, [items, search, status, classification, severity, risk, repo, env, window_, sort]);

  const page = filtered.slice(0, visible);

  const exportJson = () => {
    downloadJson(`triagezero-investigations-${new Date().toISOString().slice(0, 10)}.json`, filtered);
    pushToast(`Exported ${filtered.length} investigation${filtered.length === 1 ? '' : 's'} as JSON`, 'ok');
  };

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Investigations</h1>
          <p className="sub">
            {filtered.length} result{filtered.length === 1 ? '' : 's'}
            {hasFilters ? ' (filtered)' : ''} · {items.length} total
          </p>
        </div>
        <div className="header-actions">
          <button type="button" className="btn" onClick={() => void refresh()} disabled={loading}>
            <RefreshCw size={14} aria-hidden />
            Refresh
          </button>
          <button type="button" className="btn" onClick={exportJson} disabled={filtered.length === 0}>
            <Download size={14} aria-hidden />
            Export JSON
          </button>
          <div role="group" aria-label="View mode" style={{ display: 'inline-flex', gap: 2 }}>
            <button
              type="button"
              className={`btn btn--sm ${view === 'table' ? '' : 'btn--ghost'}`}
              aria-pressed={view === 'table'}
              onClick={() => setView('table')}
            >
              <Rows3 size={14} aria-hidden />
              Table
            </button>
            <button
              type="button"
              className={`btn btn--sm ${view === 'cards' ? '' : 'btn--ghost'}`}
              aria-pressed={view === 'cards'}
              onClick={() => setView('cards')}
            >
              <LayoutGrid size={14} aria-hidden />
              Cards
            </button>
          </div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card__body" style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'flex-end' }}>
          <div className="field" style={{ flex: '1 1 220px' }}>
            <label htmlFor="inv-search">Search</label>
            <div style={{ position: 'relative' }}>
              <Search size={14} aria-hidden style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-faint)' }} />
              <input
                id="inv-search"
                type="search"
                className="input"
                style={{ paddingLeft: 30, width: '100%' }}
                placeholder="Test name, ID, repo, branch…"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setVisible(PAGE_SIZE);
                }}
              />
            </div>
          </div>

          <div className="field">
            <label htmlFor="f-status">Status</label>
            <select id="f-status" className="select" value={status} onChange={(e) => { setStatus(e.target.value as typeof status); setVisible(PAGE_SIZE); }}>
              <option value="all">All</option>
              {Object.entries(STATUS_META).map(([key, meta]) => (
                <option key={key} value={key}>{meta.label}</option>
              ))}
            </select>
          </div>

          <div className="field">
            <label htmlFor="f-class">Classification</label>
            <select id="f-class" className="select" value={classification} onChange={(e) => { setClassification(e.target.value as typeof classification); setVisible(PAGE_SIZE); }}>
              <option value="all">All</option>
              {Object.entries(CLASSIFICATION_META).map(([key, meta]) => (
                <option key={key} value={key}>{meta.label}</option>
              ))}
            </select>
          </div>

          <div className="field">
            <label htmlFor="f-severity">Severity</label>
            <select id="f-severity" className="select" value={severity} onChange={(e) => { setSeverity(e.target.value as typeof severity); setVisible(PAGE_SIZE); }}>
              <option value="all">All</option>
              {Object.entries(SEVERITY_META).map(([key, meta]) => (
                <option key={key} value={key}>{meta.label}</option>
              ))}
            </select>
          </div>

          <div className="field">
            <label htmlFor="f-risk">Release risk</label>
            <select id="f-risk" className="select" value={risk} onChange={(e) => { setRisk(e.target.value as typeof risk); setVisible(PAGE_SIZE); }}>
              <option value="all">All</option>
              {Object.entries(RISK_META).map(([key, meta]) => (
                <option key={key} value={key}>{meta.label}</option>
              ))}
            </select>
          </div>

          <div className="field">
            <label htmlFor="f-repo">Repository</label>
            <select id="f-repo" className="select" value={repo} onChange={(e) => { setRepo(e.target.value); setVisible(PAGE_SIZE); }}>
              <option value="all">All</option>
              {repos.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </div>

          <div className="field">
            <label htmlFor="f-env">Environment</label>
            <select id="f-env" className="select" value={env} onChange={(e) => { setEnv(e.target.value as typeof env); setVisible(PAGE_SIZE); }}>
              <option value="all">All</option>
              <option value="local">local</option>
              <option value="staging">staging</option>
              <option value="production">production</option>
            </select>
          </div>

          <div className="field">
            <label htmlFor="f-date">Date</label>
            <select id="f-date" className="select" value={window_} onChange={(e) => { setWindow(e.target.value as typeof window_); setVisible(PAGE_SIZE); }}>
              {Object.entries(dateWindows).map(([key, w]) => (
                <option key={key} value={key}>{w.label}</option>
              ))}
            </select>
          </div>

          <div className="field">
            <label htmlFor="f-sort">Sort</label>
            <select id="f-sort" className="select" value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
              <option value="newest">Newest first</option>
              <option value="oldest">Oldest first</option>
              <option value="confidence">Highest confidence</option>
              <option value="severity">Most severe</option>
            </select>
          </div>

          {hasFilters && (
            <button type="button" className="btn btn--ghost" onClick={clearFilters}>
              <FilterX size={14} aria-hidden />
              Clear all
            </button>
          )}
        </div>
      </div>

      {error && items.length === 0 ? (
        <div className="card">
          <ErrorState message={error} onRetry={() => void refresh()} />
        </div>
      ) : loading && items.length === 0 ? (
        <div className="card">
          <LoadingState rows={6} />
        </div>
      ) : filtered.length === 0 ? (
        <div className="card">
          <EmptyState
            icon="search"
            title="No matching investigations"
            message="No investigations match the current filters. Try widening the search."
            action={
              hasFilters ? (
                <button type="button" className="btn" onClick={clearFilters}>
                  <FilterX size={14} aria-hidden />
                  Clear filters
                </button>
              ) : undefined
            }
          />
        </div>
      ) : view === 'table' ? (
        <div className="card">
          <InvestigationTable items={page} />
        </div>
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
            gap: 12,
          }}
        >
          {page.map((inv) => (
            <InvestigationCard key={inv.id} inv={inv} />
          ))}
        </div>
      )}

      {visible < filtered.length && (
        <div style={{ display: 'flex', justifyContent: 'center', marginTop: 16 }}>
          <button type="button" className="btn" onClick={() => setVisible((v) => v + PAGE_SIZE)}>
            Load {Math.min(PAGE_SIZE, filtered.length - visible)} more
          </button>
        </div>
      )}
    </>
  );
}
