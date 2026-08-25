import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  CheckCircle2,
  FileJson,
  FileUp,
  FlaskConical,
  Info,
  Send,
  ShieldX,
  TriangleAlert,
  Upload,
} from 'lucide-react';
import { sampleFailurePackage } from '../data/samplePackage';
import { useInvestigations } from '../context/InvestigationsContext';
import { useToast } from '../context/ToastContext';
import {
  parsePackageJson,
  validateFailurePackage,
  type ValidationResult,
} from '../utils/validatePackage';
import { config } from '../app/config';

export function IngestFailure() {
  const navigate = useNavigate();
  const { create } = useInvestigations();
  const { pushToast } = useToast();

  const [text, setText] = useState('');
  const [result, setResult] = useState<ValidationResult | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const runValidation = (source: string) => {
    setParseError(null);
    setResult(null);
    if (!source.trim()) {
      setParseError('Paste or upload a failure package first.');
      return;
    }
    const parsed = parsePackageJson(source);
    if (parsed.error) {
      setParseError(`Invalid JSON: ${parsed.error}`);
      return;
    }
    setResult(validateFailurePackage(parsed.data));
  };

  const acceptText = (source: string) => {
    setText(source);
    runValidation(source);
  };

  const readFile = (file: File) => {
    if (!file.name.endsWith('.json') && file.type !== 'application/json') {
      pushToast('Only JSON failure packages are accepted', 'warn');
      return;
    }
    const reader = new FileReader();
    reader.onload = () => acceptText(String(reader.result ?? ''));
    reader.readAsText(file);
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) readFile(file);
  };

  const loadSample = () => {
    acceptText(JSON.stringify(sampleFailurePackage, null, 2));
    pushToast('Sample failure package loaded', 'ok');
  };

  const submit = async () => {
    if (!result?.valid || !result.pkg) return;
    setSubmitting(true);
    try {
      const id = await create(result.pkg);
      pushToast(`Investigation ${id} created — status: received`, 'ok');
      navigate(`/investigations/${id}`);
    } catch (e) {
      pushToast(e instanceof Error ? e.message : 'Submission failed', 'warn');
    } finally {
      setSubmitting(false);
    }
  };

  const pkg = result?.pkg;

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Ingest Failure</h1>
          <p className="sub">
            Manual fallback for local testing and demos — in normal operation Playwright submits
            failure packages to <span className="mono">POST /api/v1/investigations</span> automatically.
          </p>
        </div>
      </div>

      <div
        className="card"
        style={{ marginBottom: 16, borderColor: 'color-mix(in srgb, var(--info) 30%, var(--border))' }}
      >
        <div className="card__body" style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
          <Info size={16} style={{ color: 'var(--info)', flexShrink: 0, marginTop: 1 }} aria-hidden />
          <p className="muted" style={{ fontSize: 13 }}>
            {config.useMockApi
              ? 'Demo mode is active: submitting a valid package creates a local investigation, persists it in your browser, and simulates the analysis pipeline.'
              : `Packages are submitted to ${config.apiBaseUrl}.`}{' '}
            Private QA-oracle fields (expected classifications, controlled-defect metadata) are rejected here and
            must never reach the AI pipeline.
          </p>
        </div>
      </div>

      <div className="section-grid" style={{ gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)' }} data-collapse="stack">
        <div className="card">
          <div className="card__header">
            <h2>
              <FileJson size={15} aria-hidden />
              Failure package
            </h2>
            <div style={{ display: 'flex', gap: 8 }}>
              <button type="button" className="btn btn--sm" onClick={loadSample}>
                <FlaskConical size={13} aria-hidden />
                Load sample
              </button>
              <button type="button" className="btn btn--sm" onClick={() => fileInputRef.current?.click()}>
                <FileUp size={13} aria-hidden />
                Choose file
              </button>
              <input
                ref={fileInputRef}
                type="file"
                accept=".json,application/json"
                className="visually-hidden"
                aria-label="Upload failure package JSON"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) readFile(file);
                  e.target.value = '';
                }}
              />
            </div>
          </div>
          <div className="card__body" style={{ display: 'grid', gap: 12 }}>
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              style={{
                border: `1.5px dashed ${dragging ? 'var(--accent)' : 'var(--border-strong)'}`,
                borderRadius: 'var(--radius)',
                padding: '18px 14px',
                textAlign: 'center',
                color: 'var(--text-faint)',
                fontSize: 12.5,
                background: dragging ? 'var(--accent-soft)' : 'transparent',
                transition: 'border-color 0.12s ease',
              }}
            >
              <Upload size={17} aria-hidden style={{ marginBottom: 4 }} />
              <div>Drag & drop a failure-package .json here, or paste below</div>
            </div>
            <label className="visually-hidden" htmlFor="pkg-editor">
              Failure package JSON
            </label>
            <textarea
              id="pkg-editor"
              className="input"
              rows={16}
              spellCheck={false}
              placeholder='{"schema_version": "1.0", "source": "novacart-playwright", …}'
              value={text}
              onChange={(e) => {
                setText(e.target.value);
                setResult(null);
                setParseError(null);
              }}
            />
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <button type="button" className="btn" onClick={() => runValidation(text)}>
                <CheckCircle2 size={14} aria-hidden />
                Validate package
              </button>
              <button
                type="button"
                className="btn btn--primary"
                onClick={() => void submit()}
                disabled={!result?.valid || submitting}
                title={!result?.valid ? 'Validate the package successfully before submitting' : undefined}
              >
                <Send size={14} aria-hidden />
                {submitting ? 'Submitting…' : 'Submit package'}
              </button>
            </div>
          </div>
        </div>

        <div className="section-grid" style={{ alignContent: 'start' }}>
          <div className="card">
            <div className="card__header">
              <h2>Validation</h2>
            </div>
            <div className="card__body" style={{ display: 'grid', gap: 10 }}>
              {!result && !parseError && (
                <p className="muted">Load or paste a package, then run validation.</p>
              )}
              {parseError && (
                <p role="alert" style={{ color: 'var(--crit)', display: 'flex', gap: 8, alignItems: 'flex-start', fontSize: 13 }}>
                  <TriangleAlert size={15} aria-hidden style={{ flexShrink: 0, marginTop: 1 }} />
                  {parseError}
                </p>
              )}
              {result && result.forbiddenFields.length > 0 && (
                <div
                  role="alert"
                  style={{
                    border: '1px solid color-mix(in srgb, var(--crit) 40%, transparent)',
                    background: 'var(--crit-soft)',
                    borderRadius: 'var(--radius-sm)',
                    padding: 12,
                    display: 'grid',
                    gap: 6,
                  }}
                >
                  <strong style={{ color: 'var(--crit)', display: 'flex', gap: 7, alignItems: 'center', fontSize: 13 }}>
                    <ShieldX size={15} aria-hidden />
                    Private QA-oracle fields rejected
                  </strong>
                  <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
                    {result.forbiddenFields.map((f) => (
                      <span key={f} className="badge badge--crit mono">{f}</span>
                    ))}
                  </div>
                  <p className="muted" style={{ fontSize: 12 }}>
                    Oracle metadata would leak the expected answer to the AI investigator. Remove these
                    fields — the backend enforces the same boundary.
                  </p>
                </div>
              )}
              {result?.errors
                .filter((e) => !e.includes('oracle'))
                .map((e) => (
                  <p key={e} role="alert" style={{ color: 'var(--crit)', fontSize: 13, display: 'flex', gap: 8 }}>
                    <TriangleAlert size={15} aria-hidden style={{ flexShrink: 0, marginTop: 1 }} />
                    {e}
                  </p>
                ))}
              {result?.warnings.map((w) => (
                <p key={w} style={{ color: 'var(--warn)', fontSize: 13, display: 'flex', gap: 8 }}>
                  <TriangleAlert size={15} aria-hidden style={{ flexShrink: 0, marginTop: 1 }} />
                  {w}
                </p>
              ))}
              {result?.valid && (
                <p style={{ color: 'var(--ok)', display: 'flex', gap: 8, alignItems: 'center', fontSize: 13, fontWeight: 600 }}>
                  <CheckCircle2 size={15} aria-hidden />
                  Package is valid and ready to submit.
                </p>
              )}
            </div>
          </div>

          {pkg && (
            <div className="card">
              <div className="card__header">
                <h2>Accepted evidence preview</h2>
              </div>
              <div className="card__body">
                <dl className="kv">
                  <dt>Test</dt>
                  <dd>{pkg.test.name}</dd>
                  <dt>File</dt>
                  <dd className="mono" style={{ fontSize: 11.5 }}>{pkg.test.file}</dd>
                  <dt>Repository</dt>
                  <dd className="mono">
                    {pkg.repository.name} · {pkg.repository.branch} @{' '}
                    {pkg.repository.commit_sha.slice(0, 7)}
                  </dd>
                  <dt>Environment</dt>
                  <dd>
                    {pkg.environment.name} · {pkg.environment.browser}
                  </dd>
                  <dt>Failure</dt>
                  <dd>{pkg.failure.message}</dd>
                  <dt>Expected / actual</dt>
                  <dd className="mono">
                    <span style={{ color: 'var(--ok)' }}>{pkg.failure.expected}</span>
                    {' → '}
                    <span style={{ color: 'var(--crit)' }}>{pkg.failure.actual}</span>
                  </dd>
                  <dt>Network evidence</dt>
                  <dd>{pkg.network_evidence?.length ?? 0} request(s)</dd>
                  <dt>Console errors</dt>
                  <dd>{pkg.console_errors?.length ?? 0} entr{(pkg.console_errors?.length ?? 0) === 1 ? 'y' : 'ies'}</dd>
                  <dt>Artifacts</dt>
                  <dd>
                    {Object.keys(pkg.artifacts ?? {}).length > 0
                      ? Object.keys(pkg.artifacts ?? {}).join(', ')
                      : 'none'}
                  </dd>
                </dl>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
