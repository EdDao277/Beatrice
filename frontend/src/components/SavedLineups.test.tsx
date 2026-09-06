import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import SavedLineups from './SavedLineups';
import type { Game } from '../api/games';
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
it('leaves flex picks unknown until confirmed and saves a versioned annotation', async () => {
  const game: Game = { id: 1, teamId: 2, format: 'TOURNAMENT', side: 'BLUE', result: 'WIN', patch: '16.17',
    actions: [{ side: 'BLUE', kind: 'PICK', championId: 'Swain' }, { side: 'BLUE', kind: 'PICK', championId: 'Ashe' }],
    roster: { id: 2, name: 'Ravens', version: 0, players: [] }, championNames: { Swain: 'Swain', Ashe: 'Ashe' },
    recordedAt: '', assignments: [], assignmentVersion: 0 };
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ...game, assignmentVersion: 1 })));
  vi.stubGlobal('fetch', fetchMock);
  const state = vi.fn();
  render(<SavedLineups game={game} onSaved={vi.fn()} onState={state} />);
  expect(screen.getByLabelText('BLUE Swain role')).toHaveValue('');
  expect(screen.getByLabelText('BLUE Swain role').closest('label')?.querySelector('img')).toHaveAttribute('src', '/api/champions/Swain/portrait');
  await userEvent.selectOptions(screen.getByLabelText('BLUE Swain role'), 'SUPPORT');
  expect(state).toHaveBeenLastCalledWith(1, true, false);
  const ashe = screen.getByLabelText('BLUE Ashe role');
  expect(Array.from((ashe as HTMLSelectElement).options).find(o => o.value === 'SUPPORT')).toBeDisabled();
  await userEvent.click(screen.getByRole('button', { name: 'Save lineup' }));
  expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ version: 0,
    assignments: [{ side: 'BLUE', championId: 'Swain', role: 'SUPPORT' }] });
});
