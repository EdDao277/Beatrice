# ML evidence and recommendation audit

Audit date: 2026-09-10. This document records the inspected production implementation, the existing offline pick experiment, and the provenance required for additional historical features or a separate ban experiment. It does not change the database, source exports, champion metadata, website, or recommendation endpoint.

## What is already implemented

The production API, the offline hand-written baselines, and the learned pick ranker are separate implementations. Results from one must not be described as results from another.

| Implementation | Candidates and evidence | Scoring and limits |
| --- | --- | --- |
| Java production picks | The selected target-role player's saved pool. Explicit requested traits and role assignments. One selected maintained collection dataset, patch and queue. | `weighted-picks-v2`: comfort 35%, composition 20%, ally synergy 15%, matchup 10%, meta 8%, team history 7%, draft value 5%. Missing factors remain 50 on a 0–100 scale; weights are not redistributed. Team history and draft value are placeholders. |
| Java underlying pick engine | The same supplied single-player context and selected evidence. | Comfort is `6 * rating`; composition adds up to 10 preference points. Role, synergy and matchup adjustments are bounded and weighted by `games / (games + 50)`. The weighted adapter converts the statistical adjustments to its component scale. |
| Java production bans | Champions supported by selected role rows or same-role matchup rows against explicitly intended picks. Unavailable and protected picks are excluded. | `evidence-bans-v1`: strongest positive role-rate threat plus strongest intended-pick disadvantage, minus saved comfort for that champion in the supplied target player's pool. At least 30 observations are required per supporting row. Only positive totals are returned, up to three; no supporting evidence means no bans. |
| Offline research baselines | All five roster members. `observed` restricts to prior player/champion observations; `inferred` permits the earlier global champion vocabulary; `saved` restricts to explicitly supplied saved pools. Each candidate requires a complete five-player assignment witness. | `pool`, `pool_rules`, `pool_rules_stats`: familiarity, then observed assignment flexibility, then shrunk historical champion/ally-pair rates. Current composition, lane matchup and saved-team history are neutral. These are Python research adapters, not the Java endpoint. |
| Initial learned pick ranker | The inferred-policy candidate export with prior familiarity, champion statistics, ally-pair evidence, missingness and stage interactions. | Pairwise linear pro-pick imitation. Training-only normalization and fitting. A learned preference score is neither calibrated win probability nor evidence that following the recommendation improves wins. |

Code anchors at audit time:

- `backend/src/main/java/com/beatrice/backend/recommendation/RecommendationService.java:33` selects the target player; lines 43–63 select metadata, lines 75–78 select maintained evidence, and lines 83–89 explicitly separate unsupported inputs and identify the algorithm.
- `backend/src/main/java/com/beatrice/backend/recommendation/WeightedRecommendations.java:18` defines the fixed components; lines 29–30 leave history and draft value neutral.
- `backend/src/main/java/com/beatrice/backend/recommendation/RecommendationEngine.java:43` implements the original pick points; line 65 begins the independent ban heuristic; lines 78–90 enforce sample support, own-pool cost and positive-score requirements.
- `scripts/benchmark/baseline.py:120` implements the research policy; `History.observe` records earlier player counts, champion results and ally pairs. Bayesian smoothing uses a Beta(25,25) prior.
- `scripts/benchmark/ml_features.py:4` defines the initial whitelist; `scripts/benchmark/linear_ranker.py:45` fits only supplied training cases.

The existing Draft UI staging is documented in [recommendation-baseline.md](recommendation-baseline.md): the retained role-specific endpoint is not the current placeholder grid's recommendation engine.

## Publisher evidence for pick and ban order

The two sources below were already cited in this repository and were directly retrieved successfully on 2026-09-10. No additional sites were searched. Firecrawl's connected scraper was used because its CLI was unavailable locally.

1. The [Oracle Match Data Dictionary](https://lol.timsevenhuysen.com/matchdata/match-data-dictionary/) explicitly defines `ban1` as “Team’s first ban.” and `ban5` as “Team’s fifth ban.” It similarly defines `ban2`, `ban3` and `ban4` as the second, third and fourth bans. This is publisher documentation of team-relative ordinal order, not merely five unordered banned champions. The retrieved page's metadata reports a 2019-09-10 modification date; its introductory text warns that export structure can change.
2. The [Oracle pick-order announcement](https://lol.timsevenhuysen.com/2024/02/void-grubs-and-pick-order-in-the-csvs/) states that the newly added five pick columns follow the existing ban columns and represent the sequence selected by the team for that row. This documents team-relative pick chronology. It does not separately specify a cross-team 20-action schedule.

This corrects the preliminary local-code-only audit: ordinal ban semantics are documented. The local `source_audit.py` currently stores an explicit `pickOrderSemantics` field but no equivalent ban-order field; absence of that field in our audit is not absence of publisher evidence.

### The remaining phase and format constraint

`scripts/benchmark/protocol.py:79` interleaves each side's arrays under a standard 20-action tournament schedule. At line 83, action indices 0–5 and 12–15 are bans. Under that schedule, each team's first three ordinal bans occur in the initial phase and its fourth/fifth bans occur in the second phase. This phase mapping is an inference combining documented ordinal fields with the schedule assumption.

The two publisher pages do not certify that every 2024/25 event used that schedule, supply original action timestamps, or verify individual game exports against recorded drafts. `draftFieldsComplete` verifies presence, uniqueness and agreement with the final champion sets; it does not establish every event's applicable rules. The current audit restricts examples to opening games, consistent identities and structurally legal prefixes. Opening-game gating avoids later-game accumulated Fearless restrictions; it does not prove all opening-game tournament rules or champion-availability restrictions.

Consequently, both pick and ban replay remain conditional on the supported standard-format opening-game policy. Early pick legality depends on the same ban-phase assumption because future second-phase bans must not be exposed as already unavailable. Do not describe the complete 20-action history as independently certified for every event. Later-game formats and games with contradictory source/rule evidence should remain excluded until separately supported.

## A separate ban model: supported experiment and deferred claims

The publisher's ordinal definitions support a **research-only next-ban imitation experiment** on the same conservative standard-format opening-game cohort, with the phase/format assumption recorded. Missing ban documentation alone is not a reason to defer that experiment after this source check. If a run requires independently verified per-event chronology, that stronger certification remains deferred because these sources do not provide it.

Ban imitation and ban utility must have separate meanings and evaluation:

- Imitation predicts which legal champion the professional team banned next. Its labels can come from the documented ordinal fields; evaluate by ban phase and whole game, using only the preceding draft prefix.
- Utility concerns what the ban removes from the opponent and costs the user's own team. Actual professional bans do not label causal win improvement, true opponent comfort, or the user's opportunity cost. Those stronger claims remain deferred.
- Current production own-pool cost covers only one target player. A team-wide utility model needs all five authoritative saved pools, or clearly labeled earlier-history proxies in a pro-only experiment. A missing observation must not silently become proof that a player cannot use a champion.
- An explicitly intended pick may be supplied at prediction time. The source game's later own-side picks must never be converted into intended-pick features: that would expose future draft choices.
- Earlier opponent familiarity, observed historical threats and own-team loss of options are potential supported factors. Preserve sample counts, missingness, unavailable/protected exclusions and a documented no-evidence abstention policy. A high learned imitation rank alone does not satisfy the production threat-evidence requirement.

## Historical feature provenance

| Feature source or group | Suitability for a clean 2024/25 replay | Required interpretation or missing prerequisite |
| --- | --- | --- |
| Earlier Oracle player/champion counts, champion results, ally-pair results | Available and already used. | Earlier observed familiarity is not the user's saved comfort. Historical pooled results are observational; retain sample support and missingness. |
| Earlier Oracle role propensities, enemy interactions, team/roster results, patch/league/recency slices | Feasible derivations from retained records, requiring explicit implementation and evaluation. | Learn only from earlier games. Historical role tendencies can inform uncertainty; target-game final roles and champion-to-player assignments cannot be prediction-time inputs. Only currently visible enemy champions may enter interactions. |
| Earlier unordered Oracle ban frequency | Feasible historical feature even without reconstructing earlier games' action timestamps. | Count bans only after the source game is past the history cutoff. This describes earlier banning behavior; next-ban labels still require the supported replay policy above. |
| Current CompCraft champion roles, utility/composition tags and damage categories | Historical applicability is not established. | Metadata is curated and stored by import ID/champion ID, with no dedicated patch/effective-date history. The archive was imported in September 2026. It cannot be called historically correct 2024/25 metadata without versioned evidence or a separately disclosed retrospective assumption. |
| Imported CompCraft role, synergy, matchup and composition aggregate rows | No safe generic as-of join for this replay. | Patch/queue/source dimensions are retained, but contributing match IDs/timestamps are unavailable here; the documented uploader can leave mixed collection vintages. Same-patch whole-period aggregates could include future matches. A verified earlier snapshot or match-level rebuild is needed. |
| Maintained Riot collection aggregates | Not a source of historical 2024/25 knowledge under the current dataset configuration. | Default split starts July 2026. The ledger keeps IDs and acceptance state but not raw responses or match timestamps needed to reconstruct earlier aggregate vintages. Dataset identity alone does not create an as-of history. |
| User's saved roster, comfort pools and manually recorded games | Authoritative present-day user context, separate from this pro-only historical experiment. | No supported historical mapping from these saved teams to 2024/25 professional player preferences. Recorded roster snapshots must not become retrospective comfort labels for unrelated pro games. |
| Current-game outcome, final roles, future picks/bans, held-out target inserted into candidate vocabulary | Inadmissible as prediction-time features. | These reveal information unavailable when choosing the action. Keep targets separate from features and retain missing-target cases in evaluation denominators. |

Provenance anchors:

- `scripts/oracle/prepare.py:45` retains final roles and player identities; lines 53–65 retain picks, bans, teams, results, dates, patches and leagues. Earlier completed games may contribute those observations after the history cutoff; the target game's final assignments may not.
- `backend/src/main/resources/db/migration/V4__reference_data_and_lineups.sql:2` records import identity/time; lines 9–14 key metadata by import/champion. Patch is a dimension of `reference_stats`, not the metadata table.
- [compcraft-reference-data.md](compcraft-reference-data.md) records the September 2026 import, curated descriptors, patch range 14.12–16.15, correlated collection population, missing-row censoring and mixed uploader vintages. Its aggregate rows are not independent training matches.
- [collection.md](collection.md) records the default 2026-07-29 split start and absence of retained raw match responses. `V7__maintained_collection_stats.sql:24` defines the match-ID ledger; `CollectionStats.java:42` records acceptance before incrementing aggregates.
- `backend/src/main/resources/db/migration/V3__recorded_games.sql:11` preserves recorded roster snapshots and line 14 records entry time. This is a separate population from Oracle professional matches.

## Boundary for expanded experiments

Every newly derived historical feature must update through the same earlier-only state as existing features. `scripts/benchmark/temporal.py:24` sets an exclusive cutoff one day before the prediction day; only earlier source matches are observed. `build_dataset.py` excludes the reserved test partition from historical state and exports training/validation only. Whole games remain together; validation uses expanding earlier observations after the lag, not a frozen end-of-2024 aggregate.

Retain original source/prepared/code/artifact hashes, label embargoes, source-group exclusions, candidate availability and missingness. Any new feature group or ban model needs its own clearly named schema and a matched validation comparison. Improvements in action agreement support an imitation claim, not calibrated win probabilities, optimal draft strategy or demonstrated win improvement.
