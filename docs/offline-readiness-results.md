# Offline production readiness — September 15, 2026

## Decision

The frozen September 14 recency model passes all preregistered final-test gates. The evidence justifies building an **optional, bounded professional-priority signal**, not replacing Java or claiming better win probability. Nothing is activated. The 2026 final test is now spent: no retraining, tuning, alternate routing, or repeat evaluation against it.

Saved-team checks support an initial **0–2.5 point positive bonus** on Java's 0–100 score, subject to evidence gates. This is not a 2.5% estimated win-rate improvement. Raw ML frequently conflicts with comfort; its unrestricted rankings are not suitable as team recommendations.

## Frozen population and provenance

The [acceptance protocol](offline-readiness-protocol.md) was frozen before scoring. Machine-readable hashes, selected game IDs and checkpoints are in `data/oracle/final-2026-readiness/receipt.json`, `games/`, and `complete.json`.

- Model SHA-256: `ea447cdced1aa541446c50ef03c2ed96f06ecd94e4f50fb50514f17d85964ec5`.
- Recency feature-source SHA-256: `188456f86da8209d43c6b82a4432ca5df082facbb24b1402111c907d0f89a78e`.
- Schema/protocol SHA-256: `f7a1c316a1b7dca31c92e4b822d75bb826b693189bb7db590be38d86105f565c`.
- 108 unchanged features; original candidates and frozen September 12 fixed/linear/tree comparators.
- 2,358 eligible opening games / 23,580 decisions from the existing 2026 batch; 6,074 of 8,432 games excluded by the existing source audit, not their results. Unsupported later-series drafts are outside this claim. Data ends September 7, not December 31.
- Before each prediction day, history contains only games strictly earlier than that day minus one day. Earlier 2026 outcomes can update later history after this lag, never model parameters. Expanding history uses earlier prepared games; prevalence uses earlier audited openings. Current outcomes, future games and final lane assignments are unavailable to features.
- Completed game checkpoints were reused after interruption. Final report, receipt and checkpoint hashes were verified; no second scoring pass or post-test model selection occurred.

## Final 2026 results

Top-K measures agreement with the champion actually picked by the professional team. MRR is mean reciprocal rank: larger means the observed pick appeared nearer the top. Neither metric measures objective pick quality.

| Stage / decisions | Model | Top-1 | Top-3 | Top-5 | MRR |
| --- | --- | ---: | ---: | ---: | ---: |
| Blind / 2,358 | Fixed | 2.63% | 7.51% | 11.32% | 0.0974 |
| | Linear | 2.25% | 6.53% | 10.39% | 0.0930 |
| | September 12 tree | 1.65% | 7.55% | 13.36% | 0.0946 |
| | **Recency** | **20.74%** | **44.95%** | **59.58%** | **0.3824** |
| Early / 11,790 | Fixed | 3.41% | 8.98% | 13.99% | 0.1092 |
| | Linear | 4.39% | 11.73% | 18.38% | 0.1351 |
| | September 12 tree | 7.78% | 15.73% | 22.43% | 0.1709 |
| | **Recency** | **13.10%** | **29.29%** | **39.95%** | **0.2690** |
| Late / 9,432 | Fixed | 4.22% | 11.44% | 16.85% | 0.1247 |
| | Linear | 7.20% | 19.39% | 27.71% | 0.1881 |
| | September 12 tree | 8.04% | 21.20% | 32.23% | 0.2090 |
| | **Recency** | **11.19%** | **25.69%** | **37.33%** | **0.2455** |
| Overall / 23,580 | Fixed | 3.66% | 9.82% | 14.86% | 0.1142 |
| | Linear | 5.30% | 14.27% | 21.31% | 0.1521 |
| | September 12 tree | 7.27% | 17.10% | 25.45% | 0.1785 |
| | **Recency** | **13.10%** | **29.41%** | **40.87%** | **0.2709** |

Blind means no visible picks; early means nonblind with fewer than three ally picks; late means at least three ally picks, not known enemy lanes.

| Preregistered gate | Observed delta | Paired 95% interval | Result |
| --- | ---: | ---: | --- |
| Blind Top-3 vs linear: lower bound > 0 | +38.42 pp | +36.13 to +40.54 pp | Pass |
| Overall Top-3 vs tree: lower bound > 0 | +12.32 pp | +11.69 to +12.94 pp | Pass |
| Late Top-3 vs tree: lower bound >= −0.50 pp | +4.48 pp | +3.55 to +5.44 pp | Pass |
| Late MRR vs tree: lower bound >= −0.005 | +0.0365 | +0.0308 to +0.0422 | Pass |

Intervals use 2,000 paired whole-game bootstrap samples, seed 1729. Repeated teams/series are not independently clustered. Linear was the preregistered blind comparator because of its validation performance; comparators were not reselected on 2026.

**Regression:** recency validation Top-3 was 54.13% blind / 33.74% overall / 32.60% late, versus 44.95% / 29.41% / 25.69% here. Final-test advantages are comparisons on the same 2026 decisions, not an assertion that performance stayed constant across years.

Coverage is 99.9958%; one absent target counts as a miss, with no abstentions. The 34 rare-target cases (1–29 earlier observations) have 100% candidate coverage but only 8.82% recency Top-3 and 0.0756 MRR. The single new/absent target has zero coverage. This does not establish cold-start ranking quality.

Across 3,776,241 candidate checks, no earlier champion observations occur in 30.43% of 14-day windows, 22.39% of 30-day windows and 48.91% of same-patch windows. Entire same-patch windows are missing for 5.00%; 14/30-day windows are never wholly missing. Missing champion evidence and missing windows are different conditions.

## Saved-team scenarios

Read-only snapshot: one real team, five players, 76 saved pool entries (11 TOP / 22 JUNGLE / 12 MID / 22 BOT / 9 SUPPORT), catalog 16.17.1. Snapshot SHA-256: `7acc5c7e55c44cc7222df8f576400a379e313c8a94bed7f1b3737f3fe990ecd4`. No Riot collection, team writes, or metadata changes. Fixed as-of day September 14; latest available pro history September 7 at 22:42:48; patch 16.17.

Seed 1729 generates 1,440 states: five roles × twelve categories × two formats × two sides × three stages × two repetitions. 840 preserve actual pools; 600 use explicitly synthetic narrowed/augmented/empty copies. These are simulated states, not independent observed games or best-pick labels. Red-side blind planning is marked as planning before its turn.

The unchanged Java candidate generator and weighted scorer run in an offline Java harness. Full candidate rankings are assembled and their Top-3 asserted equal to the normal full-pool scorer on every case. Java excludes unavailable/out-of-pool champions. This evaluates the existing role-specific player boundary, not a new team-wide role solver. No current-game role inference is added.

Java uses its default no-selected-statistics-dataset path: comfort and known requested composition, other factors neutral. Unknown metadata keeps composition neutral. There is no verified mapping between these users and pro player IDs, so ML player-history features are missing; comfort is never substituted for pro appearance counts. This limits the comparison's evidence breadth.

| Scenario category | Cases | Nonempty | Verified composition-stress cases |
| --- | ---: | ---: | ---: |
| Ordinary unchanged pools | 120 | 120 | — |
| Flex pools | 120 | 120 | — |
| Heavy AD | 120 | 120 | 21 |
| Heavy AP | 120 | 120 | 40 |
| Missing engage | 120 | 120 | 25 |
| Missing frontline | 120 | 120 | 25 |
| Missing peel | 120 | 120 | 20 |
| Synthetic narrow | 120 | 110 | — |
| Synthetic off-meta | 120 | 120 | — |
| Synthetic sparse | 120 | 120 | — |
| Synthetic unseen in training history | 120 | 120 | — |
| Synthetic empty | 120 | 0 | — |

Composition stress is counted only when at least three allies and known metadata actually realize the condition; a blind state cannot establish a heavy composition. Mixed damage is not treated as exclusively AP or AD. In the flex category, 65 states retain a legal candidate shared across saved roles. Sparse/unseen labels are checked against evidence rather than assumed to apply to every generated state.

All 16,113 legal candidate appearances remain present after ML. 7,596 (47.14%) qualify for the support gate. There are 1,310 nonempty cases and 130 safe empty cases, including ten blocked singleton pools. Zero candidate or cap violations occurred.

No natural zero-global-history candidate occurred in this current catalog. A separately labeled **synthetic evidence-fault replay** tested all 11,934 candidate appearances from unchanged pools: even an arbitrarily high ML score with a disabled evidence gate left that candidate's Java score unchanged and preserved the candidate set. All 1,310 all-evidence-missing replays returned the exact Java ranking. These are boundary tests, not cold-start model-accuracy results. Existing tests also cover corrupt/missing models, invalid/nonfinite feature matrices, score/candidate mismatches and unknown metadata.

## Disagreement analysis

Rates below use the 1,310 nonempty cases; categories overlap.

| Pattern | Cases | Rate |
| --- | ---: | ---: |
| Java #1 outside raw ML Top-5 | 690 | 52.67% |
| ML #1 at least three comfort points below Java #1 | 246 | 18.78% |
| That comfort conflict plus >2× 30-day pro priority | 203 | 15.50% |
| ML #1 fails historical-support gate | 157 | 11.98% |
| At least one rare or training-unseen candidate | 754 | 57.56% |
| Bounded top candidate changes | 667 | 50.92% |

**All 667 bounded winner changes were ties in the original Java score; none lowered comfort.** This is encouraging but also exposes how much of Java's default score is neutral. It does not prove the ML tie-break is a better pick. Narrow/off-meta sets with fewer than six candidates cannot exhibit Java #1 outside ML Top-5; that statistic is candidate-count dependent.

Concrete examples from unchanged pools:

- `s0299`, jungle late: Java leads with Diana (comfort 10), raw ML with Vi (comfort 7; 45 recent pro picks). Bounded output leads with Jarvan IV, originally tied on Java score, rather than promoting the lower-comfort Vi.
- `s0310`, jungle late: Java leads with Amumu (comfort 10), ML with Lee Sin (comfort 7; 34 recent pro picks). Bounded output keeps Amumu first.
- `s0868`, bot late: ML leads with Yunara (comfort 6), versus Java's Aphelios (comfort 10). Yunara has 32 recent picks but no exposure in the frozen training history. Her ML bonus is zero; she remains a legal candidate. Bounded output leads with the Java-tied Jhin.
- `s0288`, jungle blind: ML favors Nocturne (comfort 9), Java Diana (10); bounded output leads with Java-tied Jarvan IV. Pro priority and saved comfort answer different questions even without enemy information.

In the ordinary unchanged-pool category alone, 75/120 have Java #1 outside ML Top-5, 28/120 comfort conflicts and 5/120 unsupported ML leaders. Disagreement is not confined to synthetic pools.

## Latency and limits

- Final-test recency ranking: mean 1.03 ms, p95 2.09 ms; frozen tree p95 2.10 ms, linear 0.76 ms.
- Research feature/candidate/baseline construction: separate p95 72.29 ms. Percentiles should not be added as an end-to-end percentile.
- Saved-team feature construction plus ML scoring: p95 2.32 ms, excluding Java, history snapshot construction and model startup.

These are local offline measurements, not website response-time or simultaneous League/GPU benchmarks. No GPU-heavy runtime or new dependency was introduced. One team's simulated drafts cannot establish amateur win-rate benefit, calibrated confidence, or reliability on all patches and rosters.

## Recommended integration design — not activated

1. Preserve Java's candidate set and score. Add at most **2.5 total-score points**, using raw ML's candidate-rank percentile; never reinterpret the ranker as a win probability. This cap was fixed before scenario evaluation, not optimized against its results. A comfort step contributes 3.5 points in the current 35%-comfort scorer, larger than the entire bonus.
2. Candidate bonus is zero unless it was observed in frozen training history, has at least 30 earlier global pro games, at least five picks in the last 30-day window, and the same-patch window has at least 30 games. The last threshold is window support, not 30 appearances of that champion. These tested gates are conservative heuristics, not statistical confidence estimates.
3. Rare/new champions remain valid Java candidates with unchanged scores. Other supported candidates can gain points and change their relative positions; zero direct penalty is not a promise of unchanged rank.
4. Missing/corrupt model, schema mismatch, invalid/nonfinite inputs or outputs, or candidate-ID mismatch causes pure Java fallback. Do not return partial ML results. Keep the scorer version and model hash visible in diagnostic logs.
5. Before any production activation, implement request-wide freshness and deadline checks: a conservative starting design is latest pro evidence within seven days and a roughly 100 ms warm inference deadline. These two operational gates are **proposed, not implemented or validated here**. Never make a network history refresh part of the interactive scoring request. A stale/new patch should safely contribute zero.

Recommendation: proceed only to a separately approved guarded-integration implementation. No live shadow-data prerequisite is needed to build that bounded adapter, but offline evidence does not justify an unrestricted model or an objective-best-pick claim. No model/feature tuning against 2026 is permitted afterward.

## Files and verification

Added the frozen protocol; final evaluator and tests; read-only snapshot tool; saved-scenario runner, Java harness and tests; safety replay verifier; this report. Updated `ml-current-state.md`. Detailed artifacts remain ignored under `data/oracle/`; production backend/frontend sources, model parameters, database, metadata and saved teams were not changed.

Milestone files: `docs/offline-readiness-protocol.md`, `docs/offline-readiness-results.md`, `docs/ml-current-state.md`, `scripts/benchmark/readiness.py`, `test_readiness.py`, `capture_readiness.py`, `saved_scenarios.py`, `test_saved_scenarios.py`, `verify_readiness_scenarios.py`, and `scripts/benchmark/java/ReadinessScorer.java` (the abbreviated Python filenames share `scripts/benchmark/`). Earlier September 14 experiment files remain preserved.

Final verification: 105 benchmark tests and five Oracle-import tests passed. Frozen evaluator/feature code and model hashes match; completed-report and scenario artifact hashes verify; the live read-only team response still equals the original saved-team snapshot. No tracked production-file diff exists. No commit was created.

Safe verification from the repository root (does not launch another final-test evaluation):

```powershell
.venv-ranker/Scripts/python.exe -m unittest discover -s scripts/benchmark -p 'test_*.py'
.venv-ranker/Scripts/python.exe -m unittest discover -s scripts/oracle -p 'test_*.py'
.venv-ranker/Scripts/python.exe scripts/benchmark/verify_readiness_scenarios.py
```

The benchmark suite includes tiny temporary training fixtures for existing code; it does not retrain the frozen model or use the sealed dataset. The milestone stops here.
