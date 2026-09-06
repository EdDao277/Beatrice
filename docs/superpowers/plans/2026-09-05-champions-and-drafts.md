# Champion picker and draft recording implementation plan

Goal: use the extracted Data Dragon catalog for pools and a manual, two-format draft with persisted results.

Approved design: searchable portrait grid; blue/red picks and bans; outside recommendation panels; Ranked / Normal Draft and Tournament toggle; undo; selected-team side; win/loss saved with format and patch. Tournament means standard single-game two-phase draft, not series-wide Fearless rules. Ranked bans allow either side to be entered first, opposing duplicate bans, and no-ban slots.

Architecture: Spring reads a configured local patch folder and exposes a small catalog plus allowlisted portraits. Existing pool names remain compatible; new pool entries must resolve to official names. Draft events are validated independently on the server. PostgreSQL stores an immutable roster and draft snapshot with a unique request UUID for retry-safe saves. React shares one picker and pure draft rule functions. No added dependencies, API keys, or fake statistics.

- [x] Catalog and pools: catalog service tests (names, image, missing data, invalid image) plus live endpoint verification; champion service/controller; shared picker replacing free text, retaining unmatched legacy names visibly.
- [x] Rules: literal order and duplicate tests for both modes; pure frontend rules and matching backend validation. Bans may be skipped, picks may not. Undo removes last event.
- [x] Results: V3 game table indexed by team/date; complete and invalid save tests, retries, team isolation and roster snapshots. GET/POST /api/teams/{id}/games.
- [x] UI: draft board and history preserve in-progress work while switching tabs, confirm destructive format/team/reset changes, disable mutation during save and after recording. UI tests cover selection, undo, format reset refusal and result retry.
- [x] Verify: 14 frontend tests, lint, and build passed; 15 backend tests passed in isolated PostgreSQL. Live catalog returned 173 champions and PNG portraits. Browser QA verified pool saving, a complete tournament/result/history flow, tab retention, and desktop/mobile layouts. Removed only the temporary QA team and its result. Tutorial and limitations documented; no commit made.
