import { useEffect, useState } from "react";
import { createTeam, listTeams } from "./api/teams";
import type { Team } from "./api/teams";
import TeamEditor from "./components/TeamEditor";
import RavenMark from "./components/RavenMark";
import DraftPage from "./components/DraftPage";
import GameHistory from "./components/GameHistory";
import RiotPlayerCard from "./components/RiotPlayerCard";
import "./App.css";
import "./draft.css";

const pages = ["Home", "Draft", "Team", "History"] as const;
type Page = (typeof pages)[number];
const symbols = ["◈", "⚔", "♜", "◷"];

export default function App() {
  const [page, setPage] = useState<Page>("Home");
  const [teams, setTeams] = useState<Team[]>([]);
  const [activeId, setActiveId] = useState(() => {
    try {
      return Number(localStorage.getItem("beatrice.activeTeam")) || 0;
    } catch {
      return 0;
    }
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [reload, setReload] = useState(0);
  const [draftOpened, setDraftOpened] = useState(false);
  const [draftPending, setDraftPending] = useState(false);
  const [draftBusy, setDraftBusy] = useState(false);
  const [historyRevision, setHistoryRevision] = useState(0);
  const [historyPending, setHistoryPending] = useState(false);
  const [historyBusy, setHistoryBusy] = useState(false);
  const active = teams.find((t) => t.id === activeId) ?? teams[0];
  const filled = active?.players.filter((p) => p.name.trim()).length ?? 0;
  const poolSize =
    active?.players.reduce((sum, p) => sum + p.champions.length, 0) ?? 0;

  useEffect(() => {
    let current = true;
    listTeams()
      .then((data) => {
        if (current) {
          setTeams(data);
          setError("");
          setLoading(false);
        }
      })
      .catch((e) => {
        if (current) {
          setError(e.message);
          setLoading(false);
        }
      });
    return () => {
      current = false;
    };
  }, [reload]);
  useEffect(() => {
    try {
      if (active)
        localStorage.setItem("beatrice.activeTeam", String(active.id));
    } catch {
      /* Storage may be unavailable in private browsing. */
    }
  }, [active]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (dirty || draftPending || draftBusy) {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty, draftPending, draftBusy]);
  function mayLeave() {
    return !draftBusy && !historyBusy && (!(dirty || draftPending || historyPending) || window.confirm("Changing teams will discard unsaved roster, lineup, and draft changes. Continue?"));
  }
  function navigate(next: Page) {
    if (next === page || draftBusy || historyBusy) return;
    if (!(dirty || historyPending) || window.confirm("Discard unsaved roster or lineup changes?")) {
      setPage(next);
      setDirty(false);
      if (next === "Draft") setDraftOpened(true);
    }
  }
  async function addTeam(event: React.SubmitEvent) {
    event.preventDefault();
    if (!mayLeave()) return;
    setCreating(true);
    setError("");
    try {
      const team = await createTeam(newName.trim());
      setTeams((prev) => [...prev, team]);
      setActiveId(team.id);
      setNewName("");
      setDirty(false);
      setDraftPending(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to create team.");
    } finally {
      setCreating(false);
    }
  }
  const manage = () => navigate("Team");
  return (
    <div className="war-room">
      <aside className="sidebar">
        <a
          className="brand"
          href="#home"
          onClick={(e) => {
            e.preventDefault();
            navigate("Home");
          }}
        >
          <span className="raven-mark"><RavenMark /></span>
          <span>
            BEATRICE
          </span>
        </a>
        <div className="sidebar-rule" />
        <p className="nav-label">COMMAND CENTER</p>
        <nav aria-label="Main navigation">
          {pages.map((item, i) => (
            <button
              key={item}
              aria-current={page === item ? "page" : undefined}
              className={page === item ? "nav-item selected" : "nav-item"}
              onClick={() => navigate(item)}
            >
              <span aria-hidden="true">{symbols[i]}</span>
              {item}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <span className="status-light" /> LOCAL WAR ROOM
          <p>Your team. Your strategy.</p>
          <small>BEATRICE / EARLY DEVELOPMENT</small>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div>
            <span className="eyebrow">COMMAND CENTER</span>
            <span className="breadcrumb"> / {page}</span>
          </div>
          <label className="team-switch">
            ACTIVE TEAM
            <select
              aria-label="Active team"
              disabled={loading || creating || draftBusy || historyBusy || !teams.length}
              value={active?.id ?? ""}
              onChange={(e) => {
                if (mayLeave()) {
                  setActiveId(Number(e.target.value));
                  setDirty(false);
                  setDraftPending(false);
                }
              }}
            >
              {!teams.length && <option value="">No team selected</option>}
              {teams.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </label>
        </header>
        <main>
          <div className="page-heading">
            <div>
              <span className="eyebrow">INFORMATION IS VICTORY</span>
              <h1>
                {page === "Home"
                  ? "The war room"
                  : page === "Team"
                    ? "Your alliance"
                    : page === "Draft"
                      ? "Draft command"
                      : "Battle records"}
              </h1>
              <p className="muted">
                {page === "Home"
                  ? "Know your team. Prepare your next move."
                  : page === "Team"
                    ? "Five roles. One purpose. Build a roster you trust."
                    : page === "Draft"
                      ? "Every selection shapes the battle ahead."
                      : "Learn from the games you play together."}
              </p>
            </div>
            <span className="edition">
              NOXIAN
              <br />
              INTELLIGENCE
            </span>
          </div>
          {error && (
            <div className="error" role="alert">
              {error}{" "}
              <button
                onClick={() => {
                  if (mayLeave()) {
                    setDirty(false);
                    setLoading(true);
                    setReload((n) => n + 1);
                  }
                }}
              >
                Retry connection
              </button>
            </div>
          )}
          {loading ? (
            <p role="status">Opening the war room…</p>
          ) : (
            <>
              {page === "Home" && (
                <>
                  <section className="hero-panel">
                    <div className="hero-content">
                      <span className="eyebrow">YOUR NEXT CHAPTER</span>
                      <h2>
                        {active
                          ? active.name
                          : "An empire begins\nwith an alliance."}
                      </h2>
                      <p>
                        {active
                          ? "Your roster is the foundation of every draft. Define strengths, sharpen champion pools, and prepare as one."
                          : "Assemble your five. Define their champion pools. Give every decision a foundation."}
                      </p>
                      <button className="primary" onClick={manage}>
                        {active ? "Manage roster" : "Create your first team"}{" "}
                        <span aria-hidden="true">↗</span>
                      </button>
                    </div>
                    <div className="crest" aria-hidden="true">
                      <span>✦</span>
                      <RavenMark />
                      <span>BEATRICE</span>
                    </div>
                  </section>
                  <div className="metrics">
                    <article>
                      <span>ROSTER READINESS</span>
                      <strong>
                        {filled}
                        <small> / 5</small>
                      </strong>
                      <p>
                        {filled === 5
                          ? "All roles assigned"
                          : "Complete your starting lineup"}
                      </p>
                    </article>
                    <article>
                      <span>CHAMPION POOL ENTRIES</span>
                      <strong>{poolSize.toString().padStart(2, "0")}</strong>
                      <p>Player-defined picks</p>
                    </article>
                    <article>
                      <span>BATTLE RECORDS</span>
                      <button className="text-button" onClick={() => navigate("History")}>Open History ↗</button>
                      <p>Review recorded drafts and results</p>
                    </article>
                  </div>
                  <section className="panel">
                    <div className="section-heading">
                      <h2>Starting five</h2>
                      <button className="text-button" onClick={manage}>
                        Edit roster ↗
                      </button>
                    </div>
                    <div className="lineup">
                      {active ? active.players.map(player => <RiotPlayerCard key={active.id + ':' + player.role + ':' + player.riotId} teamId={active.id} player={player} />) : (
                        ["TOP", "JUNGLE", "MID", "BOT", "SUPPORT"].map(
                          (role) => ({ role, name: "", champions: [] }),
                        )
                      ).map((p, i) => (
                        <article className="player-card" key={p.role}>
                          <span className="eyebrow">
                            0{i + 1} / {p.role}
                          </span>
                          <div className="player-emblem">
                            {p.name ? p.name[0].toUpperCase() : "◇"}
                          </div>
                          <h3>{p.name || "Unassigned"}</h3>
                          <small>
                            {p.champions.length
                              ? p.champions.length + " champions in pool"
                              : "Awaiting champion pool"}
                          </small>
                        </article>
                      ))}
                    </div>
                  </section>
                  <section className="panel history-preview">
                    <span className="eyebrow">RECENT OPERATIONS</span>
                    <h2>Review your operations.</h2>
                    <p className="muted">
                      Record a result after your draft, then open History to review
                      picks, bans, and the saved roster.
                    </p>
                  </section>
                </>
              )}
              {page === "Team" && (
                <>
                  <form className="create-team panel" onSubmit={addTeam}>
                    <label>
                      New team name
                      <input
                        required
                        maxLength={80}
                        value={newName}
                        onChange={(e) => setNewName(e.target.value)}
                        placeholder="e.g. The Ravens"
                        disabled={creating}
                      />
                    </label>
                    <button
                      className="primary"
                      disabled={creating || !newName.trim()}
                    >
                      {creating ? "Creating…" : "Create team"}
                    </button>
                  </form>
                  {active ? (
                    <TeamEditor
                      key={active.id + ":" + reload}
                      team={active}
                      onDirty={setDirty}
                      onSaved={(saved) =>
                        setTeams((prev) =>
                          prev.map((t) => (t.id === saved.id ? saved : t)),
                        )
                      }
                    />
                  ) : (
                    <section className="panel empty">
                      <h2>Assemble your alliance</h2>
                      <p>
                        Create a team above to unlock its five roster slots.
                      </p>
                    </section>
                  )}
                </>
              )}
              {/* Keep the draft mounted between tabs so navigation never loses selections. */}
              {draftOpened && active && <div hidden={page !== "Draft"}>
                <DraftPage key={active.id} team={active} onPending={setDraftPending} onBusy={setDraftBusy}
                  onRecorded={() => setHistoryRevision(n => n + 1)} />
              </div>}
              {page === "Draft" && !active && <section className="panel empty"><h2>Select a team to draft</h2>
                <p>Create a saved team so Beatrice can attach your results to it.</p><button onClick={manage}>Create a team</button></section>}
              {page === "History" && (
                active ? <GameHistory key={active.id + ":" + historyRevision} teamId={active.id} onPending={setHistoryPending} onBusy={setHistoryBusy} /> :
                  <section className="panel empty"><h2>Select a team to view its history.</h2></section>
              )}
            </>
          )}
        </main>
        <footer>
          BEATRICE <span>STRATEGY BEGINS WITH INFORMATION.</span>
          <p>Beatrice is not endorsed by Riot Games and does not reflect the views or opinions of Riot Games or anyone officially involved in producing or managing Riot Games properties. Riot Games and all associated properties are trademarks or registered trademarks of Riot Games, Inc.</p>
        </footer>
      </div>
    </div>
  );
}
