import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderApp } from './utils';
import { SETTINGS_KEY } from '../context/SettingsContext';

describe('Settings persistence', () => {
  it('applies and persists the theme choice', async () => {
    const user = userEvent.setup();
    const { unmount } = renderApp('/settings');

    await screen.findByRole('heading', { name: 'Settings' });
    expect(document.documentElement.dataset.theme).toBe('dark');

    await user.selectOptions(screen.getByLabelText('Theme'), 'light');

    await waitFor(() => {
      expect(document.documentElement.dataset.theme).toBe('light');
    });
    expect(window.localStorage.getItem(SETTINGS_KEY)).toContain('"theme":"light"');

    // a fresh mount picks the stored value back up
    unmount();
    renderApp('/settings');
    expect(
      (await screen.findByLabelText<HTMLSelectElement>('Theme')).value,
    ).toBe('light');
  });

  it('persists refresh interval and notification preferences', async () => {
    const user = userEvent.setup();
    renderApp('/settings');

    await user.selectOptions(await screen.findByLabelText('Auto-refresh interval'), '300');
    expect(window.localStorage.getItem(SETTINGS_KEY)).toContain('"refreshIntervalSec":300');

    const completed = screen.getByRole('checkbox', { name: /completed investigations/i });
    await user.click(completed);
    expect(window.localStorage.getItem(SETTINGS_KEY)).toContain('"completed":true');
  });
});
