import { useEffect, useState } from 'react';
import { nextTurn } from '../draft/rules';
import type { Action, Format, Side } from '../draft/rules';
import type { Team } from '../api/teams';
import type { Catalog } from '../api/champions';
import { fetchPicks, recordPickSelection } from '../api/pickRecommendations';
import type { PickContext, PickReply } from '../api/pickRecommendations';
import { fetchBans } from '../api/banRecommendations';
import type { BanReply } from '../api/banRecommendations';

interface Props { format: Format; actions: Action[]; side: Side; team: Team; catalog: Catalog; onSelect: (id: string) => void; disabled: boolean; banDisabled?: boolean }

export default function useDraftAdvice({ format, actions, side, team, catalog, onSelect, disabled, banDisabled = false }: Props) {
  const turn = nextTurn(format, actions);
  const active = turn?.kind === 'PICK' && actions.filter(a => a.side === side && a.kind === 'PICK').length < 5;
  const context = JSON.stringify({ format, side, patch: catalog.version, actions });
  const key = `${team.id}:${team.version}:${context}`;
  const [state, setState] = useState<{ key: string; reply?: PickReply; error?: boolean }>();
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      fetchPicks(team.id, JSON.parse(context) as PickContext, controller.signal)
        .then(reply => { if (!controller.signal.aborted) setState({ key, reply }); })
        .catch(() => { if (!controller.signal.aborted) setState({ key, error: true }); });
    }, 150);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [active, team.id, key, context]);
  const banActive = turn?.kind === 'BAN' && actions.filter(a => a.side === side && a.kind === 'BAN').length < 5;
  const [banState, setBanState] = useState<{ key: string; reply?: BanReply; error?: boolean }>();
  useEffect(() => {
    if (!banActive) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      fetchBans(team.id, JSON.parse(context), controller.signal)
        .then(reply => { if (!controller.signal.aborted) setBanState({ key, reply }); })
        .catch(() => { if (!controller.signal.aborted) setBanState({ key, error: true }); });
    }, 150);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [banActive, team.id, key, context]);
  const currentBans = banActive && banState?.key === key ? banState : undefined;
  const bans = currentBans?.reply?.bans.slice(0, 6) ?? [];
  // Key checking hides stale results immediately, even before effect cleanup runs.
  const current = active && state?.key === key ? state : undefined;
  const picks = current?.reply?.picks ?? [];
  const debug = import.meta.env.DEV && import.meta.env.VITE_PICK_DEBUG === 'true';
  const blind = !actions.some(a => a.kind === 'PICK');
  const phase = !turn ? 'Draft complete' : turn.kind === 'BAN' ? 'Ban phase' : blind ? 'Blind pick' : 'Pick phase';
  const placeholders = <div className="advice-portrait-grid" aria-hidden="true">
    {Array.from({ length: 6 }, (_, i) => <span className="advice-empty-portrait" key={i}>◇</span>)}
  </div>;
  return {
    recordSelected: (championId: string) => {
      if (current?.reply) void recordPickSelection(team.id, current.reply.requestId, championId);
    },
    left: <aside className="recommendation-panel draft-advice">
      <span className="eyebrow">DRAFT IDEAS</span>
      <p className="advice-phase" role="status">{phase}</p>
      <section className={turn?.kind === 'BAN' ? 'advice-group active' : 'advice-group'}>
        <h3>Ban suggestions</h3>
        {bans.length ? <div className="advice-portrait-grid">{bans.map(ban => {
          const champion = catalog.champions.find(c => c.id === ban.championId);
          if (!champion) return null;
          return <button key={champion.id} className="advice-pick" disabled={banDisabled}
            title={`${champion.name} · ${ban.basis === 'EVIDENCE_BACKED' ? 'Reference statistical evidence' : 'Lower-confidence pool/composition fallback'}`}
            aria-label={`Suggest ban ${champion.name}`} onClick={() => onSelect(champion.id)}>
            <img src={champion.portrait} alt={champion.name} /></button>;
        })}</div> : placeholders}
        <p className="muted">{!turn ? 'Bans complete.' : !banActive ? 'Available during ban phases.'
          : currentBans?.error ? 'Ban suggestions unavailable. You can continue drafting.'
          : !currentBans?.reply ? 'Updating ban suggestions…' : !bans.length ? 'No defensible ban suggestions. You can ban manually.'
          : bans.some(b => b.basis === 'POOL_COMPOSITION_FALLBACK') ? 'Lower-confidence pool/composition suggestions included.' : 'Evidence-backed ban ideas.'}</p>
      </section>
      <section className={turn?.kind === 'PICK' ? 'advice-group active' : 'advice-group'}>
        <h3>Pick suggestions</h3>
        {picks.length ? <div className="advice-portrait-grid">{picks.map(pick => {
          const champion = catalog.champions.find(c => c.id === pick.championId);
          if (!champion) return null;
          return <div key={pick.championId}>
            <button className="advice-pick" title={champion.name} aria-label={`Suggest ${champion.name}`}
              disabled={disabled} onClick={() => onSelect(champion.id)}><img src={champion.portrait} alt={champion.name} /></button>
            {debug && <small>Java {pick.javaScore.toFixed(1)} · ML +{pick.mlBonus.toFixed(1)} · Final {pick.score.toFixed(1)}</small>}
          </div>;
        })}</div> : placeholders}
        <p className="muted">{!turn ? 'Draft finished. Record your result after playing.' : !active ? 'Available during pick phases.'
          : current?.error ? 'Pick suggestions unavailable. You can continue drafting.'
          : !current?.reply ? 'Updating pick suggestions…' : !picks.length ? 'No saved-pool picks fit the current draft.'
          : blind ? 'Blind-pick ideas from your saved pools.' : 'Pick ideas from your saved pools.'}</p>
      </section>
      <small className="muted">Suggestions preserve possible player swaps. Confirm lanes after the game.</small>
    </aside>,
    right: <aside className="recommendation-panel draft-advice">
      <span className="eyebrow">BEATRICE</span><h3>Draft assistance</h3>
      <div className="intel-placeholder">◇<small>No chat model connected</small></div>
      <p className="muted">Draft explanations will appear here. No lane assignments are needed during drafting.</p>
      <p className="muted">After the game, record win or loss and confirm the lanes actually played.</p>
    </aside>,
  };
}
