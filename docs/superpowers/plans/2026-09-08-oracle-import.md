# Oracle import implementation plan

**Goal:** Audit Oracle CSVs and import validated pro-game records separately from Beatrice's own games and champion metadata.

**Architecture:** A Python standard-library preparer streams CSV input into grouped, whitelisted game records and produces a manifest, JSONL and quality report. A transactional Java importer reads that prepared file into additive Oracle-only tables. Original CSVs remain unchanged. Training is out of scope.

**Approved scope:** User approved the Oracle importer and data-quality report on September 8. Continue in the existing folder; preserve all prior work. No live database import or collection run during implementation.

## Tasks

- [ ] Add `scripts/oracle/prepare.py` and unittest fixtures. Validate 10 distinct champions, five unique roles per side, opposite results, consistent patch/date/league, and team rows. Keep valid final lineups when ordered draft fields are incomplete. Reject ambiguous records; report counts and sample IDs. Test duplicates, unknown champions, missing draft fields, and prevention of post-game feature leakage.
- [ ] Add V8 Oracle-only import/match/source-link tables and a Java importer. Hash files and normalized records, deduplicate identical games, fail atomically on conflicting existing games. Test idempotence and rollback using disposable PostgreSQL.
- [ ] Audit all three real CSVs locally, generate a new output folder without overwriting previous runs, and report actual counts. Do not invoke the live DB import endpoint.
- [ ] Document preparation/import commands, source separation, draft-field limitations and future training safeguards; run fixture tests and review changes.

**Verification:** `python -m unittest discover -s scripts/oracle -p test_*.py`; backend `./mvnw.cmd test`. Audit output must reconcile input rows, rejected games and accepted unique games. All database tests use TestDatabase containers.

## Completion record

All four tasks completed. Full audited source rows: 344,016; game groups: 28,668; accepted: 28,644; rejected: 24. Reviewed report retains all rejection identities and source hashes. Five Python tests and 53 backend tests pass. Code review findings addressed: manifest-sensitive import identity, validated provenance, recomputed completeness, full rejection ledger, and multi-record rollback coverage. No live DB import or model training performed; changes remain uncommitted in the user-selected folder.
