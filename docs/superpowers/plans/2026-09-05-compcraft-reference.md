# CompCraft reference data and confirmed lineups

Approved scope: selective import of champion metadata/statistics, normalized IDs and roles, final lineup assignments, and transparent role-specific synergy evidence. Existing Beatrice teams/results remain authoritative and untouched by the import.

Architecture: a startup-only Java importer reads GZIP COPY data as text, never executes dump SQL, accepts five reference tables, validates counts and canonical IDs, and inserts an append-only checksum-identified batch transactionally. Metadata and normalized statistics have dedicated tables/indexes. Read-only endpoints expose exact patch/queue/region/source slices; mirrored pairs are not summed. Assignments use separate columns on recorded games with optimistic concurrency; no past roles are guessed.

- [x] Tests first: COPY escapes/nulls and ignored SQL; isolated-DB import, repeat import, evidence filters, no writes to teams; lineup validity and stale updates.
- [x] Reference importer and V4 migration; import command disabled by default and no file-path HTTP endpoint. Rejected rows counted in report. Confidence stored as original heuristic only.
- [x] Lineup editor after recording in Draft and in History; unique roles per side, unknown allowed; existing games can be annotated without changing result or draft. Saved roster names provide context, not verified participant mapping after player role swaps.
- [x] Reference evidence UI: explicit historical patch, queue, region, source, champion and role; games/wins/rate and descriptive delta; low-sample and non-causal warning. Never treat absent rows as zero wins.
- [x] Run all tests/lint/build, import named backup into local reference tables, verify row counts and existing team/game counts unchanged. Document source audit and remaining limitations. No commits.

Verified 2026-09-06: 19 backend tests, 16 frontend tests, lint and production build pass. Live reference endpoint returns role-specific observations. Imported 173 metadata entries and 266,086 aggregate rows, no rejections. Team/game counts remain 1/1. Independent review prompted dirty/busy navigation guards and persistent save feedback. Browser check confirmed History displays the existing result and Unknown lanes, and prompts before leaving an unsaved lineup. No test lane was saved to the user's game.

Walkthrough and methodology: `docs/compcraft-reference-data.md`. Matchup/composition rows are archived, not yet used for recommendations. Generic COPY hex escapes remain outside this archive-specific reader's supported scope.
