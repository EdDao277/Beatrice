# Riot Home profiles

Home's Starting five uses the full Riot IDs saved on Team. This first version supports NA accounts (NA1 platform, Americas account/match routing).

## Use

1. Keep `RIOT_API_KEY` in the root `.env`, never in frontend code or a `VITE_` setting. Restart the backend after changing the key.
2. Open Home and click **Refresh Riot stats** on a player card. No Riot requests are made automatically just by viewing Home.
3. Refreshes run in a bounded, single-worker queue with conservative pacing. A first 50-match refresh can take roughly 1–2 minutes per player, longer if queued. You may navigate away; refresh continues on the backend. Returning to Home resumes status polling.
4. Successful snapshots persist in PostgreSQL. Failed refreshes keep the last successful snapshot and timestamp visible; follow the error message and retry later. Backend restart cancels unfinished jobs; refresh them again.

The top section is Riot's current Solo/Duo ranked entry, including wins/losses and LP. An absent ranked entry is shown as Unranked, never a fabricated zero rank. A zero-game ranked record has no calculated win rate.

The champion section is computed from **up to 50 latest Solo/Duo match IDs** returned by Riot. It may cross patches or ranked periods; it is not a full-season champion report. Only this player's participant record is counted, queue420 is checked again, duplicate match IDs are removed, and records flagged `gameEndedInEarlySurrender` are excluded. The actual analyzed denominator is displayed. Top three are sorted by games, with champion ID as deterministic tie-breaker. Small samples are descriptive, not proof of skill.

Profile icons are public Data Dragon URLs using our configured asset patch, with an initial-letter fallback if unavailable. Riot stats never replace manually entered roster names, roles, champion pools, comfort, recorded games, or CompCraft evidence.

## Code

- `backend/.../riot/RiotClient.java`: fixed HTTPS routing, token header, timeouts, pacing and sanitized errors. No third-party requests receive the key.
- `RiotStats.java`: pure recent-match aggregation.
- `RiotProfiles.java`: persisted successful snapshots and background refresh lifecycle.
- `RiotController.java`: GET `/api/teams/{id}/players/{role}/riot`, POST same path plus `/refresh`.
- `V5__riot_profile_cache.sql`: independent profile snapshots, keyed by normalized NA Riot ID. No API key or PUUID is stored in the snapshot.
- `frontend/src/components/RiotPlayerCard.tsx`: Home display, manual refresh, and cache-only polling every three seconds while a job is active.

Rate-limit handling respects Retry-After for subsequent calls; there is no automatic retry storm. Refresh requests for one account have a one-minute cooldown within a backend run. This application cannot coordinate another application using the same key: avoid simultaneous CompCraft crawls. Development keys can expire; use the appropriate registered key for Beatrice and do not reuse a production key across products.

Sources: [Riot League documentation](https://developer.riotgames.com/docs/lol), [API portal guidance](https://developer.riotgames.com/docs/portal), [API reference](https://developer.riotgames.com/apis).

Tests use fixtures and disposable PostgreSQL, not live Riot credentials. Run `mvn -B test` from backend and `npm test`, `npm run lint`, `npm run build` from frontend.
