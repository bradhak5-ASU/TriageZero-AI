import { Inbox, RefreshCw, SearchX, TriangleAlert } from 'lucide-react';

export function LoadingState({ rows = 4 }: { rows?: number }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, padding: 16 }} aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skeleton" style={{ height: 34 }} />
      ))}
    </div>
  );
}

interface EmptyStateProps {
  title: string;
  message: string;
  icon?: 'inbox' | 'search';
  action?: React.ReactNode;
}

export function EmptyState({ title, message, icon = 'inbox', action }: EmptyStateProps) {
  const Icon = icon === 'search' ? SearchX : Inbox;
  return (
    <div className="state">
      <Icon size={30} aria-hidden />
      <h3>{title}</h3>
      <p>{message}</p>
      {action}
    </div>
  );
}

interface ErrorStateProps {
  title?: string;
  message: string;
  onRetry?: () => void;
}

export function ErrorState({ title = 'Something went wrong', message, onRetry }: ErrorStateProps) {
  return (
    <div className="state" role="alert">
      <TriangleAlert size={30} style={{ color: 'var(--warn)' }} aria-hidden />
      <h3>{title}</h3>
      <p>{message}</p>
      {onRetry && (
        <button type="button" className="btn" onClick={onRetry}>
          <RefreshCw size={14} aria-hidden />
          Retry
        </button>
      )}
    </div>
  );
}
