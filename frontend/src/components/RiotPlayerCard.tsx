import { useEffect, useRef, useState } from 'react';
import { request } from '../api/teams';
import type { Player } from '../api/teams';

interface RiotState {
  refreshing: boolean; message: string;
  profile: null | { riotId: string; iconUrl: string; updatedAt: string; requestedMatches: number;
    queues?: number[] | null; scannedMatches?: number | null; historyScanLimited?: boolean | null;
    highestRank?: null | { tier: string; division: string; lp: number; mode: string };
    splitStart?: string | null; splitComplete?: boolean | null; splitWins?: number | null;
    mastery?: { id: string; level: number; points: number }[] | null;
    rank: null | { tier: string; division: string; lp: number; wins: number; losses: number };
    sample: { games: number; modeGames?: Record<string,number> | null; champions: { id: string; name?: string; games: number; wins: number; winRate: number }[] } };
}
export default function RiotPlayerCard({ teamId, player }: { teamId: number; player: Player }) {
  const [state, setState] = useState<RiotState | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(!!player.riotId);
  const [iconFailed, setIconFailed] = useState(false);
  const [showAll, setShowAll] = useState(false);
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
  const split = !!profile?.splitStart;
  const rank = split ? profile?.highestRank : profile?.rank;
  const legacyRank = profile?.rank;
  const rankedGames = legacyRank ? legacyRank.wins + legacyRank.losses : 0;
  const refreshing = loading || busy || !!state?.refreshing;
  return <article className="player-card riot-player-card">
    <span className="eyebrow">{player.role} / NA</span>
    {profile?.iconUrl && !iconFailed ? <img className="riot-profile-icon" src={profile.iconUrl} alt={`${profile.riotId} profile icon`} onError={() => setIconFailed(true)} />
      : <div className="player-emblem">{player.name ? player.name[0].toUpperCase() : '◇'}</div>}
    <h3>{player.name || 'Unassigned'}</h3>
    <small className="riot-id">{profile?.riotId || player.riotId || 'Add a Riot ID on the Team page'}</small>
    {player.riotId && <button className="riot-refresh" disabled={refreshing} aria-label={`Refresh ${player.name}`}
      title={refreshing ? 'Refreshing Riot stats…' : 'Refresh Riot stats'} aria-busy={refreshing} onClick={refresh}>
      <span aria-hidden="true">↻</span></button>}
    {profile ? <>
      <div className="riot-rank"><small>{split ? `${profile.highestRank?.mode || 'Supported queues'} · Highest current rank` : 'SOLO / DUO · CURRENT RANKED RECORD'}</small>
        <strong>{rank ? `${rank.tier} ${rank.division} · ${rank.lp} LP` : 'Unranked'}</strong>
        {split ? <><small>{profile.splitComplete ? 'COMBINED SPLIT WIN RATE' : 'PARTIAL SPLIT WIN RATE'}</small>
          <span>{profile.splitWins ?? 0}W · {profile.sample.games - (profile.splitWins ?? 0)}L · {profile.sample.games ? (100 * (profile.splitWins ?? 0) / profile.sample.games).toFixed(1) + '%' : '—'} WR</span></>
          : legacyRank && <span>{legacyRank.wins}W · {legacyRank.losses}L · {rankedGames ? (100 * legacyRank.wins / rankedGames).toFixed(1) + '%' : '—'} WR</span>}
      </div>
      {split && <section className="riot-mastery" aria-label="Top champion mastery"><small>TOP MASTERY · ALL TIME</small>
        <div>{profile.mastery?.map(champion => <div key={champion.id} title={`${champion.id}: mastery ${champion.level}, ${champion.points.toLocaleString()} points`}>
          <img src={`/api/champions/${encodeURIComponent(champion.id)}/portrait`} alt={champion.id} width="36" height="36" />
          <small>Level {champion.level}</small><small>{champion.points.toLocaleString()} pts</small>
        </div>)}</div>{!profile.mastery?.length && <p>No mastery returned.</p>}</section>}
      <div className="riot-champions"><small>Most played champion</small>
        <table className="riot-champion-table"><thead><tr><th>Champion</th><th>Games</th><th>WR</th></tr></thead>
        <tbody>{profile.sample.champions.slice(0,showAll ? undefined : 8).map(champion => <tr key={champion.id}><td><div className="riot-champion">
          <img src={`/api/champions/${encodeURIComponent(champion.id)}/portrait`} alt="" width="32" height="32" />
          <div><strong>{champion.name || (champion.id === 'MonkeyKing' ? 'Wukong' : champion.id)}</strong>
            </div></div></td><td>{champion.games}</td><td title={`${champion.wins} wins in ${champion.games} games`}>{champion.winRate.toFixed(1)}%</td></tr>)}</tbody></table>
        {profile.sample.champions.length>8 && <button className="riot-show-all" onClick={() => setShowAll(!showAll)} aria-expanded={showAll}>
          {showAll ? 'Show fewer' : `Show all ${profile.sample.champions.length} champions`}</button>}
        {!profile.sample.games && <p>No eligible recent matches returned for this sample.</p>}
      </div>
      <small className="riot-updated">Updated {new Date(profile.updatedAt).toLocaleString()}</small>
    </> : player.riotId && <p className="muted">No synced stats yet. Refresh to fetch this player's Riot profile.</p>}
    <small>{player.champions.length} champions in your saved pool</small>
    {state?.refreshing && <small role="status">{state.message}</small>}
    {(error || (!state?.refreshing && state?.message)) && <p className="error" role="alert">{error || state?.message}</p>}
  </article>;
}
