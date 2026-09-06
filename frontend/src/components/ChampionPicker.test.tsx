import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import ChampionPicker from './ChampionPicker';
afterEach(cleanup);
it('searches official names and prevents selecting unavailable champions', async () => {
  const select = vi.fn();
  render(<ChampionPicker champions={[
    { id: 'Swain', name: 'Swain', portrait: '/api/champions/Swain/portrait' },
    { id: 'Ahri', name: 'Ahri', portrait: '/api/champions/Ahri/portrait' },
  ]} unavailable={['Ahri']} onSelect={select} />);
  expect(screen.getByRole('button', { name: 'Ahri' })).toBeDisabled();
  await userEvent.type(screen.getByRole('searchbox'), 'swA');
  expect(screen.queryByRole('button', { name: 'Ahri' })).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Swain' }));
  expect(select).toHaveBeenCalledWith('Swain');
});
