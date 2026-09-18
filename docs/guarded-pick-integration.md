# Guarded pick integration — completed September 17, 2026

## Outcome and scope

The existing Draft portrait panel now calls `POST /api/teams/{teamId}/draft/picks`. Java owns legal saved-pool candidates, base scoring, validation, the bounded bonus and final Top-3. The persistent Python service is CPU inference over the frozen model, bound only to `127.0.0.1:8766`. No new dependencies, model retraining, sealed-2026 reevaluation, ban-engine changes, LLM, schema migrations, team edits or metadata edits were performed.

**Current ML influence is zero:** available pro history ends `2026-09-07T22:42:48Z`, outside the seven-day freshness gate. Real requests correctly use Java only. This milestone integrates the guarded path; it does not manufacture fresh evidence. A separately audited history refresh is necessary before bonuses can apply. The model estimates pro drafting preference, not objective pick quality or win probability.

## Architecture and candidate legality

For each candidate, Java checks whether all allied picks plus that candidate can be assigned one-to-one to distinct roster players through saved champion-pool membership. Backtracking preserves alternatives that greedy assignment would lose. Banned/picked/unavailable champions stay excluded. Missing statistics or ML exposure cannot remove a legal candidate.

Every feasible candidate/player option is retained. Java scores those options with the existing `WeightedRecommendations` singleton-pool path, keeping the highest base score with deterministic tie-breaking. `scoringRole` is an optimistic scoring hypothesis, never a committed lane; `feasibleRoles` preserves alternatives. Comfort affects scoring, not membership. No lane is inferred from selection order.

Java sends only approved candidate IDs, visible picks, patch and protocol identifiers to Python. Python builds the frozen 108 features from audited, earlier-only history with the original one-day lag. Saved players are not falsely linked to professional identities. Loading, feature/artifact verification and history/model warmup finish before readiness. Background daily maintenance rebuilds history off the request path; requests fail closed while unavailable or busy.

The UI preserves server ordering, aborts/ignores stale requests, and selects rather than auto-locks portraits. No role dropdown or redesign was introduced. Default users see no numeric internals; `VITE_PICK_DEBUG=true` exposes Java/bonus/final scores only in development.

## Exact accepted bonus policy

This is the same policy as `scripts/benchmark/saved_scenarios.py:bounded`, not a newly selected transformation:

1. Sort **all** Java candidates by ascending raw model score, then champion ID.
2. For supported candidate at zero-based index `i`, `mlBonus = 2.5 * i / (N - 1)`.
3. Unsupported candidates receive zero but remain in `N` and the ordering.
4. Singleton or all-equal model scores produce zero for everyone.
5. `finalScore = javaScore + mlBonus`; sort descending final score, then ID; return Top-3.

Thus `0 <= mlBonus <= 2.5`. Raw scores are not public probabilities, confidence or win chances. Component evidence and Java scores remain separately available to future reasoning.

## Gates and failure behavior

Candidate support requires all of: training-history exposure, at least 30 global historical games, at least five picks in the 30-day window, and at least 30 games in the same-patch window. Cold/unseen/sparse candidates stay legal with zero bonus. Unknown patches retain valid global 14/30-day features, but have no same-patch evidence and cannot pass that gate.

Whole-request fallback applies to unavailable service/model, timeout, HTTP errors, malformed/oversized responses, missing/extra/duplicate candidates, invalid scores/counts, wrong request/patch, or model/schema/hash mismatch. History must respect the one-day lag and be no more than seven days old relative to current time. Java's inference deadline is 100 ms; it is not a deadline on database work or full application startup.

Fallback preserves the original Java candidate order and scores exactly, with zero bonus. Internal errors are not exposed to users. Diagnostic failures cannot break recommendations.

Frozen identifiers:

- Model: `recency-2026-09-14`
- Schema: `beatrice-pick-recency-108-v1`
- Model SHA-256: `ea447cdced1aa541446c50ef03c2ed96f06ecd94e4f50fb50514f17d85964ec5`
- Artifact: `data/oracle/blind-2026-09-14-reviewed/recency_tree.txt`

Startup also verifies frozen feature-code and source/context artifacts against their manifests. The frozen model hash was checked again after verification.

## Verification

| Check | Result |
| --- | --- |
| Backend regression suite | 67 passed; zero failures/errors/skips |
| Frontend tests | 24 passed |
| Frontend lint / production build | Passed |
| Python service tests | 11 passed |
| Existing benchmark regression tests | 105 passed (temporary synthetic fixtures, not real-model retraining) |
| Scoped code review | No remaining critical/important findings |
| Real saved-team read-only requests | 84 service-up + 84 service-down requests passed |
| Saved-team snapshots | Identical before/after and across runs |
| Frozen model and existing scorer/ban files | Unchanged |

Added tests cover complete matching and flexibility, outside-pool and banned/picked exclusion, comfort preservation, candidate cold starts, exact percentile/tie behavior, cap/nonnegative bonus, exact fallback, schema/hash/response validation, timeout/service failure, safe diagnostics, actual lock-in correlation, UI stale requests, startup warmup, contexts corruption, unknown-patch parity and automatic UTC rollover recovery.

Real measurements used a temporary backend on 8081 with migrations disabled and the real saved roster, catalog and database. Each case had one first request plus 20 warm requests. Values include HTTP, Java/database work, Python request where available, diagnostics and response serialization; they exclude the UI's 150 ms debounce.

| Draft case | Python-up warm median / p95 | Python-down warm median / p95 |
| --- | --- | --- |
| Blind blue | 38.96 / 49.39 ms | 27.95 / 35.41 ms |
| Blind red | 29.18 / 37.84 ms | 27.11 / 35.05 ms |
| Early | 30.94 / 39.10 ms | 30.79 / 33.35 ms |
| Late | 28.27 / 37.48 ms | 25.63 / 30.89 ms |

The first blind-blue HTTP request was 243.15 ms, including cold Java request-path overhead. This is not a claim that startup fits the inference deadline. Python-up returned `STALE_EVIDENCE`; Python-down returned `ML_UNAVAILABLE`. The complete returned pick IDs, base/final scores, components and feasible roles matched exactly in both runs. Detailed local artifacts: `data/guarded-integration/online.json` and `offline.json`.

### Ranking examples (deterministic integration fixtures, not fresh live evidence)

| Candidate | Java base | Bonus | Final | Observation |
| --- | --- | --- | --- | --- |
| C0 | 67.5 | 0 | 67.5 | Java tie-break winner before ML |
| C1 | 67.5 | 1.6667 | 69.1667 | Supported ML preference resolves the tie |
| C2 | 64.0 | 2.5 | 66.5 | Highest raw preference cannot overcome the 3.5-point comfort gap |
| C3 | 64.0 | 0 | 64.0 | Cold-start candidate remains legal |

After banning C0 in another fixture, cold C3 remains selectable in the final Top-3. These verify mechanics, not improved real-game outcomes. No current live ranking changes are claimed with stale evidence.

## Diagnostics and limitations

Rotating JSONL logs live under `data/diagnostics/picks` when the backend is started from `backend`. They retain Java/ML/final ranks, bonus and gate per candidate, model version and inference latency. Rotation bounds disk use to roughly 6 MB. Selection receipts are bounded to 256 requests and expire after 30 minutes. A valid allied lock-in is correlated when its receipt is still known; clicking a suggestion alone is not reported as the chosen champion. Logs exclude player names and API keys.

The no-dropdown UI does not invent a Riot statistics queue from draft format. Java statistics remain neutral without an explicit exact dataset/queue slice. The API retains optional `datasetId`, `queueId` and `desiredTraits`; unresolved lanes do not become matchup assignments. This milestone does not add automatic evidence-slice selection or team-history scoring. Missing frontline/composition evidence must not be presented as a measured fact.

Cold-start mechanics are covered, but their recommendation quality is not established. The small real-roster smoke check is operational verification, not another ML acceptance study. No GPU or League-running latency benchmark was performed.

## Run locally

Start the existing database as usual (`docker compose up -d` from the repository root). In separate terminals:

```powershell
# Repository root: keep this terminal open. Existing .venv-ranker dependencies are reused.
.\.venv-ranker\Scripts\python.exe scripts/pick_service/service.py
```

```powershell
cd backend
mvn spring-boot:run '-Dspring-boot.run.profiles=local'
```

```powershell
cd frontend
npm run dev
```

Restart any previously running backend so it loads the new code. Check Python readiness with `Invoke-RestMethod http://127.0.0.1:8766/health`; readiness does not override Java's freshness gate. Stopping Python with Ctrl+C leaves Draft recommendations working through Java fallback.

To rerun regression checks: `mvn test` in backend; `npm test`, `npm run lint`, `npm run build` in frontend; and `.venv-ranker/Scripts/python.exe -m unittest discover -s scripts/pick_service -p 'test_*.py'` from root. The measurement script refuses to overwrite its saved reports. Do not rerun the sealed final evaluation.

## Files changed

- Backend recommendation package: new `TeamPickFeasibility`, `GuardedPickBonus`, `PickModelClient`, `TeamPickService`, `TeamPickController`, `PickDiagnostics`, plus five focused test classes. Existing scorer and ban paths untouched.
- `scripts/pick_service/service.py`, `test_service.py`: persistent verified local inference and contract tests.
- `frontend/src/api/pickRecommendations.ts`, `components/useDraftAdvice.tsx`, `components/DraftBoard.tsx`, their tests, and `draft.css`: existing panel connected to guarded picks and lock-in diagnostics.
- `scripts/benchmark/measure_guarded_http.py`: read-only operational verification.
- This report, `ml-current-state.md`, integration progress/plan and Python implementation report: decisions, evidence and startup guidance.

Milestone complete. No further model experiment, ban work or LLM integration is running.
