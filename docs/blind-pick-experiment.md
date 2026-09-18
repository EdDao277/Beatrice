# Blind-pick experiment — preregistered September 14, 2026

Status: design approved; no new validation scores inspected when this specification was written.

## Fixed protocol

Reuse `compact-2026-09-11-resumable` and frozen `scaled-2026-09-12-reviewed` unchanged. Training is 2024; chronological development validation is 2025. Never score 2026. The target remains recorded professional pick imitation, not optimal picks or wins.

Two experiments only, using the frozen 100-round / 15-leaf LambdaRank configuration:

1. Recency tree: all training decisions, original features plus the features below.
2. Blind specialist: blind training decisions only, with the same extended features. Route to it only when BOTH visible pick lists are empty. All other decisions use the original frozen tree, without modification. This routing is fixed before validation, not selected afterward.

New history uses audited eligible opening games only, before the prediction day's exclusive one-day-lag cutoff. Windows are `[cutoff - 14 days, cutoff)` and `[cutoff - 30 days, cutoff)`; same-patch history is expanding with that same cutoff. Exact source patch labels are used. Each window supplies champion pick rate, ban rate, pick-or-ban priority, log pick count, log ban count, log game denominator, empty-window flag, and champion-unseen flag. Rates are per game, not per player. Each champion counts at most once per game. Add 14-day minus 30-day priority and blind/late interactions of these features. No results, final roles, champion IDs as categorical features, or current metadata joins.

The original candidate sets and original features remain unchanged. Missing window rates are zero with explicit missingness; this is absence of evidence, not a quality penalty. Same-patch zero support is flagged. Original baseline history population remains unchanged (all earlier prepared games); new prevalence intentionally uses only supported audited openings.

## Evaluation and decision

Compare both experiments with the frozen strongest fixed baseline, linear, and tree on identical cases. Report blind and overall Top-1/3/5 and MRR, late Top-3/MRR, missingness, latency, and rare/new target coverage. Rare means fewer than 30 original earlier global observations; new means zero observations or absent from the frozen vocabulary. Do not insert missing targets.

Blind success requires Top-3 above the frozen linear's 11.61%, with a positive lower bound of the paired whole-game 95% bootstrap interval (2,000 replicates, seed 1729). Late loss must not exceed 0.5 percentage points Top-3 or 0.005 MRR; report point deltas and intervals. Report overall regressions explicitly. No parameter search, third experiment, validation-selected routing, or automatic model promotion. A candidate passing the gates is only eligible for a later shadow-mode discussion, not live deployment.

Validation was already used in earlier development; confidence intervals are descriptive, not an untouched final test. Whole-game resampling does not account fully for repeated teams or series.
