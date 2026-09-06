import { useState } from "react";
import type { Team } from "../api/teams";
import { saveTeam } from "../api/teams";
import { useChampions } from "../api/champions";
import ChampionPicker from "./ChampionPicker";

interface Props {
  team: Team;
  onSaved: (team: Team) => void;
  onDirty: (dirty: boolean) => void;
}
export default function TeamEditor({ team, onSaved, onDirty }: Props) {
  // A draft copy makes Save explicit; typing never mutates the saved roster.
  const [draft, setDraft] = useState<Team>(() => structuredClone(team));
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [pickerRole, setPickerRole] = useState<string | null>(null);
  const { catalog, error: catalogError, retry } = useChampions();
  const change = (next: Team) => {
    setDraft(next);
    onDirty(true);
    setMessage("");
    setError("");
  };
  async function submit(event: React.SubmitEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const saved = await saveTeam(draft);
      setDraft(saved);
      onDirty(false);
      onSaved(saved);
      setMessage("Roster saved.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to save.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={submit} className="editor">
      <div className="section-heading">
        <div>
          <span className="eyebrow">ROSTER MANAGEMENT</span>
          <h2>{team.name}</h2>
        </div>
        <span className="tag">5 ROLE SLOTS</span>
      </div>
      <label className="team-name">
        Team name
        <input
          required
          maxLength={80}
          value={draft.name}
          disabled={busy}
          onChange={(e) => change({ ...draft, name: e.target.value })}
        />
      </label>
      <p className="muted">
        Build your starting five. Comfort is your player's own rating,
        independent of mastery or match results.
      </p>
      <fieldset disabled={busy} className="roster-editor">
        {draft.players.map((player, index) => {
          const update = (next: typeof player) =>
            change({
              ...draft,
              players: draft.players.map((p, i) => (i === index ? next : p)),
            });
          return (
            <section className="player-editor" key={player.role}>
              <div className="role-banner">
                <span className="role-index">0{index + 1}</span>
                <h3>{player.role}</h3>
                <span
                  className={"dot " + (player.name.trim() ? "ready" : "")}
                />
              </div>
              <label>
                Player name
                <input
                  maxLength={80}
                  value={player.name}
                  onChange={(e) => update({ ...player, name: e.target.value })}
                  placeholder="Summoner name"
                />
              </label>
              <label>
                Riot ID
                <input
                  maxLength={100}
                  value={player.riotId}
                  onChange={(e) =>
                    update({ ...player, riotId: e.target.value })
                  }
                  placeholder="GameName#TAG"
                />
              </label>
              <small>Saved for future Riot import. Not connected yet.</small>
              <div className="pool-heading">
                <h4>Champion pool</h4>
                <span>{player.champions.length}</span>
              </div>
              {player.champions.map((champion, ci) => (
                <div className="champion-row" key={ci}>
                  <div className="pool-champion">
                    {catalog?.champions.find(c => c.name.toLowerCase() === champion.name.toLowerCase()) ?
                      <img width="40" height="40" alt="" src={catalog.champions.find(c => c.name.toLowerCase() === champion.name.toLowerCase())!.portrait} /> : null}
                    <span>{champion.name}
                      {catalog && !catalog.champions.some(c => c.name.toLowerCase() === champion.name.toLowerCase()) &&
                        <small className="legacy-champion">Unmatched saved name — remove and re-add to correct.</small>}
                    </span>
                  </div>
                  <label>
                    Comfort
                    <select
                      value={champion.comfort}
                      onChange={(e) =>
                        update({
                          ...player,
                          champions: player.champions.map((c, i) =>
                            i === ci
                              ? { ...c, comfort: Number(e.target.value) }
                              : c,
                          ),
                        })
                      }
                    >
                      {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => (
                        <option key={n} value={n}>
                          {n} / 10
                        </option>
                      ))}
                    </select>
                  </label>
                  <button
                    type="button"
                    className="icon-button"
                    aria-label={
                      "Remove champion " + (ci + 1) + " from " + player.role
                    }
                    onClick={() =>
                      update({
                        ...player,
                        champions: player.champions.filter((_, i) => i !== ci),
                      })
                    }
                  >
                    ×
                  </button>
                </div>
              ))}
              <button
                className="subtle"
                type="button"
                disabled={!player.name.trim() || player.champions.length >= 100}
                aria-expanded={pickerRole === player.role}
                onClick={() => setPickerRole(pickerRole === player.role ? null : player.role)}
              >
                + Add champion
              </button>
              {pickerRole === player.role && <div className="pool-picker-panel">
                <div className="section-heading"><h4>Add to {player.role}</h4>
                  <button type="button" onClick={() => setPickerRole(null)}>Close picker</button></div>
                {catalogError ? <p role="alert">{catalogError} <button type="button" onClick={retry}>Retry catalog</button></p> :
                  !catalog ? <p>Loading champions…</p> :
                  <ChampionPicker champions={catalog.champions}
                    unavailable={catalog.champions.filter(c => player.champions.some(p => p.name.toLowerCase() === c.name.toLowerCase())).map(c => c.id)}
                    onSelect={id => {
                      const selected = catalog.champions.find(c => c.id === id)!;
                      update({ ...player, champions: [...player.champions, { name: selected.name, comfort: 6 }] });
                      setPickerRole(null);
                    }} />}
              </div>}
            </section>
          );
        })}
      </fieldset>
      <div className="save-bar">
        <div>
          <strong>Make every pick personal.</strong>
          <p className="muted">
            1 = learning · 6 = comfortable · 10 = signature pick
          </p>
        </div>
        <button className="primary" disabled={busy}>
          {busy ? "Saving…" : "Save roster"}
        </button>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {message && (
        <p role="status" className="success">
          {message}
        </p>
      )}
    </form>
  );
}
