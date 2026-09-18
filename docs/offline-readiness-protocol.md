# Offline production readiness — frozen before final-test scoring

Approved by the user September 14, 2026. No retraining, parameter selection, live integration, ban-model work, or LLM work is authorized.

## Phase 1: one final generalization evaluation

Freeze September 14 `recency_tree.txt` SHA-256 `ea447cdced1aa541446c50ef03c2ed96f06ecd94e4f50fb50514f17d85964ec5`, its 108-feature schema and transformations, and September 12 fixed/linear/tree comparators. Frozen recency feature source hash: `188456f86da8209d43c6b82a4432ca5df082facbb24b1402111c907d0f89a78e`. Frozen protocol/schema hash: `f7a1c316a1b7dca31c92e4b822d75bb826b693189bb7db590be38d86105f565c`.

Test population: every eligible opening game dated on or after 2026-01-01 in the already prepared, hashed Oracle batch and its existing source audit. No sampling or results-based exclusions. Unsupported later-series drafts remain excluded under the original audit. Freeze a receipt with all input/code hashes and selected game IDs before scoring any test case. Write resumable per-game observations; recovery reuses completed observations, never selects models or changes features. A completed receipt cannot launch a second evaluation. A technical failure does not authorize tuning.

Chronological prequential history: before each prediction day, only games strictly older than that day minus one day are available. Earlier 2026 games may inform later 2026 history after that lag, just as earlier validation history did in 2025. No current/future outcomes or final roles enter features. Original expanding history uses all earlier prepared games; added prevalence uses audited eligible earlier openings. The research-only pre-2026 guard needs a separate final-test adapter; parity tests must prove unchanged numeric features on development dates. Never weaken the old training guard.

Metrics: blind (no visible picks), early (nonblind and fewer than three ally picks), late (at least three ally picks), and overall Top-1/3/5 and MRR. Missing targets count as misses. Report coverage, rare/new targets, missingness and scoring latency. Compare on identical legal candidates. Paired 95% percentile intervals: 2,000 whole-game resamples, seed 1729; repeated teams/series remain a limitation.

Acceptance (all required): blind Top-3 delta against frozen linear has lower interval bound >0; overall Top-3 delta against frozen September 12 tree has lower bound >0; late Top-3 delta against that tree has lower bound >=-0.005; late MRR delta has lower bound >=-0.005. No tuning or alternate routing after 2026 is seen. The blind specialist is not a candidate in this milestone.

## Phases 2–3: saved-team safety and disagreement scenarios

Read-only snapshots of all real saved teams and champion pools; no Riot calls, collection jobs, database writes or saved-team mutations. Seed 1729. Cover both sides and blind/early/late stages, flex pools, narrow and off-meta pools, sparse and unseen champions, AP/AD skew, and absent frontline/engage/peel. Preserve real pools as the main cohort; clearly label any narrowed or augmented copies as synthetic stress tests. Draft-time lane assignments stay unresolved. Java remains authoritative for candidates and scores; retain its role-specific boundary explicitly rather than pretending a team-wide generator exists.

Use the real Java scorer in an offline harness. ML receives only its legal saved-pool candidates, never adds or removes one, and may abstain from influencing their scores. Compare full rankings, not only the public endpoint's truncated three picks. Current pro history and local player history are distinct: never encode comfort ratings as professional appearance counts, nor invent evidence for unlinked user identities. Report unsupported features and stale/new patch evidence.

Safety gates: zero candidates introduced by ML; zero picked/banned/out-of-pool candidates returned; unseen/rare champions remain candidates; empty pools safely abstain; invalid/nonfinite features and corrupt/missing models fall back exactly to Java. Test bounded influence with an offline-only policy prototype, not production integration. Scenario results do not estimate win-rate improvement because they have no counterfactual quality labels.

Disagreements: Java #1 outside ML Top-5; ML #1 with weak history; ML versus saved comfort (at least three comfort points below Java #1); strong pro-priority preference; rare/cold-start cases. Report rates and concrete examples. Do not optimize weights to mimic scenario preferences or tune the model using final-test labels.

## Phase 4: design only

Recommend a capped ML contribution and conservative evidence gating from the offline findings. Missingness/support gates are engineering safeguards, not calibrated confidence. ML failure is pure Java fallback; cold-start validity never depends on ML support. No visible recommendation changes. Update current-state and report; STOP.
