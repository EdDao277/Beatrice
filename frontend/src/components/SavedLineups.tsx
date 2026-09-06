import { useEffect, useState } from 'react';
import { saveAssignments } from '../api/games';
import type { Game, Assignment } from '../api/games';
import { roles } from '../api/teams';
import type { Role } from '../api/teams';
import type { Side } from '../draft/rules';

export default function SavedLineups({ game, onSaved, onState }: { game: Game; onSaved: (game: Game) => void;
  onState?: (id: number, dirty: boolean, busy: boolean) => void }) {
  const [assignments, setAssignments] = useState<Assignment[]>(game.assignments ?? []);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const dirty = JSON.stringify(assignments) !== JSON.stringify(game.assignments ?? []);
  useEffect(() => { onState?.(game.id, dirty, busy); }, [game.id, dirty, busy, onState]);
  useEffect(() => () => { onState?.(game.id, false, false); }, [game.id, onState]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (dirty) { event.preventDefault(); event.returnValue = ''; } };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);
  function assign(side: Side, championId: string, role: string) {
    // No role means genuinely unknown, not an assumed default based on pick order.
    const others = assignments.filter(a => !(a.side === side && a.championId === championId));
    setAssignments(role ? [...others, { side, championId, role: role as Role }] : others);
    setMessage('');
  }
  async function save() {
    setBusy(true); setError('');
    try { onSaved(await saveAssignments(game, assignments)); setMessage('Lineup saved.'); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to save lineup.'); }
    finally { setBusy(false); }
  }
  return <section className="lineup-editor" aria-label="Final lineup">
    <div className="history-compositions">{(['BLUE', 'RED'] as const).map(side => <section key={side}>
      <h3>{side} · {game.side === side ? 'Your team' : 'Opponent'}</h3>
      <div className="compact-lineup-picks">{game.actions.filter(a => a.kind === 'PICK' && a.side === side && a.championId).map(a => {
        const id = a.championId!;
        const selected = assignments.find(item => item.side === side && item.championId === id)?.role ?? '';
        return <label className="compact-lineup-pick" key={id}>
          <img src={`/api/champions/${id}/portrait`} alt="" width="48" height="48" />
          <span>{game.championNames[id] ?? id}</span>
          <select disabled={busy} aria-label={`${side} ${game.championNames[id] ?? id} role`} value={selected} onChange={e => assign(side, id, e.target.value)}>
            <option value="">Unknown</option>
            {roles.map(role => <option key={role} value={role} disabled={assignments.some(item => item.side === side && item.role === role && item.championId !== id)}>
              {role}
            </option>)}
          </select>
        </label>;
      })}</div>
      <small>Bans: {game.actions.filter(a => a.kind === 'BAN' && a.side === side).map(a => a.championId ? game.championNames[a.championId] ?? a.championId : 'No ban').join(', ') || 'None'}</small>
    </section>)}</div>
    <small className="muted">Final lanes after swaps · Leave uncertain roles Unknown.</small>
    <button className="primary" disabled={busy || !dirty} onClick={save}>{busy ? 'Saving lineup…' : 'Save lineup'}</button>
    <button disabled={busy || !dirty} onClick={() => { setAssignments(game.assignments ?? []); setError(''); setMessage(''); }}>Discard lineup edits</button>
    {message && <p role="status">{message}</p>}{error && <p role="alert">{error}</p>}
  </section>;
}
