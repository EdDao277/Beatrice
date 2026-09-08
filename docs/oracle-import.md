# Oracle pro-game import

This milestone prepares historical pro-game evidence. It does not train a model, update champion metadata, run Riot collection, or change manually recorded team games.

## Files and responsibilities

- `scripts/oracle/prepare.py`: Python standard-library CSV parser, champion/role normalization, game validation, deduplication, and report generation. No pip dependencies.
- `data/oracle/*.csv`: unchanged source exports. This folder is already ignored by Git.
- Each newly named prepared folder contains `games.jsonl` and `report.json`. Never edit these by hand; create a new batch when source data changes.
- `OracleImporter`: explicit transactional database import, checksum verification, duplicate/conflict checks.
- Migration V8 adds only `oracle_imports`, `oracle_matches`, and `oracle_match_sources`. The report and source hashes are retained for traceability.

## Prepare and audit

Run from the repository root with Python 3.11 or newer:

```powershell
python scripts/oracle/prepare.py --output data/oracle/prepared-next
python -m unittest discover -s scripts/oracle -p 'test_*.py'
```

Change the output name for each run. An existing folder is rejected, not overwritten. Use `--catalog path/to/champion.json` when the local Data Dragon patch changes. The default catalog is `data/ddragon/extracted/16.17.1/data/en_US/champion.json`; it is read only. A interrupted preparation may leave an incomplete folder; it is not an importable batch without a matching final report.

The first audit of the supplied 2024–2026 files found 344,016 rows, 28,668 game groups, 28,644 accepted games, 27,048 games with complete draft fields, and 1,596 lineup-only games. It rejected 2 games for result inconsistencies, 12 for missing/inconsistent patches, and 10 for duplicate champions. No duplicate rows or games occurred in that audit. The original rejected records remain in the CSVs; the report gives reasons and example game IDs.

## Import into Beatrice (explicit database write)

First restart the backend from `backend/` with the existing local profile setup. Flyway creates the new Oracle tables on startup. Then, after reviewing the report, run:

```powershell
Invoke-RestMethod -Method Post http://localhost:8080/api/oracle/imports/prepared-2026-09-08-reviewed
```

Replace the final name with your prepared folder name. The route accepts only named folders under `data/oracle`, and is available only with the `local` Spring profile. It does not accept uploaded CSVs, database credentials or arbitrary paths. This is a synchronous operation; wait for its response. If the response is lost, retrying the same batch is safe. Identical file content is a no-op. Existing identical games are linked to the new batch; differing records for an existing game ID reject the entire transaction, without overwriting old evidence. Corrected exports need an explicit reconciliation workflow later.

The live import was NOT run during development. Automated Java tests import fixtures into disposable Testcontainers databases only. Repeat detection hashes both prepared games and the audit manifest, so a new manifest is retained even when all accepted games already exist. Every game's source hashes must match a nonempty source list in that manifest.

Verified after review: 5 Python tests and 53 backend tests passed. The reviewed output is `data/oracle/prepared-2026-09-08-reviewed/`; the earlier `prepared-2026-09-08/` output is preserved, but use the reviewed batch because it includes the complete rejection ledger. Both retain the same 28,644 accepted games.

## Meaning and limitations

- Player positions normalize `jng` to `JUNGLE`, `sup` to `SUPPORT`, and `adc` to `BOT`. Champion IDs come from the local catalog, including the Wukong/MonkeyKing alias.
- Each accepted game has two sides, ten distinct champions, five distinct roles per side and opposite results. Date/patch/league must agree. Patch formatting is canonical (`16.01` becomes `16.1`). Source timestamps are preserved without inventing a timezone.
- `draftFieldsComplete` means the team-row pick lists match their final lineups and all ten bans are present, unique and disjoint from the picks. It is not proof of verified chronological draft events. Missing order is never reconstructed from player row order.
- Partial source completeness is preserved. Missing draft fields do not discard an otherwise valid final lineup. Unknown champions quarantine a game instead of altering the catalog. Empty/no-ban values make draft completeness false conservatively.
- The normalized payload includes outcomes as labels and final roles for later analysis. Neither is a legal input to an earlier draft prediction. Kills, damage, gold and other post-game statistics are deliberately excluded from the prepared payload.
- Pro data remains separate from the collection and team-history tables. No pro game is treated as a user's game. These rows are not yet used by the recommendation endpoint.
- Before training, verify pick-order semantics, account for relevant series/Fearless rules, split chronologically by whole match/series, and derive aggregate features only from earlier data. All rows and draft prefixes of one match must stay in the same split. Current champion metadata is not historical patch metadata.

Next milestone: use the audited records to evaluate a role-uncertain, team-wide recommendation baseline before adding ML or an LLM.
