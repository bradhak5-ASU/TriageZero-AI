import { screen } from '@testing-library/react';
import { renderApp } from './utils';

describe('Command Center', () => {
  it('renders KPI cards and investigation data from the mock API', async () => {
    renderApp('/');

    expect(await screen.findByRole('heading', { name: 'Command Center' })).toBeInTheDocument();

    // KPI cards
    expect(screen.getByText('Investigations today')).toBeInTheDocument();
    expect(screen.getByText('Currently processing')).toBeInTheDocument();
    expect(screen.getByText('Block-release failures')).toBeInTheDocument();
    expect(screen.getByText('Average confidence')).toBeInTheDocument();

    // featured critical failure from mock data
    expect(await screen.findByText('Latest critical failure')).toBeInTheDocument();
    expect(
      (await screen.findAllByText('successful checkout shows confirmation page')).length,
    ).toBeGreaterThan(0);

    // recent investigations table renders rows
    expect((await screen.findAllByText('product search returns results')).length).toBeGreaterThan(0);
  });

  it('shows the investigation queue with processing stages', async () => {
    renderApp('/');
    expect(await screen.findByText('Investigation queue')).toBeInTheDocument();
    expect((await screen.findAllByText('Similarity search')).length).toBeGreaterThan(0);
  });
});
