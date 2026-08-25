import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderApp } from './utils';

// first page of results (newest first) contains INV-2035
const FIRST_PAGE_TEST = 'mini-cart badge shows item count';

describe('Investigations page filters', () => {
  it('filters by search text', async () => {
    const user = userEvent.setup();
    renderApp('/investigations');

    expect((await screen.findAllByText(FIRST_PAGE_TEST)).length).toBeGreaterThan(0);

    await user.type(screen.getByLabelText('Search'), 'wishlist');

    await waitFor(() => {
      expect(screen.getByText(/1 result/)).toBeInTheDocument();
    });
    expect(screen.getByText('wishlist persists for logged-in user')).toBeInTheDocument();
    expect(screen.queryByText(FIRST_PAGE_TEST)).not.toBeInTheDocument();
  });

  it('filters by status and clears all filters', async () => {
    const user = userEvent.setup();
    renderApp('/investigations');

    await screen.findAllByText(FIRST_PAGE_TEST);

    await user.selectOptions(screen.getByLabelText('Status'), 'needs_review');
    await waitFor(() => {
      expect(screen.getByText(/1 result/)).toBeInTheDocument();
    });
    expect(screen.getByText('payment iframe loads on checkout')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /clear all/i }));
    await waitFor(() => {
      expect(screen.queryByText(/\(filtered\)/)).not.toBeInTheDocument();
    });
  });

  it('shows an empty state when nothing matches', async () => {
    const user = userEvent.setup();
    renderApp('/investigations');

    await screen.findAllByText(FIRST_PAGE_TEST);
    await user.type(screen.getByLabelText('Search'), 'zzz-no-such-test');

    expect(await screen.findByText('No matching investigations')).toBeInTheDocument();
  });
});
