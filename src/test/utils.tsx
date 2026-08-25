import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../app/AppRoutes';
import { InvestigationsProvider } from '../context/InvestigationsContext';
import { SettingsProvider } from '../context/SettingsContext';
import { ToastProvider } from '../context/ToastContext';

export function renderApp(initialPath = '/') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <SettingsProvider>
        <ToastProvider>
          <InvestigationsProvider>
            <AppRoutes />
          </InvestigationsProvider>
        </ToastProvider>
      </SettingsProvider>
    </MemoryRouter>,
  );
}
