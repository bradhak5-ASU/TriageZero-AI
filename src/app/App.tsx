import { AuthProvider } from '../context/AuthContext';
import { RequireAuth } from '../components/layout/RequireAuth';
import { InvestigationsProvider } from '../context/InvestigationsContext';
import { SettingsProvider } from '../context/SettingsContext';
import { ToastProvider } from '../context/ToastContext';
import { AppRoutes } from './AppRoutes';

export function App() {
  return (
    <SettingsProvider>
      <ToastProvider>
        <AuthProvider>
          {/* Investigation data is only fetched once a session exists, so an
              anonymous visitor never triggers an authenticated request. */}
          <RequireAuth>
            <InvestigationsProvider>
              <AppRoutes />
            </InvestigationsProvider>
          </RequireAuth>
        </AuthProvider>
      </ToastProvider>
    </SettingsProvider>
  );
}
