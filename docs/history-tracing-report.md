# Java history tracing report

## Scope

Task 1 traces the active history identity supplied by local Python ranking without changing the public recommendation response, ranking thresholds, or guarded bonus arithmetic.

## Contract

`PickModelClient` validates the complete response provenance before reading score rows:

- `historyBundleVersion` is nonblank, at most 100 characters, and matches `[A-Za-z0-9._-]+`.
- `historyBundleSha256` and `historySnapshotId` are lowercase, 64-character hexadecimal SHA-256 values.
- Missing or malformed provenance rejects the entire model response as `INVALID_PROVENANCE`. The returned result contains no signals or provenance, so the existing guarded fallback keeps the Java base ranking exactly intact.

Validated values are retained in `PickModelClient.Result`. `TeamPickService` passes that result to `PickDiagnostics`, which writes the three fields alongside the recommendation event, including the applied gate result and inference latency. The legacy three-argument `Result` constructor remains available for existing fallback fixtures.

## Verification

Focused tests were run from `backend`:

```powershell
mvn -q '-Dtest=PickModelClientTest,PickDiagnosticsTest' test
```

The command completed with exit code 0 on September 17, 2026 (9 tests, 0 failures). The valid HTTP provenance test uses a fresh evidence timestamp because the production client deliberately evaluates staleness using the live clock; deterministic envelope validation tests continue to use a fixed clock. The same test warms the local `HttpClient` before its assertion so its result is not coupled to one-time client initialization inside the production 100 ms request budget.

## Limits

This task records provenance only. It does not alter model/schema versions, scoring signals, support gates, bonus bounds, training exposure, bundle activation, or the API response shape.
