import type { ReactNode } from 'react';
import { Loader2 } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { SignIn } from '../../pages/SignIn';

/**
 * Route guard.
 *
 * `loading` renders a spinner rather than the sign-in page: Firebase restores
 * a persisted session asynchronously, and showing sign-in first would flash
 * the wrong screen at an already-signed-in user on every reload.
 *
 * `unconfigured` renders the app open, which keeps local demo mode working
 * without a Firebase project.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { status } = useAuth();

  if (status === 'loading') {
    return (
      <div className="auth-shell" role="status" aria-live="polite">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--text-muted)' }}>
          <Loader2 size={18} aria-hidden className="spin" />
          Restoring your session…
        </div>
      </div>
    );
  }

  if (status === 'signed-out') return <SignIn />;

  return <>{children}</>;
}
