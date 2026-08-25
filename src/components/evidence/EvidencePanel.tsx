import { useState } from 'react';
import type { Investigation } from '../../types';
import { Tabs } from '../ui/Tabs';
import { EmptyState } from '../ui/States';
import { ArtifactCards } from './ArtifactCards';
import { NetworkTable } from './NetworkTable';

export function EvidencePanel({ inv }: { inv: Investigation }) {
  const [tab, setTab] = useState('summary');
  const ev = inv.evidence;

  // the raw package view mirrors what Playwright submitted — evidence only,
  // never private oracle data or model reasoning
  const rawPackage = {
    schema_version: '1.0',
    source: 'novacart-playwright',
    run: { run_id: inv.runId, trigger: inv.trigger },
    repository: {
      name: inv.repository,
      branch: inv.branch,
      commit_sha: inv.commitSha,
    },
    environment: { name: inv.environment, browser: inv.browser },
    test: { name: inv.testName, file: inv.testFile, status: 'failed' },
    failure: {
      expected: ev.expected,
      actual: ev.actual,
      message: ev.message,
      stack_trace: ev.stackTrace,
    },
    network_evidence: ev.network.map((n) => ({
      method: n.method,
      url: n.url,
      status: n.status,
    })),
    console_errors: ev.consoleErrors,
    artifacts: Object.fromEntries(ev.artifacts.map((a) => [`${a.kind}_path`, a.path])),
  };

  return (
    <div className="card">
      <Tabs
        tabs={[
          { id: 'summary', label: 'Summary' },
          { id: 'network', label: 'Network', count: ev.network.length },
          { id: 'console', label: 'Console', count: ev.consoleErrors.length },
          { id: 'stack', label: 'Stack trace' },
          { id: 'artifacts', label: 'Artifacts', count: ev.artifacts.length },
          { id: 'raw', label: 'Raw package' },
        ]}
        active={tab}
        onChange={setTab}
      />
      <div className="card__body" role="tabpanel">
        {tab === 'summary' && (
          <dl className="kv">
            <dt>Expected</dt>
            <dd className="mono" style={{ color: 'var(--ok)' }}>
              {ev.expected || '—'}
            </dd>
            <dt>Actual</dt>
            <dd className="mono" style={{ color: 'var(--crit)' }}>
              {ev.actual || '—'}
            </dd>
            <dt>Failure message</dt>
            <dd>{ev.message || '—'}</dd>
            <dt>Test file</dt>
            <dd className="mono">{inv.testFile}</dd>
            <dt>Browser</dt>
            <dd>{inv.browser}</dd>
            <dt>Retry</dt>
            <dd>0</dd>
          </dl>
        )}
        {tab === 'network' && <NetworkTable entries={ev.network} />}
        {tab === 'console' && (
          ev.consoleErrors.length === 0 ? (
            <EmptyState
              title="No console errors"
              message="The browser console was clean during this test run."
            />
          ) : (
            <pre className="codeblock" style={{ whiteSpace: 'pre-wrap' }}>
              {ev.consoleErrors.map((line) => `✖ ${line}`).join('\n')}
            </pre>
          )
        )}
        {tab === 'stack' && (
          ev.stackTrace ? (
            <pre className="codeblock">{ev.stackTrace}</pre>
          ) : (
            <EmptyState title="No stack trace" message="No stack trace was captured for this failure." />
          )
        )}
        {tab === 'artifacts' && <ArtifactCards artifacts={ev.artifacts} />}
        {tab === 'raw' && (
          <pre className="codeblock" style={{ maxHeight: 420, overflow: 'auto' }}>
            {JSON.stringify(rawPackage, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
}
