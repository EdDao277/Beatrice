# Approved frozen-history refresh — September 17

User-approved design is the authority: isolated versioned bundles, verified before atomic activation; frozen model/schema/gates/bonus/training exposure unchanged. Earlier completed outcomes remain in original base features; draft prevalence uses audited opening games only. No test evaluation, training, bans, LLM, team or draft mutations.

## Task 1: Java history tracing

Modify PickModelClient, PickDiagnostics, TeamPickService and focused tests only. Consume Python response fields `historyBundleVersion` (nonblank <=100 safe `[A-Za-z0-9._-]+`), `historyBundleSha256` and `historySnapshotId` (lowercase64hex). Reject missing/malformed provenance as whole-request fallback. Preserve validated provenance in Result and recommendation diagnostics. Keep old internal Result constructor for fixtures if useful. No thresholds or score changes. Test valid provenance and malformed rejection, log provenance and exact fallback. No commits/subagents. Report docs/history-tracing-report.md.

## Task 2: Python history bundle and activation

Approved amendment (September 18): preserve all existing normalized records and audit decisions exactly; append new game IDs only. Log ignored upstream player/team identity/name revisions. Reject missing old records, gameplay revisions, source-series metadata changes, or eligibility changes after reclassifying retained records plus new records.

New scripts/pick_service/history_bundle.py and tests. Reuse importer + audit unchanged. Build under new data/oracle/history-bundles/version; preserve immutable training export. Bundle contains normalized games, audit, prepared report, manifest with hashes/source/date/count/lag/schema/training-exposure compatibility. Frozen pre-training games must match original; original newer records may only add (conflicting overlap rejected). Atomic active.json pointer only after independent load/hash/count/normalization/chronology/lag + warmed-model probe. In-memory service remains previous on failed hot refresh; on startup invalid pointer uses original audited stale history, Java gates unchanged. Separate validation and activation commands. Do not partially publish. Record active pointer and previous pointer for recovery.

Service supports optional bundle and default active pointer, startup original model lineage remains verified. Stable training exposure computed from frozen inputs, not refreshed data. Hot reload warms replacement before swap; retain previous instance on failures. Every rank response includes bundle identity and snapshot ID; keep localhost only. Test corrupt bundle, conflict/future/training change, missing hashes, atomic failed activation and provenance. Original 108-feature arithmetic unchanged.

## Task 3: verification and report

Build refreshed2026 bundle from existing2024/25 CSVs +new2026 CSV separately. Review audit differences; never drop existing valid games silently. Confirm fresh eligible date after1day lag. Validate beforeatomicactivation. Start localservice +temporarybackend migrationsdisabled. Read-only savedteam/game snapshots and POST picks acrossblind/early/late; verify nonzero<=2.5 supportedbonuses and changedTop3, sparsezerobonus, provenance. StopPython repeatrequests exact Java bases/rankingfallback. Restart validated service afterchecks; no productionbackendkill withoutcheckedownership. Document counts/hashes/commands/latency/examples/limitations. Stopafterverified.

## Progress and interface review

| Boundary | Check |
| --- | --- |
| Tasks1/2 JSON | Three explicit provenance fields; no new model features |
| Task2 original importer | Reuse unchanged normalization and series audit; preserve historical outcomes and training population |
| Tasks2/3 activation | Manifest hash pointer, warmed probe, atomic replace; old bundle retained |
| Task1 tests | Invalid provenance whole fallback, original scoring gates untouched |
| Task2 tests | Failed activation must preserve pointer and running instance |
| Task3 verification | GET snapshots and recommendation POST only, no team/game saves |

Working in user-selected existing folder, preserve unrelated changes; no commits. Using a focused implementation agent for Task1 while main handles Task2; review both beforeactivation.

## Completion — September 18

All three tasks verified. Separate `oracle-20260918-v1` bundle activated atomically; 71 backend and 23 Python tests passed. Forty-eight read-only online and 48 service-down requests verified bonuses, legality, provenance and exact whole-candidate fallback. Forty-eight further requests reached the website backend (47 valid ML, one safe initial fallback). Real cold/sparse pool candidates remain legal at zero bonus. Saved teams/games unchanged. See `history-refresh-results.md`. No model training, test-set evaluation, gate changes, bans or LLM work.
