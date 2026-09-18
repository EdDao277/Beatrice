# Guarded Pick Task 1 Report

## Scope and result

Task 1 adds a standalone Python scoring service at `scripts/pick_service/service.py` with focused contract and parity tests in `scripts/pick_service/test_service.py`.

The service:

- binds only to literal IPv4 loopback `127.0.0.1` (default port `8766`);
- loads the prepared professional history, compact source audit, and frozen LightGBM model once before serving;
- verifies artifact hashes, dataset lineage, the frozen source hashes used by feature construction, the exact 108-feature protocol, and model feature width before `/health` can report ready;
- reuses the reviewed `ml_features.vector`, `recency_features.extend`, `saved_scenarios.evidence_for`, one-day-lag `EarlierHistory`, audited-opening `FinalHistory`, and `tree_ranker.tree_score` paths without changing them;
- represents unavailable saved-player familiarity as five zero-evidence placeholder players, never as comfort or identity data;
- serializes history-table construction and prediction behind one lock, while caching only the current day's per-patch recency tables;
- returns rows in the exact requested candidate order with finite scores, safe nonnegative integral counts, and `recent30Picks <= globalGames`;
- requires the exact request fields, frozen schema/model/hash, `application/json`, no more than five visible picks per side, no more than 200 unique candidates, and a body no larger than 64 KiB;
- emits generic JSON errors without exception details and sends no permissive CORS headers.

No model training, model modification, database/network collection, saved-team writes, ban changes, or final-2026 evaluation was performed.

## Frozen contract

- Model version: `recency-2026-09-14`
- Schema: `beatrice-pick-recency-108-v1`
- Model SHA-256: `ea447cdced1aa541446c50ef03c2ed96f06ecd94e4f50fb50514f17d85964ec5`
- Endpoint: `POST http://127.0.0.1:8766/rank`
- Readiness endpoint: `GET http://127.0.0.1:8766/health`

Run from the repository root:

```powershell
.\.venv-ranker\Scripts\python.exe scripts\pick_service\service.py
```

Optional existing artifact locations and port can be selected with `--prepared-dir`, `--compact-dir`, `--model-dir`, and `--port`. There is deliberately no host option.

## Verification

The focused unittest command is:

```powershell
.\.venv-ranker\Scripts\python.exe -m unittest discover -s scripts/pick_service -p 'test_*.py'
```

Initial Task 1 result before the reviewer follow-up below: **6 tests passed** in 9.789 seconds.

The suite covers:

- exact candidate ID/order preservation and finite `(N, 108)` feature matrices;
- one-day cutoff and honest UTC source-history timestamps;
- exact evidence counts and training-exposure flags from hand-built tiny histories;
- wrong request schema, model version, and hash;
- duplicate/overlapping IDs, candidate and pick limits, malformed patch/request IDs, wrong model width, and nonfinite predictions;
- literal loopback binding, successful readiness only after construction, required JSON content type, bounded request bodies, no CORS, and generic HTTP failures;
- fixed-day parity against the reviewed `saved-team-readiness` scenario: all ten raw scores match to 12 decimal places and all four evidence fields match exactly.

The related frozen feature/history tests were run with:

```powershell
.\.venv-ranker\Scripts\python.exe -m unittest discover -s scripts/benchmark -p 'test_recency_features.py'
.\.venv-ranker\Scripts\python.exe -m unittest discover -s scripts/benchmark -p 'test_saved_scenarios.py'
```

Both modules passed: **5 recency-feature tests** and **5 saved-scenario tests**. `py_compile` also completed successfully for both new Python files.

## Current freshness limitation

On 2026-09-16, a production-artifact request honestly returned:

- `evidenceCutoff`: `2026-09-15T00:00:00Z`
- `historyLatest`: `2026-09-07T22:42:48Z`

This is more than seven days behind the cutoff, so the Java guard should reject the request-wide ML signal and preserve the original Java ranking exactly. The Python service does not disguise or relax that stale state. A separately audited data refresh is required before the ML bonus can become eligible.

The prepared source dates are timezone-free and have historically been treated as UTC by this pipeline; the service makes that assumption explicit when formatting them with `Z`. If source timestamp semantics change, they must be audited before refreshing history.

## Reviewer follow-up: startup readiness and context integrity

Two reviewer findings were reproduced and fixed with tests first.

Previously, production artifact loading returned a cold service: load took about 2,671 ms, the first two-candidate rank took about 2,147 ms while it lazily advanced history and built prevalence, and the second rank took about 20.5 ms. `RankService` now completes the following work before it can bind or report healthy:

- advances the frozen one-day-lag history for the current UTC day;
- prepares prevalence tables for every patch present in the audited history;
- primes the frozen 108-feature model and verifies its warmup output is finite;
- atomically publishes the warmed snapshot and tables only after every step succeeds.

With production artifacts after the fix, load-and-warm took about 6,997 ms outside the recommendation budget; the first two-candidate rank took 0.91 ms and the second took 0.31 ms. These are direct service-component timings, not Java-to-Python end-to-end HTTP latency.

Interactive requests no longer call history advancement or prevalence-table construction. After the final parity review, an unknown patch retains the frozen global 14/30-day windows and empties only its same-patch window (`patchGames=0`). When the UTC day changes, health and ranking fail closed until automatic background maintenance publishes a warmed snapshot. Readiness checks and busy inference fail immediately rather than waiting for warmup. No manual daily restart is required.

The compact manifest's SHA-256 for `contexts.jsonl.gz` is now verified before contexts are parsed to derive `seenInTrainingHistory`. A regression copies the real manifest boundary, changes one byte of the compressed contexts artifact, and verifies startup rejects `contexts.jsonl.gz` before reading it.

The exact post-fix service command was:

```powershell
.\.venv-ranker\Scripts\python.exe -m unittest discover -s scripts/pick_service -p 'test_*.py' -v
```

Final September 17 verification: **11 tests passed** in 9.288 seconds, including automatic HTTP rollover recovery and unknown-patch parity. The complete benchmark suite passed 105 tests, including the frozen recency and saved-scenario regressions. Scoped review cleared the warmup and integrity fixes. No frozen-model retraining or 2026 final-set evaluation was run. End-to-end measurements and exact service-down fallback results are recorded in `docs/guarded-pick-integration.md`.
