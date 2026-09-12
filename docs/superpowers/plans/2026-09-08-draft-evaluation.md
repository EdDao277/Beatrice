# Draft Evaluation Implementation Plan

> **For agentic workers:** Execute inline with test-driven development. Preserve the user's checkout and existing changes. Do not commit or run live collection.

**Goal:** Build an offline, reproducible comparison and feature/label boundary for the next ML milestone.

**Architecture:** Consume checksummed Oracle prepared JSONL, freeze earlier history, and replay only visible prefixes. A pure Python team-wide baseline returns candidates with feasible player assignments and neutral missing factors. Save separate contexts, labels, predictions, split membership, and a manifest.

**Tech stack:** Python 3.11+ standard library; no new dependencies or database changes.

**Approved scope:** User's role-uncertain, team-wide baseline evaluation milestone, before ML/LLM or UI integration.

## Global constraints

- Current-match final roles, player/champion pairings, outcomes, and future bans never enter scorer contexts.
- Pools are historical observations, not the user's comfort ratings. Unknown players cause an explicit abstention.
- All prefixes of a game remain together. Default reference: before 2025-01-01; validation: 2025; 2026 test stays unscored.
- Freeze evidence before the reference cutoff, with a seven-day boundary embargo. No validation outcomes update history.
- Oracle ordering and series/Fearless rules are unverified. Require an explicit provisional replay flag, and label every output accordingly. No claim of verified draft legality or ML readiness.
- Historical composition-trait snapshots are absent. Composition remains neutral; do not substitute today's metadata. Compare pool-only, pool plus assignment flexibility, and pool plus flexibility plus smoothed statistics. Explain this narrower ablation.

## Task 1: Protocol and leakage boundary

Files: `scripts/benchmark/protocol.py`, `scripts/benchmark/test_protocol.py`.

- [x] Write failing tests for checksum rejection, disjoint chronological splits, prefix-only bans, and final-role/outcome mutation invariance.
- [x] Run `python -m unittest discover -s scripts/benchmark -p 'test_*.py'` and observe failures.
- [x] Implement `load_prepared(path)`, `partition(games, validation_start, test_start)`, and `pick_cases(game)` returning `(context, label)` records. Contexts contain sorted player IDs only, never current player/champion associations.
- [x] Re-run tests; verify the first pick sees exactly six bans and no champions.

## Task 2: Pure team-wide baseline

Files: `scripts/benchmark/baseline.py`, `scripts/benchmark/test_baseline.py`.

- [x] Write failing tests: two champions cannot consume the same player's only slot; bans exclude candidates; sparse stats shrink toward 50; unseen evidence remains neutral; blind picks and flex picks return feasible witnesses.
- [x] Implement `History.observe(game)` for earlier games only, `History.pools(player_ids)`, and `recommend(context, history, variant)`.
- [x] Use bipartite matching for a five-player completion, retaining a concrete witness. Keep roles unknown; role-agnostic ally pair evidence is not lane synergy. Enemy lane matchup remains neutral.
- [x] Run tests and inspect hand-calculated scores.

## Task 3: Reproducible offline runner

Files: `scripts/benchmark/evaluate.py`, `scripts/benchmark/test_evaluate.py`, `docs/draft-evaluation.md`.

- [x] Test end-to-end output on fixtures: immutable directories, sealed test labels, evidence cutoff, explicit provisional gating, hashes, sample limit accounting.
- [x] Implement CLI with `--prepared`, `--output`, `--provisional-replay`, optional `--max-games`; deterministic game ordering, no network or SQL.
- [x] Export contexts/labels separately, all scored candidates with factor evidence, predictions, and cohort metrics (top-3 agreement, pool/candidate coverage, abstentions, legality checks, p50/p95 latency).
- [x] Run the audited local data; preserve the source and any earlier outputs. Report limitations alongside results, including inability to infer causal win improvement.
- [x] Request independent review, fix material findings, run tests and `git diff --check`, then document commands and the remaining ML-readiness gates.

## Outcome

The provisional offline implementation and 500-game pilot are delivered. Nineteen benchmark tests and five existing Oracle preparation tests pass. Review fixes preserve partial known-pool coverage on abstentions and reject finalization if code changes during a run. Source/artifact hashes were verified after the pilot. No live application, metadata, database, or original source data changed.

The stronger claim of a verified ML-ready benchmark is **not** complete: chronology, series/Fearless rules, historical trait features, and earlier-only training snapshots remain explicit prerequisites in `docs/draft-evaluation.md`. The user's live-team scenarios are not represented by this pro-only pilot.
