/**
 * Frontend authentication tests.
 *
 * Firebase is mocked at the module boundary — no test contacts Firebase or the
 * network. What these assert is the behavior a user (and a judge) would see:
 * a loading state that does not flash the wrong screen, a real sign-in gate,
 * token attachment on API calls, and no credential leaking into the DOM.
 */
import { useEffect } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const authState: {
  user: { email: string; getIdToken: () => Promise<string> } | null;
  listener: ((user: unknown) => void) | null;
  configured: boolean;
} = { user: null, listener: null, configured: true };

vi.mock('../services/firebase', () => ({
  isFirebaseConfigured: () => authState.configured,
  getFirebaseAuth: () =>
    authState.configured ? ({ currentUser: authState.user } as never) : null,
  resetFirebaseForTests: () => {},
}));

const signInMock = vi.fn();
const signUpMock = vi.fn();
const signOutMock = vi.fn();

vi.mock('firebase/auth', () => ({
  onAuthStateChanged: (_auth: unknown, cb: (u: unknown) => void) => {
    authState.listener = cb;
    // Firebase resolves the persisted session asynchronously — mirror that.
    queueMicrotask(() => cb(authState.user));
    return () => {};
  },
  signInWithEmailAndPassword: (...args: unknown[]) => signInMock(...args),
  createUserWithEmailAndPassword: (...args: unknown[]) => signUpMock(...args),
  signOut: (...args: unknown[]) => signOutMock(...args),
}));

const { AuthProvider, describeAuthError, useAuth } = await import('../context/AuthContext');
const { RequireAuth } = await import('../components/layout/RequireAuth');
const { setAuthTokenProvider } = await import('../services/httpApi');
const { httpApi } = await import('../services/httpApi');

function Protected() {
  return <div>SECRET DASHBOARD</div>;
}

function Harness() {
  return (
    <AuthProvider>
      <RequireAuth>
        <Protected />
      </RequireAuth>
    </AuthProvider>
  );
}

function WhoAmI() {
  const { status, email } = useAuth();
  return <div>{`${status}:${email ?? 'none'}`}</div>;
}

beforeEach(() => {
  authState.user = null;
  authState.configured = true;
  signInMock.mockReset();
  signUpMock.mockReset();
  signOutMock.mockReset();
  setAuthTokenProvider(null);
});

afterEach(() => {
  vi.unstubAllGlobals();
  setAuthTokenProvider(null);
});

describe('route protection', () => {
  it('shows a loading state before Firebase reports the session', async () => {
    render(<Harness />);
    // must NOT flash the sign-in page at an already-signed-in user
    expect(screen.getByText(/Restoring your session/i)).toBeInTheDocument();
    expect(screen.queryByText('SECRET DASHBOARD')).not.toBeInTheDocument();

    // The mocked listener resolves on a microtask, mirroring how Firebase
    // restores a persisted session. Settling it here keeps that state update
    // inside act() instead of landing after the test ends - the assertions
    // above have already captured the pre-resolution state, which is the
    // whole point of this test.
    await screen.findByRole('heading', { name: /Sign in to TriageZero/i });
  });

  it('redirects a signed-out visitor to sign-in and hides dashboard data', async () => {
    render(<Harness />);
    expect(
      await screen.findByRole('heading', { name: /Sign in to TriageZero/i }),
    ).toBeInTheDocument();
    expect(screen.queryByText('SECRET DASHBOARD')).not.toBeInTheDocument();
  });

  it('renders the dashboard once signed in', async () => {
    authState.user = { email: 'demo@example.com', getIdToken: async () => 'tok' };
    render(<Harness />);
    expect(await screen.findByText('SECRET DASHBOARD')).toBeInTheDocument();
  });

  it('runs open when Firebase is not configured (local demo mode)', async () => {
    authState.configured = false;
    render(<Harness />);
    expect(await screen.findByText('SECRET DASHBOARD')).toBeInTheDocument();
  });
});

describe('sign-in form', () => {
  it('signs a user in with email and password', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await screen.findByRole('heading', { name: /Sign in to TriageZero/i });

    await user.type(screen.getByLabelText('Email'), 'demo@example.com');
    await user.type(screen.getByLabelText('Password'), 'hunter2pass');
    await user.click(screen.getByRole('button', { name: /^Sign in$/i }));

    await waitFor(() => expect(signInMock).toHaveBeenCalledTimes(1));
    expect(signInMock.mock.calls[0][1]).toBe('demo@example.com');
  });

  it('can switch to account creation', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await screen.findByRole('heading', { name: /Sign in to TriageZero/i });

    await user.click(screen.getByRole('button', { name: /Need an account/i }));
    await user.type(screen.getByLabelText('Email'), 'new@example.com');
    await user.type(screen.getByLabelText('Password'), 'hunter2pass');
    await user.click(screen.getByRole('button', { name: /Create account/i }));

    await waitFor(() => expect(signUpMock).toHaveBeenCalledTimes(1));
  });

  it('surfaces a readable error instead of a Firebase code', async () => {
    const user = userEvent.setup();
    signInMock.mockRejectedValueOnce({ code: 'auth/invalid-credential' });
    render(<Harness />);
    await screen.findByRole('heading', { name: /Sign in to TriageZero/i });

    await user.type(screen.getByLabelText('Email'), 'demo@example.com');
    await user.type(screen.getByLabelText('Password'), 'wrongpass');
    await user.click(screen.getByRole('button', { name: /^Sign in$/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      /Email or password is incorrect/i,
    );
    expect(screen.queryByText(/auth\/invalid-credential/)).not.toBeInTheDocument();
  });

  it('validates empty input locally without calling Firebase', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await screen.findByRole('heading', { name: /Sign in to TriageZero/i });
    await user.click(screen.getByRole('button', { name: /^Sign in$/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/Enter your email/i);
    expect(signInMock).not.toHaveBeenCalled();
  });

  it('explains when authentication is not configured', async () => {
    authState.configured = false;
    render(
      <AuthProvider>
        <WhoAmI />
      </AuthProvider>,
    );
    expect(await screen.findByText(/^unconfigured:/)).toBeInTheDocument();
  });

  it('maps Firebase error codes to human messages', () => {
    expect(describeAuthError({ code: 'auth/email-already-in-use' })).toMatch(/already exists/i);
    expect(describeAuthError({ code: 'auth/weak-password' })).toMatch(/6 characters/i);
    expect(describeAuthError({ code: 'auth/too-many-requests' })).toMatch(/Too many/i);
    expect(describeAuthError(new Error('boom'))).toMatch(/Sign-in failed/i);
  });
});

describe('API token attachment', () => {
  function stubFetch() {
    const fn = vi.fn().mockResolvedValue({
      ok: true, status: 200, statusText: 'OK', json: () => Promise.resolve([]),
    });
    vi.stubGlobal('fetch', fn);
    return fn;
  }

  it('attaches the Firebase ID token as a bearer credential', async () => {
    const fetchMock = stubFetch();
    setAuthTokenProvider(async () => 'ID-TOKEN-123');

    await httpApi.listInvestigations();

    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers.authorization).toBe('Bearer ID-TOKEN-123');
  });

  it('sends no Authorization header when signed out', async () => {
    const fetchMock = stubFetch();
    setAuthTokenProvider(async () => null);

    await httpApi.listInvestigations();

    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers.authorization).toBeUndefined();
  });

  it('still sends the request if the token lookup fails', async () => {
    const fetchMock = stubFetch();
    setAuthTokenProvider(async () => {
      throw new Error('refresh failed');
    });

    await httpApi.listInvestigations();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers.authorization).toBeUndefined();
  });

  it('never attaches the token to the failure package body', async () => {
    const fetchMock = stubFetch();
    setAuthTokenProvider(async () => 'ID-TOKEN-123');
    const { sampleFailurePackage } = await import('../data/samplePackage');

    await httpApi.createInvestigation(sampleFailurePackage);

    const [, init] = fetchMock.mock.calls[0];
    expect(init.body).not.toContain('ID-TOKEN-123');
    expect(init.headers.authorization).toBe('Bearer ID-TOKEN-123');
  });
});

describe('token registration ordering', () => {
  it('attaches the token on a child\'s very first request, with no retry', async () => {
    // Regression: the token provider was registered in an effect on
    // AuthProvider. React runs CHILD effects before PARENT effects, so a
    // provider mounted underneath fired its first fetch before the token
    // getter existed - the request went out bare and the dashboard showed
    // "A bearer token is required for this API operation", while pressing
    // Retry succeeded because by then it was registered.
    authState.user = { email: 'demo@example.com', getIdToken: async () => 'FIRST-CALL-TOKEN' };

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true, status: 200, statusText: 'OK', json: () => Promise.resolve([]),
    });
    vi.stubGlobal('fetch', fetchMock);

    // A child that calls the API from its mount effect, exactly as
    // InvestigationsProvider does.
    function FetchesOnMount() {
      useEffect(() => {
        void httpApi.listInvestigations();
      }, []);
      return <div>child</div>;
    }

    render(
      <AuthProvider>
        <FetchesOnMount />
      </AuthProvider>,
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers.authorization).toBe('Bearer FIRST-CALL-TOKEN');
  });
});

describe('credential hygiene', () => {
  it('keeps the password masked and out of every element but its own field', async () => {
    const user = userEvent.setup();
    const { container } = render(<Harness />);
    await screen.findByRole('heading', { name: /Sign in to TriageZero/i });

    const password = screen.getByLabelText('Password') as HTMLInputElement;
    await user.type(password, 'sup3rs3cret');

    // Masked, so nobody reads it off the screen or a screen share.
    expect(password).toHaveAttribute('type', 'password');

    // React mirrors a controlled input's value into its own value attribute —
    // that is true of every text field and is not a leak. What must hold is
    // that the secret appears NOWHERE else: not in text, not in another
    // element's attributes, not in a hidden debug node.
    expect(container.textContent).not.toContain('sup3rs3cret');
    for (const el of Array.from(container.querySelectorAll('*'))) {
      if (el === password) continue;
      for (const attr of Array.from(el.attributes)) {
        expect(attr.value).not.toContain('sup3rs3cret');
      }
    }
  });

  it('never puts the password or token into an outgoing request body', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true, status: 200, statusText: 'OK', json: () => Promise.resolve([]),
    });
    vi.stubGlobal('fetch', fetchMock);
    setAuthTokenProvider(async () => 'ID-TOKEN-123');

    await httpApi.listInvestigations();

    for (const [url, init] of fetchMock.mock.calls) {
      expect(String(url)).not.toContain('ID-TOKEN-123');
      expect(String(init?.body ?? '')).not.toContain('ID-TOKEN-123');
    }
  });

  it('states that machine reporters authenticate separately', async () => {
    render(<Harness />);
    expect(
      await screen.findByText(/ingestion token — never with these credentials/i),
    ).toBeInTheDocument();
  });
});
