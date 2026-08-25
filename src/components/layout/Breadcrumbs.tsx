import { Link, useLocation } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';

const names: Record<string, string> = {
  '': 'Command Center',
  investigations: 'Investigations',
  ingest: 'Ingest Failure',
  system: 'System Health',
  settings: 'Settings',
};

export function Breadcrumbs() {
  const { pathname } = useLocation();
  const parts = pathname.split('/').filter(Boolean);

  const crumbs = [
    { label: 'TriageZero', to: '/' },
    ...parts.map((part, i) => ({
      label: names[part] ?? part,
      to: '/' + parts.slice(0, i + 1).join('/'),
    })),
  ];

  if (parts.length === 0) crumbs.push({ label: 'Command Center', to: '/' });

  return (
    <nav className="breadcrumbs" aria-label="Breadcrumb">
      {crumbs.map((crumb, i) => {
        const last = i === crumbs.length - 1;
        return (
          <span key={crumb.to + i} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            {i > 0 && <ChevronRight size={12} aria-hidden />}
            {last ? (
              <span className="current" aria-current="page">
                {crumb.label}
              </span>
            ) : (
              <Link to={crumb.to}>{crumb.label}</Link>
            )}
          </span>
        );
      })}
    </nav>
  );
}
