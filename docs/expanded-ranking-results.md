# Beatrice expanded pick/ban experiment — September 12, 2026

## Decision

**Keep the CPU LightGBM tree as the overall pro-pick imitation research winner. Do not replace the live recommendation service yet.** It beats the matched fixed baselines and linear ranker overall, but regresses on blind picks. The separate linear ban model improves ban imitation; retain Java `evidence-bans-v1` for actual ban recommendations.

These models learn recorded professional choices, **not objectively optimal picks, counterfactual ban utility, or win probability**. No website, database, champion metadata, saved teams, or LLM integration was changed.

## Data and evaluation boundary

- Training: all 2,912 eligible opening games, 29,120 decisions, from the 2024 training partition.
- Validation: all 4,203 eligible opening games, 42,030 decisions, from 2025.
- Earlier-only expanding history, one-day availability lag, seven-day label embargo at partition boundaries. Earlier validation history can inform later validation cases, but never model fitting or normalization.
- The 2026 test set remains unscored. Validation selected the winning fixed configuration, so these are development results, not an untouched final-test estimate.
- Standard opening-game chronology is supported by publisher pick/ban ordinal definitions and source audits. Later-series drafting rules and all historical champion disables are not certified.
- Pick export: 71,150 cases, 530 history snapshots, 11,122,116 candidate legality/player-completion checks, and zero recorded violations. Source timestamp checks: 6,396,299; unavailable timestamps: zero.
- Pro-history absence remains unknown. Authoritative saved pools are separately enforced by the inference adapter. A five-player completion witness is not a confirmed five-role lineup.

## Pick comparison

All five methods rank the same candidates for the same decisions. Top-k agreement asks whether the actual pro choice appears in the first k suggestions. Other candidates are alternatives, not proven bad picks. MRR is mean reciprocal rank; higher is better.

| Method | Top-1 | Top-3 | Top-5 | MRR |
| --- | --- | --- | --- | --- |
| Inferred pool | 4.47% | 11.98% | 17.94% | 0.1323 |
| Pool + flexibility rules | 4.54% | 11.85% | 17.77% | 0.1326 |
| Pool + flexibility + statistics | 4.75% | 12.35% | 18.59% | 0.1362 |
| Pairwise linear | 6.86% | 18.21% | 27.61% | 0.1832 |
| CPU tree / LambdaRank | 8.83% | **21.02%** | **30.13%** | **0.2051** |

The tree gains **8.67 percentage points** in top-three agreement over the strongest fixed baseline (paired whole-game bootstrap 95% interval: **+8.23 to +9.08**). Its gain over linear is **2.81 points**, interval **+2.42 to +3.20**. These intervals use 2,000 resamples of whole games. They do not eliminate dependence between repeated teams/series or model-selection optimism.

Validation candidate coverage is 99.979% for every method: nine actual picks are absent and remain misses. Training has three absent targets. No candidate-list abstentions occurred in this permissive pro-history experiment; that does not imply a user's narrower saved pools will always permit a recommendation.

### The important blind-pick regression

| Stage | Cases | Strongest overall fixed baseline | Linear | Tree |
| --- | --- | --- | --- | --- |
| Blind: no visible picks | 4,203 | 10.90% | **11.61%** | 9.18% |
| Early: other non-late decisions | 21,015 | 11.30% | 14.12% | **14.88%** |
| Late: at least three allied picks | 16,812 | 14.03% | 24.98% | **31.66%** |

Values are top-three agreement. Blind here means the first pick with neither side showing a pick, not every champion considered safe to blind in a lane. The overall tree winner must not hide its blind-stage weakness. A tree/linear stage switch chosen after seeing these results would be a new, post-hoc model—not an already validated improvement.

Tree training top-three agreement is 31.08%, versus 21.02% in validation. Linear is 20.35% versus 18.21%. The larger tree gap and blind regression warrant further generalization checks. Small patch cohorts are unstable: patch 15.22 has only 70 decisions from seven games.

### Evidence and failure analysis

Of 6,636,603 validation candidates, 4,036,679 have no observed roster-player familiarity and 884,077 have fewer than 30 global observations. Pair evidence is sparse: 6,827,483 observed pair entries have small samples. Missing-pair flags also include cases with no visible allies; they must not all be interpreted as collection failures.

Training split gains are largest for historical champion sample size, pair sample sizes, champion posterior rate, pair coverage, and player familiarity. This suggests reliance on historical prevalence/co-occurrence, not proof of causal synergy. Split gain is descriptive, biased feature importance; no validation ablation established that a particular feature helps or hurts. Historical composition metadata, lane-specific enemy matchups, actual saved comfort, and the user's team-outcome history are not ML features here.

Concrete examples from the saved report:

- **Baseline beats ML:** `LOLTMNT05_130638:19`, Kayn ranks third under the fixed baseline but 83rd under the tree.
- **Rare pick:** `LOLTMNT02_243477:16`, Master Yi ranks 152nd of 154 candidates. Broad candidate coverage alone does not solve rare-pick ranking.
- **Cold start:** `LOLTMNT02_207868:17`, Mel is absent from the historical candidate set. The label is not inserted afterward.
- **Blind failure:** `LOLTMNT02_292891:6`, both methods rank Yunara 160th of 165 candidates.
- **Meaningful imitation gain:** `LOLTMNT05_114117:8`, Lulu improves from 161st under the baseline to first under the tree.

The error file selects deterministic extreme examples; these are illustrations, not representative frequencies. Scores and margins are not calibrated confidence. Roles remain unknown.

## Separate ban result

| Method | Top-1 | Top-3 | Top-5 | MRR |
| --- | --- | --- | --- | --- |
| Earlier ban popularity | 3.84% | 10.18% | 17.50% | 0.1228 |
| Linear ban imitation | 5.72% | **14.47%** | **21.80%** | **0.1566** |

Top-three gain: **4.29 points**, paired game interval **+3.94 to +4.65**. Validation has five absent targets, 99.988% coverage, and zero illegal suggestions. The model uses a separate objective/schema and deterministic sampled training alternatives; evaluation includes all candidates. It does not certify ban threats or justify abandoning evidence-backed abstention. Known professional opponent rosters also differ from an unscoutable queue. See [the ban report](ban-imitation.md) for phase metrics, errors, and commands.

## Artifacts, runtime, and verification

- Pick dataset: `data/oracle/compact-2026-09-11-resumable/`.
- Pick models/reports: `data/oracle/scaled-2026-09-12-reviewed/` (`tree.txt`, `linear.json`, `schema.json`, `selected.json`, `report.json`, `error-analysis.json`, predictions, manifest).
- Ban dataset: `data/oracle/ban-2026-09-12-all/`.
- Ban model/reports: `data/oracle/ban-ranker-2026-09-12-reviewed/`.
- Pick dataset-manifest SHA-256: `208e5921b06ce8f2f4a1b9cd6f74c037e4a191d66f10156550cbcfc7dcb87692`.
- Pick model-manifest SHA-256: `d1ff1696c4aa1e09bd3c5402cb104b91441526c52e9f299712623fa0427615b5`.

The selected tree file is 186,199 bytes: 100 rounds, at most 15 leaves per tree, two CPU threads, no GPU. This run measured validation rank-and-sort p95 of 0.88 ms for tree and 2.99 ms for linear. These are implementation/run measurements, not inherent speed guarantees. Fixed-baseline latency only measures precomputed-score lookup/sorting. Derived tree pipeline p95, adding recorded evidence/feature construction, is 80.57 ms and still excludes API, database/network, startup, and UI overhead.

The offline pick job took 1,526.5 seconds (about 25.4 minutes): loading/checks 463.4 seconds, linear fit 214.3 seconds, tree fit 29.7 seconds, ranking/reload evaluation 523.0 seconds, plus reporting and final checks. It is not the runtime cost of one recommendation. Ban optimization took 22 seconds; its full job took 506 seconds.

Verified:

- 86 benchmark tests and five Oracle ingestion tests pass.
- All final pick and ban artifact hashes match their manifests.
- Both pick models reproduce scores after saving/reloading across every evaluated matrix.
- The selected tree passes the JSON-lines adapter using real exported case `LOLTMNT02_68127:6`: all 159 candidate ranks and scores match exactly, and feature contributions plus bias reconstruct scores.
- That adapter check uses synthetic broad saved pools to reproduce the offline universe; it does not modify or validate a real user team.
- `offlineOnly: true` requires explicit `allowResearchModel: true`, even when the artifact records a positive validation advantage as `deploymentEligible`.

Schema details, installation, and rerun commands are in [the ranker guide](pro-pick-ranker.md). Reuse completed datasets, but choose a new model-output directory for a rerun. No commits or live service integration were performed.

## Exact next milestone

**Improve and evaluate blind-pick behavior before live ML integration.**

Hypothesis: pooled old-season evidence and limited context make blind recommendations insensitive to current pro priorities, while the tree benefits disproportionately from ally-pair observations later in the draft.

Method: freeze this result as the benchmark; test earlier-only rolling/patch-recency features and a predeclared stage-aware scoring policy using chronological folds inside training history. Historical role propensities may later provide soft role-feasibility evidence, but must not become current-game role labels or hard bans on unusual picks. Keep saved user pools authoritative and 2026 sealed.

Metrics: blind and overall top-1/3/5, MRR, rare/new champion coverage, late-stage non-regression, missing evidence, and CPU latency. Expected outcome: improve blind top-three agreement without losing the current late-draft advantage. Possible failure: shorter history windows worsen rare-player/champion coverage or a stage-specific model overfits a smaller sample.

Do not declare an improvement from a post-hoc switch on this same validation report. After that experiment, evaluate the frozen signal in shadow mode with real saved pools before allowing it to influence live recommendations. The LLM remains a later explanation/chat layer, not a substitute for these checks.
