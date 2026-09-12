# Offline draft evaluation

**Follow-up:** The [temporal dataset pipeline](temporal-draft-data.md) now preserves source series fields, uses documented pick-order semantics for an opening-game-only cohort, exports earlier-only training features, and distinguishes incomplete pro history from authoritative saved pools. The frozen-history pilot below remains a historical baseline; its provisional limitations describe that original run.

This is a **provisional research benchmark and export pipeline**, not a trained model, a verified tournament simulator, or the live recommendation endpoint. It makes no Riot calls, starts no services, and writes no database records. Champion metadata and the website are unchanged.

## Run it

From `D:\Projects\Beatrice`, using Python 3.11 or newer (standard library only):

```powershell
python -m unittest discover -s scripts/benchmark -p 'test_*.py'
python scripts/benchmark/evaluate.py --prepared data/oracle/prepared-2026-09-08-reviewed --output data/oracle/benchmark-next --provisional-replay --max-games 500
```

Choose a **new output directory** each time. Existing directories are never overwritten. Without `--provisional-replay`, the command refuses to run: chronological pick fields and series/Fearless rules are not independently verified. That flag acknowledges an assumption; it does not certify the records.

`--max-games 500` chooses evenly spaced eligible games across the validation period, keeping all ten pick decisions of each selected game together. It is a descriptive pilot, not a random sample with population confidence intervals. Omit the limit for all eligible validation games; expect more processing time and disk usage. Interrupting a run can leave partial files; only a final `manifest.json` identifies a completed run.

The bundled development Python used here is:

```powershell
& 'C:/Users/EdDao/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' -m unittest discover -s scripts/benchmark -p 'test_*.py'
```

## What the three baselines compare

All three exclude visible picks/bans, use all five players' **previously observed** champion pools, and require a possible five-player completion. A matching algorithm checks that no player must cover two champions. Each candidate includes a concrete hypothetical completion and its feasible players. These are not confirmed lane assignments and do not guarantee that the team will secure the remaining champions.

| Variant | Scoring inputs |
| --- | --- |
| `pool` | Historical player/champion frequency proxy; remaining factors neutral |
| `pool_rules` | Same, plus a small bonus for champions assignable to multiple players |
| `pool_rules_stats` | Same, plus shrunk historical champion and role-agnostic ally-pair evidence |

The requested full **composition-rules ablation is deferred**: there is no historical, patch-appropriate trait snapshot yet. Substituting current metadata into older games would compromise the evaluation. Assignment flexibility is an explicitly narrower rule, not engage/frontline/AP–AD analysis.

The fixed weights match the proposed framework: comfort 35%, composition 20%, synergy 15%, matchup 10%, meta 8%, team history 7%, draft value 5%. Unsupported factors contribute 50/100 without redistributing their weights. In this research adapter:

- “Comfort” is `100 × historical champion games / that player's most-played champion games`, using the best feasible player. It is **not** the user's 1–10 rating, nor proof of proficiency.
- Draft value is `50 + 12.5 × (number of feasible players − 1)`. This rewards assignment flexibility only; it does not model pick priority or opponent responses.
- Meta uses `(wins + 25) / (games + 50)`, a Beta(25,25) prior. Missing evidence is 50. One win in one game produces approximately 51%, not 100%.
- Synergy compares a pair's shrunk win rate to the mean of the two individual shrunk rates: `50 + 100 × mean(pair difference)`, clamped to 0–100. Counts are retained. These overlapping observational samples are not independent experiments or causal synergy estimates.
- Final roles are never supplied to scoring. Ally pairs are role-agnostic; enemy lane matchups, composition traits, and user's team history remain neutral. No guesses from selection order.
- Reference patches and leagues are explicitly pooled. This is not current-patch meta. Counts below 30 trigger a small-sample warning; larger samples do not eliminate bias.

Scores are preferences, **not win probabilities**. Factor coverage says which weights had inputs, not statistical confidence. Missing player history or an impossible pool completion causes an abstention, not a fabricated recommendation. Pool coverage still counts champions observed for the other known players.

## Chronology and leakage controls

Default split boundaries are fixed before running:

- Reference evidence: before December 25, 2024.
- First seven-day embargo: December 25–31, 2024.
- Validation: January 1–December 24, 2025.
- Second embargo: December 25–31, 2025.
- Reserved test: January 1, 2026 onward. Membership is recorded, but its contexts, predictions, and labels are not exported or scored.

The source's timezone-free dates are retained without inventing a timezone. `--validation-start` and `--test-start` change the boundaries; both have a seven-day preceding embargo. This conservative gap is **not proof of whole-series isolation** without series identifiers.

All validation decisions share a frozen reference snapshot. No validation result, later game, current matchup role, or future ban updates it. At the provisional first pick, a context contains six visible bans, no picks, and sorted roster IDs. It never includes the source's role-sorted player/champion associations. The roster itself is assumed known before drafting.

The audited source is checksum-verified. Complete fields are replayed under the standard tournament sequence, with BLUE first pick required. Incomplete or inconsistent draft fields are excluded as whole games and logged. Later bans are not exposed during earlier picks.

The primary [Oracle data dictionary](https://lol.timsevenhuysen.com/matchdata/match-data-dictionary/) describes older export fields, but does not establish the semantics of these newer `pick1`–`pick5` fields. The preparation audit's `draftFieldsComplete` flag must not be treated as chronological verification.

## Artifacts and code

| File | Purpose |
| --- | --- |
| `contexts.jsonl` | Prediction-time inputs only; case ID joins other files |
| `labels.jsonl` | Actual next champion and result, kept separate from scorer inputs |
| `history.json` | Frozen earlier pools, champion counts, ally-pair counts, dates and source game IDs |
| `predictions.jsonl.gz` | All candidates, factors, evidence, assignment witnesses, warnings and abstention reasons for every variant |
| `timings.jsonl` | Runtime measurements, separate from deterministic predictions |
| `splits.json` | Whole-game reference/embargo/validation/test membership |
| `exclusions.jsonl` | Every omitted validation game and its reason |
| `report.json` | Counts and metrics overall, by draft stage, league and patch |
| `manifest.json` | Input/artifact/code hashes, cutoffs, weights, prior, Python version and limitations |

`scripts/benchmark/protocol.py` owns the data boundary; `baseline.py` owns the pure baseline; `evaluate.py` orchestrates exports and metrics. All generated data stays beneath the already-ignored `data/` directory. No new runtime dependency is added to Beatrice.

The same source/configuration produces the same contexts and prediction records. Runtime timings and the report/manifest hashes that include them naturally vary. A code-file change during evaluation prevents the final manifest from being written; rerun in a fresh folder after edits settle.

Metrics distinguish:

- **Pool coverage:** was the actual pro pick in any known player's available historical pool?
- **Candidate coverage:** did it also have a feasible whole-team completion?
- **Top-3 agreement:** how often the real pick appeared among three suggestions; denominator includes abstentions and out-of-pool targets.
- **Conditional agreement:** agreement only among cases whose target was a feasible candidate. Always read alongside unconditional agreement.
- **Legality violations:** an independent check of every returned completion against visible unavailable champions and historical pools. This does not verify Fearless or lane legality.
- **Latency:** p50/p95 per scorer call, excluding input loading, serialization and independent output checks. Not an end-to-end UI performance measurement.

These metrics cannot establish that following recommendations improves win rate. Ban recommendations are not evaluated by this pick benchmark.

## Before training the ML model

1. Verify chronological pick/ban semantics and preserve supporting evidence. Add audited series identifiers, game number and the applicable draft/Fearless rules; exclude unsupported formats.
2. Supply dated historical composition metadata if testing engage, frontline, damage balance and similar features. Never silently use today's catalog traits for old predictions.
3. Generate **training** contexts with earlier-only temporal snapshots, using this same context/label boundary. `history.json` from the 2025 validation run contains all reference outcomes and is **unsafe as a feature source for its own 2024 training games**. It is safe only for later validation decisions.
4. Decide how to represent unseen players/champions and incomplete historical pools without adding the held-out target to its pool. Evaluate those changes on validation, not the reserved test.
5. Freeze the protocol and model choices before a one-time test evaluation. Keep user's saved-team scenario tests separate from pro historical evaluation.

This milestone supplies the reusable adapter, baseline, diagnostics and export contract. It intentionally does not declare the current records ML-ready or train a model.

## September 8 pilot results

Output: `data/oracle/benchmark-2026-09-08-pilot/`. This supersedes the earlier chronological 100-game smoke run for discussion; both outputs remain preserved. The pilot uses 10,181 reference games and 500 evenly spaced eligible 2025 validation games (5,000 decisions). It excludes 236 incomplete drafts and leaves 9,280 other eligible games outside the sample. Fifteen boundary games are embargoed; 8,432 games are reserved for testing and not scored.

| Variant | Top-3 hits / all decisions | Agreement when candidate covered | Scorer p95 |
| --- | --- | --- | --- |
| Pool | 170 / 5,000 (3.4%) | 14.60% | 4.28 ms |
| Pool + flexibility | 170 / 5,000 (3.4%) | 14.60% | 4.45 ms |
| Pool + flexibility + stats | 185 / 5,000 (3.7%) | 15.89% | 4.76 ms |

Across variants, 58.32% of targets were in a known available pool, but only 23.28% (1,164) had feasible whole-roster completions. There were **zero visible-pool legality violations**, not a certification of tournament/Fearless correctness.

The 3,298 abstentions per variant break down into 1,710 missing-player-history cases, 150 invalid/incomplete roster-identity cases, and 1,438 cases with no feasible pool completion. The other 1,702 decisions returned candidates. Frozen previous-year pro pools become stale, and a player's unobserved champion is not necessarily unplayable. This is the main finding to address before interpreting ranking differences.

The extra 15 top-three hits from statistics do **not** establish meaningful superiority or win improvement. No significance claim is made from this deterministic, provisional sample. Latency includes fast abstentions and excludes disk I/O; it is not a frontend SLA.

Follow-up: [Temporal draft data and reviewed comparison](temporal-draft-data.md) adds source-series auditing, opening-game eligibility, expanding earlier-only snapshots, separate pool policies, and training exports. Its cohort and history protocol differ, so its scores are not a direct before/after comparison with this first pilot.

Verification: 19 benchmark tests and 5 Oracle preparation tests pass. An independent review checked both leakage boundaries and matching behavior, including randomized comparisons against exhaustive assignments. All pilot artifact and implementation hashes match the final manifest. No backend/frontend runtime code changed, so those application suites were not rerun for this offline-only work.
