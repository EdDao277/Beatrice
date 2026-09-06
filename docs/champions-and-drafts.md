# Champion pools and manual drafts

## Start the app

Keep Docker Desktop running. In three PowerShell terminals:

```powershell
cd D:\Projects\Beatrice
docker compose up -d
```

```powershell
cd D:\Projects\Beatrice\backend
.\mvnw.cmd spring-boot:run '-Dspring-boot.run.profiles=local'
```

```powershell
cd D:\Projects\Beatrice\frontend
npm run dev
```

Open http://localhost:5173. Restart an already-running backend after Java changes. Flyway applies V3 automatically; it adds a new table, without deleting teams or changing existing migrations.

## Local champion assets

The default patch root is `data/ddragon/extracted/16.17.1`, relative to the repository root when running Java from `backend`.

- `data/en_US/champion.json`: official names, stable Data Dragon IDs and portrait filenames.
- `img/champion/*.png`: square portraits for pool and draft selection.
- `/api/champions`: small JSON catalog with patch version and local portrait URLs.
- `/api/champions/{id}/portrait`: serves only filenames allowlisted by that catalog.

No Riot API key, internet connection, npm dependency, or PostgreSQL image storage is needed. The archive and extracted files remain ignored by Git. The server caches the catalog in memory. Failed loads can be retried after fixing the extraction; changing a successfully loaded patch requires restarting the backend.

To use another extracted patch, set `BEATRICE_DDRAGON_PATH` to its absolute folder in the backend terminal before launching Java. The folder must contain `data/en_US/champion.json` and `img/champion`. Do not point it at the `.tgz` archive.

## Champion pools

1. Select a saved team and open Team.
2. Enter a player name, click **+ Add champion**, and search/select a portrait.
3. Adjust comfort from 1–10, then **Save roster**.

New pool entries use official display names; duplicate champions on the same player are disabled. Different players may share a champion. Existing names and ratings are not removed: names that do not match this catalog are visibly flagged, and can be corrected by removing/re-adding the champion. The server permits unchanged legacy names but rejects new misspellings. Empty pools and incomplete rosters remain saveable.

## Draft and results

1. Select a team, open Draft, choose the format and your team's blue/red side before entering actions.
2. **Ranked / Normal Draft** lets you enter five bans per side in either order. Opposing teams may ban the same champion. Picks follow B–R–R–B–B–R–R–B–B–R.
3. **Tournament** follows standard single-game two-phase draft: six alternating bans starting blue; B–R–R–B–B–R picks; four alternating bans starting red; R–B–B–R picks.
4. Select a portrait and confirm it. **No ban** records an empty ban slot; picks cannot be empty. **Undo last action** removes the most recent entry.
5. After 20 actions and the actual match, use **Record win** or **Record loss**. The result is from the selected team's perspective.
6. Open History for format, side, patch, picks/bans, official names, recording timestamp, and roster snapshot. History is filtered by the active team.

Switching tabs preserves an unfinished draft in memory. Switching teams or changing format asks before discarding it. Refresh/close warns about unrecorded work; drafts are **not** auto-restored after a browser restart. Results are saved in PostgreSQL, not browser storage.

The first save attempt freezes the payload and UUID. If the connection fails, use **Retry recording**. The database enforces one record per UUID, so retrying cannot duplicate a game. After saving, selections and result buttons lock; use **New draft** for another match. Recorded results are currently immutable through the UI.

## What is and is not analysis

The comfort shortlist is a simple sort of still-available champion-pool entries by the user's comfort rating. It is not AI, mastery, a role recommendation, or a win-probability estimate. The opponent panel reserves space for later evidence-based analysis.

This release does not include automatic League-client reading, timers, role assignment/trades, Riot match verification, series-wide Fearless restrictions, professional First Selection variants, or AI-generated bans. Picks are shown in selection order, not assigned to a player's lane. A snapshot captures the saved roster at recording time. Historical names and patch are preserved; portraits use the currently configured local catalog.

## Code guide

- `backend/.../champion/ChampionCatalog.java`: local asset loading and allowlisting.
- `frontend/src/components/ChampionPicker.tsx`: shared searchable portrait grid.
- `frontend/src/components/TeamEditor.tsx`: explicit roster editing and pool selection.
- `frontend/src/draft/rules.ts`: pure client draft rules, separate from layout.
- `frontend/src/components/DraftBoard.tsx`: manual draft state, recommendations, and recording controls.
- `backend/.../game/DraftRules.java`: independent validation of all submitted actions.
- `backend/.../game/GameService.java` and `GameRepository.java`: transactional, retry-safe saves with snapshots.
- `backend/src/main/resources/db/migration/V3__recorded_games.sql`: constrained JSON snapshots and a team/date index.
- `frontend/src/components/GameHistory.tsx`: per-team saved results.
- `frontend/src/draft.css`: responsive board and shared picker styling. Wide desktops show outside recommendation columns; smaller screens move them below the draft.

## Verify

Run `npm test`, `npm run lint`, and `npm run build` in `frontend`. Run `mvn test` in `backend` with Docker Desktop running; backend tests use a disposable database and a tiny generated champion fixture, never your saved teams.

Manual checks: add Swain at 10/10; reopen the picker and confirm it is disabled; save/reload. Draft in each format, try a duplicate, undo, navigate away/back, finish and record a result, then verify History after reloading. Never record a pretend result against a real team merely to test the UI.

Data source: [Riot Data Dragon](https://developer.riotgames.com/docs/lol#data-dragon). Standard tournament sequence reference: [Riot LCS rulebook, draft mode](https://nexus.leagueoflegends.com/wp-content/uploads/2019/01/2019-LCS-Rule-Set-v19.5_ckcwnabxx8cnojli7ggu.pdf).
