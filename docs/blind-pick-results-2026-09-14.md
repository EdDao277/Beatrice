# Blind-pick improvement results — September 14, 2026

## Decision

**Both preregistered experiments passed. Recommend the recency-enhanced tree for a separate, future shadow-mode milestone.** It improved blind, overall, and late-stage professional pick imitation on chronological 2025 validation. The blind-only specialist is a valid conservative alternative: it improves blind decisions while retaining the frozen tree exactly everywhere else.

The September 12 tree remains an immutable comparator; no model was promoted or integrated. No website, database, metadata, saved-team, ban-model, or LLM changes were made. The 2026 test set remains unscored. These results measure **what professionals picked**, not objectively optimal picks or win probability.

## Features and protocol

The [preregistration](blind-pick-experiment.md) was written before new validation scoring and its hash is saved in the completed experiment manifest.

- Original 33 features and legal candidate lists were preserved.
- Added 25 history features: eight each for 14-day, 30-day, and same-patch history, plus the 14-day minus 30-day priority difference. Each window supplies pick rate, ban rate, pick-or-ban priority, log pick count, log ban count, log game count, empty-window flag, and champion-unseen flag.
- Added blind and late interactions of those 25 features, producing 108 total features.
- New history includes only audited eligible opening games before the exclusive one-day-lag cutoff. Rolling windows end at that cutoff; same-patch history uses the exact source patch label. Original baseline history remains unchanged.
- No final roles, outcome labels, categorical champion identities, or current metadata were added as features. Unusual flex candidates were not removed.
- Both models retained the frozen 100-round, 15-leaf CPU LambdaRank settings. Recency tree: 29,120 training decisions. Blind specialist: 2,912 blind training decisions. Training was 2024 only, with equal total weight per usable game.
- Specialist routing was fixed beforehand: use the specialist only when both visible pick lists are empty; use the frozen September 12 tree for all 37,827 nonblind validation decisions.
- Validation: 4,203 games / 42,030 decisions from 2025. Earlier validation games may inform later history, never parameter fitting. Original timestamps, lag, splits, and label embargo were preserved.

## Blind decisions — 4,203 cases

Top-k measures whether the actual recorded pick appears among the first k suggestions. MRR averages reciprocal rank; higher is better.

| Method | Top-1 | Top-3 | Top-5 | MRR |
| --- | ---: | ---: | ---: | ---: |
| Frozen strongest overall fixed baseline | 4.64% | 10.90% | 17.49% | 0.1313 |
| Frozen linear | 4.12% | 11.61% | 18.34% | 0.1351 |
| Frozen tree | 4.97% | 9.18% | 14.11% | 0.1213 |
| Recency tree | 24.39% | **54.13%** | 66.79% | **0.4321** |
| Blind specialist + frozen nonblind tree | 23.27% | 52.72% | **66.95%** | 0.4218 |

Against the preregistered strongest frozen blind comparator (linear):

- Recency tree: **+42.52 percentage points Top-3**, paired 95% interval **+40.80 to +44.25**.
- Blind specialist: **+41.11 points**, interval **+39.35 to +42.87**.

Both positive lower bounds pass the blind gate. The specialist slightly exceeds the recency tree on blind Top-5, despite lower Top-1/Top-3/MRR; neither model dominates every metric. No extra feature ablation or third configuration was run, so the improvement cannot be attributed to an individual window or feature.

## Overall — 42,030 cases

| Method | Top-1 | Top-3 | Top-5 | MRR |
| --- | ---: | ---: | ---: | ---: |
| Frozen fixed baseline | 4.75% | 12.35% | 18.59% | 0.1362 |
| Frozen linear | 6.86% | 18.21% | 27.61% | 0.1832 |
| Frozen tree | 8.83% | 21.02% | 30.13% | 0.2051 |
| Recency tree | **14.66%** | **33.74%** | **45.66%** | **0.2973** |
| Blind specialist + frozen nonblind tree | 10.66% | 25.37% | 35.42% | 0.2352 |

Recency tree improves overall Top-3 by **12.71 points** over the frozen tree (95% interval **+12.29 to +13.15**). The specialist policy improves it by **4.35 points** (interval **+4.19 to +4.53**). Both also improve overall Top-1, Top-5, and MRR; no overall regression was observed.

## Late decisions — 16,812 cases

| Method | Top-3 | MRR |
| --- | ---: | ---: |
| Frozen fixed baseline | 14.03% | 0.1480 |
| Frozen linear | 24.98% | 0.2331 |
| Frozen tree | 31.66% | 0.2787 |
| Recency tree | **32.60%** | **0.2893** |
| Blind specialist + frozen nonblind tree | 31.66% | 0.2787 |

Recency tree: late Top-3 **+0.94 points** (95% interval **+0.34 to +1.53**), MRR **+0.01060** (interval **+0.00728 to +0.01414**). Thus it passes the maximum-loss limits of 0.5 Top-3 points and 0.005 MRR, with positive intervals for both.

The specialist policy has exactly zero late change, by construction—not a newly learned late-stage improvement. Saved observations and top-five lists were independently checked for exact frozen-tree equality across every nonblind case. Early-stage Top-3 also rises for the recency tree (14.88% to 30.57%); the specialist leaves it unchanged.

## Coverage and missing evidence

Candidate coverage is unchanged for all methods: **99.9786% overall**, nine absent targets, zero empty-list abstentions. Blind coverage is 99.9524%, with two absent targets. Missing targets remain misses; they were not inserted into the candidate list.

Rare means 1–29 earlier global observations in the original features. Integer counts are recovered before comparison to avoid a float32 rounding error at exactly 30 observations.

| Target cohort | Cases | Candidate coverage | Frozen tree Top-3 / MRR | Recency Top-3 / MRR | Specialist policy Top-3 / MRR |
| --- | ---: | ---: | ---: | ---: | ---: |
| Rare | 191 | 100% | 0% / 0.0083 | 1.57% / 0.0288 | 1.05% / 0.0196 |
| New or absent from frozen vocabulary | 9 | 0% | 0% / 0 | 0% / 0 | 0% / 0 |

**Rare-pick ranking remains weak, and cold-start coverage is not solved.** All nine new/absent cases were outside the frozen candidate set. Coverage here means target inclusion, not good ranking or coverage of every champion released at that time.

New feature missingness across 6,636,603 validation candidate rows:

| History window | No historical games | Champion never picked/banned in window |
| --- | ---: | ---: |
| 14 days | 0.26% | 26.66% |
| 30 days | 0.21% | 18.65% |
| Same patch | 4.06% | 45.13% |

Missingness is explicitly flagged. Existing evidence quality is unchanged: missing roster-player history for 60.82% of candidate rows; no ally-pair evidence for 26.36% (includes contexts without allies); 13.32% have small global samples. These are descriptive history signals, not calibrated confidence.

## Latency

Re-measured ranking plus deterministic sorting on this machine:

| Method | Overall mean | Overall p95 |
| --- | ---: | ---: |
| Fixed scores already cached | 0.17 ms | 0.31 ms |
| Frozen linear | 6.39 ms | 13.36 ms |
| Frozen tree | 1.20 ms | 2.15 ms |
| Recency tree | 0.96 ms | 1.70 ms |
| Specialist policy | 1.15 ms | 2.07 ms |

Additional recency feature construction: mean **2.39 ms**, p95 **3.84 ms**, maximum **179.85 ms**. History is cached per day/patch; cache creation is included for the case that triggers it. These are offline component timings, not live end-to-end latency. Do not add the two p95 values and call it a measured pipeline p95. Baseline timing excludes its original evidence computation; no GPU, API, game-running contention, or model startup is measured. Differences from September 12 timing are not controlled speedup claims.

Training took 113.37 seconds for the recency tree and 12.10 seconds for the specialist. The complete verification, feature, training, and evaluation run took 1,662.23 seconds (27.7 minutes).

## Verification and limitations

- 95 benchmark tests and five Oracle-import tests passed. Boundary tests cover lag, rolling-window edges, unseen patch/champion flags, future mutation independence, preserved candidate rows, training-only selection, frozen artifact tampering, model reloads, and exact nonblind routing.
- The run reproduced the frozen full-validation metrics, verified saved models against their in-memory originals, and finished with a complete manifest. Output artifact hashes, code hashes, preregistration hash, and 42,030 unique pre-2026 validation observations were checked after completion.
- Dataset manifest SHA-256 remains `208e5921b06ce8f2f4a1b9cd6f74c037e4a191d66f10156550cbcfc7dcb87692`; frozen experiment manifest remains `d1ff1696c4aa1e09bd3c5402cb104b91441526c52e9f299712623fa0427615b5`.
- The large blind gain is consistent with professional drafts concentrating on recent priority champions, but this experiment does not establish a causal explanation. Features were added as a bundle.
- This 2025 validation set has already been used for development. Confidence intervals use 2,000 whole-game bootstrap resamples, not team/series clusters, and do not correct for repeated experimentation. The sealed 2026 test was not evaluated.
- This is not proof of better recommendations for a saved amateur team, unfamiliar champions, new patches, or live games. Historical role tendencies did not become hard current-game assignments. Saved pools must remain authoritative at eventual inference.

## Files and next boundary

New code: `scripts/benchmark/recency_features.py`, `blind_experiment.py`, and their two test files. Documentation: this report, the frozen preregistration, and `docs/ml-current-state.md`.

Generated artifacts: `data/oracle/blind-2026-09-14-reviewed/` contains both model files, protocol/schema, per-case observations, report, and hashed manifest. This directory remains git-ignored. Reproduction commands are in the current-state document.

**Stop here.** The recency tree is recommended for a separately authorized shadow-mode milestone, retaining the old tree for comparison. No shadow integration, deployment, ban-model work, LLM work, or further tuning was performed.
