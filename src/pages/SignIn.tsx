import { useState, type FormEvent } from 'react';
import { KeyRound, Loader2, LogIn, ShieldCheck, TriangleAlert, UserPlus } from 'lucide-react';
import { Logo } from '../components/ui/Logo';
import { describeAuthError, useAuth } from '../context/AuthContext';

type Mode = 'sign-in' | 'sign-up';

export function SignIn() {
  const { signIn, signUp, configured } = useAuth();
  const [mode, setMode] = useState<Mode>('sign-in');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    if (!email.trim() || !password) {
      setError('Enter your email and password.');
      return;
    }
    setBusy(true);
    try {
      if (mode === 'sign-in') await signIn(email.trim(), password);
      else await signUp(email.trim(), password);
    } catch (err) {
      setError(describeAuthError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="auth-shell">
      <section className="auth-card card" aria-labelledby="auth-heading">
        <div className="auth-card__brand">
          <Logo />
        </div>

        <h1 id="auth-heading" className="auth-card__title">
          {mode === 'sign-in' ? 'Sign in to TriageZero' : 'Create your account'}
        </h1>
        <p className="auth-card__sub">
          Autonomous regression-failure investigation. Sign in to view
          investigations and approve recommended actions.
        </p>

        {!configured && (
          <p className="auth-card__notice" role="status">
            <TriangleAlert size={14} aria-hidden />
            Authentication is not configured for this build. Set the{' '}
            <code>VITE_FIREBASE_*</code> values to enable sign-in.
          </p>
        )}

        <form onSubmit={submit} noValidate>
          <div className="field">
            <label htmlFor="auth-email">Email</label>
            <input
              id="auth-email"
              className="input"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={busy || !configured}
              required
            />
          </div>

          <div className="field" style={{ marginTop: 12 }}>
            <label htmlFor="auth-password">Password</label>
            <input
              id="auth-password"
              className="input"
              type="password"
              autoComplete={mode === 'sign-in' ? 'current-password' : 'new-password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={busy || !configured}
              required
            />
          </div>

          {error && (
            <p className="auth-card__error" role="alert">
              <TriangleAlert size={14} aria-hidden />
              {error}
            </p>
          )}

          <button
            type="submit"
            className="btn btn--primary auth-card__submit"
            disabled={busy || !configured}
          >
            {busy ? (
              <Loader2 size={15} aria-hidden className="spin" />
            ) : mode === 'sign-in' ? (
              <LogIn size={15} aria-hidden />
            ) : (
              <UserPlus size={15} aria-hidden />
            )}
            {busy
              ? 'Working…'
              : mode === 'sign-in'
                ? 'Sign in'
                : 'Create account'}
          </button>
        </form>

        <button
          type="button"
          className="btn btn--ghost auth-card__switch"
          onClick={() => {
            setMode(mode === 'sign-in' ? 'sign-up' : 'sign-in');
            setError(null);
          }}
          disabled={busy}
        >
          <KeyRound size={14} aria-hidden />
          {mode === 'sign-in'
            ? 'Need an account? Create one'
            : 'Already have an account? Sign in'}
        </button>

        <p className="auth-card__footer">
          <ShieldCheck size={13} aria-hidden />
          Automated test reporters authenticate separately with their own
          ingestion token — never with these credentials.
        </p>
      </section>
    </main>
  );
}
