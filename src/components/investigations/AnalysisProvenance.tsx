import {
  BrainCircuit,
  CircleSlash,
  Clock,
  Cpu,
  FlaskConical,
  ShieldCheck,
  Sparkles,
  UserCheck,
} from 'lucide-react';
import type {
  AiMetadata,
  HumanResolution,
  OriginalPrediction,
} from '../../types';
import { formatDuration, formatFullDateTime, titleCase } from '../../utils/format';
import { CLASSIFICATION_META, RISK_META, SEVERITY_META } from '../../utils/labels';
import { ClassificationBadge, RiskBadge, SeverityBadge } from '../ui/StatusBadge';

const PROVIDER_LABEL: Record<string, string> = {
  deterministic: 'Deterministic rules',
  gemini: 'Gemini',
  gemini_adk: 'Gemini + Google ADK',
  deterministic_fallback: 'Deterministic (fallback)',
};

/** Small label for a seeded benchmark row, so synthetic data is never mistaken for real. */
export function SyntheticBadge() {
  return (
    <span className="badge badge--ai" title="Seeded benchmark data, not a real failure">
      <FlaskConical size={12} aria-hidden />
      Synthetic benchmark
    </span>
  );
}

export function AnalysisProvenanceCard({ meta }: { meta?: AiMetadata | null }) {
  if (!meta) {
    return (
      <div className="card">
        <div className="card__header">
          <h2>
            <BrainCircuit size={15} style={{ color: 'var(--ai)' }} aria-hidden />
            Analysis provenance
          </h2>
        </div>
        <div className="card__body">
          <p className="muted" style={{ fontSize: 13 }}>
            No analysis metadata recorded for this investigation yet.
          </p>
        </div>
      </div>
    );
  }

  const usedFallback = Boolean(meta.usedFallback);
  return (
    <div className="card">
      <div className="card__header">
        <h2>
          <BrainCircuit size={15} style={{ color: 'var(--ai)' }} aria-hidden />
          Analysis provenance
        </h2>
        {usedFallback ? (
          <span className="badge badge--warn" title="The configured AI provider did not run">
            <CircleSlash size={12} aria-hidden />
            Fallback used
          </span>
        ) : (
          <span className="badge badge--ai">
            <Sparkles size={12} aria-hidden />
            {PROVIDER_LABEL[meta.provider] ?? meta.provider}
          </span>
        )}
      </div>
      <div className="card__body" style={{ display: 'grid', gap: 12 }}>
        <dl className="kv">
          <dt>Provider</dt>
          <dd>{PROVIDER_LABEL[meta.provider] ?? meta.provider}</dd>
          <dt>Model</dt>
          <dd className="mono">{meta.modelName ?? '— (no model used)'}</dd>
          <dt>Prompt version</dt>
          <dd className="mono">{meta.promptVersion ?? '—'}</dd>
          <dt>Result schema</dt>
          <dd className="mono">{meta.analysisSchemaVersion ?? '—'}</dd>
          <dt>Analysis duration</dt>
          <dd>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
              <Clock size={12} aria-hidden />
              {meta.durationMs != null ? formatDuration(meta.durationMs) : '—'}
            </span>
          </dd>
          <dt>Token usage</dt>
          <dd>
            {meta.inputTokens != null || meta.outputTokens != null ? (
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                <Cpu size={12} aria-hidden />
                {meta.inputTokens ?? 0} in · {meta.outputTokens ?? 0} out
              </span>
            ) : (
              <span className="faint">Not reported by this provider</span>
            )}
          </dd>
        </dl>

        {usedFallback && meta.fallbackReason && (
          <p
            style={{
              fontSize: 12.5,
              color: 'var(--warn)',
              background: 'var(--warn-soft)',
              border: '1px solid color-mix(in srgb, var(--warn) 30%, transparent)',
              borderRadius: 'var(--radius-sm)',
              padding: '9px 11px',
            }}
          >
            The configured AI provider did not run ({meta.fallbackReason}); this conclusion
            came from the deterministic analyzer. No model result is being presented as
            though a model produced it.
          </p>
        )}

        {meta.stageSummaries && meta.stageSummaries.length > 0 && (
          <div>
            <div className="cell-sub" style={{ marginBottom: 6 }}>
              Workflow stages
            </div>
            <ol className="timeline">
              {meta.stageSummaries.map((stage) => (
                <li key={stage.stage}>
                  <span className="timeline__dot" aria-hidden />
                  <div className="timeline__label">{titleCase(stage.stage)}</div>
                  <div className="cell-sub">{stage.summary}</div>
                  {stage.durationMs != null && stage.durationMs > 0 && (
                    <div className="timeline__time">{formatDuration(stage.durationMs)}</div>
                  )}
                </li>
              ))}
            </ol>
          </div>
        )}

        <p className="faint" style={{ fontSize: 11.5, display: 'flex', gap: 6 }}>
          <ShieldCheck size={13} aria-hidden style={{ flexShrink: 0, marginTop: 1 }} />
          Stage summaries are conclusions only. Model reasoning is never requested,
          stored, or displayed.
        </p>
      </div>
    </div>
  );
}

export function HumanResolutionCard({
  resolution,
  prediction,
}: {
  resolution?: HumanResolution | null;
  prediction?: OriginalPrediction | null;
}) {
  if (!resolution) {
    return (
      <div className="card">
        <div className="card__header">
          <h2>
            <UserCheck size={15} aria-hidden />
            Human resolution
          </h2>
          <span className="badge badge--muted">Not reviewed</span>
        </div>
        <div className="card__body">
          <p className="muted" style={{ fontSize: 13 }}>
            No human-reviewed outcome recorded. Unreviewed AI predictions never enter the
            historical corpus used to inform future investigations.
          </p>
        </div>
      </div>
    );
  }

  const changed =
    prediction?.classification != null &&
    prediction.classification !== resolution.classification;

  return (
    <div className="card" style={{ borderColor: 'color-mix(in srgb, var(--ok) 30%, var(--border))' }}>
      <div className="card__header">
        <h2>
          <UserCheck size={15} style={{ color: 'var(--ok)' }} aria-hidden />
          Human resolution
        </h2>
        <span className="badge badge--ok">
          Reviewed{resolution.revision && resolution.revision > 1 ? ` · rev ${resolution.revision}` : ''}
        </span>
      </div>
      <div className="card__body" style={{ display: 'grid', gap: 12 }}>
        <p style={{ fontSize: 13.5 }}>{resolution.resolutionSummary}</p>
        <dl className="kv">
          <dt>Final classification</dt>
          <dd>
            <ClassificationBadge value={resolution.classification} />
          </dd>
          <dt>Final severity</dt>
          <dd>
            <SeverityBadge value={resolution.severity} />
          </dd>
          <dt>Final release risk</dt>
          <dd>
            <RiskBadge value={resolution.releaseRisk} />
          </dd>
          <dt>Component</dt>
          <dd>{resolution.responsibleComponent || '—'}</dd>
          <dt>Resolver</dt>
          <dd>{resolution.resolver || '—'}</dd>
          <dt>Resolved</dt>
          <dd>{formatFullDateTime(resolution.resolvedAt)}</dd>
        </dl>

        {prediction?.classification && (
          <div
            style={{
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-sm)',
              padding: 11,
              display: 'grid',
              gap: 6,
            }}
          >
            <div className="cell-sub">AI prediction vs. reviewed outcome</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <span className="muted" style={{ fontSize: 12.5 }}>
                Predicted {CLASSIFICATION_META[prediction.classification].label}
              </span>
              <span aria-hidden>→</span>
              <span style={{ fontSize: 12.5, fontWeight: 600 }}>
                {CLASSIFICATION_META[resolution.classification].label}
              </span>
              <span className={`badge badge--${changed ? 'warn' : 'ok'}`}>
                {changed ? 'Corrected by reviewer' : 'Confirmed'}
              </span>
            </div>
            {prediction.severity && prediction.releaseRisk && (
              <div className="faint" style={{ fontSize: 11.5 }}>
                Predicted severity {SEVERITY_META[prediction.severity].label} · risk{' '}
                {RISK_META[prediction.releaseRisk].label}
                {prediction.provider ? ` · via ${PROVIDER_LABEL[prediction.provider] ?? prediction.provider}` : ''}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
