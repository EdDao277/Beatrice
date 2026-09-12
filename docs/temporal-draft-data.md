# Temporal draft dataset and baseline comparison

This extends the [first offline benchmark](draft-evaluation.md). It exports training and validation examples with earlier-only features. It does **not** train ML, call Riot, start Docker, change the website, edit champion metadata, or read/write your saved teams.

## Run

From the repository root, using Python 3.11 or newer:

```powershell
python -m unittest discover -s scripts/benchmark -p 'test_*.py'
python scripts/benchmark/build_dataset.py --prepared data/oracle/prepared-2026-09-08-reviewed --raw-dir data/oracle --output data/oracle/temporal-next --max-training-games 100 --max-validation-games 100
```

Use a new output name every time. Omit the two sample limits to export all supported training/validation games; this takes longer and uses more disk space. Limits select evenly spaced **whole games**, not independent draft decisions or randomly sampled rows.

If `python` is not on PATH, the development runtime used for verification is:

```powershell
& 'C:/Users/EdDao/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' scripts/benchmark/build_dataset.py --prepared data/oracle/prepared-2026-09-08-reviewed --raw-dir data/oracle --output data/oracle/temporal-next --max-training-games 100 --max-validation-games 100
```

No additional packages are required. A missing final `manifest.json` means the run is incomplete. Output folders and original inputs are never overwritten. If you replace the CSV downloads, prepare a **new** batch first; mismatched original source hashes are rejected.

## 1. Source audit and supported drafts

`source_audit.py` checks the original CSVs against the prepared manifest and joins their source metadata into a separate audit file. It retains `game`, `year`, `split`, `playoffs`, `url`, `league`, and `date`. The existing prepared payloads and database-import hashes are unchanged.

Evidence supporting the protocol:

- Oracle's author states that the new pick fields are in chronological order for the team represented by the row: [February 2024 announcement](https://lol.timsevenhuysen.com/2024/02/void-grubs-and-pick-order-in-the-csvs/).
- The older [Oracle data dictionary](https://lol.timsevenhuysen.com/matchdata/match-data-dictionary/) describes the game-within-series field, including a special historical BO1 day-number convention. We retain raw values rather than inventing official series identifiers.
- Riot's [2025 overview](https://lolesports.com/en-GB/news/lol-esports-in-2025) explains that prior-game champion restrictions accumulate in Full Fearless. Riot's [2024 NACL announcement](https://lolesports.com/en-US/news/introducing-the-2024-north-american-challengers-league) describes a team-specific variant. These must not be treated as interchangeable.

The supported replay cohort is deliberately **opening-game-only** (`game == 1`). Those games do not need prior-game Fearless bans. The audit also requires:

- Consistent source date, season, league and stage fields.
- Two nonblank distinct team IDs and ten nonblank distinct player IDs.
- Complete five-pick/five-ban lists per side, agreement with the final champion sets, legal uniqueness, and BLUE first pick.
- No ambiguous duplicate/unknown game numbers or contradictory timestamp ordering in the inferred group.

Group identifiers combine league, season, split, stage, teams and calendar date. They are labeled `inferred_team_date_group`, **not official series IDs**. Cross-midnight series and rematches need further source work before later-game support. The audit verifies the meaning of columns and structural consistency, not every match against a VOD. Its eligibility field should not be read as blanket support for every tournament format or historical champion-availability restriction.

Later games, missing metadata and contradictions receive explicit exclusion reasons. They are not silently replayed using standard rules. Structurally accepted earlier pro games, including later series games, still contribute historical observations; this population is stated in the manifest.

## 2. Earlier-only snapshots

`temporal.py` walks forward through games. For a prediction on February 10, only source matches dated **before February 9 at 00:00** can contribute. February 9 and February 10 are excluded. This one-day extra lag avoids using current or recently unfinished matches when exact original data-availability timestamps are unavailable.

Each exported snapshot contains its cutoff, latest observation, source game IDs, patch counts and a chained history digest. Each context and candidate-feature record references that snapshot ID. The exported feature values are computed from that state, not from a final aggregate over all matches.

Default label partitions:

- Before April 1, 2024: warmup history, no training labels.
- April 1–December 24, 2024: training labels.
- December 25–31, 2024: label embargo.
- January 1–December 24, 2025: validation labels.
- December 25–31, 2025: label embargo.
- January 1, 2026 onward: reserved test, never scored, exported as features/labels, or added to history by this command.

The test cutoff may be moved **earlier**, not later than January 1, 2026. Changing it cannot expose the sealed 2026 data. Every prefix of a match stays in one partition.

Validation is **walk-forward/prequential**: once an earlier validation result is old enough, it can inform a later validation snapshot. No model parameters are fitted here. This simulates updating historical knowledge over time; it is different from the first benchmark's frozen-2024 history. Label embargo games may later become historical observations once they are old enough. A seven-day label gap and opening-game-only evaluation reduce series dependence, but inferred groups are not proof of globally verified series isolation.

## 3. Pool policies

`baseline.recommend(..., pool_policy=...)` makes the distinction explicit:

| Policy | Candidate restrictions | Familiarity input |
| --- | --- | --- |
| `observed` | Previously observed champion/player pairs only; full five-player completion required | Original relative frequency within that player's history |
| `inferred` | Earlier observed global champion vocabulary; missing individual observations do not prohibit a champion | `50 + 50 × games / (games + 10)`; no observations gives neutral 50 |
| `saved` | Only the five explicitly supplied saved pools; empty pools remain empty | Actual saved comfort rating × 10 |

The old evaluator keeps its `observed` default. The new runner compares `observed` and `inferred` on exactly the same selected games and snapshots. It does not load real saved teams; fixtures verify that `saved` cannot be widened using pro history. This is a tested research adapter contract, not a change to the Java endpoint or UI.

Inferred capability remains **unknown**. A five-player witness means the assignment is possible under that permissive policy, not that all five players can actually play every champion. The output separately records players with real observations. Only those observed options earn a flexibility bonus. Visible ally picks can be accommodated as commitments even when previously unseen, but the held-out next pick is never added to the vocabulary or a pool.

The inferred familiarity formula also changes how observations are scored, so this is a **policy bundle comparison**, not an experiment isolating only the hard filter. A known observation provides some positive evidence without making an unobserved champion look worse than a rarely observed one by definition.

The three variants remain pool-only, pool plus assignment flexibility, and pool plus flexibility plus shrunk historical stats. Unknown composition traits, lane-specific matchups and saved-team history remain neutral. Scores are preferences, not win probabilities. Historical stats pool prior patches/leagues/formats; no claim of current-patch or causal synergy is made.

## 4. Training export contract

The new output directory contains:

| Artifact | Contents |
| --- | --- |
| `source-audit.jsonl.gz` | Preserved source series fields, grouping status and reasons for every prepared game |
| `splits.json` | Whole-game warmup/training/validation/embargo/test membership |
| `snapshots.jsonl.gz` | Earlier-only history provenance, once per exported prediction day |
| `contexts.jsonl.gz` | Visible picks/bans, side/patch, sorted roster IDs, split and snapshot reference |
| `features.jsonl.gz` | Candidate factors, evidence counts, observation masks via observed-player lists, and per-player champion counts under the inferred policy |
| `labels.jsonl.gz` | Actual next champion, own-side result, split, and `caseWeight: 0.1` |
| `predictions.jsonl.gz` | Candidates/witnesses/warnings for both policies and all three variants |
| `timings.jsonl.gz` | Per-call scorer latency, separate from deterministic predictions |
| `exclusions.jsonl.gz` | Every omitted development game and its reasons, including sample limits |
| `report.json` | Metrics and abstentions by split, policy and variant |
| `manifest.json` | Original/prepared/artifact/code hashes, documentation sources, cutoffs, policy, limits and remaining assumptions |

Join context, features and labels on **`caseId`**. Match outcomes and actual next champions are only labels; they do not enter scoring. Final roles and player/champion pairings from the current game are not in features. The ten case weights sum to one per exported match; ten decisions are not ten independent matches.

For the next ML milestone:

- Use only the `training` partition for fitting parameters and preprocessing. Validation is for model selection. The 2026 seal stays closed.
- A target may be absent from the earlier candidate vocabulary. Count and explicitly handle these cases; do not inject the label champion into the features or silently discard it from the reported denominator.
- Candidate list sizes vary. A ranker needs masked/padded or per-candidate inputs and grouping by case; a next-champion classifier needs an explicit vocabulary/unknown policy.
- Context IDs, snapshot IDs, source group IDs, labels and results are join/provenance fields, not free-form model features. Choose a declared feature schema before fitting.
- Compare against the exported baselines on the same cohort. Keep outcome-prediction metrics separate from next-pick agreement. Neither alone proves that an alternative pick would improve a game's result.
- Preserve the manifest, source files and matching source-code revision for reproducibility. Timing values and hashes containing timings naturally differ between runs.

This supplies a usable, explicitly scoped **opening-game research dataset**. It does not claim support for later-game Fearless recommendations, complete historical champion availability, or a trained draft model.

## Reviewed pilot: September 9, 2026

Completed output: `data/oracle/temporal-2026-09-09-reviewed/`. The earlier `temporal-2026-09-09-pilot/` folder was interrupted and has no completion manifest; do not use it for training.

The reviewed run exported **100 training games and 100 validation games**, producing 2,000 decision examples and 192 dated snapshots. It left all 8,432 reserved test games unscored and out of the historical snapshots. Source checks found 11,354 structurally eligible opening games across the complete batch; the development partitions contain 2,912 eligible training games and 4,203 eligible validation games before pilot sampling.

Validation results use all 1,000 decision cases from the same 100 games, including abstentions in the agreement denominator:

| Policy | Baseline | Top-three agreement | Actual pick in candidates | Abstentions |
| --- | --- | --- | --- | --- |
| Observed-only | Pool | 14.7% | 71.0% | 211 |
| Observed-only | Pool + flexibility | 14.6% | 71.0% | 211 |
| Observed-only | Pool + flexibility + stats | 16.0% | 71.0% | 211 |
| Incomplete-history / inferred | Pool | 14.6% | 100.0% | 0 |
| Incomplete-history / inferred | Pool + flexibility | 14.0% | 100.0% | 0 |
| Incomplete-history / inferred | Pool + flexibility + stats | 14.0% | 100.0% | 0 |

All variants had zero detected draft-legality/completion violations. Validation p95 scorer latency for the stats variant was approximately 5.2 ms observed-only and 16.0 ms inferred on this machine, excluding history construction, export and any server/UI overhead.

**Interpretation:** permitting unknown pro capabilities fixes a coverage problem, but does not establish better ranking. The broader candidate list and changed familiarity formula need further experiments. Neither the 2-point stats-policy difference nor the small differences between variants establish statistical significance: the sample contains 100 games, not 1,000 independent games. No win-improvement claim follows from predicting a pro's next pick.

Verification completed:

- 35 benchmark tests and 5 preparation regression tests passed.
- All 10 artifact hashes and 6 implementation-source hashes matched the manifest.
- All 192 snapshots used source games strictly before their declared cutoff, with no reserved-test IDs.
- All 2,000 context/feature/label IDs aligned; each game's label weights summed to one; the current game was absent from its snapshot.
- Independent review checked chronology/test-boundary fixes and compared the equal-domain assignment optimization against exhaustive results on 200 randomized cases.

Next: declare a small ML feature schema and missing-vocabulary policy, then train a simple candidate ranker on training labels only. Use these same validation games and baselines for the first comparison; reserve a larger development evaluation for checking stability, and keep 2026 sealed until model selection is complete.
