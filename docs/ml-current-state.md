# Beatrice ML current state

## Latest milestone: frozen history refreshed and active (September 18, 2026)

Activated `oracle-20260918-v1` after isolated build, source-normalization replay, chronology/audit checks and frozen-model warmup. Added 376 games, retaining every existing normalized game and audit decision. Ignored identity revisions in 225 old records are logged in the manifest. The combined history has 29,020 games, including 11,423 eligible openings; latest eligible evidence after the unchanged one-day lag is September 16 at 16:07:58 UTC.

The frozen model, 108-feature schema, training exposure, seven-day freshness/support gates and 0–2.5 bonus remain unchanged. No retraining or spent-2026 evaluation occurred. Earlier completed outcomes remain available through the original base-history pipeline; prevalence still uses audited opening games only.

Real saved-pool verification: 48/48 valid ML requests on the verification backend; 48/48 exact whole-candidate Java fallbacks with Python stopped; 47/48 valid ML requests on the website backend after restart, with one safe first-request fallback. Sparse and training-unseen candidates remain legal at zero bonus. Saved teams and recorded games were unchanged. Python is running with the active bundle; diagnostics include bundle version/hash and daily snapshot ID.

Tests: 71 backend and 23 Python passed. See [refresh results, hashes, latency, ranking examples and update commands](history-refresh-results.md). This is operational activation, not another model-quality study. No bans or LLM work. Milestone stopped after verification.

## Previous experiment: evidence freshness (September 17, 2026)

Completed offline only: preregistered A (seven-day), B (window-aware) and C (season-fallback) policies were compared on 512 development-2025 games / 5,120 decisions and 80 saved-roster scenarios. Frozen model, 108 features, candidate legality and maximum +2.5 bonus were preserved. Raw Top-3 fell from 33.61% fresh to 30.14/28.28/23.91/15.86/14.16% at 7/10/14/21/30-day cutoffs. All adequately sized delayed same/different-patch cohorts failed the registered full-influence guardrail.

Recommendation: **retain the current production gate; do not promote B or C.** Reduced window-aware evidence remains a research option, not demonstrated safe saved-team ranking. Saved scenarios have no correct-pick labels, so stability and support rates are reported separately from pro-label accuracy. Old history is not worthless, but neither age nor same-patch membership alone establishes reliable current influence. See [freshness results](freshness-policy-results.md) and [the frozen protocol](freshness-policy-protocol.md).

No production policy, database, saved-team, model or feature changes. No 2026 reevaluation or updated-CSV import. Eight freshness tests plus the existing recency and saved-scenario suites passed; 33 receipt hashes rechecked unchanged. Experiment stopped after recommendation.

## Previous completed milestone: guarded pick integration (September 17, 2026)

The existing Draft panel now uses the Java-owned team-wide pick endpoint. Java preserves every candidate for which allied picks plus that candidate can be matched to distinct saved-pool players. Feasible roles are possibilities, not inferred assignments. Comfort affects the unchanged Java scorer, never legality.

The persistent localhost Python service supplies the frozen September 14 model's evidence only. Java validates its exact candidate set, model/schema/hash, timestamps and scores; applies the **same offline-tested 0–2.5 rank-percentile bonus**; then selects the final Top-3. Candidate-level cold starts receive zero bonus. Request-level failures preserve Java ranking and scores exactly. Bans and the LLM remain untouched.

**Historical limitation at this milestone:** the old pro history ended September 7 and failed the seven-day freshness gate. This was resolved by the September 18 audited refresh above. No gate was relaxed, no model retrained, and the spent 2026 test was not reevaluated. See [integration verification and startup instructions](guarded-pick-integration.md).

## Previous milestone: offline production readiness (September 15, 2026)

The user approved a one-time final 2026 test, saved-team scenario evaluation, disagreement analysis, and a guarded integration design. See [the frozen acceptance protocol](offline-readiness-protocol.md). The final evaluator uses the unchanged September 14 recency model; no fitting or tuning is allowed. Per-game checkpoints and a hash-locked receipt preserve the single evaluation across interruptions.

Status: **completed, no activation**. All four preregistered final-test gates passed across 2,358 games / 23,580 decisions. Recency Top-3: 44.95% blind, 29.29% early, 25.69% late, 29.41% overall. Overall MRR: 0.2709. The 2026 test is now spent: do not tune or repeat evaluation against it. See [the final results, disagreements and guarded design](offline-readiness-results.md).

The 1,440 saved-team scenarios preserve Java's legal candidates; 130 correctly have no candidates. Zero cap/legality violations occurred. All 667 bounded winner changes resolved existing Java-score ties and none lowered comfort. Raw ML nevertheless shows substantial comfort and support conflicts. Recommend only an optional 0–2.5 point bonus with support gates, not replacement of the scorer. Freshness/deadline integration checks remain proposed work, not activated behavior.

Read-only snapshots and generated artifacts are in `data/oracle/final-2026-readiness/` and `data/oracle/saved-team-readiness/`. Original model and feature files are unchanged. One real team's scenarios and synthetic missing-evidence boundary tests do not establish win-rate gains or natural cold-start accuracy. No live website, database, metadata, saved-team, ban-model or LLM changes. Stop at this milestone.

## Previous milestone: blind-pick improvement experiment (September 14, 2026)

Status: **completed**. Both preregistered experiments passed the blind and late-retention gates. Recommend the recency-enhanced tree for a separate shadow-mode milestone; nothing has been promoted or integrated. See [the full results](blind-pick-results-2026-09-14.md).

The frozen September 12 LambdaRank tree remains the overall benchmark: overall Top-3 21.02%, blind Top-3 9.18%, late Top-3 31.66%. Frozen linear blind Top-3 is 11.61%; the strongest overall fixed baseline has overall Top-3 12.35% and blind Top-3 10.90%.

The new recency tree improves validation Top-3 to **54.13% blind, 33.74% overall, and 32.60% late**. Late MRR improves from 0.2787 to 0.2893. Blind Top-3 gain against linear is +42.52 percentage points, paired 95% interval +40.80 to +44.25.

The predeclared blind-specialist policy reaches **52.72% blind and 25.37% overall Top-3**, with all nonblind predictions unchanged. Its blind gain against linear also has a positive interval. It is a conservative alternative, not a post-hoc stage switch.

Coverage remains 99.9786% overall; nine new/absent targets remain outside the frozen candidates. Rare-champion ranking is still weak. Both experiments are development-validation results, not independently tested objective pick quality. Full coverage, missingness, timing, uncertainty, and limitations are in the report.

See [the preregistered protocol](blind-pick-experiment.md). Both experiments add lagged 14-day, 30-day, and same-patch pick/ban prevalence and stage interactions. One trains across all draft stages; the other trains only on blind decisions and uses the frozen tree everywhere else.

The completed dataset and frozen models were reused unchanged. Training was 2024 and development validation 2025; 2026 was unscored at completion of that earlier milestone and has now been evaluated once in the readiness milestone above. These models predict professional pick preference, not objective pick quality or win probability. No live website, database, metadata, saved teams, ban model, or LLM changes were part of that milestone.

## Reproduce

From the repository root, choose a new output directory (existing output is never overwritten):

```powershell
.venv-ranker/Scripts/python.exe scripts/benchmark/blind_experiment.py --dataset data/oracle/compact-2026-09-11-resumable --frozen data/oracle/scaled-2026-09-12-reviewed --prepared data/oracle/prepared-2026-09-08-reviewed --output data/oracle/blind-reproduction --registration docs/blind-pick-experiment.md
```

Run tests:

```powershell
.venv-ranker/Scripts/python.exe -m unittest discover -s scripts/benchmark -p 'test_*.py'
```

No new dependencies were added in that experiment. Generated models and detailed observations stay in the ignored `data/oracle/` directory. The later guarded integration above uses its frozen feature schema; saved team pools remain authoritative at inference time.

Completed output: `data/oracle/blind-2026-09-14-reviewed/`. Verification: 95 benchmark tests plus five Oracle-import tests passed; artifact/code/protocol hashes verified; frozen full-validation metrics reproduced; all 37,827 nonblind specialist-policy observations matched the frozen tree exactly. The milestone stops here—no additional experiments or shadow implementation are running.
