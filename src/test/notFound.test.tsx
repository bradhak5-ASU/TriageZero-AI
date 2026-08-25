import { screen } from '@testing-library/react';
import { renderApp } from './utils';

describe('Unknown routes', () => {
  it('renders the not-found page', async () => {
    renderApp('/this/route/does/not/exist');
    expect(await screen.findByText('404 — page not found')).toBeInTheDocument();
    const links = screen.getAllByRole('link', { name: /command center/i });
    expect(links.length).toBeGreaterThan(0);
    expect(links.every((l) => l.getAttribute('href') === '/')).toBe(true);
  });
});
