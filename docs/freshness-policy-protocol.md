# Evidence freshness experiment — preregistered September 17, 2026

Approved scope: offline 2025 development only; no frozen-model fitting, 2026 evaluation, production modification, pool writes or schema changes. Freeze this file's SHA-256 in the run receipt before scoring. Never adjust thresholds from results.

## Hypothesis and populations

Older observations may remain useful while actual windows retain support. Season-only support may be less reliable and receives only a small bonus. Failure possibilities include patch transitions, empty recent windows, cold candidates and pro-priority drift.

Select up to 128 validation games per calendar quarter by ascending SHA-256 of `freshness-1729|gameId`, all ten draft decisions per selected game. Original compact candidates are fixed across delays, including candidates that become cold when history is withheld. Target absence counts as a miss; no target injection. This is previously inspected development validation, not a new generalization test.

Raw ML Top-1/3/MRR uses historical labels and original professional player histories rebuilt at the withheld boundary. A separate saved-pool panel uses the captured real roster unchanged, 20 seeded synthetic draft prefixes at one selected prediction date/patch per quarter. Java's current team-wide matcher and existing base scorer own candidates and comfort. Saved-player professional identity evidence stays missing. Saved scenarios have no correct-pick labels: bounded Top-1/3/MRR are **not estimable**, not borrowed from unrelated pro picks. Report bounded ranking stability, support, bonuses and exact Java fallback instead. Metadata is omitted/neutral to isolate freshness and avoid retrospective traits.

## Time and patch definition

Prediction time is midnight UTC on each historical game date, preserving existing availability semantics. Fresh source boundary = prediction minus one day, exclusive. Delayed boundary = prediction minus 7/10/14/21/30 days, exclusive. All history (player/champion/outcome/pair as well as prevalence) excludes observations at or after that boundary. Rebuild 14/30 windows relative to prediction-minus-one-day, **not** relative to the source boundary. Same-patch counts retain the original all-earlier-same-patch arithmetic. No fabricated or shifted observations.

Report actual source age from the latest retained base-history observation: a seven-day simulated cutoff usually means slightly MORE than seven days of actual age. Test the exact age=7 boundary separately. Same/different-patch group compares prediction patch with the patch of the latest retained audited prevalence game (timestamp, then gameId tie-break); report missing if none. Also report absent same-patch windows separately, since global esports can play several patches concurrently.

## Frozen policy rules

Common candidate gate: seen before the frozen training-history boundary AND >=30 earlier global champion games. Individual failures keep the legal candidate with cap zero. Raw model outputs never mean probability/confidence. Technical failures (invalid shape/schema/hash, nonfinite values, wrong candidate set, unavailable inference) cause exact whole-request Java fallback for A/B/C.

Let G14/G30/GP be actual audited window game counts, P14/P30 candidate pick counts, and age actual latest base-source age in days. Full means eligible cap=2.5, reduced means 0<cap<2.5, zero means cap=0. Eligibility is distinct from realized bonus: bottom percentile and all-equal/singleton scores can yield zero despite eligibility.

- **A:** cap 2.5 iff common gate AND age<=7 AND P30>=5 AND GP>=30; else zero. This reproduces production eligibility.
- **B:** common gate required. If G14>=30 AND P14>=5: cap 2.5 when GP>=30, otherwise 1.25. Else if G30>=30 AND P30>=5: cap 1.25 when GP>=30, otherwise 0.625. Else zero. No separate age gate.
- **C:** use B whenever B>0. Otherwise common gate AND >=30 candidate games in prediction calendar year AND >=100 retained audited opening games in that year AND the candidate's latest retained season appearance is <=90 days old: cap 0.5, tagged season-only. Else zero. Season counts affect eligibility ONLY; never feed them into 14/30/patch or any other frozen feature.

Apply unchanged percentile ordering over ALL Java candidates (ascending score, then ID), per-candidate cap*i/(N-1). Cold candidates remain in denominator; all-equal/singleton=>zero. Base+bonus sorted descending then ID. Maximum remains 2.5. Fresh reference for each policy uses that same policy on fresh history; also report Java-only reference. Exact fallback means all IDs, scores AND order equal Java, not merely unchanged Top-1. Separate technical fallback from evidence-driven zero contribution.

## Metrics and decision rule

Per delay, policy and patch group: candidate/request counts; full/reduced/zero eligibility rates; realized-zero bonus rate; exact Java fallback rate; technical failure count; bonus mean/p50/p95/max; Top-1 stability and Top-3 set overlap versus fresh counterpart and Java. Raw pro ranking separately: Top-1/3/MRR, fresh-rank stability, candidate zero-history / training-unseen rates, each window missing/unseen rate, and stage breakdown. Report empty groups explicitly.

Predeclared recommendation guardrail (development-only): do not recommend ordinary full influence in a delay/patch cohort if raw paired Top-3 loss exceeds 2 percentage points OR MRR loss exceeds .02 versus fresh. At least 30 games needed for a cohort judgment; smaller cohorts inconclusive. Game-cluster bootstrap 95% intervals (1000 resamples, seed1729) quantify raw deltas. Saved-panel safety violations must be zero. Reduced policy may be recommended conservatively, but synthetic stability cannot prove effectiveness or justify activation. If raw degradation is large, recommend abstention or a restricted evidence tier; do not search new caps post hoc.

Run receipt records model/schema/input/code/protocol hashes before inference. Check no input/code changes after run. Outputs are new and refuse overwrite. No live gate changes. Stop after report and recommendation.
