import { fireEvent, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderApp } from './utils';
import { sampleFailurePackage } from '../data/samplePackage';

describe('Ingest Failure page', () => {
  it('accepts a valid package in mock mode and creates an investigation', async () => {
    const user = userEvent.setup();
    renderApp('/ingest');

    await user.click(await screen.findByRole('button', { name: /load sample/i }));
    expect(await screen.findByText('Package is valid and ready to submit.')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /submit package/i }));

    // navigates to the created investigation's detail page
    expect(
      await screen.findByRole(
        'heading',
        { name: 'successful checkout shows confirmation page' },
        { timeout: 4000 },
      ),
    ).toBeInTheDocument();

    // and it is persisted locally for demo mode
    const stored = window.localStorage.getItem('triagezero.created.v1');
    expect(stored).toBeTruthy();
    expect(JSON.parse(stored!)[0].id).toMatch(/^INV-/);
  });

  it('warns loudly about forbidden oracle fields', async () => {
    const user = userEvent.setup();
    renderApp('/ingest');

    const poisoned = JSON.stringify({
      ...sampleFailurePackage,
      expected_severity: 'critical',
      controlled_defect: true,
    });

    const editor = await screen.findByLabelText('Failure package JSON');
    fireEvent.change(editor, { target: { value: poisoned } });
    await user.click(screen.getByRole('button', { name: /validate package/i }));

    expect(await screen.findByText('Private QA-oracle fields rejected')).toBeInTheDocument();
    expect(screen.getByText('expected_severity')).toBeInTheDocument();
    expect(screen.getByText('controlled_defect')).toBeInTheDocument();

    // submission stays disabled
    expect(screen.getByRole('button', { name: /submit package/i })).toBeDisabled();
  });
});
