# Pro-pick imitation and CPU ranking experiments

The full 2,912-training / 4,203-validation game experiment is complete. See [the expanded results and next milestone](expanded-ranking-results.md): the tree wins overall, but regresses on blind picks and remains offline-only.

## Purpose and boundaries

This model learns **what professional teams tend to pick**, not the objectively best champion for the user's team and not a win probability. Other legal champions are comparison alternatives, not proven bad picks. It remains an offline research component; the website, Spring Boot endpoint, saved teams, champion metadata and PostgreSQL schema are unchanged.

The eventual hybrid system should keep separate signals:

- Hard rules enforce availability, saved champion pools and feasible assignments before ranking.
- Statistical evidence retains its sample sizes, missingness and historical scope.
- ML supplies an uncalibrated pro-choice preference.
- Actual saved comfort and team results remain distinct from pro-history familiarity.
- A future Beatrice LLM may interpret these signals and answer questions, but cannot override hard constraints. No LLM is implemented here.

See [the evidence audit](ml-evidence-audit.md) for the precise separation between Java production scorers, the Python research baselines and the learned models, including the documented ban-order semantics.

## Feature schema v1

`scripts/benchmark/ml_features.py` defines a whitelist of 11 base features:

1. Log of one plus the greatest earlier candidate-game count across the five players.
2. Log of one plus the total earlier count across those players.
3. Fraction of the roster previously observed playing the candidate.
4. Smoothed historical champion win rate, using a Beta(25,25) prior.
5. Log of one plus the champion's historical sample size.
6. Missing champion-statistic indicator.
7. Mean observed ally-pair delta against individual champion baselines.
8. Log of one plus mean pair sample size.
9. Log of one plus minimum pair sample size.
10. Fraction of visible allies with pair observations.
11. Missing pair-evidence indicator.

The 11 values are also multiplied by blind and late-stage indicators, producing **33 features**. A blind decision has no visible picks; late means at least three allied picks. These interactions allow evidence to carry different weights at different stages. The chronological action index is not a lane assignment.

Missing champion performance maps to 0.5, missing pair delta to 0, each accompanied by a missingness indicator. An unobserved player/champion pair remains unknown, not prohibited. No final role, current-game outcome, actual target, player/game/champion identity, or previous scorer's candidate ordering enters the feature vector.

The schema deliberately omits unsupported composition and lane-matchup features. The imported metadata has no verified historical 2024/25 version. Current-split Riot aggregates cannot be retroactively joined into older pro drafts. Earlier Oracle records could support future recency, patch-specific and enemy-interaction features, but those require separately tested earlier-only derivations.

## Linear model and reproducibility

`linear_ranker.py` minimizes weighted pairwise logistic loss plus L2 regularization. A training comparison is the chosen champion versus one available alternative. Every usable game has equal total weight, every usable decision within it has equal weight, and its alternatives share that decision's comparison weight.

Normalization uses only covered training cases, with equal case mass regardless of candidate-list length. Constant columns are disabled, including if they vary later in validation. Standardized values are clipped to [-8,8]. Missing targets are never inserted: unusable training decisions are counted, and missing targets remain evaluation misses.

The configuration is fixed before validation: zero initialization, 300 full-batch steps, learning rate 0.1, L2 0.01. There is no validation hyperparameter search. Validation is prequential: earlier validation results can update historical evidence after the one-day availability lag; they never fit model parameters or preprocessing. The 2026 period remains sealed.

## Reproduced 100-game pipeline pilot

Input: `data/oracle/temporal-2026-09-09-reviewed/`.

Two completed runs, `ranker-2026-09-09-pilot/` and `ranker-2026-09-10-reproduction/`, produced byte-identical model and prediction files. All six old baseline top-three metrics were reproduced. This is a pipeline pilot, not final training.

Validation: 100 whole games, 1,000 decisions.

| Method | Top-1 | Top-3 | Top-5 | MRR | Candidate coverage |
| --- | --- | --- | --- | --- | --- |
| Inferred pool | 6.0% | 14.6% | 19.8% | 0.1488 | 100% |
| Inferred pool + flexibility + stats | 5.6% | 14.0% | 20.6% | 0.1473 | 100% |
| Observed-only pool + flexibility + stats | 5.7% | 16.0% | 24.4% | 0.1518 | 71% |
| Linear ranker | 8.4% | 19.9% | 29.2% | 0.1960 | 100% |

The inferred-policy baseline is the matched-candidate comparison. Observed-only results have different candidate restrictions and should not be described as isolating model quality. The linear ranker's pilot improvement over inferred stats was 5.9 percentage points; the paired whole-game bootstrap interval was approximately +3.4 to +8.4 points. Repeated teams/dates may make this interval too optimistic. These are imitation metrics, not estimated win gains.

The pilot's 1,000 training decisions generated 153,030 comparisons. Optimization took about 6 seconds in the initial run. Ranking p95 was below 1 ms per case with already-computed features; it excludes data collection, historical aggregation, feature extraction, subprocess startup and backend/UI overhead. Timing varies by machine and load.

## Environment and commands

The isolated environment `.venv-ranker/` is ignored by git. LightGBM was added because a tree ranking objective is a compact CPU-friendly nonlinear comparison. It uses no GPU. NumPy and SciPy support numerical operations; the pinned requirements do not modify Java or frontend dependencies.

From the repository root:

```powershell
python -m venv .venv-ranker
.\.venv-ranker\Scripts\python.exe -m pip install -r scripts/benchmark/requirements-ml.txt
.\.venv-ranker\Scripts\python.exe -m unittest discover -s scripts/benchmark -p 'test_*.py'
.\.venv-ranker\Scripts\python.exe -m unittest discover -s scripts/oracle -p 'test_*.py'
.\.venv-ranker\Scripts\python.exe scripts/benchmark/train_ranker.py --dataset data/oracle/temporal-2026-09-09-reviewed --output data/oracle/ranker-new-pilot
```

Use new output directories; completed artifacts are never overwritten. Interrupted folders without `manifest.json` are not valid training inputs. Preserve the source code, dataset manifests and artifact hashes together. JSON artifacts avoid executable pickle models.

## Full chronological export

`compact_dataset.py` evaluates the inferred scorer once per case and derives all three fixed baselines on exactly the same candidates. It verifies candidate legality and complete five-player assignment witnesses before omitting those redundant witnesses from compact training files. It retains structured evidence separately for later inspection.

```powershell
.\.venv-ranker\Scripts\python.exe scripts/benchmark/resume_dataset.py --prepared data/oracle/prepared-2026-09-08-reviewed --raw-dir data/oracle --output data/oracle/compact-2026-09-11-resumable --workers 2 --chunk-games 50
```

Defaults include all eligible training and validation opening games. Current source eligibility yields 2,912 training and 4,203 validation games. The resumable wrapper uses two CPU workers, each processing at most 50 games per partition in a shard. Rerun the exact same command to reuse completed, hash-verified shards. Input, code, or selection changes are rejected rather than silently mixing experiments. A shard interrupted before its manifest is written is preserved but not reused. The final manifest is published only after all shards have been verified and merged.

The older `compact_dataset.py` command remains available for small one-shot exports. The interrupted `compact-2026-09-10-all` and `compact-2026-09-11-all` folders have no completion manifest and must not be used for training.

After the resumable export completes:

```powershell
.\.venv-ranker\Scripts\python.exe scripts/benchmark/scaled_train.py --dataset data/oracle/compact-2026-09-11-resumable --output data/oracle/scaled-2026-09-12-reviewed
```

This compares the fixed linear model, a fixed 100-round CPU LightGBM LambdaRank model, and three fixed baselines using identical candidates. The tree uses 15 leaves and two threads; it does not use GPU memory. Its text model is saved as exact UTF-8 bytes because Windows newline conversion can invalidate LightGBM's internal byte offsets. Reports separate model-only ranking latency from historical evidence/feature construction.

The full comparison is much slower than an individual prediction: it verifies and reads large compressed artifacts, trains both models, saves all candidate rankings, then rereads evidence for error examples. The final error-analysis phase can take several minutes without a progress line. `selected.json` appearing is not completion; wait for a successful exit and `manifest.json`. A model-only latency figure does not describe this offline job's duration.

## Future Spring Boot boundary

`inference.py` is a persistent JSON-lines subprocess adapter, not an HTTP server or a live product integration. It loads the selected artifact once and accepts one request/response per line. The backend must supply canonical champion IDs, a trustworthy timestamped evidence snapshot, the available champion catalog, the current draft, and all five authoritative saved pools.

It independently excludes picked/banned/unavailable champions and requires a feasible five-player completion within saved pools. Saved comfort is returned separately; it is not substituted for pro-game counts. Responses retain score, rank, feature contributions, familiarity, statistical evidence, missing information and hypothetical player assignments. Roles remain unknown. `modelConfidence` is null because there is no calibrated confidence model. Even a model marked eligible on pro validation has an explicit pro-to-user domain-shift warning.

The caller's `evidenceAsOf` must not follow `decisionTime`; timestamps alone cannot certify the upstream pipeline. A backend adapter must enforce genuine as-of retrieval. Production bans keep their separate evidence-backed abstention and protected-pick rules; the pick adapter does not silently become a ban API.

All scaled models are marked `offlineOnly: true`. Requests must explicitly include `allowResearchModel: true`, even when validation yields `deploymentEligible: true`. That latter field records a validation advantage only; it does not authorize live use or establish usefulness for your team. Both linear and tree adapters are tested for saved-pool filtering and empty-candidate abstention. `featureContributions` plus `modelBias` reconstruct the model score, but are not causal explanations.
