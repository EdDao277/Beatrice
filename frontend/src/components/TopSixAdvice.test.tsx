import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import useDraftAdvice from './useDraftAdvice';
import DraftBoard from './DraftBoard';
import userEvent from '@testing-library/user-event';
import { roles } from '../api/teams';
import type { Action } from '../draft/rules';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const catalog = { version: 'test', champions: Array.from({ length: 8 }, (_, i) => ({ id: `C${i}`, name: `Champion ${i}`, portrait: `/${i}.png` })) };
const initialPicks: Action[] = Array.from({ length: 10 }, (_, i) => ({ kind: 'BAN', side: i < 5 ? 'BLUE' : 'RED', championId: null }));
function Harness({ actions }: { actions: Action[] }) {
  return useDraftAdvice({ format: 'RANKED', actions, side: 'BLUE', team: { id: 1, version: 0, name: 'Team', players: [] }, catalog, onSelect: vi.fn(), disabled: false }).left;
}
function reply(kind: 'picks' | 'bans', ids: number[]) {
  return { ok: true, json: async () => kind === 'bans' ? { bans: ids.map(i => ({ championId: `C${i}`, basis: 'EVIDENCE_BACKED' })) }
    : { requestId: 'r', modelVersion: 'frozen', picks: ids.map(i => ({ championId: `C${i}`, javaScore: 60, mlBonus: 0, score: 60, mlEvidenceQuality: 'ML_UNAVAILABLE' })) } };
}
it('allows manual bans and picks while recommendation requests are pending', async () => {
  vi.stubGlobal('fetch', vi.fn().mockImplementation(() => new Promise(() => {})));
  render(<DraftBoard team={{ id: 1, version: 0, name: 'Team', players: roles.map(role => ({ role, name: 'Player', riotId: '', champions: [] })) }}
    catalog={catalog} onPending={vi.fn()} onBusy={vi.fn()} onRecorded={vi.fn()} />);
  for (let i = 0; i < 10; i++) await userEvent.click(screen.getByRole('button', { name: 'No ban' }));
  expect(screen.getByText(/Updating pick suggestions/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Champion 0' }));
  await userEvent.click(screen.getByRole('button', { name: 'Lock in pick' }));
  expect(screen.getByRole('button', { name: 'Champion 0' })).toBeDisabled();
});
it.each(['picks', 'bans'] as const)('shows all six %s in response order without expansion controls', async kind => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(kind, [5, 2, 4, 0, 3, 1])));
  render(<Harness actions={kind === 'picks' ? initialPicks : []} />);
  const buttons = await screen.findAllByRole('button', { name: /Suggest/ });
  expect(buttons.map(b => b.getAttribute('aria-label'))).toEqual([5, 2, 4, 0, 3, 1].map(i => `Suggest ${kind === 'bans' ? 'ban ' : ''}Champion ${i}`));
  buttons.forEach(b => expect(b).toBeVisible());
  expect(screen.queryByRole('button', { name: /more|expand|collapse/i })).not.toBeInTheDocument();
});
it.each(['picks', 'bans'] as const)('updates %s after an action and ignores a late obsolete response', async kind => {
  let resolveOld!: (value: ReturnType<typeof reply>) => void;
  const fetcher = vi.fn().mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve; }))
    .mockResolvedValue(reply(kind, [1, 2, 3, 4, 5, 6]));
  vi.stubGlobal('fetch', fetcher);
  const actions = kind === 'picks' ? initialPicks : [];
  const { rerender } = render(<Harness actions={actions} />);
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
  rerender(<Harness actions={[...actions, { kind: kind === 'picks' ? 'PICK' : 'BAN', side: 'BLUE', championId: 'C0' }]} />);
  await screen.findByRole('button', { name: `Suggest ${kind === 'bans' ? 'ban ' : ''}Champion 1` });
  await act(async () => resolveOld(reply(kind, [0])));
  expect(screen.queryByRole('button', { name: `Suggest ${kind === 'bans' ? 'ban ' : ''}Champion 0` })).not.toBeInTheDocument();
  expect(screen.getAllByRole('button', { name: /Suggest/ })).toHaveLength(6);
});
