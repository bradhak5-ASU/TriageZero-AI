/**
 * Authentication state for the dashboard.
 *
 * Three states the UI must handle distinctly: `loading` (Firebase has not yet
 * told us whether a session exists — rendering a sign-in page here would flash
 * the wrong screen), `signed-in`, and `signed-out`.
 *
 * When Firebase is not configured the provider reports `unconfigured` and the
 * app runs open, which is what keeps local demo mode usable without a Firebase
 * project.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import {
  createUserWithEmailAndPassword,
  onAuthStateChanged,
  signInWithEmailAndPassword,
  signOut as firebaseSignOut,
  type User,
} from 'firebase/auth';
import { getFirebaseAuth, isFirebaseConfigured } from '../services/firebase';
import { setAuthTokenProvider } from '../services/httpApi';

export type AuthStatus = 'loading' | 'signed-in' | 'signed-out' | 'unconfigured';

interface AuthContextValue {
  status: AuthStatus;
  user: User | null;
  email: string | null;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  /** True when a Firebase project is configured for this build. */
  configured: boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

/** Firebase error codes mapped to messages a person can act on. */
export function describeAuthError(error: unknown): string {
  const code =
    typeof error === 'object' && error !== null && 'code' in error
      ? String((error as { code: unknown }).code)
      : '';
  switch (code) {
    case 'auth/invalid-email':
      return 'That email address is not valid.';
    case 'auth/missing-password':
      return 'Enter your password.';
    case 'auth/weak-password':
      return 'Password must be at least 6 characters.';
    case 'auth/email-already-in-use':
      return 'An account already exists for that email — sign in instead.';
    case 'auth/invalid-credential':
    case 'auth/wrong-password':
    case 'auth/user-not-found':
      return 'Email or password is incorrect.';
    case 'auth/too-many-requests':
      return 'Too many attempts. Wait a moment and try again.';
    case 'auth/network-request-failed':
      return 'Could not reach the authentication service.';
    default:
      return 'Sign-in failed. Please try again.';
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const configured = isFirebaseConfigured();
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<AuthStatus>(
    configured ? 'loading' : 'unconfigured',
  );

  useEffect(() => {
    const auth = getFirebaseAuth();
    if (!auth) {
      setStatus('unconfigured');
      return;
    }
    // Firebase restores a persisted session asynchronously; until this fires
    // we must not decide the user is signed out.
    return onAuthStateChanged(auth, (next) => {
      setUser(next);
      setStatus(next ? 'signed-in' : 'signed-out');
    });
  }, []);

  // Hand the API client a token getter. getIdToken() refreshes automatically
  // when the token is close to expiry, so requests carry a fresh credential
  // without us managing timers.
  useEffect(() => {
    if (!configured) {
      setAuthTokenProvider(null);
      return;
    }
    setAuthTokenProvider(async () => {
      const auth = getFirebaseAuth();
      const current = auth?.currentUser;
      if (!current) return null;
      try {
        return await current.getIdToken();
      } catch {
        return null;
      }
    });
    return () => setAuthTokenProvider(null);
  }, [configured, user]);

  const signIn = useCallback(async (email: string, password: string) => {
    const auth = getFirebaseAuth();
    if (!auth) throw new Error('Authentication is not configured for this build.');
    await signInWithEmailAndPassword(auth, email, password);
  }, []);

  const signUp = useCallback(async (email: string, password: string) => {
    const auth = getFirebaseAuth();
    if (!auth) throw new Error('Authentication is not configured for this build.');
    await createUserWithEmailAndPassword(auth, email, password);
  }, []);

  const signOut = useCallback(async () => {
    const auth = getFirebaseAuth();
    if (auth) await firebaseSignOut(auth);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      email: user?.email ?? null,
      signIn,
      signUp,
      signOut,
      configured,
    }),
    [status, user, signIn, signUp, signOut, configured],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}
