import { useEffect, useRef, useState } from 'react';
import { request } from '../api/teams';
import type { Player } from '../api/teams';

interface RiotState {
  refreshing: boolean; message: string;
  profile: null | { riotId: string; iconUrl: string; updatedAt: string; requestedMatches: number;
    rank: null | { tier: string; division: string; lp: number; wins: number; losses: number };
    sample: { games: number; champions: { id: string; name?: string; games: number; wins: number; winRate: number }[] } };
}
export default function RiotPlayerCard({ teamId, player }: { teamId: number; player: Player }) {
  const [state, setState] = useState<RiotState | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(!!player.riotId);
  const [iconFailed, setIconFailed] = useState(false);
  const mounted = useRef(false);
  const endpoint = `/api/teams/${teamId}/players/${player.role}/riot`;
  useEffect(() => {
    mounted.current = true;
    if (player.riotId) request<RiotState>(endpoint).then(data => { if (mounted.current) setState(data); })
      .catch(e => { if (mounted.current) setError(e.message); })
      .finally(() => { if (mounted.current) setLoading(false); });
    return () => { mounted.current = false; };
  }, [endpoint, player.riotId]);
  useEffect(() => {
    if (!state?.refreshing) return;
    let current = true;
    // Poll only our cache/job state, never Riot itself. Keep cached stats visible during refresh.
    const timer = window.setTimeout(() => {
      request<RiotState>(endpoint).then(data => { if (current) { setState(data); setError(''); } })
        .catch(e => { if (current) { setError(e.message); setState(old => old ? { ...old, refreshing: false } : old); } });
    }, 3000);
    return () => { current = false; window.clearTimeout(timer); };
  }, [endpoint, state]);
  async function refresh() {
    setBusy(true); setError('');
    try { const data = await request<RiotState>(endpoint + '/refresh', { method: 'POST' });
      if (mounted.current) { setState(data); setIconFailed(false); }
    } catch (e) { if (mounted.current) setError(e instanceof Error ? e.message : 'Refresh failed.'); }
    finally { if (mounted.current) setBusy(false); }
  }
  const profile = state?.profile;
  const rank = profile?.rank;
  const rankedGames = rank ? rank.wins + rank.losses : 0;
  return <article className="player-card riot-player-card">
    <span className="eyebrow">{player.role} / NA</span>
    {profile && !iconFailed ? <img className="riot-profile-icon" src={profile.iconUrl} alt={`${profile.riotId} profile icon`} onError={() => setIconFailed(true)} />
      : <div className="player-emblem">{player.name ? player.name[0].toUpperCase() : '◇'}</div>}
    <h3>{player.name || 'Unassigned'}</h3>
    <small className="riot-id">{profile?.riotId || player.riotId || 'Add a Riot ID on the Team page'}</small>
    {profile ? <>
      <div className="riot-rank"><small>SOLO / DUO · CURRENT RANKED RECORD</small>
        <strong>{rank ? `${rank.tier} ${rank.division} · ${rank.lp} LP` : 'Unranked'}</strong>
        {rank && <span>{rank.wins}W · {rank.losses}L · {rankedGames ? (100 * rank.wins / rankedGames).toFixed(1) + '%' : '—'} WR</span>}
      </div>
      <div className="riot-champions"><small>RECENT SOLO / DUO</small>
        <p>Up to {profile.requestedMatches} latest matches · {profile.sample.games} games analyzed · remakes excluded</p>
        {profile.sample.champions.map(champion => <div className="riot-champion" key={champion.id}>
          <img src={`/api/champions/${encodeURIComponent(champion.id)}/portrait`} alt="" width="32" height="32" />
          <div><strong>{champion.name || (champion.id === 'MonkeyKing' ? 'Wukong' : champion.id)}</strong>
            <small>{champion.games} games · {champion.wins} wins · {champion.winRate.toFixed(1)}% WR</small></div>
        </div>)}
        {!profile.sample.games && <p>No eligible recent Solo/Duo matches returned.</p>}
      </div>
      <small className="riot-updated">Updated {new Date(profile.updatedAt).toLocaleString()}</small>
    </> : player.riotId && <p className="muted">No synced stats yet. Refresh to fetch this player's Riot profile.</p>}
    <small>{player.champions.length} champions in your saved pool</small>
    {player.riotId && <button className="riot-refresh" disabled={loading || busy || state?.refreshing} aria-label={`Refresh ${player.name}`} onClick={refresh}>
      {loading ? 'Loading cached stats…' : busy || state?.refreshing ? 'Refreshing…' : 'Refresh Riot stats'}</button>}
    {state?.refreshing && <small role="status">{state.message}</small>}
    {(error || (!state?.refreshing && state?.message)) && <p className="error" role="alert">{error || state?.message}</p>}
  </article>;
}
