import { useCallback, useEffect, useState } from 'react';
import type { Team } from '../api/teams';
import type { Catalog } from '../api/champions';
import { recordGame } from '../api/games';
import type { Game, GameRequest } from '../api/games';
import SavedLineups from './SavedLineups';
import { appendAction, formatLabel, nextTurn, unavailable } from '../draft/rules';
import type { Action, Format, Side } from '../draft/rules';
import ChampionPicker from './ChampionPicker';

interface Props {
  team: Team; catalog: Catalog; onPending: (pending: boolean) => void;
  onBusy: (busy: boolean) => void; onRecorded: () => void;
}
export default function DraftBoard({ team, catalog, onPending, onBusy, onRecorded }: Props) {
  const [format, setFormat] = useState<Format>('RANKED');
  const [side, setSide] = useState<Side>('BLUE');
  const [banSide, setBanSide] = useState<Side>('BLUE');
  const [actions, setActions] = useState<Action[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [savedGame, setSavedGame] = useState<Game | null>(null);
  const [lineupDirty, setLineupDirty] = useState(false);
  const [lineupBusy, setLineupBusy] = useState(false);
  const reportLineup = useCallback((_id: number, dirty: boolean, saving: boolean) => { setLineupDirty(dirty); setLineupBusy(saving); }, []);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState<GameRequest | null>(null);
  const turn = nextTurn(format, actions);
  const actingSide = turn?.side ?? banSide;
  // Freeze a save attempt until it is acknowledged; retries reuse its UUID and payload.
  const locked = busy || saved || attempt !== null;
  const blocked = unavailable(format, actions, actingSide);
  useEffect(() => { onPending((actions.length > 0 && !saved) || lineupDirty); }, [actions.length, saved, lineupDirty, onPending]);
  useEffect(() => { onBusy(busy || lineupBusy); }, [busy, lineupBusy, onBusy]);
  const champion = (id: string | null) => catalog.champions.find(c => c.id === id);
  const shortlist = team.players.flatMap(p => p.champions.map(c => ({ ...c, player: p.name || p.role,
    entry: catalog.champions.find(entry => entry.name.toLowerCase() === c.name.toLowerCase()) })))
    .filter(c => c.entry && !actions.some(a => a.championId === c.entry!.id))
    .sort((a,b) => b.comfort - a.comfort).slice(0, 5);

  function reset(nextFormat = format) {
    if (lineupBusy || (lineupDirty && !window.confirm('Discard unsaved lineup edits and start a new draft?'))) return;
    if (!saved && actions.length && !window.confirm(attempt
      ? 'A recording may already have reached the server. Check History before starting another. Reset this draft?'
      : 'Reset this draft? All current picks and bans will be cleared.')) return;
    setFormat(nextFormat); setActions([]); setSelected(null); setSaved(false); setSavedGame(null); setAttempt(null); setError(''); setBanSide('BLUE');
  }
  function confirm(id: string | null) {
    if (locked) return;
    try {
      const next = appendAction(format, actions, actingSide, id);
      setActions(next); setSelected(null); setError('');
      if (format === 'RANKED' && next.length < 10 && next.filter(a => a.side === actingSide).length === 5)
        setBanSide(actingSide === 'BLUE' ? 'RED' : 'BLUE');
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to select.'); }
  }
  async function save(result: 'WIN' | 'LOSS') {
    if (busy || saved || turn) return;
    const payload = attempt ?? { requestId: crypto.randomUUID(), format, side, result, patch: catalog.version, actions };
    setAttempt(payload); setBusy(true); onBusy(true); setError('');
    try { setSavedGame(await recordGame(team.id, payload)); setSaved(true); onRecorded(); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to record game.'); }
    finally { setBusy(false); onBusy(false); }
  }
  function teamColumn(column: Side) {
    const picks = actions.filter(a => a.side === column && a.kind === 'PICK');
    const bans = actions.filter(a => a.side === column && a.kind === 'BAN');
    return <section className={'draft-team ' + column.toLowerCase()} aria-label={column + ' selections'}>
      <span className="eyebrow">{column} SIDE</span>
      <h3>{side === column ? team.name : 'Opponent'}</h3>
      <div className="ban-slots" aria-label={column + ' bans'}>{Array.from({ length: 5 }, (_, n) =>
        <div className="ban-slot" key={n} title={bans[n] ? champion(bans[n].championId)?.name ?? 'No ban' : 'Empty ban slot'}>
          {bans[n]?.championId ? <img alt={champion(bans[n].championId)?.name} src={champion(bans[n].championId)?.portrait} /> : bans[n] ? '—' : '⊘'}
        </div>)}</div>
      {Array.from({ length: 5 }, (_, n) => <div className={'pick-slot' + (turn?.kind === 'PICK' && actingSide === column && picks.length === n ? ' current' : '')} key={n}>
        <div className="pick-portrait">{picks[n] ? <img src={champion(picks[n].championId)?.portrait} alt="" /> : <span>◇</span>}</div>
        <div><small>PICK {n + 1}</small><strong>{picks[n] ? champion(picks[n].championId)?.name : 'Awaiting pick'}</strong></div>
      </div>)}
      <p className="muted draft-note">Selection order, not lane assignment. Players can trade picks in the client.</p>
    </section>;
  }
  return <section className="draft-command">
    <div className="draft-toolbar">
      <div className="format-toggle" role="group" aria-label="Draft format">
        {(['RANKED', 'TOURNAMENT'] as const).map(mode => <button key={mode} aria-pressed={mode === format}
          disabled={busy} onClick={() => { if (mode !== format) reset(mode); }}>{formatLabel(mode)}</button>)}
      </div>
      <label>Your team’s side<select aria-label="Your team's side" value={side} disabled={locked || actions.length > 0}
        onChange={e => setSide(e.target.value as Side)}><option value="BLUE">Blue · first pick</option><option value="RED">Red · second pick</option></select></label>
      <span className="tag">PATCH {catalog.version}</span>
    </div>
    <p className="muted draft-note">{format === 'RANKED'
      ? 'Enter five bans for each side in any order, then follow the pick sequence. Opposing duplicate bans are allowed.'
      : 'Standard single-game tournament draft: bans → picks → bans → picks. Series-wide Fearless restrictions are not included.'}</p>
    <div className="draft-arena">
      <aside className="recommendation-panel">
        <span className="eyebrow">YOUR INTELLIGENCE</span><h3>Comfort shortlist</h3>
        <p className="muted">Available pool entries, highest comfort first. Not AI or matchup predictions.</p>
        {shortlist.length ? shortlist.map((c,n) => <div className="recommendation" key={n}>
          <img src={c.entry!.portrait} alt="" width="36" height="36" />
          <div><strong>{c.entry!.name}</strong><small>{c.player} · {c.comfort}/10</small></div>
        </div>) : <p className="muted">No available pool entries. Add champions to your roster, or undo a selection to make a saved comfort pick available again.</p>}
      </aside>
      {teamColumn('BLUE')}
      <section className="draft-center">
        <div className="draft-phase" aria-live="polite"><span className="eyebrow">{actions.length} / 20 ACTIONS</span>
          <h2>{!turn ? 'Draft complete' : turn.kind === 'BAN' ? 'Ban a champion' : 'Choose your champion'}</h2>
          <span>{turn ? `${actingSide} SIDE · ${turn.kind}` : 'Ready for the Rift'}</span>
        </div>
        {turn?.side === null && <div className="ban-side-toggle" role="group" aria-label="Enter bans for">
          {(['BLUE', 'RED'] as const).map(value => <button key={value} aria-pressed={banSide === value}
            disabled={locked || actions.filter(a => a.kind === 'BAN' && a.side === value).length >= 5}
            onClick={() => { setBanSide(value); setSelected(null); }}>{value} bans</button>)}
        </div>}
        <ChampionPicker key={format + ':' + actions.length} champions={catalog.champions} unavailable={blocked} selected={selected} onSelect={setSelected} disabled={locked || !turn} />
        <div className="draft-controls">
          <button className="primary" disabled={locked || !turn || !selected || blocked.includes(selected)} onClick={() => confirm(selected)}>
            {turn?.kind === 'BAN' ? 'Confirm ban' : 'Lock in pick'}</button>
          {turn?.kind === 'BAN' && <button disabled={locked} onClick={() => confirm(null)}>No ban</button>}
          <button disabled={locked || !actions.length} onClick={() => { setActions(actions.slice(0, -1)); setSelected(null); setError(''); }}>Undo last action</button>
        </div>
      </section>
      {teamColumn('RED')}
      <aside className="recommendation-panel"><span className="eyebrow">OPPONENT INTELLIGENCE</span><h3>Ban & matchup analysis</h3>
        <p className="muted">Reserved for evidence-based recommendations. Opponent pools and matchup analysis are not connected yet.</p>
        <div className="intel-placeholder">◇<small>Awaiting scouting data</small></div>
      </aside>
    </div>
    <section className="result-bar" aria-label="Record game result">
      <div><span className="eyebrow">AFTER THE NEXUS FALLS</span><h3>Record the outcome</h3>
        <p className="muted">For {team.name} · {side} · {formatLabel(format)}{turn ? ' · Complete the draft first.' : ''}</p></div>
      <div className="result-actions">
        <button className="win-button" disabled={!!turn || locked} onClick={() => save('WIN')}>Record win</button>
        <button className="loss-button" disabled={!!turn || locked} onClick={() => save('LOSS')}>Record loss</button>
        <button disabled={busy} onClick={() => reset()}>New draft</button>
      </div>
      {busy && <p role="status">Saving result…</p>}
      {saved && <p role="status" className="success">Result saved. View it in History.</p>}
      {error && <div role="alert" className="error">{error} {attempt && !saved && <button disabled={busy} onClick={() => save(attempt.result)}>Retry recording</button>}</div>}
    </section>
    {savedGame?.actions && <SavedLineups key={savedGame.id} game={savedGame} onState={reportLineup} onSaved={setSavedGame} />}
  </section>;
}
