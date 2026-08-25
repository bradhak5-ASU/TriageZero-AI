import { InvestigationsProvider } from '../context/InvestigationsContext';
import { SettingsProvider } from '../context/SettingsContext';
import { ToastProvider } from '../context/ToastContext';
import { AppRoutes } from './AppRoutes';

export function App() {
  return (
    <SettingsProvider>
      <ToastProvider>
        <InvestigationsProvider>
          <AppRoutes />
        </InvestigationsProvider>
      </ToastProvider>
    </SettingsProvider>
  );
}
