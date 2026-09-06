# Split profiles implementation plan

**Goal:** Implement the user-approved highest-rank, combined split win rate, mastery, expanded champion table and centered refresh icon for every saved player.

**Architecture:** Extend the existing background Riot refresh. Store compact per-player match evidence keyed by PUUID and match ID, independently of manual games. Fetch paginated IDs in a fixed time window; cached details are reused on retry. Publish only a completed split snapshot, retaining the previous snapshot during work or failure.

**Tech stack:** Java 21, Spring JDBC/Flyway/PostgreSQL, React/TypeScript, JUnit/Vitest. No new dependencies.

**Spec:** User-approved design in this conversation. Current NA Season 3 starts July 29, 2026, noon server time (Riot patch 26.15 notes). Keep the UTC boundary configurable and display it. Never describe API-returned history as guaranteed lifetime coverage.

## Tasks

- [x] Backend evidence: test all-champion aggregation, rank ordering and deduplicated reusable split history; run focused Maven tests red, implement, run green. Add V6 cache keyed by account/match; bound each refresh's new detail downloads, preserve progress across retries, never mark a capped scan complete.
- [x] Profile orchestration: select highest supported rank by tier/division/LP, resolve mastery numeric IDs through Data Dragon, add split fields with legacy-cache compatibility. Test empty history and older snapshots.
- [x] Shared player card: tests for combined wins, eight/show-all rows, mastery, accessible centered refresh, legacy labels and partial-state messaging. Run Vitest red, implement, run green.
- [x] Verify complete backend/frontend suites, lint/build and diff checks. Update usage documentation. Do not commit or modify saved teams, pools, manual games or CompCraft evidence.

## Verification outcome

33 backend and 20 frontend tests passed; lint and production build passed. Independent read-only review found no major issues. V6 applied successfully on the running local backend. BOT's first live split import is running; a complete live split snapshot has not yet been verified. All five cards share the implementation; the other four players can be refreshed individually.

## Verification fixtures

Rank: Diamond I 10 LP in Ranked 5s beats Diamond III 59 LP in Solo/Duo; Gold I beats Gold II regardless of LP. Unknown queues do not become a ranked badge. Four distinct eligible champions remain four rows, not three. Two wins in three games yields 66.7%, not the arithmetic mean of champion win rates. Duplicate IDs count once; cached details require no second download; interrupted imports remain retryable. Zero eligible games has no calculated win rate.
