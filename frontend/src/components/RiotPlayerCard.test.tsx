import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import RiotPlayerCard from './RiotPlayerCard';
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
it('waits for the initial cache read before enabling refresh', async () => {
  let finish!: (value: Response) => void;
  vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise<Response>(resolve => { finish = resolve; })));
  render(<RiotPlayerCard teamId={1} player={{role:'BOT',name:'Ed',riotId:'Ed#NA1',champions:[]}} />);
  expect(screen.getByRole('button',{name:'Refresh Ed'})).toBeDisabled();
  finish(new Response(JSON.stringify({profile:null,refreshing:false,message:''})));
  expect(await screen.findByText('Refresh Riot stats')).toBeEnabled();
});
it('shows cached rank separately from champion sample and preserves it on refresh failure', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ refreshing:false,message:'',profile:{
    riotId:'Ed#NA1',iconUrl:'https://ddragon.leagueoflegends.com/cdn/16.17.1/img/profileicon/1.png',
    rank:{tier:'DIAMOND',division:'III',lp:59,wins:44,losses:42},sample:{games:2,champions:[{id:'Ashe',games:2,wins:1,winRate:50}]},
    requestedMatches:50,updatedAt:'2026-09-06T07:00:00Z' } })))
    .mockResolvedValueOnce(new Response(JSON.stringify({detail:'Riot key expired.'}),{status:502})));
  render(<RiotPlayerCard teamId={1} player={{role:'BOT',name:'Ed',riotId:'Ed#NA1',champions:[]}} />);
  expect(await screen.findByText('DIAMOND III · 59 LP')).toBeInTheDocument();
  expect(screen.getByText(/44W · 42L · 51.2%/)).toBeInTheDocument();
  expect(screen.getByText(/2 games analyzed/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button',{name:'Refresh Ed'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Riot key expired.');
  expect(screen.getByText('DIAMOND III · 59 LP')).toBeInTheDocument();
});
