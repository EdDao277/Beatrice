import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import useDraftAdvice from './useDraftAdvice';
import DraftBoard from './DraftBoard';
import { roles } from '../api/teams';
import type { Action, Side } from '../draft/rules';
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const catalog = { version: 'test', champions: Array.from({ length: 6 }, (_, i) => ({ id: `C${i}`, name: `Champion ${i}`, portrait: `/${i}.png` })) };
const reply = { bans: catalog.champions.map(c => ({ championId: c.id, basis: 'POOL_COMPOSITION_FALLBACK' })) };
function Harness({ side = 'BLUE', actions = [], select = vi.fn(), disabled = false }: {side?: Side; actions?: Action[]; select?: (id: string) => void; disabled?: boolean}) {
  const advice = useDraftAdvice({ format: 'TOURNAMENT', actions, side, team: { id: 1, version: 0, name: 'Team', players: [] }, catalog,
    onSelect: select, disabled: true, banDisabled: disabled });
  return advice.left;
}
it('requests only bans, shows six portraits and selects without locking', async () => {
  const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => reply });vi.stubGlobal('fetch', fetcher);
  const select = vi.fn();render(<Harness select={select} />);
  await userEvent.click(await screen.findByRole('button', { name: 'Suggest ban Champion 0' }));
  expect(screen.getAllByRole('button')).toHaveLength(6);
  expect(select).toHaveBeenCalledWith('C0');expect(fetcher).toHaveBeenCalledTimes(1);
  expect(fetcher.mock.calls[0][0]).toBe('/api/teams/1/draft/bans');
  expect(screen.getByText(/Lower-confidence pool/)).toBeInTheDocument();
});
it('hides stale bans immediately and respects disabled opponent turns', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => reply }));
  const { rerender } = render(<Harness disabled />);
  expect(await screen.findByRole('button', { name: 'Suggest ban Champion 0' })).toBeDisabled();
  rerender(<Harness side="RED" />);
  expect(screen.queryByRole('button', { name: 'Suggest ban Champion 0' })).not.toBeInTheDocument();
});
it('reports failure safely and allows manual drafting', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('private stack')));render(<Harness />);
  expect(await screen.findByText(/Ban suggestions unavailable. You can continue drafting/)).toBeInTheDocument();
  expect(screen.queryByText(/private stack/)).not.toBeInTheDocument();
});
it('manual ban confirmation still works after the recommendation endpoint fails', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));
  render(<DraftBoard team={{ id: 1, version: 0, name: 'Team', players: roles.map(role => ({ role, name: 'Player', riotId: '', champions: [] })) }}
    catalog={catalog} onPending={vi.fn()} onBusy={vi.fn()} onRecorded={vi.fn()} />);
  await screen.findByText(/Ban suggestions unavailable/);
  await userEvent.click(screen.getByRole('button', { name: 'Champion 0' }));
  await userEvent.click(screen.getByRole('button', { name: 'Confirm ban' }));
  expect(screen.getByRole('button', { name: 'Champion 0' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Undo last action' })).toBeEnabled();
});
it('does not fill sparse results with invented recommendations', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ bans: reply.bans.slice(0, 1) }) }));
  render(<Harness />);
  await screen.findByRole('button', { name: 'Suggest ban Champion 0' });
  expect(screen.getAllByRole('button')).toHaveLength(1);
});
it('treats malformed responses as unavailable rather than breaking the draft', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ bans: [null] }) }));
  render(<Harness />);
  expect(await screen.findByText(/Ban suggestions unavailable/)).toBeInTheDocument();
});
