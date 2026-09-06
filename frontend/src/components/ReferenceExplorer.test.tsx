import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import ReferenceExplorer from './ReferenceExplorer';
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
it('requests an explicit data slice and labels sparse observations', async () => {
  const fetchMock = vi.fn().mockImplementation((url: string) => Promise.resolve(new Response(JSON.stringify(url.endsWith('/options')
    ? { importId: 1, slices: [{ patch: '16.15', queueId: 420, region: 'americas', source: 'general-network' }] }
    : { roles: ['MID', 'SUPPORT'], roleStats: [], synergies: [{ role: 'MID', partnerId: 'Ashe', partnerRole: 'BOT', games: 5, wins: 4, winRate: .8, delta: .1, tier: null }] }))));
  vi.stubGlobal('fetch', fetchMock);
  render(<ReferenceExplorer catalog={{ version: '16.17.1', champions: [{ id: 'Swain', name: 'Swain', portrait: '' }, { id: 'Ashe', name: 'Ashe', portrait: '' }] }} />);
  await screen.findByLabelText('Reference role');
  await userEvent.selectOptions(screen.getByLabelText('Reference role'), 'MID');
  expect(await screen.findByText('4 / 5')).toBeInTheDocument();
  expect(screen.getByText(/Very small sample/)).toBeInTheDocument();
  expect(fetchMock.mock.calls.at(-1)![0]).toContain('patch=16.15&queueId=420&region=americas&source=general-network&role=MID');
  expect(screen.getByText(/No role statistic/)).toBeInTheDocument();
});
