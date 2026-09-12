# Temporal Draft Data Implementation Plan

> Execute the approved four-step extension inline with TDD. Keep the existing checkout, do not commit, and do not touch live services.

**Goal:** Preserve source series metadata, gate supported opening-game replays, export earlier-only training/validation features, and compare observed versus incomplete-history pool policies.

**Architecture:** A source-audit sidecar joins exact original CSV hashes to the existing prepared batch without changing database-import payloads. A temporal runner advances a history snapshot only to dates strictly before the prediction day's one-day safety lag. The pure scorer gains explicit observed/inferred/saved pool policies; the website remains unchanged.

**Tech stack:** Python 3.11+ standard library, JSONL/gzip outputs.

**Approved design:** The user's four numbered requirements in this conversation.

## Constraints

- Preserve original CSVs, old batches, database schema, champion metadata, saved teams and the 2026 held-out test.
- Cite the Oracle pick-order announcement and Riot Fearless definitions. First-game-only support avoids guessing later-game restrictions.
- Preserve game/year/split/playoffs/URL and conservative team/date group identifiers. Inferred series groups are never described as official IDs.
- Refuse malformed/inconsistent metadata, duplicate game numbers in a group, or invalid draft fields. Later games stay available as earlier historical observations, not supported replay labels.
- Snapshot inputs use only earlier dates; same-day and previous-day matches are excluded. Snapshot source IDs and feature values are exported. Test outcomes never update history.
- Inferred pro pools use the earlier observed champion universe; missing player/champion observations are unknown, not prohibited. Saved pools are hard constraints and use their actual ratings.
- Training labels and outcomes are separate from features. No ML fit and no claim that imitation metrics establish win improvement.

## Tasks

- [x] `source_audit.py` and `test_source_audit.py`: test source-hash joins, series-field retention, first-game gating, duplicates and chronology. Implement `audit_sources(prepared, raw_dir)` returning games, per-game audit and provenance. Run on originals read-only.
- [x] `baseline.py` and `test_baseline.py`: test inferred unknown players, forbidden future champions, saved-pool authority and neutral missing evidence. Add an explicit `pool_policy` argument, preserving the old default.
- [x] `temporal.py` and `test_temporal.py`: test `advance(day)` and snapshot isolation. Implement dated snapshots and immutable gzip feature/label exports, train/validation membership and sealed test IDs.
- [x] `build_dataset.py` and end-to-end tests: compare three variants under observed/inferred policies on exactly the same selected opening games, with separate metrics and exclusion reasons. Export candidate features for future ML using the inferred policy and prior history only.
- [x] Run preparation regression tests and benchmark tests, generate a bounded training/validation pilot, review independently, verify artifact hashes, and document commands/results/limitations in `docs/temporal-draft-data.md`.

## Test commands

```powershell
python -m unittest discover -s scripts/oracle -p 'test_*.py'
python -m unittest discover -s scripts/benchmark -p 'test_*.py'
```

Each task begins with failing behavioral tests, then implementation and the same tests. No unrelated refactors. Source consistency and prediction-time isolation take precedence over maximizing eligible rows.
