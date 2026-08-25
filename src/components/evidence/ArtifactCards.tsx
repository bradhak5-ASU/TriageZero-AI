import {
  FileArchive,
  FileImage,
  FileTerminal,
  FileVideo,
  Network,
} from 'lucide-react';
import type { ArtifactInfo, ArtifactKind } from '../../types';
import { formatBytes } from '../../utils/format';
import { EmptyState } from '../ui/States';
import { useToast } from '../../context/ToastContext';

const icons: Record<ArtifactKind, typeof FileImage> = {
  screenshot: FileImage,
  trace: FileArchive,
  video: FileVideo,
  console_log: FileTerminal,
  network_log: Network,
};

export function ArtifactCards({ artifacts }: { artifacts: ArtifactInfo[] }) {
  const { pushToast } = useToast();

  if (artifacts.length === 0) {
    return (
      <EmptyState
        title="No artifacts"
        message="This failure package did not include screenshots, traces, or logs."
      />
    );
  }

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(210px, 1fr))',
        gap: 12,
      }}
    >
      {artifacts.map((artifact) => {
        const Icon = icons[artifact.kind];
        return (
          <div key={artifact.path} className="card" style={{ padding: 13, display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Icon size={17} style={{ color: artifact.available ? 'var(--accent)' : 'var(--text-faint)' }} aria-hidden />
              <strong style={{ fontSize: 13 }}>{artifact.label}</strong>
            </div>
            <div className="cell-sub mono" style={{ wordBreak: 'break-all' }}>
              {artifact.path}
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 'auto' }}>
              <span className="muted" style={{ fontSize: 12 }}>
                {formatBytes(artifact.sizeBytes)}
              </span>
              {artifact.available ? (
                <button
                  type="button"
                  className="btn btn--sm"
                  onClick={() =>
                    pushToast('Artifact storage is not connected yet — download available after backend integration.', 'info')
                  }
                >
                  Download
                </button>
              ) : (
                <span className="badge badge--muted">Unavailable</span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
