import { useCallback, useEffect, useState } from 'react';
import { listGames } from '../api/games';
import type { Game } from '../api/games';
import { formatLabel } from '../draft/rules';
import SavedLineups from './SavedLineups';
export default function GameHistory({ teamId, onPending, onBusy }: { teamId: number;
  onPending?: (value: boolean) => void; onBusy?: (value: boolean) => void }) {
  const [edits, setEdits] = useState<Record<number, { dirty: boolean; busy: boolean }>>({});
  const report = useCallback((id: number, dirty: boolean, busy: boolean) => {
    setEdits(prev => prev[id]?.dirty === dirty && prev[id]?.busy === busy ? prev : { ...prev, [id]: { dirty, busy } });
  }, []);
  useEffect(() => { onPending?.(Object.values(edits).some(e => e.dirty)); onBusy?.(Object.values(edits).some(e => e.busy)); }, [edits, onPending, onBusy]);
  useEffect(() => () => { onPending?.(false); onBusy?.(false); }, [onPending, onBusy]);
  const [games, setGames] = useState<Game[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let current = true;
    listGames(teamId).then(data => { if (current) { setGames(data); setLoading(false); } })
      .catch(e => { if (current) { setError(e.message); setLoading(false); } });
    return () => { current = false; };
  }, [teamId, retry]);
  if (loading) return <p role="status">Loading battle records…</p>;
  if (error) return <p role="alert">{error} <button onClick={() => { setLoading(true); setError(''); setRetry(n => n + 1); }}>Retry history</button></p>;
  if (!games.length) return <section className="panel empty"><h2>No battles recorded yet.</h2><p>Complete a draft, then record its win or loss. Your team's games will appear here.</p></section>;
  return <div className="game-history">
    <p className="muted">{games.length} recorded games · {games.filter(g => g.result === 'WIN').length} wins · Manual records, not Riot-verified results.</p>
    {games.map(game => <article className="panel game-record" key={game.id}>
      <div className="section-heading"><div><span className={'result-badge ' + game.result.toLowerCase()}>{game.result}</span>
        <h2>{game.roster.name}</h2></div><time dateTime={game.recordedAt}>{new Date(game.recordedAt).toLocaleString()}</time></div>
      <p>{formatLabel(game.format)} · {game.side} side · Patch {game.patch}</p>
      <SavedLineups game={game} onState={report} onSaved={updated => setGames(items => items.map(item => item.id === updated.id ? updated : item))} />
      <details><summary>Saved roster and draft sequence</summary>
        <p className="muted">Roster snapshot at recording time. Pick order does not assign champions to lanes.</p>
        <ul>{game.roster.players.map(p => <li key={p.role}>{p.role}: {p.name || 'Unassigned'}</li>)}</ul>
        <ol>{game.actions.map((a,n) => <li key={n}>{a.side} {a.kind.toLowerCase()}: {a.championId ? game.championNames[a.championId] ?? a.championId : 'No ban'}</li>)}</ol>
      </details>
    </article>)}
  </div>;
}
