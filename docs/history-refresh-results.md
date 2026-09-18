# Frozen ML history refresh — September 18, 2026

## Result

The versioned history bundle `oracle-20260918-v1` was built separately, independently validated, and activated through an atomic pointer replacement. Real saved-team recommendation requests on both the verification backend and the website backend passed with fresh, nonzero bounded ML bonuses. Stopping Python produced exact Java fallback across every candidate, not merely the returned Top-3. Python was restarted with the same verified bundle and left running.

No training, spent-2026 accuracy evaluation, feature-schema change, gate/bonus change, ban change, LLM integration, or saved-team/match-history write was performed. This is operational verification, not evidence of improved win rate or recommendation quality.

## Provenance and population

| Item | Value |
| --- | --- |
| Source SHA-256 | `d13fe165a1e56f7f1699c5530a91a4e608a509cc3ce040faf0fd2935f3e95299` |
| Bundle manifest SHA-256 | `e4a59c5f40fdd0853ba15f186c96ae5cb5206f34eadb5641e7ef76c8868267b7` |
| Daily snapshot ID at verification | `6bd6d70ce35a5ccd24cc6865b93ff4bf30edef6720c826f48afd25ae4ea0de4c` |
| Frozen model SHA-256 | `ea447cdced1aa541446c50ef03c2ed96f06ecd94e4f50fb50514f17d85964ec5` |
| Model / schema | `recency-2026-09-14` / `beatrice-pick-recency-108-v1` |
| Frozen training exposure | 167 champions; SHA-256 `69aa252e57b9c4bb34c877c87da41a0018edfc382c074702d69c93fb41ee0656` |
| Source games / appended games | 8,808 / 376 |
| Combined validated history | 29,020 games |
| Eligible opening games / possible draft decisions | 11,423 / 114,230 |
| Latest source game | September 16, 2026, 18:24:13 UTC |
| Latest eligible opening after lag | September 16, 2026, 16:07:58 UTC |
| Exclusive observation cutoff at verification | September 17, 2026, 00:00 UTC |

The manifest records rebuild time, source/catalog/frozen-input provenance, all output hashes, counts, cutoff, and ignored revisions. Decision counts are ten possible pick decisions per eligible game, **not** evaluated examples. No historical target labels were scored for accuracy during this milestone.

### Approved merge policy

The source revised names/identities in 225 old games. Every original normalized record is retained exactly; only new game IDs are appended. The manifest records ignored revision paths and old/new record hashes. Missing old games, duplicate IDs, gameplay changes, and changed source-series metadata fail closed.

One upstream identity correction would promote `LOLTMNT02_460841` from ineligible to eligible. Reclassifying the retained record correctly keeps it excluded. All existing eligibility decisions are unchanged. New games still participate in series ambiguity and chronological checks. Old 2024/2025 inputs are retained from the frozen prepared history, not reimported from newer files.

### Validation and runtime

- Replay the unchanged importer against staged CSV/catalog into temporary storage; compare normalized output and report hashes.
- Verify original source bytes, champion IDs, exact normalized patch labels, chronological order, counts, timestamp bounds, one-day lag, and retained record/audit compatibility.
- Verify original training lineage and feature/model code hashes. Compute training exposure from frozen inputs **before** replacing inference history.
- Earlier completed outcomes remain in the unchanged base-history features. Draft prevalence uses only eligible opening games. Current/future outcomes and games inside the one-day lag remain excluded.
- Load and warm the entire candidate bundle, validate eligible-opening freshness and a model probe, then atomically replace `active.json`. Failed activation does not publish a pointer.
- The persistent localhost-only service builds replacements off request threads and swaps a complete instance only after validation/warmup. Failed reload retains the old instance. A bad startup pointer retains original verified history, subject to unchanged Java gates.
- Responses and Java diagnostics carry bundle version/hash and daily snapshot ID. Missing/malformed provenance triggers whole-request fallback. No raw model value is presented as probability.

## Real saved-team verification

Receipts: `data/history-refresh-verification/online.json` and `offline.json`. Each contains four draft cases, 12 requests per case. Read-only snapshots include both saved teams and recorded games. All 48 online requests were `VALID`; all 48 service-down requests were `ML_UNAVAILABLE` with zero bonus, exact full Java candidate order/base scores, and unchanged saved state.

| Case | Legal candidates | Nonzero bonus candidates | Java Top-3 | Guarded Top-3 |
| --- | --- | --- | --- | --- |
| Blind blue | 74 | 41 | Amumu, Aphelios, Ashe | Jarvan IV, Karma, Seraphine |
| Blind red | 74 | 41 | Amumu, Aphelios, Ashe | Jarvan IV, Karma, Seraphine |
| Early | 64 | 35 | Amumu, Aphelios, Ashe | Jarvan IV, Karma, Seraphine |
| Late | 31 | 18 | Aphelios, Ashe, Jhin | Jhin, Ashe, Karma |

These are reproducible partial-draft fixtures built from the real saved pools, not newly saved drafts or actual gameplay selections. Independent pool-membership matching checks every diagnostic candidate; bans/picks remain excluded. The model never introduces candidates or assigns current-game roles.

Blind example: Jarvan IV has Java 67.5, bonus +2.3630, final 69.8630. Karma has Java 67.5, bonus +2.1575, final 69.6575. These break Java ties. Nocturne receives the maximum +2.5, but Java 64 becomes only 66.5: it cannot overtake a 67.5 Java candidate even if that candidate receives zero bonus. Late-stage Ezreal is similarly capped at 66.5.

Sparse candidates such as Amumu (zero recent picks), Aphelios (two), and Lux (two) remained in legal candidate lists with zero bonus. Master Yi and Yunara are real saved-pool candidates absent from frozen training exposure; both remained legal with zero bonus. Yunara has 46 recent picks, but new history does not silently expand the frozen training-exposure set. Being unsupported here does **not** mean unplayable or objectively bad. Natural cold-start recommendation quality is not established by this smoke test.

### Latency

End-to-end HTTP timings include Java/database work, Python inference, diagnostic logging and serialization, not UI debounce. Eleven warm samples per case; reported p95 uses nearest rank and therefore equals the maximum at this small sample size.

| Case | Python up median / p95 | Python down median / p95 |
| --- | --- | --- |
| Blind blue | 52.84 / 78.27 ms | 32.23 / 43.57 ms |
| Blind red | 42.27 / 50.16 ms | 41.09 / 369.33 ms |
| Early | 49.06 / 63.88 ms | 46.80 / 58.85 ms |
| Late | 49.30 / 55.93 ms | 40.16 / 48.35 ms |

First cold HTTP request: 764.17 ms. Its inference portion was 68.86 ms; warm inference portions were approximately 4.17–11.01 ms. The service-down 369 ms outlier is retained, not hidden. No League-running benchmark was performed and startup validation/warmup is intentionally outside the 100 ms Java inference budget.

### Website backend after restart

An additional 48 requests reached the existing website backend on port 8080, with receipts in `website-online.json`. There were 47 valid ML responses and one first-request `ML_UNAVAILABLE` Java fallback. Every request passed legality/cap/base-score checks; valid diagnostics matched the exact active bundle and daily snapshot above. Saved teams and recorded games remained unchanged. This is not a claim of zero possible timeouts: the real fallback was exercised and preserved.

Warm HTTP median/p95: blind blue 58.54/163.13 ms, blind red 56.39/154.11 ms, early 50.43/151.23 ms, late 47.10/56.21 ms. These are whole-HTTP timings, not Python-only inference. First website request: 609.53 ms, with safe Java fallback.

## Repeat an operational refresh

From the repository root, use a **new version directory** each time; never edit an activated bundle:

```powershell
.\.venv-ranker\Scripts\python.exe scripts/pick_service/history_bundle.py build --bundle data/oracle/history-bundles/oracle-YYYYMMDD-v1
.\.venv-ranker\Scripts\python.exe scripts/pick_service/history_bundle.py validate --bundle data/oracle/history-bundles/oracle-YYYYMMDD-v1
.\.venv-ranker\Scripts\python.exe scripts/pick_service/history_bundle.py activate --bundle data/oracle/history-bundles/oracle-YYYYMMDD-v1
```

Build defaults to the local 2026 Oracle CSV and existing 16.17.1 champion catalog; explicit `--source` and `--catalog` are available. Unknown champions or compatibility conflicts must be resolved by an audited update, never by inventing observations or weakening gates. The prepared training artifact is never overwritten. These commands do not retrain or evaluate the spent test set.

Start the persistent service normally:

```powershell
.\.venv-ranker\Scripts\python.exe scripts/pick_service/service.py
Invoke-RestMethod http://127.0.0.1:8766/health
```

It follows the active pointer automatically. Leave the service running; stopping it safely returns recommendations to Java-only. New data will eventually become stale again under the unchanged seven-day gate.

## Files and tests

- `scripts/pick_service/history_bundle.py`: approved merge, validation, manifests, atomic pointer, safe reload manager and CLI.
- `scripts/pick_service/service.py`: verified inference-history loading and provenance; frozen feature arithmetic unchanged.
- `scripts/pick_service/test_history_bundle.py`, `test_service.py`, `test_refresh_verification.py`: retention, corruption, source replay, failed activation/reload, lag and traceability checks.
- `scripts/pick_service/verify_refresh.py`: repeatable read-only HTTP/legality/bonus/fallback verification.
- Java `PickModelClient`, `PickDiagnostics`, `TeamPickService` and focused tests: strict provenance validation and diagnostic propagation. Existing bonus/gates unchanged.
- This report, `history-refresh-plan.md`, `history-refresh-source-conflict.md`, `history-tracing-report.md`, `ml-current-state.md`: operational decisions, checks and commands.

Backend regression: **71 passed**, zero failures/errors/skips. Python service/bundle/verification suite: **23 passed**. The tests include the complete activation call failing during model warmup while preserving the old pointer. Independent review found no remaining critical or important issues after source replay and eligible-freshness validation were added.
