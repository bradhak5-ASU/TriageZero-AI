import { Link } from 'react-router-dom';
import { ArrowLeft, Compass } from 'lucide-react';

export function NotFound() {
  return (
    <div className="card">
      <div className="state" style={{ padding: '72px 20px' }}>
        <Compass size={36} aria-hidden />
        <h3 style={{ fontSize: 18 }}>404 — page not found</h3>
        <p>
          This route doesn’t exist in TriageZero. The investigation you’re after may live under
          Investigations.
        </p>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'center' }}>
          <Link to="/" className="btn btn--primary" style={{ textDecoration: 'none' }}>
            <ArrowLeft size={14} aria-hidden />
            Command Center
          </Link>
          <Link to="/investigations" className="btn" style={{ textDecoration: 'none' }}>
            Investigations
          </Link>
        </div>
      </div>
    </div>
  );
}
