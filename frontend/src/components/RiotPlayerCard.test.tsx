import { cleanup, render, screen, waitFor } from '@testing-library/react';
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
  await waitFor(() => expect(screen.getByRole('button',{name:'Refresh Ed'})).toBeEnabled());
});
it('shows split wins, mastery and eight champions with an expansion control', async () => {
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({refreshing:false,message:'',profile:{
    riotId:'Ed#NA1',iconUrl:'',rank:null,highestRank:{tier:'DIAMOND',division:'I',lp:53,mode:'Ranked 5s'},
    splitStart:'2026-07-29T19:00:00Z',splitComplete:true,splitWins:6,mastery:[{id:'Ashe',level:25,points:250000}],
    queues:[400,420,440,710],requestedMatches:0,updatedAt:'2026-09-06T07:00:00Z',
    sample:{games:10,modeGames:{'400':10},champions:Array.from({length:9},(_,i)=>({id:`Champion${i}`,games:1,wins:1,winRate:100}))}
  }}))));
  render(<RiotPlayerCard teamId={1} player={{role:'BOT',name:'Ed',riotId:'Ed#NA1',champions:[]}} />);
  expect(await screen.findByText(/6W · 4L · 60.0%/)).toBeInTheDocument();
  expect(screen.getByText(/Ranked 5s · Highest current rank/i)).toBeInTheDocument();
  expect(screen.getByText(/250,000/)).toBeInTheDocument();
  expect(screen.getByText('Most played champion')).toBeInTheDocument();
  expect(screen.queryByText(/games analyzed|remakes excluded|Available split history|Normal Draft:/)).not.toBeInTheDocument();
  expect(screen.queryByText('Champion8')).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button',{name:'Show all 9 champions'}));
  expect(screen.getByText('Champion8')).toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Refresh Ed'})).toHaveAttribute('title','Refresh Riot stats');
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
  expect(screen.getByText('Ashe')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button',{name:'Refresh Ed'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Riot key expired.');
  expect(screen.getByText('DIAMOND III · 59 LP')).toBeInTheDocument();
});
it('keeps the champion section compact for older combined samples', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({refreshing:false,message:'',profile:{
    riotId:'Ed#NA1',iconUrl:'',rank:null,requestedMatches:100,queues:[400,420,440,710],scannedMatches:130,historyScanLimited:false,
    sample:{games:100,champions:[],modeGames:{'400':70,'420':10,'440':5,'710':15}},updatedAt:'2026-09-06T07:00:00Z'
  }}))));
  render(<RiotPlayerCard teamId={1} player={{role:'BOT',name:'Ed',riotId:'Ed#NA1',champions:[]}} />);
  expect(await screen.findByText('Most played champion')).toBeInTheDocument();
  expect(screen.queryByText(/games analyzed|Normal Draft:|Ranked 5s:/)).not.toBeInTheDocument();
  expect(screen.getByText('Unranked')).toBeInTheDocument();
});
