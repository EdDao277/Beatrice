# Guarded Pick Integration Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or executing-plans. Preserve existing in-place changes; no commits or deployment outside this local application.

**Goal:** Activate bounded pick evidence in the existing no-role-dropdown Draft panel.
**Architecture:** Java generates and scores all feasible saved-pool candidates. A loopback Python service returns frozen-model scores and evidence counts. Java validates, gates and applies the accepted bonus before final Top-3. Bans unchanged.
**Tech Stack:** Java 21/Spring, Python standard-library HTTP + existing NumPy/LightGBM, React/TypeScript.
**Spec:** User-approved guarded integration and complete injective saved-pool assignment rule; offline policy in `scripts/benchmark/saved_scenarios.py:bounded`.

## Global constraints / contract

- No model training, sealed-test scoring, ban engine changes, LLM, saved-team or metadata writes.
- In-place work explicitly chosen by user earlier; preserve all uncommitted artifacts.
- Complete injective matching of allied picks + candidate onto distinct players; keep every feasible candidate-player assignment. Comfort never affects membership. Score each feasible candidate-player option using existing Java components, select maximum Java base (deterministic role tie-break), expose all feasible roles, never claim chosen scoring option is an assigned lane.
- Frozen model version `recency-2026-09-14`, schema `beatrice-pick-recency-108-v1`, SHA256 `ea447cdced1aa541446c50ef03c2ed96f06ecd94e4f50fb50514f17d85964ec5`.
- Python bound strictly to `127.0.0.1:8766`. POST `/rank`: requestId, schemaVersion, modelVersion, modelSha256, patch, allyPicks, enemyPicks, candidateIds. No player identity or comfort sent.
- Response echoes requestId/schemaVersion/modelVersion/modelSha256/patch and includes evidenceCutoff (UTC ISO instant), historyLatest (UTC ISO instant), and scores array: championId, score (finite), globalGames, recent30Picks, patchGames, seenInTrainingHistory. Counts nonnegative integral. Exact requested ID set, no duplicates. At most 200 candidates, five picks each side; bounded HTTP payload.
- Java gates each candidate: training seen, globalGames>=30, recent30Picks>=5, patchGames>=30. Request-wide history freshness <=7 days, cutoff not future, valid schema/hash, finite values and exact ID set; failure returns original Java picks exactly. 100ms inference request deadline; service warmup is not in recommendation request.
- Offline bonus: sort all legal candidates by ascending raw ML score then ID; `2.5*i/(N-1)` for supported candidates, zero otherwise. Singleton/all-equal raw scores yield zero. Unsupported candidates count in N. Final descending score then ID. No probability/confidence output.

## Task 1 — frozen loopback service

Files: `scripts/pick_service/{service.py,test_service.py}`. Reuse frozen feature functions unchanged. Load audited pro history and frozen model once at startup; hash/schema validation before health ready; no database/network collection. Evidence tables follow existing one-day lag and audited opening prevalence; user familiarity missing. Cache only current-day tables, not old responses. Thread-safe scoring or serialize predict. Add JSON request validation and generic failures with no trace in HTTP response. Bind only literal loopback; no arbitrary host flag. Require application/json and bounded body, no permissive CORS.

- [ ] Write failing unittest fixtures for exact ID preservation, 108-feature contract, wrong hash/schema, nonfinite/duplicate input, loopback binding and generic errors.
- [ ] Implement `RankService.rank(payload)` and `serve()` plus `--port` and existing artifact directory options. Tests use tiny histories/injected model boundaries, not training.
- [ ] Run `.venv-ranker/Scripts/python.exe -m unittest discover -s scripts/pick_service -p 'test_*.py'` and verify numeric parity against saved-scenario vectors on fixed day (never reevaluate 2026 test).

## Task 2 — Java matching, guard and endpoint

Files: new `TeamPickFeasibility.java`, `GuardedPickBonus.java`, `PickModelClient.java`, `TeamPickService.java`, `TeamPickController.java`; modify `WeightedRecommendations.java` to expose `scoreAll` while existing `score` still limits three; focused backend tests.

- [ ] Tests first: matching counterexample pools P1={A,B}, P2={A}, picks={A}, candidate B must stay legal for P1; C outside all pools illegal; candidate requiring already occupied sole player illegal. Enumerate all feasible player choices, comfort-independent, unavailable excluded.
- [ ] Java guard hand fixtures: bases A=80,B=80 => B=82.5 when ML favors B; A=84,B=80 => A remains first. Three rows raw tied A=B<C uses ID tie-break; unsupported middle stays in denominator; singleton/equal raw scores unchanged. Outside IDs/NaN/schema failure exact fallback.
- [ ] Implement request-wide validation before any bonus. Preserve Java components/evidence/coverage in final record; fields javaScore/mlBonus/score/mlEvidenceQuality/feasibleRoles/scoringRole. No raw score in public DTO.
- [ ] Add POST `/api/teams/{teamId}/draft/picks` with format/side/patch/actions only. Validate existing DraftRules and catalog. Reuse Java evidence/scoring without changing existing recommendation or ban endpoint. Read latest maintained dataset conservatively; keep unavailable role-specific evidence neutral when roles unknown. No lane assignments inferred from matchings.
- [ ] Add loopback client fault tests and MockMvc endpoint tests; verify existing recommendation tests.

## Task 3 — UI and diagnostics

Files: `frontend/src/api/pickRecommendations.ts`, existing `useDraftAdvice.tsx`, `DraftBoard.tsx`, tests; backend diagnostic selection endpoint/service. Preserve ban placeholders and panel layout.

- [ ] Test existing picks visible from team-wide endpoint, loading/failure nonblocking, old requests cancelled/ignored, no role dropdown and no numerical scores by default.
- [ ] Fetch automatically on selected team/version, side, format, patch and draft changes during pick planning; debounce input, abort stale requests. Show portrait recommendations; click selects champion but does not auto-lock.
- [ ] Backend emits bounded rotating local structured diagnostics: request UUID, Java/ML/final ranking, bonuses/gates/version/latency. No API keys/names. Link actual lock-in with UUID, team ID and champion validated against a bounded expiring request cache. No DB migration needed. Log write failure never breaks draft.
- [ ] Development flag only may show javaScore/mlBonus/final score; no redesign or AI explanations.

## Task 4 — integration verification and documentation

- [ ] Run all backend tests, frontend tests/lint/build, service tests and existing benchmark tests. Verify frozen hashes and unchanged ban engine.
- [ ] Start localhost service and backend safely, use read-only real-team recommendations; measure complete HTTP latency incl Java and Python. Verify service-down and timeout return Java-only exact rankings. Do not save games or teams.
- [ ] Record real or clearly labeled deterministic-fixture examples where ML resolves close rankings and where cap protects larger differences. Never relax gates to manufacture a current result.
- [ ] Update `docs/ml-current-state.md` and write `docs/guarded-pick-integration.md` with run commands, schema/hash, bonus/gates, freshness limitations, tests and measured latency. Stop after verification.

## Progress

**Completed September 17, 2026.** The task checklists below/above preserve the original plan; execution evidence and the two adjustments (unchanged singleton scorer reuse; no invented default queue) are recorded in `docs/guarded-integration-progress.md`. Final verified results, service instructions and stale-history limitation are in `docs/guarded-pick-integration.md`. All four tasks are complete; no further work is authorized under this milestone.

Plan reviewed: service produces exact contract consumed by Java guard; UI consumes only new team-wide endpoint; old role-specific endpoint and bans remain unchanged. Per-player scoring maximum is an optimistic Java scoring option, not an assignment commitment. All feasible roles remain available to callers.
