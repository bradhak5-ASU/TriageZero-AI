import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  BrainCircuit,
  ExternalLink,
  GitBranch,
  GitCommitHorizontal,
  Globe,
  History,
  Lightbulb,
  ListChecks,
  RefreshCw,
  RotateCcw,
  ShieldAlert,
  Sparkles,
  Target,
} from 'lucide-react';
import { EvidencePanel } from '../components/evidence/EvidencePanel';
import { ConfirmModal } from '../components/ui/ConfirmModal';
import { CopyButton } from '../components/ui/CopyButton';
import { ErrorState, LoadingState } from '../components/ui/States';
import {
  ApprovalBadge,
  ClassificationBadge,
  InvestigationStatusBadge,
  RiskBadge,
  SeverityBadge,
} from '../components/ui/StatusBadge';
import { useInvestigations } from '../context/InvestigationsContext';
import { useSettings } from '../context/SettingsContext';
import { useToast } from '../context/ToastContext';
import type { ApprovalState, Investigation } from '../types';
import {
  formatConfidence,
  formatDuration,
  formatFullDateTime,
  formatRelativeTime,
  shortSha,
} from '../utils/format';
import {
  CLASSIFICATION_META,
  RISK_META,
  SEVERITY_META,
  STAGE_META,
  confidenceTone,
} from '../utils/labels';

const ACTIVE = ['received', 'queued', 'analyzing'];

export function InvestigationDetail() {
  const { investigationId = '' } = useParams();
  const { getById, fetchById, retry } = useInvestigations();
  const { settings } = useSettings();
  const { pushToast } = useToast();

  const cached = getById(investigationId);
  const [inv, setInv] = useState<Investigation | undefined>(cached);
  const [notFound, setNotFound] = useState(false);
  const [busy, setBusy] = useState(false);
  const [retryOpen, setRetryOpen] = useState(false);
  const [approvalOverride, setApprovalOverride] = useState<ApprovalState | null>(null);

  const load = useCallback(async () => {
    try {
      const fresh = await fetchById(investigationId);
      setInv(fresh);
      setNotFound(false);
    } catch {
      setNotFound(true);
    }
  }, [fetchById, investigationId]);

  useEffect(() => {
    setInv(getById(investigationId));
    setApprovalOverride(null);
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [investigationId]);

  // live progression while the investigation is still processing
  useEffect(() => {
    if (!inv || !ACTIVE.includes(inv.status)) return;
    const id = window.setInterval(() => void load(), 5000);
    return () => window.clearInterval(id);
  }, [inv, load]);

  const doRetry = async () => {
    setRetryOpen(false);
    setBusy(true);
    try {
      await retry(investigationId);
      await load();
      pushToast('Re-analysis started (simulated in demo mode)', 'ok');
    } catch (e) {
      pushToast(e instanceof Error ? e.message : 'Retry failed', 'warn');
    } finally {
      setBusy(false);
    }
  };

  const requestRetry = () => {
    if (settings.confirmDangerousActions) setRetryOpen(true);
    else void doRetry();
  };

  const decide = (state: ApprovalState) => {
    setApprovalOverride(state);
    pushToast(
      state === 'approved'
        ? 'Approval recorded locally — no external action executed in demo mode'
        : 'Rejection recorded locally',
      'info',
    );
  };

  const approvalState = approvalOverride ?? inv?.recommendedAction?.approvalState;

  const detailRows = useMemo(
    () =>
      inv
        ? [
            ['Run ID', inv.runId],
            ['Trigger', inv.trigger],
            ['Browser', inv.browser],
            ['Environment', inv.environment],
            ['Created', formatFullDateTime(inv.createdAt)],
            ['Completed', inv.completedAt ? formatFullDateTime(inv.completedAt) : '—'],
            ['Duration', formatDuration(inv.elapsedMs)],
          ]
        : [],
    [inv],
  );

  if (notFound) {
    return (
      <div className="card">
        <ErrorState
          title="Investigation not found"
          message={`No investigation with ID “${investigationId}” exists.`}
        />
        <div style={{ display: 'flex', justifyContent: 'center', paddingBottom: 24 }}>
          <Link to="/investigations" className="btn" style={{ textDecoration: 'none' }}>
            <ArrowLeft size={14} aria-hidden />
            Back to investigations
          </Link>
        </div>
      </div>
    );
  }

  if (!inv) {
    return (
      <div className="card">
        <LoadingState rows={8} />
      </div>
    );
  }

  const active = ACTIVE.includes(inv.status);

  return (
    <>
      <div className="page-header">
        <div style={{ minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 4 }}>
            <span className="mono muted" style={{ fontSize: 12.5 }}>{inv.id}</span>
            <InvestigationStatusBadge status={inv.status} />
            {active && <span className="badge badge--ai">{STAGE_META[inv.stage]}</span>}
          </div>
          <h1 style={{ fontSize: 19 }}>{inv.testName}</h1>
          <p className="sub" style={{ gap: 12 }}>
            <span className="mono" style={{ display: 'inline-flex', gap: 4, alignItems: 'center' }}>
              <GitBranch size={12} aria-hidden />
              {inv.repository} · {inv.branch}
            </span>
            <span className="mono" style={{ display: 'inline-flex', gap: 2, alignItems: 'center' }}>
              <GitCommitHorizontal size={12} aria-hidden />
              {shortSha(inv.commitSha)}
              <CopyButton text={inv.commitSha} label="Copy commit SHA" />
            </span>
            <span style={{ display: 'inline-flex', gap: 4, alignItems: 'center' }}>
              <Globe size={12} aria-hidden />
              {inv.environment} · {inv.browser}
            </span>
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              onClick={() =>
                pushToast('GitHub Actions link becomes available after GitHub integration is connected.', 'info')
              }
              title="GitHub Actions run (integration not yet connected)"
            >
              <ExternalLink size={12} aria-hidden />
              {inv.runId}
            </button>
          </p>
        </div>
        <div className="header-actions">
          <button type="button" className="btn" onClick={() => void load()} disabled={busy}>
            <RefreshCw size={14} aria-hidden />
            Refresh
          </button>
          <button type="button" className="btn" onClick={requestRetry} disabled={busy || active}>
            <RotateCcw size={14} aria-hidden />
            Retry analysis
          </button>
        </div>
      </div>

      {/* decision summary */}
      <div className="kpi-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))' }}>
        <div className="card kpi">
          <div className="kpi__top">
            <span>Classification</span>
            <Target size={14} aria-hidden style={{ color: 'var(--accent)' }} />
          </div>
          <div style={{ marginTop: 2 }}>
            <ClassificationBadge value={inv.classification} />
          </div>
          <div className="kpi__meta">
            {inv.classification ? CLASSIFICATION_META[inv.classification].label : 'Analysis in progress'}
          </div>
        </div>
        <div className="card kpi">
          <div className="kpi__top">
            <span>Confidence</span>
            <BrainCircuit size={14} aria-hidden style={{ color: 'var(--ai)' }} />
          </div>
          <div className="kpi__value" style={{ color: `var(--${confidenceTone(inv.confidence) === 'muted' ? 'text-muted' : confidenceTone(inv.confidence)})` }}>
            {formatConfidence(inv.confidence)}
          </div>
          <div className="progress" aria-hidden>
            <span
              style={{
                width: `${(inv.confidence ?? 0) * 100}%`,
                background: `var(--${confidenceTone(inv.confidence) === 'muted' ? 'border-strong' : confidenceTone(inv.confidence)})`,
              }}
            />
          </div>
        </div>
        <div className="card kpi">
          <div className="kpi__top">
            <span>Severity</span>
            <ShieldAlert size={14} aria-hidden style={{ color: 'var(--warn)' }} />
          </div>
          <div style={{ marginTop: 2 }}>
            <SeverityBadge value={inv.severity} />
          </div>
          <div className="kpi__meta">
            {inv.severity ? SEVERITY_META[inv.severity].label : 'Pending'} impact
          </div>
        </div>
        <div className="card kpi">
          <div className="kpi__top">
            <span>Release risk</span>
            <ShieldAlert size={14} aria-hidden style={{ color: 'var(--crit)' }} />
          </div>
          <div style={{ marginTop: 2 }}>
            <RiskBadge value={inv.releaseRisk} />
          </div>
          <div className="kpi__meta">
            {inv.releaseRisk === 'block_release'
              ? 'Requires sign-off before release'
              : inv.releaseRisk
                ? RISK_META[inv.releaseRisk].label
                : 'Pending assessment'}
          </div>
        </div>
      </div>

      <div
        className="section-grid"
        style={{ gridTemplateColumns: 'minmax(0, 2fr) minmax(0, 1fr)' }}
        data-collapse="stack"
      >
        <div className="section-grid" style={{ alignContent: 'start' }}>
          {inv.rootCause ? (
            <div className="card">
              <div className="card__header">
                <h2>
                  <Lightbulb size={15} style={{ color: 'var(--warn)' }} aria-hidden />
                  Root cause
                </h2>
              </div>
              <div className="card__body" style={{ display: 'grid', gap: 12 }}>
                <p style={{ fontSize: 14, lineHeight: 1.65 }}>{inv.rootCause.summary}</p>
                <dl className="kv">
                  <dt>Component</dt>
                  <dd>{inv.rootCause.component}</dd>
                  <dt>Why this confidence</dt>
                  <dd className="muted">{inv.rootCause.confidenceExplanation}</dd>
                  <dt>Recommended next step</dt>
                  <dd>{inv.rootCause.nextStep}</dd>
                </dl>
              </div>
            </div>
          ) : (
            <div className="card">
              <div className="card__body">
                <p className="muted" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Sparkles size={15} style={{ color: 'var(--ai)' }} aria-hidden />
                  {active
                    ? 'Root-cause analysis is in progress. This page refreshes automatically.'
                    : 'No root-cause conclusion is available for this investigation.'}
                </p>
              </div>
            </div>
          )}

          <EvidencePanel inv={inv} />

          <div className="card">
            <div className="card__header">
              <h2>Similar historical failures</h2>
              <span className="count-chip">{inv.similarFailures.length}</span>
            </div>
            {inv.similarFailures.length === 0 ? (
              <div className="card__body">
                <p className="muted">
                  {active
                    ? 'Similarity search runs during analysis.'
                    : 'No sufficiently similar past failures were found.'}
                </p>
              </div>
            ) : (
              <div className="table-wrap">
                <table className="data" style={{ minWidth: 640 }}>
                  <thead>
                    <tr>
                      <th scope="col">Match</th>
                      <th scope="col">Previous test</th>
                      <th scope="col">Classification</th>
                      <th scope="col">Root cause</th>
                      <th scope="col">Date</th>
                      <th scope="col">Resolution</th>
                      <th scope="col">Issue</th>
                    </tr>
                  </thead>
                  <tbody>
                    {inv.similarFailures.map((s) => (
                      <tr key={s.id}>
                        <td>
                          <span className="badge badge--ai">{Math.round(s.similarity * 100)}%</span>
                        </td>
                        <td>
                          <div className="cell-main">{s.testName}</div>
                          <div className="cell-sub mono">{s.id}</div>
                        </td>
                        <td>
                          <ClassificationBadge value={s.classification} />
                        </td>
                        <td className="muted" style={{ maxWidth: 260 }}>{s.rootCauseSummary}</td>
                        <td className="muted" style={{ whiteSpace: 'nowrap' }}>
                          {formatRelativeTime(s.date)}
                        </td>
                        <td className="muted" style={{ maxWidth: 200 }}>{s.resolution}</td>
                        <td>
                          {s.issueRef ? (
                            <button
                              type="button"
                              className="btn btn--ghost btn--sm mono"
                              onClick={() =>
                                pushToast('Issue links open once GitHub integration is connected.', 'info')
                              }
                            >
                              {s.issueRef}
                            </button>
                          ) : (
                            '—'
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {inv.recommendedAction && (
            <div className="card" style={{ borderColor: 'color-mix(in srgb, var(--ai) 30%, var(--border))' }}>
              <div className="card__header">
                <h2>
                  <ListChecks size={15} style={{ color: 'var(--ai)' }} aria-hidden />
                  Recommended action
                </h2>
                {approvalState && <ApprovalBadge value={approvalState} />}
              </div>
              <div className="card__body" style={{ display: 'grid', gap: 12 }}>
                <p style={{ fontWeight: 600, fontSize: 14 }}>{inv.recommendedAction.action}</p>
                <p className="muted" style={{ fontSize: 13 }}>{inv.recommendedAction.rationale}</p>
                <dl className="kv">
                  <dt>Suggested issue</dt>
                  <dd className="mono" style={{ fontSize: 12 }}>{inv.recommendedAction.issueTitle}</dd>
                  <dt>Labels</dt>
                  <dd style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
                    {inv.recommendedAction.labels.map((l) => (
                      <span key={l} className="badge badge--muted mono">{l}</span>
                    ))}
                  </dd>
                  <dt>Suggested owner</dt>
                  <dd>{inv.recommendedAction.owner}</dd>
                </dl>
                {(approvalState === 'awaiting_approval' || approvalState === 'proposed') && (
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                    <button type="button" className="btn btn--primary" onClick={() => decide('approved')}>
                      Approve
                    </button>
                    <button type="button" className="btn" onClick={() => decide('rejected')}>
                      Reject
                    </button>
                    <span className="faint" style={{ fontSize: 12 }}>
                      Actions are never executed automatically. Approvals here are simulated in demo mode.
                    </span>
                  </div>
                )}
                {approvalState === 'approved' && (
                  <p className="faint" style={{ fontSize: 12 }}>
                    Approved — execution will be available once the GitHub integration is connected.
                  </p>
                )}
                {approvalState === 'executed' && (
                  <p className="faint" style={{ fontSize: 12 }}>
                    This action was executed after human approval (recorded in the audit log below).
                  </p>
                )}
              </div>
            </div>
          )}
        </div>

        {/* side column */}
        <div className="section-grid" style={{ alignContent: 'start' }}>
          <div className="card">
            <div className="card__header">
              <h2>Details</h2>
            </div>
            <div className="card__body">
              <dl className="kv">
                {detailRows.map(([k, v]) => (
                  <span key={k} style={{ display: 'contents' }}>
                    <dt>{k}</dt>
                    <dd className={k === 'Run ID' ? 'mono' : undefined}>{v}</dd>
                  </span>
                ))}
                <dt>Commit</dt>
                <dd className="mono" style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                  {shortSha(inv.commitSha)}
                  <CopyButton text={inv.commitSha} label="Copy commit SHA" />
                </dd>
                <dt>Test file</dt>
                <dd className="mono" style={{ fontSize: 11.5 }}>{inv.testFile}</dd>
              </dl>
            </div>
          </div>

          <div className="card">
            <div className="card__header">
              <h2>Investigation timeline</h2>
            </div>
            <div className="card__body">
              {inv.timeline.length === 0 ? (
                <p className="muted">Timeline will appear as the investigation progresses.</p>
              ) : (
                <ol className="timeline">
                  {inv.timeline.map((t) => (
                    <li key={t.id}>
                      <span
                        className={`timeline__dot ${t.label.toLowerCase().includes('failed') ? 'timeline__dot--crit' : ''}`}
                        aria-hidden
                      />
                      <div className="timeline__label">{t.label}</div>
                      <div className="timeline__time">{formatFullDateTime(t.at)}</div>
                      {t.detail && <div className="cell-sub">{t.detail}</div>}
                    </li>
                  ))}
                </ol>
              )}
            </div>
          </div>

          <div className="card">
            <div className="card__header">
              <h2>
                <History size={15} aria-hidden />
                Action history
              </h2>
            </div>
            <div className="card__body">
              {inv.actionHistory.length === 0 ? (
                <p className="muted">No actions have been proposed or taken yet.</p>
              ) : (
                <ol className="timeline">
                  {inv.actionHistory.map((a) => (
                    <li key={a.id}>
                      <span className="timeline__dot" aria-hidden />
                      <div className="timeline__label" style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                        {a.action}
                        <ApprovalBadge value={a.state} />
                      </div>
                      <div className="timeline__time">
                        {a.actor} · {formatFullDateTime(a.at)}
                      </div>
                      {a.note && <div className="cell-sub">{a.note}</div>}
                    </li>
                  ))}
                </ol>
              )}
            </div>
          </div>
        </div>
      </div>

      <ConfirmModal
        open={retryOpen}
        title="Retry analysis?"
        message={`This queues ${inv.id} for a fresh AI investigation. In demo mode the re-run is simulated locally.`}
        confirmLabel="Retry analysis"
        onConfirm={() => void doRetry()}
        onCancel={() => setRetryOpen(false)}
      />
    </>
  );
}
