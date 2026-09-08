import { nextTurn } from '../draft/rules';
import type { Action, Format } from '../draft/rules';

interface Props { format: Format; actions: Action[] }

// UI-only staging: the old endpoint requires a target role. Do not quietly
// select a role or present its role-specific results as team-wide advice.
export default function useDraftAdvice({ format, actions }: Props) {
  const turn = nextTurn(format, actions);
  const blind = !actions.some(a => a.kind === 'PICK');
  const phase = !turn ? 'Draft complete' : turn.kind === 'BAN' ? 'Ban phase' : blind ? 'Blind pick' : 'Pick phase';
  const placeholders = <div className="advice-portrait-grid" aria-hidden="true">
    {Array.from({ length: 6 }, (_, i) => <span className="advice-empty-portrait" key={i}>◇</span>)}
  </div>;
  return {
    left: <aside className="recommendation-panel draft-advice">
      <span className="eyebrow">DRAFT IDEAS</span>
      <p className="advice-phase" role="status">{phase}</p>
      <section className={turn?.kind === 'BAN' ? 'advice-group active' : 'advice-group'}>
        <h3>Ban suggestions</h3>{placeholders}
        <p className="muted">{!turn ? 'Bans complete.' : turn.kind === 'BAN' ? 'Ban recommendations will appear here.' : 'Available during ban phases.'}</p>
      </section>
      <section className={turn?.kind === 'PICK' ? 'advice-group active' : 'advice-group'}>
        <h3>Pick suggestions</h3>{placeholders}
        <p className="muted">{!turn ? 'Draft finished. Record your result after playing.' : blind
          ? 'Blind-pick ideas before either team has picked.' : 'Pick ideas based on the current draft.'}</p>
      </section>
      <small className="muted">The role-free recommendation engine update is next. These are empty slots, not scored recommendations.</small>
    </aside>,
    right: <aside className="recommendation-panel draft-advice">
      <span className="eyebrow">BEATRICE</span><h3>Draft assistance</h3>
      <div className="intel-placeholder">◇<small>Awaiting recommendation engine</small></div>
      <p className="muted">Draft explanations will appear here. No lane assignments are needed during drafting.</p>
      <p className="muted">After the game, record win or loss and confirm the lanes actually played.</p>
    </aside>,
  };
}
