# Pro-pick Imitation Ranker Implementation Plan

> Execute inline using executing-plans and TDD. The user approved this design and continued work in the existing checkout. Do not commit or modify live services.

**Goal:** Train and evaluate one small CPU-only candidate ranker that imitates pro choices, not optimal picks or wins.

**Architecture:** Read the immutable reviewed temporal export. Convert whitelisted prior-evidence fields to numeric vectors, fit training-only normalization and a regularized linear pairwise model, then evaluate against the same exported baseline decisions. Write a new offline model/report directory without modifying inputs.

**Tech Stack:** Python 3.12, NumPy 2.3.5 (already installed in the bundled runtime); no GPU, network or database calls.

**Spec:** User-approved design in this conversation: candidate familiarity, smoothed historical performance, ally evidence, draft-stage interactions and missingness. Pro-pick imitation is only one future signal alongside rules, Bayesian statistics and authoritative saved-team evidence; an LLM may explain those signals but must not bypass hard constraints.

## Global constraints

- Use `data/oracle/temporal-2026-09-09-reviewed` (100 training and 100 validation games). Do not train/evaluate on the reserved 2026 test.
- Do not use outcomes, final roles, current-game assignments, player/game IDs or candidate list order as features.
- Never insert a missing target into candidate features. Skip such training cases with explicit counts; retain them in evaluation denominators.
- Equal total training weight per game, equal comparison weight per case, all available alternatives (no random negative sampling).
- One declared configuration: L2=0.01, learning rate=0.1, 300 full-batch steps, zero initialization. No validation-driven tuning.
- Scores are uncalibrated imitation preferences. Saved-team comfort is not equivalent to observed pro frequency; no live integration this milestone.

## Tasks

- [x] Feature contract: create `scripts/benchmark/ml_features.py` and `test_ml_features.py`. First test `vector(context, candidate)` ignores IDs/results, has neutral missing indicators, is roster-order invariant and rejects invalid evidence. Run tests red, implement named schema and bounded stage interactions, run green.
- [x] Optimizer: create `linear_ranker.py` and `test_linear_ranker.py`. First test a hand-made two-candidate dataset learns the positive direction, gradients match finite differences, missing targets are not injected, and serialization reproduces scores. Implement training-only weighted scaling, pairwise logistic loss plus L2, deterministic fitting and finite checks. Run red/green.
- [x] Runner: create `train_ranker.py` and `test_train_ranker.py`. Use the real tiny export fixture from `test_build_dataset.py`. Test hash rejection, split isolation, training artifact invariance to validation labels/features, duplicate/invalid joins, missing target accounting and no overwrite. Implement `run(dataset: Path, output: Path)` with streamed evidence loading, source/boundary validation and separate labels; export schema/model/predictions/report/manifest.
- [x] Compare and document: run the reviewed pilot once, report top-1/3/5 agreement, MRR, candidate coverage, abstentions, latency and paired whole-game bootstrap differences against exported baselines. Run all benchmark and Oracle tests, request independent code review, verify model reload and artifact hashes, add `docs/pro-pick-ranker.md` with commands, results and limitations.

## Verification commands

```powershell
python -m unittest discover -s scripts/benchmark -p 'test_*.py'
python -m unittest discover -s scripts/oracle -p 'test_*.py'
python scripts/benchmark/train_ranker.py --dataset data/oracle/temporal-2026-09-09-reviewed --output data/oracle/ranker-2026-09-09-reviewed
```

Tests must fail for the missing behavior before implementing it. Each task is verified before proceeding. No UI/backend test rerun is necessary when runtime code remains unchanged.
