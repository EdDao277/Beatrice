# Updating Beatrice's champion statistics

The collector is opt-in. Starting Beatrice does **not** start collection. The PowerShell launcher starts a job in the existing local backend, sharing `RiotClient` pacing with Home's profile refreshes. Avoid simultaneously running CompCraft or another application with the same Riot key.

## Run later

1. Start PostgreSQL with your existing Docker Compose command.
2. Start the updated backend from `backend/`:

   ```powershell
   mvn spring-boot:run '-Dspring-boot.run.profiles=local'
   ```

   Flyway applies V7 on startup. It adds collection/statistics tables; it does not change the archive, metadata, roster, pools, profile caches, or recorded games.

3. From `D:\Projects\Beatrice`:

   ```powershell
   powershell -NoProfile -File .\scripts\Update-Stats.ps1
   ```

The launcher reads no credentials. The backend reads the ignored root `.env` and the fixed `data/collection/config.json` path. It validates the config before contacting Riot. Keep the backend running until the command finishes; closing just the launcher terminal does not cancel the job.

To inspect a job without starting another:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/api/collection
```

## Configuration

Your existing seed list and limits work unchanged. Supported routing is NA1/Americas. Queues are 400 (Normal Draft), 420 (Solo/Duo), 440 (Flex), 710 (Ranked 5s). Other queues are rejected.

The default split start is `2026-07-29T19:00:00Z` (NA Season 3, noon Pacific). Add `"splitStart": "2026-07-29T19:00:00Z"` to make it explicit. Update this setting for future splits; the collector does not guess new season dates.

`maxNewMatchesPerRun` limits new match-detail downloads, including rejected games—not every HTTP request. Seed resolutions and match-ID requests also consume Riot quota. `maxDiscoveryDepth: 1` allows seed participants plus one discovery hop. `maxTrackedPlayers` bounds the tracked account pool. Accounts' histories may include varied skill levels; this is a **seed-network sample**, not a verified high-elo population.

## Storage and calculations

- `collection_datasets` identifies a seed set, routing, queues, split start and read-only metadata import version. Limits may change without creating a new dataset. Different datasets are independent samples and must not be summed blindly.
- `collection_players` stores discovered PUUIDs and depth. Seed IDs are resolved each run; update a renamed seed's ID in the private config.
- `collection_cursors` fixes each account/queue's time window and saves progress per ID. Completed windows reopen with a one-day overlap for delayed availability. No match can contribute twice to the same dataset.
- `collection_matches` records accepted/rejected IDs. Raw match responses are **not retained** in this first version. This is not yet a raw-data warehouse or a pipeline for retroactively changing aggregation definitions.
- `collection_runs` stores timestamps, counts and completion/failure status. After an interrupted backend process, old RUNNING entries may remain as an audit record; rerun resumes the persistent cursors.

Four maintained tables store games, wins, win rate (0–1), patch, queue and dataset identity:

1. `champion_role_stats`: one contribution per participant.
2. `champion_synergy_stats`: directed ally pairs, with both roles. A–B and B–A are separate views of the same games; never sum them as independent samples.
3. `champion_matchup_stats`: directed **same-role** enemy pairs (counter evidence). These are match outcomes, not lane-win measurements.
4. `team_comp_signature_stats`: one contribution per team, using a versioned sorted set of existing composition/utility traits and damage categories. Missing required metadata skips that composition only. Metadata is read, never inserted, updated, or deleted.

The new trait-signature format is `traits-v1`; it is not silently combined with CompCraft's older flag signatures. The old imported reference statistics are preserved and are not copied into or mixed with the maintained tables. Existing reference UI/API remains unchanged; an AI consumer can read the new tables later.

Games with invalid/incomplete roles, non-five-player teams, inconsistent outcomes, unsupported queues, or early-surrender flags are excluded. Unknown roles are not guessed from pick order. `low_sample` means fewer than 30 observations—a display heuristic, **not** statistical confidence. Win rates are descriptive; no causal counter or win-probability claim is generated.

## Results and retry

`BUDGET_REACHED`: saved progress, rerun later to continue. `WINDOWS_CHECKED`: currently tracked windows checked, not proof Riot exposes every historical game. A rate limit or API error stops the run safely; wait, fix an expired key if needed, then run again. The backend status message is sanitized; secrets are never printed. Aggregates and the per-match ledger commit in one transaction.

## Offline verification

```powershell
cd backend
mvn -B '-Dtest=CollectionTest' test
```

Tests use fake Riot responses and a disposable PostgreSQL Testcontainer. They do not read the private seed configuration, contact Riot, or update the real Beatrice database. Docker must be available for the disposable database.
