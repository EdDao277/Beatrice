# Expanded Pick/Ban Ranking Experiment

The user approved autonomous implementation in the pasted "Accelerate Pick/Ban Recommendation Model" request. Continue the existing checkout and preserve all uncommitted work; no commit, UI, database schema, metadata, scraping or LLM changes.

## Completed prerequisites

- [x] Inspect code rather than relying on stale docs; distinguish production and research baselines.
- [x] Reproduce linear pilot artifacts byte-for-byte and all six baseline agreement metrics.
- [x] Audit earlier-only snapshots, preprocessing and whole-game weighting independently.
- [x] Verify publisher definitions of team-relative pick and ban ordinal fields; preserve conditional standard-format opening-game assumption.
- [x] Exclude current metadata/aggregate joins without historical as-of provenance.

## Implementation and experiment work

- [x] Add one-pass compact export with identical candidate sets for all fixed baselines and structured evidence retained.
- [x] Complete full eligible chronological pick export (2,912 training / 4,203 validation opening games); keep 2026 sealed.
- [x] Train fixed linear and CPU LightGBM rankers on identical examples; no sealed-test tuning.
- [x] Generate comparison/cohort metrics, evidence availability, error samples and saved selected-model artifacts.
- [x] Implement and evaluate a separate ban-imitation baseline, preserving production ban utility/abstention behavior unchanged.
- [x] Implement JSON-lines pick inference adapter with saved-pool/catalog/visible-draft checks and structured evidence; test it independently.
- [x] Run complete regression suites, independent reviews, artifact reload/hash checks; document results and next experiment.

## Interfaces and ownership

- `compact_dataset.py`: manifest v3, compact feature matrix plus separate context/label/evidence records.
- `scaled_train.py`: verified compact input to linear/tree artifacts, selected.json, comparison/error reports.
- `inference.py`: selected artifact directory plus JSON-lines request to validated structured pro-pick imitation output.
- `ban_experiment.py`: independently generated earlier-only ban contexts, distinct features/targets, baseline/model/evaluation artifacts.

The strongest justified result may still be a fixed baseline. Model selection must report that honestly. A pro-choice imitation winner is not proof of optimal team drafting or win improvement.

## Verified continuation checkpoint (September 12)

- Full pick dataset: `data/oracle/compact-2026-09-11-resumable/`, complete manifest; 71,150 cases, 11,122,116 legality and completion checks, zero violations, 12 absent targets.
- Full ban dataset: `data/oracle/ban-2026-09-12-all/`, complete manifest.
- Full ban experiment: `data/oracle/ban-ranker-2026-09-12-reviewed/`, complete and all artifact hashes verified. Validation top-three: popularity 10.18%, linear 14.47%; keep production ban scorer unchanged.
- Real-shard pick smoke: `data/oracle/scaled-2026-09-12-shard-smoke/`, both models trained/reloaded successfully; not the final comparison.
- Full pick comparison completed in `data/oracle/scaled-2026-09-12-reviewed/`; final manifest and all artifact hashes verified. Tree top-three validation agreement 21.02%, linear 18.21%, strongest fixed baseline 12.35%. Tree blind regression is documented; no live integration. See `docs/expanded-ranking-results.md`.
- Latest regression evidence: 86 benchmark tests and five Oracle tests passed. Both linear/tree inference contracts are tested; `offlineOnly` requires an explicit research override even if validation advantage is positive.
- Do not reuse old incomplete exports (`compact-2026-09-10-all`, `compact-2026-09-11-all`, `ban-2026-09-11-all`). They were preserved, not deleted.
