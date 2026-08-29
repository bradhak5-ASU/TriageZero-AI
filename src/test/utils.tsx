import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../app/AppRoutes';
import { AuthProvider } from '../context/AuthContext';
import { RequireAuth } from '../components/layout/RequireAuth';
import { InvestigationsProvider } from '../context/InvestigationsContext';
import { SettingsProvider } from '../context/SettingsContext';
import { ToastProvider } from '../context/ToastContext';

/**
 * Renders the real provider tree from App.tsx so tests exercise the same
 * composition users get. Firebase has no VITE_FIREBASE_* config under Vitest,
 * so AuthProvider settles on `unconfigured` and RequireAuth runs open — which
 * is exactly local demo mode, and keeps these suites offline.
 */
export function renderApp(initialPath = '/') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <SettingsProvider>
        <ToastProvider>
          <AuthProvider>
            <RequireAuth>
              <InvestigationsProvider>
                <AppRoutes />
              </InvestigationsProvider>
            </RequireAuth>
          </AuthProvider>
        </ToastProvider>
      </SettingsProvider>
    </MemoryRouter>,
  );
}
