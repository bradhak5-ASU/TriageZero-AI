import { Fragment, useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import type { NetworkEntry } from '../../types';
import { formatDuration } from '../../utils/format';
import { EmptyState } from '../ui/States';

export function NetworkTable({ entries }: { entries: NetworkEntry[] }) {
  const [open, setOpen] = useState<number | null>(null);

  if (entries.length === 0) {
    return (
      <EmptyState
        title="No network evidence"
        message="This failure package did not include captured network requests."
      />
    );
  }

  return (
    <div className="table-wrap">
      <table className="data" style={{ minWidth: 560 }}>
        <thead>
          <tr>
            <th scope="col" aria-label="Expand" style={{ width: 30 }} />
            <th scope="col">Method</th>
            <th scope="col">URL</th>
            <th scope="col">Status</th>
            <th scope="col">Duration</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry, i) => {
            const expanded = open === i;
            const hasDetail = entry.requestHeaders || entry.responseSummary;
            return (
              <Fragment key={`${entry.method}-${entry.url}-${i}`}>
                <tr
                  className={hasDetail ? 'rowlink' : undefined}
                  onClick={() => hasDetail && setOpen(expanded ? null : i)}
                >
                  <td>
                    {hasDetail && (
                      <button
                        type="button"
                        className="icon-btn"
                        style={{ width: 22, height: 22 }}
                        aria-expanded={expanded}
                        aria-label={`${expanded ? 'Collapse' : 'Expand'} request detail`}
                        onClick={(e) => {
                          e.stopPropagation();
                          setOpen(expanded ? null : i);
                        }}
                      >
                        {expanded ? (
                          <ChevronDown size={13} aria-hidden />
                        ) : (
                          <ChevronRight size={13} aria-hidden />
                        )}
                      </button>
                    )}
                  </td>
                  <td>
                    <span className={`method method--${entry.method.toLowerCase()}`}>
                      {entry.method}
                    </span>
                  </td>
                  <td className="mono" style={{ wordBreak: 'break-all', maxWidth: 380 }}>
                    {entry.url}
                  </td>
                  <td>
                    <span className={`http-status http-status--${String(entry.status)[0]}`}>
                      {entry.status === 0 ? 'ERR' : entry.status}
                    </span>
                  </td>
                  <td className="muted mono">{formatDuration(entry.durationMs)}</td>
                </tr>
                {expanded && (
                  <tr>
                    <td colSpan={5} style={{ background: 'var(--bg-sunken)' }}>
                      <dl className="kv" style={{ padding: '4px 0' }}>
                        {entry.requestHeaders && (
                          <>
                            <dt>Request headers</dt>
                            <dd className="mono">
                              {Object.entries(entry.requestHeaders)
                                .map(([k, v]) => `${k}: ${v}`)
                                .join(' · ')}
                            </dd>
                          </>
                        )}
                        <dt>Response</dt>
                        <dd className="mono">{entry.responseSummary ?? '—'}</dd>
                      </dl>
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
