# Evidence freshness policy experiment — September 17, 2026

## Recommendation

**Do not replace the production seven-day gate with B or C on this evidence. Keep exact Java fallback for expired ML evidence for now.** Older pro games are not worthless, but the frozen recency ranker's output deteriorated as recent observations disappeared. None of the adequately sized delayed same/different-patch cohorts passed the predeclared full-influence guardrail. This does not establish seven days as an optimal mathematical boundary; it rejects promoting the tested alternatives as proven safe.

If more research is authorized, reduced window-aware influence (B) is a more defensible direction than season-only influence (C). This run does **not** establish that either improves bounded saved-team decisions. Do not treat a small bonus as harmless: it can still select the winner among equal Java scores. No new cap was selected or tested after looking at results.

The distinction is important: old evidence may remain useful as historical context while being insufficient to trust this particular model as a current-draft ranking signal. Missing same-patch features remain missing; we did not move observations forward or substitute season counts into the 108 features.

## Frozen design and verification

Protocol: [freshness-policy-protocol.md](freshness-policy-protocol.md), frozen before scoring; SHA-256 `86b7d3e9277a6e861306a093323b963bfb48e873ad5e251271961aba4d643d86`.

- Frozen model `recency-2026-09-14`, SHA-256 `ea447cdced1aa541446c50ef03c2ed96f06ecd94e4f50fb50514f17d85964ec5`; unchanged 108-feature schema.
- 512 validation games, 128 per quarter selected by fixed game-ID hash; 5,120 draft decisions. This is already-inspected **2025 development validation**, not new independent test evidence.
- 80 synthetic saved-team prefixes (20 at each of four historical anchor dates) using the previously captured real roster and comfort values unchanged. 4,492 legal candidate appearances per delay. Java's actual matcher/scorer produces this panel's candidates and base scores. Unknown metadata/statistics remain neutral.
- Fresh history respects the existing one-day availability lag. Delayed observations are strictly earlier than prediction minus 7/10/14/21/30 days. All history-dependent features are rebuilt, including player, outcome and pair history. Window anchors stay at prediction minus one day.
- Every fresh historical base-feature vector matched the original exported 33-feature vector within 1e-6. The unchanged recency extension supplies the remaining features.
- Model inference and retained-record scoring took 192.28 seconds, excluding initial archive verification/loading. No training or sealed-2026 evaluation occurred. The newly downloaded 2026 CSV was not imported, evaluated or modified.
- Eight new freshness tests, five frozen recency tests and five saved-scenario tests passed. Scoped review found no blocking issue for the verified run. All 33 receipt hashes were independently rechecked after completion with no mismatches.
- Zero raw inference failures, zero saved-panel technical failures and zero candidate/cap safety violations. Production service, Java policy, website, database, saved pools and frozen feature code were unchanged.

The initial slow loader was stopped **before scoring** and replaced with a hash-verified subset loader. Policies, selection and protocol were unchanged. The completed run finished and wrote its report before the conversation interruption; no scored pass was rerun after resuming.

## Exact A/B/C rules tested

All require frozen training-history exposure and at least 30 earlier global champion games. Technical failure always causes exact whole-request Java fallback. Candidate support failure never removes a legal champion.

| Policy | Candidate eligibility and maximum bonus |
| --- | --- |
| A: current | Actual source age <=7 days, >=5 candidate picks in 30 days, >=30 same-patch games: +2.5; otherwise zero |
| B: windows | >=30 games and >=5 candidate picks in 14-day window: +2.5 with >=30 same-patch games, otherwise +1.25. Else equivalent 30-day support: +1.25 with same-patch support, otherwise +0.625. Else zero |
| C: season | Use B first. Otherwise >=30 candidate games and >=100 audited opening games in the prediction calendar year, plus a candidate appearance within 90 days: +0.5. Else zero |

The actual bonus is the eligible cap times the unchanged candidate-relative rank percentile. All candidates remain in the denominator; singleton/equal raw scores produce zero. No raw score is a probability or confidence. C's season counts are used only for eligibility, never as model features.

## Raw ML accuracy — separate from bounded recommendations

Top-1/Top-3 measure agreement with the historical professional pick, not pick quality or win chance. MRR rewards placing that observed pick nearer the top. Rankings include original candidates even when delayed history makes them cold; targets are never injected.

| Source cutoff | Top-1 | Top-3 | MRR | Top-1 unchanged vs fresh | Top-3 overlap vs fresh |
| --- | ---: | ---: | ---: | ---: | ---: |
| Fresh (1-day lag) | 13.93% | 33.61% | .2926 | 100.00% | 100.00% |
| 7 days | 12.03% | 30.14% | .2678 | 60.00% | 70.53% |
| 10 days | 11.25% | 28.28% | .2556 | 52.19% | 63.48% |
| 14 days | 10.47% | 23.91% | .2287 | 35.18% | 49.05% |
| 21 days | 5.43% | 15.86% | .1617 | 17.54% | 29.70% |
| 30 days | 5.21% | 14.16% | .1516 | 15.39% | 26.24% |

Overall paired Top-3 deltas versus fresh (1,000 game-cluster bootstrap resamples, seed 1729):

| Cutoff | Top-3 delta | Paired 95% interval | MRR delta |
| --- | ---: | ---: | ---: |
| 7 | -3.48 pp | [-4.38, -2.52] pp | -.0248 |
| 10 | -5.33 pp | [-6.48, -4.16] pp | -.0370 |
| 14 | -9.71 pp | [-11.04, -8.30] pp | -.0638 |
| 21 | -17.75 pp | [-19.12, -16.43] pp | -.1308 |
| 30 | -19.45 pp | [-20.80, -18.16] pp | -.1410 |

The full-influence guardrail allowed at most 2 pp Top-3 loss and .02 MRR loss, with at least 30 games. All adequately sized delayed cohorts fail. This checks general raw degradation, not the causal accuracy of only those candidates B/C support.

### Same-patch versus different-patch

Group means whether the latest **retained audited source game** has the prediction's patch. Multiple regions can play different patches concurrently, so this is not identical to having any same-patch observations. Cohorts change with delay; paired deltas compare each cohort with its own fresh results, not the full fresh population.

| Cutoff | Latest-source patch | Games | Top-1 | Top-3 | MRR | Paired Top-3 loss |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 7 | Same | 241 | 13.36% | 32.28% | .2840 | 3.57 pp |
| 7 | Different | 271 | 10.85% | 28.23% | .2534 | 3.39 pp |
| 10 | Same | 155 | 13.16% | 30.00% | .2736 | 4.58 pp |
| 10 | Different | 357 | 10.42% | 27.54% | .2478 | 5.66 pp |
| 14 | Same | 64 | 13.28% | 28.13% | .2586 | 7.03 pp |
| 14 | Different | 448 | 10.07% | 23.30% | .2245 | 10.09 pp |
| 21 | Same | 11 | 6.36% | 16.36% | .1796 | 14.55 pp — too small |
| 21 | Different | 501 | 5.41% | 15.85% | .1613 | 17.82 pp |
| 30 | Same | 1 | 0.00% | 10.00% | .1222 | 30.00 pp — not estimable reliably |
| 30 | Different | 511 | 5.23% | 14.17% | .1517 | 19.43 pp |

There were no missing-source-patch cohorts. Seven-day same-patch Top-3 delta CI was [-4.77, -2.32] pp; ten-day same-patch [-6.26, -2.97] pp; fourteen-day same-patch [-10.47, -3.44] pp. Same-patch alone does not justify retaining full influence.

### Draft stage (raw Top-3 / MRR)

| Cutoff | Blind | Early | Late |
| --- | ---: | ---: | ---: |
| Fresh | 54.88% / .4271 | 30.08% / .2737 | 32.71% / .2826 |
| 7 | 48.05% / .3801 | 26.05% / .2418 | 30.76% / .2722 |
| 10 | 43.36% / .3469 | 24.30% / .2290 | 29.49% / .2660 |
| 14 | 31.84% / .2819 | 20.63% / .2055 | 26.03% / .2444 |
| 21 | 12.89% / .1372 | 11.45% / .1283 | 22.12% / .2096 |
| 30 | 9.18% / .1115 | 9.92% / .1183 | 20.70% / .2033 |

Blind/early rankings are especially sensitive to missing recent observations. Stage results are descriptive; no stage-dependent production policy was added.

## Bounded Java+ML saved-team results

**Top-1/Top-3 accuracy and MRR are not estimable for this panel:** synthetic saved-team states have no known correct-pick labels. Assigning unrelated pro choices as their labels would be misleading. Below are eligibility, realized bonuses and ranking stability—not accuracy. Candidate counts total 4,492 per policy/delay; exact fallback uses all scores and the entire ordering, not just Top-1.

### Candidate eligibility and realized-zero contribution

| Cutoff | Policy | Full +2.5 eligible | Reduced eligible | Zero eligible | Actual zero bonus | Exact Java fallback (requests) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 7 | A | 0% | 0% | 100% | 100% | 100% |
| 7 | B | 4.19% | 32.99% | 62.82% | 62.82% | 25% |
| 7 | C | 4.19% | 54.34% | 41.47% | 41.85% | 25% |
| 10 | A | 0% | 0% | 100% | 100% | 100% |
| 10 | B | 0% | 34.22% | 65.78% | 65.78% | 25% |
| 10 | C | 0% | 57.93% | 42.07% | 42.45% | 25% |
| 14 | A | 0% | 0% | 100% | 100% | 100% |
| 14 | B | 0% | 31.48% | 68.52% | 68.52% | 25% |
| 14 | C | 0% | 57.93% | 42.07% | 42.65% | 25% |
| 21 | A | 0% | 0% | 100% | 100% | 100% |
| 21 | B | 0% | 25.67% | 74.33% | 74.33% | 25% |
| 21 | C | 0% | 57.61% | 42.39% | 42.92% | 25% |
| 30 | A | 0% | 0% | 100% | 100% | 100% |
| 30 | B | 0% | 0% | 100% | 100% | 100% |
| 30 | C | 0% | 56.92% | 43.08% | 43.83% | 25% |

“Full eligible” means the candidate's cap is +2.5, not that it actually receives +2.5. A zero percentile can yield zero despite eligibility. A's seven-day result follows the strict cutoff: the newest retained game is actually more than seven days old. Its exact age=7 boundary was tested separately and remains eligible if the other gates pass.

Request tiers classify by the highest eligible cap in the request:

| Cutoff | Policy | Any full eligibility | Reduced-only eligibility | All-zero eligibility |
| --- | --- | ---: | ---: | ---: |
| 7–30 | A | 0% | 0% | 100% |
| 7 | B / C | 25% | 50% | 25% |
| 10–21 | B / C | 0% | 75% | 25% |
| 30 | B | 0% | 0% | 100% |
| 30 | C | 0% | 75% | 25% |

Fresh-reference candidate eligibility (full/reduced/zero): A 25.62/0/74.38%; B 19.97/20.01/60.02%; C 19.97/39.78/40.25%. Fresh exact fallback: A 50%, B/C 25%. Even fresh collection is not guaranteed to contain recent games or the current patch.

### Bounded stability and bonus distribution

Stability compares each policy with **that same policy** on fresh history. For A, stale recommendations revert to Java: Top-1 agreement with fresh A is 50%, Top-3 overlap 65%, and all stale bonuses are zero.

| Cutoff | Policy | Top-1 unchanged | Top-3 overlap | Bonus mean | p50 | p95 | Max |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 7 | B | 98.75% | 90.00% | .3626 | 0 | 1.2500 | 2.5 |
| 7 | C | 98.75% | 88.33% | .3958 | .1397 | 1.2500 | 2.5 |
| 10 | B | 68.75% | 82.08% | .2416 | 0 | 1.1213 | 1.25 |
| 10 | C | 68.75% | 81.67% | .2832 | .1288 | 1.1213 | 1.25 |
| 14 | B | 51.25% | 75.83% | .1899 | 0 | .9523 | 1.25 |
| 14 | C | 51.25% | 73.33% | .2408 | .1324 | .9523 | 1.25 |
| 21 | B | 76.25% | 77.50% | .1550 | 0 | .9418 | 1.25 |
| 21 | C | 68.75% | 73.33% | .2273 | .1269 | .9418 | 1.25 |
| 30 | B | 25.00% | 43.75% | 0 | 0 | 0 | 0 |
| 30 | C | 46.25% | 74.58% | .1597 | .0702 | .4667 | .5 |

C adds 959 / 1,065 / 1,188 / 1,435 / 2,557 season-only eligible candidate appearances at 7 / 10 / 14 / 21 / 30 days. At 30 days it changes Java scores in 75% of requests despite no candidate qualifying under B. We have no correctness labels showing those changes help.

Saved-pool patch split: at 7/14/21/30 days there are 20 same-patch and 60 different-patch requests; at 10 days all 80 are different-patch (same-patch metrics not estimable). B's same-patch Top-1 stability is 95/70/90/0% for those four cutoffs; C's is 95/70/85/20%. Exact fallback is zero for same-patch B at 7/14/21, 100% at 30; same-patch C never falls back in these scenarios. Different-patch B/C fallback is 33.33% except B at 30 (100%); at 10 it is 25%. These small repeated-roster groups are operational probes, not independent samples of team effectiveness.

## Missingness and cold starts

Rates below are means over draft-level candidate rates. Window absence is a draft-level property. Training-unseen candidates average 1.61% at every delay because the candidate universe and training-exposure gate are frozen.

| Cutoff | Zero earlier global history | 14-day window absent | 30-day window absent | Same-patch window absent |
| --- | ---: | ---: | ---: | ---: |
| Fresh | 0.000% | .59% | .39% | 4.30% |
| 7 | .037% | 2.34% | 1.37% | 41.80% |
| 10 | .049% | 3.52% | 2.34% | 61.72% |
| 14 | .074% | 9.38% | 4.49% | 84.57% |
| 21 | .100% | 100% | 7.23% | 97.46% |
| 30 | .118% | 100% | 12.50% | 99.80% |

At 30 days, 100% / 71.77% / 99.94% of candidate appearances on average lack pick/ban exposure in the 14-day / 30-day / same-patch windows respectively. No legal cold champion was removed. Remaining long-window games do not necessarily imply sufficient candidate-specific support.

Actual median source ages were 1.05 / 7.06 / 10.05 / 14.07 / 21.06 / 30.05 days; maxima 34.62 / 40.62 / 42.62 / 46.62 / 54.62 / 63.62. Calendar downtime was retained honestly, not filled with imaginary games.

## Limitations and stop condition

- These are development results for pro-pick imitation, not win probability or objective draft quality.
- The raw panel rebuilds professional identity history; the saved panel correctly leaves that identity evidence missing. Its 2026-captured pools are synthetic retrospective scenarios, not claims about what those players owned in 2025.
- The saved panel has one roster and four anchor dates. Its high seven-day stability cannot prove a safe replacement policy. The full raw population also cannot establish whether a narrower B-supported subset has acceptable accuracy; that was not a separate registered acceptance claim.
- Same-patch 21/30-day groups have only 11/1 games. Their bootstrap intervals must not be treated as reliable evidence. No missing-source cohorts were observed.
- The subset loader relies on the frozen export's verified artifact hashes. Its reshape-based feature loader could be hardened for future untrusted exports; this does not affect these verified inputs.
- Season-only C increases coverage, but increased coverage is not demonstrated benefit. At 21–30 days the raw model loses substantial accuracy, especially blind/early.

**Decision:** retain A in production; do not activate B/C or relax gates from this experiment. Reduced window-aware evidence remains a research candidate, not an approved policy. Keep old pro records as historical evidence, but do not relabel them as fresh. Stop here.

## Artifacts, files and reproduction

Local output: `data/oracle/freshness-2025-2026-09-17/` contains the hash receipt, complete JSON report, six compressed per-decision observations and compiled offline Java harness. Input files remain unchanged. Complete same/different-patch, stage and policy metrics are in `report.json`; the tables above summarize them.

New files: `scripts/benchmark/freshness.py`, `test_freshness.py`, `java/FreshnessScorer.java`, the preregistered protocol and this report. `docs/ml-current-state.md` records the outcome. Production files were not changed in this milestone.

Test: `.venv-ranker/Scripts/python.exe -m unittest discover -s scripts/benchmark -p test_freshness.py`.

To reproduce on the same frozen inputs, use a new output directory: `.venv-ranker/Scripts/python.exe scripts/benchmark/freshness.py --output data/oracle/freshness-reproduction`. Existing output is never overwritten. Do not use this command as authorization to evaluate 2026, tune thresholds or alter the live gate.
