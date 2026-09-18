# History refresh validation checkpoint — September 17, 2026

**Resolved September 18:** the user approved preserving old normalized records and appending only new IDs. Identity-only revisions are logged; gameplay changes still fail validation. Re-auditing retained records preserved old eligibility, including one game whose corrected upstream identities would otherwise promote it. See `history-refresh-results.md` for successful activation and live verification. The text below preserves the original blocked checkpoint.

Activation is blocked; no new history pointer was published.

The staged Oracle source has SHA-256 `d13fe165a1e56f7f1699c5530a91a4e608a509cc3ce040faf0fd2935f3e95299`.
The unchanged importer accepted 8,808 games with no rejected or conflicting games within that source. Latest source game: `2026-09-16 18:24:13`.

Comparison with frozen normalized 2026 history found:

- 376 newly added games.
- No missing old games.
- 225 changed existing records.
- Changes are confined to team names (55 field differences), team IDs (59), player names (170), and player IDs (221).
- No changes to other normalized fields, including outcomes, champions, draft order, timestamps, or patches.

The strict merge correctly rejected the candidate bundle before writing its manifest or activating it. Opening-game audit compatibility and full end-to-end verification have not been completed. The candidate directory `data/oracle/history-bundles/oracle-20260917-v1` contains only staged source/catalog/import artifacts, not an activatable bundle.

Recommended resolution, requiring an explicit policy decision: retain every previously normalized record exactly and append only new game IDs; record ignored upstream identity revisions in the bundle provenance. Do not silently adopt revised identities, since historical player identity affects frozen history semantics. Re-run audit eligibility and all activation checks after that policy is approved.

No model retraining, spent-test evaluation, gate change, saved-team write, or draft write was performed at this checkpoint. Python bundle/hot-reload implementation remains incomplete; do not treat the refresh milestone as finished.
