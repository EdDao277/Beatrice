# Guarded integration progress

Plan: `docs/superpowers/plans/2026-09-15-guarded-picks.md`

## Preflight

| Tasks | Shared boundary | Check |
| --- | --- | --- |
| 1 / 2 | Loopback rank JSON | Explicit model/schema/hash, exact ID set, evidence counts; Java owns bonuses |
| 2 / 3 | Team-wide pick endpoint | Portrait ID, scores/components and feasible roles; no assigned lanes |
| 1 / 4 | Frozen history/features | No training or repeat sealed-test evaluation; only new request inference |
| 2 / 4 | Existing scorer | Existing three-pick/ban endpoint preserved; all-picks method is additive |
| 1 | Service tests vs contract | Hash mismatch, finite scores, generic HTTP errors covered |
| 2 | Java tests vs matching | Injective assignment, not greedy player selection; every candidate/player option retained |
| 3 | UI vs user constraints | No role control, no redesign, no ban-engine connection changes |
| 4 | Verification vs scope | Local read-only recommendation calls; no game/team writes |

Existing Java pure recommendation tests passed using installed Maven. The wrapper cannot start in this environment; `mvn` is the verified fallback. Maven required approved access to its dependency cache/network. Existing user preference is to work in place on main; no commit/push is planned.

Completed September 17: Java matching, guard, endpoint, diagnostics and UI are implemented. Backend 67, frontend 24, Python service 11 and benchmark 105 tests passed; frontend lint/build passed. Startup warmup, context integrity, unknown-patch parity and automatic daily maintenance were fixed and reviewed. Real saved-team HTTP verification passed 84 service-up and 84 service-down requests with exact Java fallback and unchanged teams. See `docs/guarded-pick-integration.md` for measurements and limitations. Stop condition reached; no training, bans or LLM changes.

Implementation adjustment: existing `WeightedRecommendations` is entirely unchanged. Each feasible candidate-player option is scored using a singleton pool (the same technique used by the acceptance harness), then merged before final Top-3. This avoids changing historical Java scorer hashes or its existing API while preserving exact per-candidate component math.

Clarification: draft format does not uniquely determine Riot queue. The no-dropdown UI must not invent a statistics queue. Preserve neutral Java statistics when no exact evidence slice is supplied; optional explicit API context can use the existing scorer's evidence path. Historical pro features remain separately sourced.
