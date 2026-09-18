import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import DraftBoard from './DraftBoard';
import { roles } from '../api/teams';
const team = { id: 1, name: 'Ravens', version: 0, players: roles.map(role => ({ role, name: 'Ed', riotId: '', champions: [] })) };
const catalog = { version: 'test', champions: Array.from({length: 20}, (_, n) => ({ id: 'C'+n, name: 'Champion '+n, portrait: '/C'+n+'.png' })) };
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
it('locks a selection, undoes it, and confirms a format reset', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('[]')));
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
  render(<DraftBoard team={team} catalog={catalog} onPending={vi.fn()} onBusy={vi.fn()} onRecorded={vi.fn()} />);
  await userEvent.click(screen.getByRole('button', { name: 'Champion 0' }));
  await userEvent.click(screen.getByRole('button', { name: 'Confirm ban' }));
  expect(screen.getByRole('button', { name: 'Champion 0' })).toBeDisabled();
  await userEvent.click(screen.getByRole('button', { name: 'Tournament' }));
  expect(confirm).toHaveBeenCalled();
  expect(screen.getByRole('button', { name: 'Champion 0' })).toBeDisabled();
  await userEvent.click(screen.getByRole('button', { name: 'Undo last action' }));
  expect(screen.getByRole('button', { name: 'Champion 0' })).toBeEnabled();
  expect(screen.getByRole('button', { name: 'Record win' })).toBeDisabled();
});
it('records a completed tournament and retries an uncertain save with the same payload', async () => {
  const fetchMock = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(new Response(JSON.stringify({ id: 4 })));
  vi.stubGlobal('fetch', (url: string, options?: RequestInit) => {
    if (url.endsWith('/draft/picks')) return Promise.resolve(new Response(JSON.stringify({ requestId: 'r', picks: [] })));
    if (url.endsWith('/draft/picks/selected')) return Promise.resolve(new Response(null, { status: 204 }));
    return url.includes('/datasets') ? Promise.resolve(new Response('[]')) : fetchMock(url, options);
  });
  render(<DraftBoard team={team} catalog={catalog} onPending={vi.fn()} onBusy={vi.fn()} onRecorded={vi.fn()} />);
  await userEvent.click(screen.getByRole('button', { name: 'Tournament' }));
  for (let n=0; n<20; n++) {
    await userEvent.click(screen.getByRole('button', { name: 'Champion '+n }));
    await userEvent.click(screen.getByRole('button', { name: n<6 || (n>=12 && n<16) ? 'Confirm ban' : 'Lock in pick' }));
  }
  await userEvent.click(screen.getByRole('button', { name: 'Record win' }));
  expect(await screen.findByRole('alert')).toHaveTextContent(/connect/i);
  await userEvent.click(screen.getByRole('button', { name: 'Retry recording' }));
  expect(await screen.findByText(/Result saved/)).toBeInTheDocument();
  expect(fetchMock.mock.calls[0][1].body).toBe(fetchMock.mock.calls[1][1].body);
  expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toMatchObject({ format: 'TOURNAMENT', result: 'WIN', side: 'BLUE' });
  expect(screen.getByRole('button', { name: 'Record loss' })).toBeDisabled();
});
it('records an actual allied lock-in against the displayed recommendation request', async () => {
  const selected = vi.fn();
  vi.stubGlobal('fetch', (url: string, options?: RequestInit) => {
    if (url.endsWith('/selected')) {
      selected(JSON.parse(String(options?.body)));
      return Promise.resolve(new Response(null, { status: 204 }));
    }
    return Promise.resolve(new Response(JSON.stringify({ requestId: 'trace', picks: [
      { championId: 'C0', javaScore: 67.5, mlBonus: 0, score: 67.5, mlEvidenceQuality: 'ML_UNAVAILABLE' },
    ] })));
  });
  render(<DraftBoard team={team} catalog={catalog} onPending={vi.fn()} onBusy={vi.fn()} onRecorded={vi.fn()} />);
  for (let n = 0; n < 10; n++) await userEvent.click(screen.getByRole('button', { name: 'No ban' }));
  await userEvent.click(await screen.findByRole('button', { name: 'Suggest Champion 0' }));
  expect(selected).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole('button', { name: 'Lock in pick' }));
  expect(selected).toHaveBeenCalledWith({ requestId: 'trace', championId: 'C0' });
});
