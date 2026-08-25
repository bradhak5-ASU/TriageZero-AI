import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderApp } from './utils';

describe('Investigation detail', () => {
  it('displays classification, decision summary, and root cause', async () => {
    renderApp('/investigations/INV-2041');

    expect(
      await screen.findByRole('heading', { name: 'successful checkout shows confirmation page' }),
    ).toBeInTheDocument();

    expect((await screen.findAllByText('Backend Defect')).length).toBeGreaterThan(0);
    expect(screen.getAllByText('Block Release').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Critical').length).toBeGreaterThan(0);
    expect(screen.getByText('93%')).toBeInTheDocument();

    expect(screen.getByRole('heading', { name: 'Root cause' })).toBeInTheDocument();
    expect(screen.getByText(/order-creation endpoint throws/)).toBeInTheDocument();
  });

  it('shows evidence tabs with network requests', async () => {
    const user = userEvent.setup();
    renderApp('/investigations/INV-2041');

    await screen.findByRole('heading', { name: 'successful checkout shows confirmation page' });

    // summary tab first
    expect(screen.getByText('Expected HTTP 201 but received HTTP 500')).toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: /network/i }));
    expect(await screen.findByText('/api/v1/orders')).toBeInTheDocument();
    expect(screen.getByText('500')).toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: /console/i }));
    expect(await screen.findByText(/Failed to load resource/)).toBeInTheDocument();
  });

  it('shows a not-found state for unknown investigation IDs', async () => {
    renderApp('/investigations/INV-DOES-NOT-EXIST');
    expect(await screen.findByText('Investigation not found')).toBeInTheDocument();
  });
});
