import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import useDraftAdvice from './useDraftAdvice';
import type { Action, Side } from '../draft/rules';
import type { Team } from '../api/teams';
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const team: Team = { id: 1, version: 0, name: 'Team', players: [] };
const catalog = { version: 'test', champions: [{ id: 'Swain', name: 'Swain', portrait: '/swain.png' }] };
const bans: Action[] = Array.from({ length: 10 }, (_, i) => ({ kind: 'BAN', side: i < 5 ? 'BLUE' : 'RED', championId: null }));
const response = { requestId: 'r', modelVersion: 'recency-2026-09-14', picks: [
  { championId: 'Swain', javaScore: 80, mlBonus: 2.5, score: 82.5, mlEvidenceQuality: 'SUPPORTED' },
] };
function Harness({ actions = bans, side = 'BLUE', select = vi.fn() }: { actions?: Action[]; side?: Side; select?: (id: string) => void }) {
  const advice = useDraftAdvice({ format: 'RANKED', actions, team, catalog, side, onSelect: select, disabled: false });
  return <>{advice.left}{advice.right}</>;
}
it('shows real pick portraits without role controls or internal scores and does not lock automatically', async () => {
  const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => response });
  vi.stubGlobal('fetch', fetcher);
  const select = vi.fn();
  render(<Harness select={select} />);
  await userEvent.click(await screen.findByRole('button', { name: 'Suggest Swain' }));
  expect(select).toHaveBeenCalledWith('Swain');
  expect(screen.queryAllByRole('combobox')).toHaveLength(0);
  expect(screen.queryByText(/82.5/)).not.toBeInTheDocument();
  expect(fetcher.mock.calls[0][0]).toBe('/api/teams/1/draft/picks');
  const payload = JSON.parse(fetcher.mock.calls[0][1].body);
  expect(payload.targetRole).toBeUndefined();
  expect(payload.actions).toEqual(bans);
  expect(fetcher).toHaveBeenCalledTimes(1);
});
it('keeps drafting usable on request failure without leaking internal errors', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('private stack trace')));
  render(<Harness />);
  expect(await screen.findByText(/Pick suggestions unavailable/)).toBeInTheDocument();
  expect(screen.queryByText(/private stack/)).not.toBeInTheDocument();
});
it('does not request picks during bans and clears stale suggestions when side changes', async () => {
  const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => response });
  vi.stubGlobal('fetch', fetcher);
  const { rerender } = render(<Harness actions={[]} />);
  expect(screen.getByText('Ban phase')).toBeInTheDocument();
  expect(fetcher).not.toHaveBeenCalled();
  rerender(<Harness />);
  await screen.findByRole('button', { name: 'Suggest Swain' });
  fetcher.mockImplementation(() => new Promise(() => {}));
  rerender(<Harness side="RED" />);
  expect(screen.queryByRole('button', { name: 'Suggest Swain' })).not.toBeInTheDocument();
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
});
