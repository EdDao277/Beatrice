# CompCraft archive: what Beatrice uses

## Imported on 2026-09-05

The supplied gzip backup was read as COPY text, **not restored or executed as SQL**. Only the five reference tables below were imported. Existing Beatrice teams, pools, and results were not imported from CompCraft or replaced. No API key, Supabase connection, or external upload is required.

| Source table | Accepted rows |
| --- | ---: |
| champion_metadata | 173 |
| champion_role_stats | 9,549 |
| champion_synergy_stats | 157,298 |
| champion_matchup_stats | 84,814 |
| team_comp_signature_stats | 14,425 |

Rejected rows: 0. These are aggregate rows, **not 266,086 distinct matches**. Local team/game counts were 1/1 before and after import. Checksum-based import identity prevents importing the identical archive twice. A new archive becomes a new batch; the UI reads only the latest committed batch, never adds overlapping snapshots together.

## Try it

1. In History, choose the role actually played using the small dropdown beneath each champion portrait, then **Save lineup**. Opponent roles may remain Unknown. The same compact editor appears after recording a new game in Draft.
2. Imported evidence remains available through the backend reference APIs for future LLM and pick/ban algorithms. The archive explorer is intentionally not displayed on Draft.
3. When consuming the evidence, retain patch, queue, region, source, wins, and sample size together. The API's top 40 pairs are ordered by sample size, not highest win rate. No row means unavailable evidence, not zero success.

Lineup annotations do not change pick order, game result, or the roster snapshot. Player names alongside roles refer to the saved roster's role slots, not a separately verified Riot participant mapping. If your players swapped their usual roles, this annotation alone does not identify the actual player: explicit participant assignment is future work.

## What the scripts establish

Reviewed the supplied `processMatches`, role/matchup/synergy/composition aggregators, `crawlMatchNetwork`, `pipelineConfigs`, and `env` scripts. Also inspected their local sample-confidence, team-signature, and cache/upload implementations. These scripts were read, not executed; credentials were not read.

- Observed roles originate from Riot `teamPosition`, falling back to `individualPosition`. IDs are matched to Beatrice's catalog; ADC/BOTTOM normalize to BOT and UTILITY to SUPPORT.
- Metadata roles and composition tags are curated descriptors. They indicate plausible flexibility, not proof of the role played in a particular game.
- Synergy is an ordered champion-role pair: A→B and B→A describe the same pair's games. Beatrice queries one direction and does not sum them.
- Observed win rate is recomputed as wins / games. The stored delta is pair win rate minus the mean of both individual champion-role baselines in the same cohort. Those baselines include the pair games: this is descriptive association, not independent causal evidence.
- The original `confidence` is only a sample-size lookup: <20 → .15; 20–49 → .35; 50–99 → .65; 100–199 → .85; ≥200 → 1. It is preserved for provenance but not displayed as statistical confidence.
- The crawler starts from ladder seeds and expands through recurring players. This is a nonrandom, correlated network sample, not representative of all League players. Seed ranks do not establish each match's rank; imported tier fields are null.
- The backup covers patches 14.12 through 16.15, region `americas`, source `general-network`, and queue IDs 400, 420, 440. It is not Clash-specific evidence and is older than the current 16.17.1 portrait catalog.
- 146,360 of 157,298 synergy rows have fewer than 20 observations. A high percentage from a few games is not a reliable recommendation.

## Limitations and next research steps

The scripts deduplicate match IDs during crawling, but the processor itself does not enforce distinct IDs or five unique roles, and does not explicitly filter remakes/duration. The uploader uses thresholds (role 20, synergy 5, same-role matchup 5, cross-role matchup 10, composition 5) plus row caps and prioritization. Missing rows are therefore censored evidence, not population zeros. Upserts replace counts but do not necessarily remove older rows absent from a later upload, so collection vintages may differ within a backup.

Composition signatures are coarse, overlapping metadata flags; for example the old logic counts true-damage tags toward both physical and magic presence. They are archived alongside matchups but **are not yet used to rank recommendations or shown as validated composition scores**. The first UI exposes metadata roles, role statistics, and pair statistics only.

Before ML: retain raw match IDs, patch, queue, timestamps, participant roles and outcomes; validate role uniqueness and remake handling; deduplicate across crawls; split evaluation by time and account/group where appropriate; establish a simple baseline with minimum samples and uncertainty. Do not train on these aggregate tables as if each row were an independent match.

## Code map

- `backend/.../reference/CopyDumpReader.java`: narrow streaming COPY reader, no SQL interpreter. Supports the ordinary escapes used by this archive; it is not a general PostgreSQL restore tool.
- `ReferenceImporter.java`: validation, ID/role normalization, transactional batches and audit report.
- `ReferenceService.java` / `ReferenceController.java`: read-only exact-slice API.
- `V4__reference_data_and_lineups.sql`: separate reference tables and versioned lineup columns.
- `frontend/src/components/ReferenceExplorer.tsx`: evidence and caveats.
- `SavedLineups.tsx` plus game API/service/repository: explicit final lane annotations and stale-update protection.

## Import again only when needed

Stop the running backend first. From `D:\Projects\Beatrice\backend`:

```powershell
mvn -B spring-boot:run '-Dspring-boot.run.profiles=local' '-Dspring-boot.run.arguments=--beatrice.reference.import-file=C:/Users/EdDao/Downloads/db_cluster-14-08-2026@15-20-04.backup.gz'
```

The archive stays outside Git. Do not place it in frontend/public. Normal later starts need only `mvn -B spring-boot:run '-Dspring-boot.run.profiles=local'`; the data persists in PostgreSQL. Import is disabled unless that explicit argument is supplied. No `.env` change is needed.

Verification: `mvn -B test` in backend; `npm test`, `npm run lint`, `npm run build` in frontend. Backend integration tests use disposable PostgreSQL containers, not your team database.
