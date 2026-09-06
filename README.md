# Beatrice
Beatrice is a local League of Legends team and drafting assistant with a Noxian war-room interface.

## Working today

- Home, Draft, Team, and History navigation with one selected team.
- Create multiple teams with case-insensitive unique names and edit their names.
- Save exactly five roster slots: Top, Jungle, Mid, Bot, Support.
- Enter player names, Riot IDs, champion pools, and comfort ratings from 1 to 10.
- Persist teams in PostgreSQL; preserve the selected team in this browser.
- Detect stale edits and protect unsaved roster changes.

Champion pools use searchable local Data Dragon names and portraits. Draft supports Ranked / Normal Draft and standard Tournament sequences, undo, and win/loss recording. History stores the format, side, picks, bans, patch, and roster snapshot. Riot IDs are still manually entered; Riot imports and AI matchup analysis are not connected. The comfort shortlist uses only player-entered ratings, not invented statistics.

## Run locally (PowerShell)

Keep Docker Desktop running. The root `.env` needs POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, and optionally POSTGRES_PORT. See `.env.example`; never commit your real `.env`.

From the project root:

```powershell
docker compose up -d
```

In a backend terminal:

```powershell
cd D:\Projects\Beatrice\backend
.\mvnw.cmd spring-boot:run '-Dspring-boot.run.profiles=local'
```

The quotes matter in PowerShell. The local profile reads `../.env` as a properties file, so use simple unquoted `KEY=value` entries. Spring connects to PostgreSQL and Flyway applies pending migrations automatically. Maven must run from `backend/` for that relative path.

In another terminal:

```powershell
cd D:\Projects\Beatrice\frontend
npm install
npm run dev
```

Open the URL Vite prints (normally http://localhost:5173). Both servers must run: Vite forwards `/api` to Spring on port 8080. The Vite proxy is development-only; production hosting is not configured in this slice.

Use Team to create a roster, fill the player slots, add champion names and comfort, and click Save roster. Home shows the saved data. Refresh to confirm persistence. To clear a slot, remove its champions and Riot ID and clear its player name before saving.

Stop application terminals with Ctrl+C. `docker compose down` stops PostgreSQL while keeping its volume. Do not use `--volumes` unless intentionally erasing the database.

## Verify

```powershell
cd D:\Projects\Beatrice\backend
.\mvnw.cmd test
cd ..\frontend
npm test
npm run lint
npm run build
```

Backend tests start disposable PostgreSQL containers with Testcontainers. They do not use your saved-team database or require the local profile. If using a terminal with a globally set SPRING_PROFILES_ACTIVE, unset it before running tests.

## Code guide

- `backend/.../team/TeamController.java`: routes HTTP requests.
- `TeamData.java`: JSON request/response records and validation.
- `TeamService.java`: business rules and atomic transactions.
- `TeamRepository.java`: parameterized SQL; Spring JDBC is used for this first slice instead of JPA to keep persistence explicit.
- `backend/src/main/resources/db/migration/`: versioned schema changes. Never edit a migration already applied to a shared database; add a new version.
- `frontend/src/api/teams.ts`: HTTP boundary and TypeScript types.
- `frontend/src/components/TeamEditor.tsx`: unsaved form state and save behavior.
- `frontend/src/App.tsx`: navigation, active-team state, and page composition.
- `docs/implementation.md`: decisions, limitations, and next steps.

Comments explain transactions, concurrency, configuration, and component state. Start with the API records, then follow one request from controller to service to repository.
## Champion picker and draft recording

The app now supports local Data Dragon champion selection, Ranked / Normal Draft and standard Tournament rules, and PostgreSQL-backed win/loss history. See [the tutorial and code guide](docs/champions-and-drafts.md) for setup, usage, tests, and current limitations.
