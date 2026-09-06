# Riot Home profiles

Home's Starting five uses the full Riot IDs saved on Team. This first version supports NA accounts (NA1 platform, Americas account/match routing).

## Use

1. Keep `RIOT_API_KEY` in the root `.env`, never in frontend code or a `VITE_` setting. Restart the backend after changing the key.
2. Open Home and click **Refresh Riot stats** on a player card. No Riot requests are made automatically just by viewing Home.
3. Use the small circular refresh icon centered below the player's name. Refreshes run in a bounded, single-worker queue with conservative pacing. A full split may require several minutes and multiple refreshes: each job downloads at most 300 new match details, then offers manual continuation if incomplete. Cached details survive retries/restarts. You may navigate away; refresh continues on the backend. Returning to Home resumes status polling.
4. Successful snapshots persist in PostgreSQL. Failed refreshes keep the last successful snapshot and timestamp visible; follow the error message and retry later. Backend restart cancels unfinished jobs; refresh them again.

The top section selects the highest official current rank across Solo/Duo, Flex, and Ranked 5s by tier, division, then LP, with its mode labeled. Classic ranks are excluded. An absent supported rank is Unranked. Below it, combined split wins/losses and win rate use all eligible games, not an average of champion or queue percentages. Zero games has no calculated win rate. All five saved players use the same card; refresh each after saving their full Riot ID on Team.

The champion section covers **available current-split history** across Normal Draft (400), Solo/Duo (420), Flex (440), and Ranked 5s (710). ARAM, bots, Clash, Classic, other queues and early-surrender records are excluded. Eight champion rows appear initially; Show all expands every champion in the data, sorted by games then champion ID. Top three mastery champions are a separate all-time points ranking, with levels and points, not split performance.

The configured NA boundary is July 29, 2026, noon America/Los_Angeles (19:00 UTC), based on [Riot patch 26.15](https://www.leagueoflegends.com/en-us/news/game-updates/league-of-legends-patch-26-15-notes/) and [NA's server time zone](https://support-leagueoflegends.riotgames.com/hc/en-us/articles/33520940721043-End-of-Season-2024-Split-2). Override `beatrice.riot.split-start` with an ISO UTC instant when the next split begins; this is not automatically inferred from patch number. Dates display in the viewer's local time. Data spans patches within that window and is limited to Riot's available history, not guaranteed identical to another site's stored history.

Initial import paginates a fixed start/end window. Completed syncs advance a persistent cursor; subsequent refreshes scan only the new window plus a one-day overlap for delayed matches. Each match is stored once per account, with only necessary participant fields. A capped job publishes explicitly partial stats and never advances the cursor. A failed job preserves the previous card and any already-cached match details. Older 50/100-game snapshots keep their old labels until refreshed. No database reset is needed.

Profile icons are public Data Dragon URLs using our configured asset patch, with an initial-letter fallback if unavailable. Riot stats never replace manually entered roster names, roles, champion pools, comfort, recorded games, or CompCraft evidence.

## Code

- `backend/.../riot/RiotClient.java`: fixed HTTPS routing, token header, timeouts, pacing and sanitized errors. No third-party requests receive the key.
- `RiotStats.java`: pure recent-match aggregation.
- `RiotSplitHistory.java`: split pagination, compact match cache and completed-window cursor.
- `RiotRanks.java`, `RiotMastery.java`: official rank comparison and top mastery ordering.
- `V6__riot_split_matches.sql`: additive cache tables separate from manual team games and CompCraft data.
- `RiotProfiles.java`: persisted successful snapshots and background refresh lifecycle.
- `RiotController.java`: GET `/api/teams/{id}/players/{role}/riot`, POST same path plus `/refresh`.
- `V5__riot_profile_cache.sql`: independent profile snapshots, keyed by normalized NA Riot ID. No API key or PUUID is stored in the snapshot.
- `frontend/src/components/RiotPlayerCard.tsx`: Home display, manual refresh, and cache-only polling every three seconds while a job is active.

Rate-limit handling respects Retry-After for subsequent calls; there is no automatic retry storm. Refresh requests for one account have a one-minute cooldown within a backend run. This application cannot coordinate another application using the same key: avoid simultaneous CompCraft crawls. Development keys can expire; use the appropriate registered key for Beatrice and do not reuse a production key across products.

Sources: [Riot League documentation](https://developer.riotgames.com/docs/lol), [API portal guidance](https://developer.riotgames.com/docs/portal), [API reference](https://developer.riotgames.com/apis).

Tests use fixtures and disposable PostgreSQL, not live Riot credentials. Run `mvn -B test` from backend and `npm test`, `npm run lint`, `npm run build` from frontend.
