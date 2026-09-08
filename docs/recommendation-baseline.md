# Draft recommendation service

## UI staging update (September 8)

The Draft screen now removes all draft-time role and evidence controls. Its left panel displays phase-aware ban/pick placeholder grids; the right panel is reserved for Beatrice explanations. The old role-specific endpoint remains implemented but is no longer called by this screen. This is intentional until the team-wide, role-uncertain engine is implemented; placeholder slots are not recommendations. Backend scoring and data remain unchanged. Record the result after playing, then use the preserved final-lineup editor to update History with actual lanes. The API instructions below describe the retained baseline, not the current screen controls.

## Current UI / API: weighted picks v2

The Draft page now calls a read-only backend adapter. It loads the selected team's saved target-role pool and champion metadata, plus one explicitly selected maintained dataset/patch/queue. It never runs the collector, calls Riot, or starts an LLM.

Pick weights are fixed: comfort 35%, composition 20%, ally synergy 15%, enemy matchup 10%, meta 8%, team history 7%, draft value 5%. Each component is 0–100. Missing/unsupported components contribute **50**, not zero; weights are not redistributed. Example: comfort 8/10 and everything else unknown gives `80×0.35 + 50×0.65 = 60.5` with 35% factor coverage. Coverage is not statistical confidence, and score is not win probability.

- Composition measures how many explicitly requested, not-yet-covered traits the candidate supplies. Absent metadata or no outstanding requested traits means neutral. Known metadata with none of the requested traits can legitimately score zero.
- Synergy/matchup convert the v1 sample-weighted adjustments below to `clamp(50 + adjustment×10, 0, 100)`. Explicit ally/enemy roles and relevant role baselines are required.
- Meta uses the selected collection's role adjustment on the same scale. It is **not pro-game evidence**.
- Team history and strategic draft value remain neutral placeholders. Composition-signature statistics and professional games are not yet scoring inputs. Manual team history is never mixed with the collection.
- Bans retain v1 preference points, not a 0–100 scale; unsupported bans are omitted. Only the target player's pool is penalized, not all five players' pools.

### Trying it

Restart the backend to load the new endpoints (Flyway will apply pending migrations, including collection tables). On Draft, choose a role, queue and optional collected dataset, then click **Suggest picks and bans**. Without a collected dataset, comfort/available metadata still work. This does not start collection. Choose optional composition needs and an intended pick to protect from bans. After a pick, use its role dropdown only when its intended lane is known; leave flex picks unknown otherwise.

The left portraits show bans then picks. Clicking a portrait displays component values, factor coverage, warnings, and games/wins on the right. Suggestions are planning advice, never automatic actions. They disappear when their request context changes. Draft-time role assumptions are not final match-history assignments: confirm actual lanes separately after recording the game.

### API contract

`GET /api/recommendations/datasets` returns collected dataset IDs, metadata import IDs and split-start Unix seconds. No dataset is automatically selected.

`POST /api/teams/{teamId}/draft/recommendations` takes:

```json
{
  "format": "RANKED", "side": "BLUE", "targetRole": "MID",
  "queueId": 400, "patch": "16.17.1", "datasetId": null,
  "actions": [], "assignments": [], "intendedPicks": [], "desiredTraits": ["AP"]
}
```

Actions use `{ "side": "BLUE", "kind": "PICK", "championId": "Swain" }` within a valid draft prefix. Assignments use `{ "side": "BLUE", "championId": "Swain", "role": "MID" }` for an existing pick. Roles are TOP/JUNGLE/MID/BOT/SUPPORT. Never derive them from selection order. Responses include picks, bans, patch/queue/dataset/metadata-import provenance, notices and algorithm version. Patch `16.17.1` uses statistical slice `16.17`; other patches/queues/datasets and the historical imported archive are not silently substituted.

Run backend tests with `./mvnw.cmd test` (Docker required for disposable databases); frontend `npm test`, `npm run lint`, `npm run build`. These use fixtures, not live Riot collection.

## Underlying pick and ban baseline v1

`RecommendationEngine` is a pure Java scoring component. It performs no database queries, Riot calls, LLM inference, or UI changes. `WeightedRecommendations` converts its pick adjustments for the current API; v1 ban scoring is retained.

## Inputs and boundary

Supply the target player's pool, canonical champion IDs, unavailable champions, explicitly protected/intended picks, requested composition traits, already-covered traits, and explicit ally/enemy role assignments. Unknown roles are absent, never inferred from pick order. The adapter validates the draft phase/turn with server draft rules and provides one exact dataset/patch/queue evidence slice. The pure engine accepts already-selected evidence, not raw database rows across populations.

## Picks

Preference points, not probabilities:

- Comfort: `6 * rating`, maximum 60.
- Composition: 5 per requested trait newly supplied, maximum 10. Desired traits must be explicit; missing metadata is not treated as missing capability.
- Role: `(observed win rate - 0.5) * 10 * reliability`, bounded to ±5.
- Synergy: average pair-rate difference from the mean of both role baselines, multiplied by 10 and the weakest reliability among all three samples, bounded to ±5.
- Matchup: average same-role matchup-rate difference from the candidate's role baseline, multiplied by 10 and the weaker sample reliability, bounded to ±5. Requires an explicitly assigned enemy role.

Reliability is `games / (games + 50)`: a shrinkage heuristic, not a confidence interval. Missing baselines skip the adjustment. Scores and every contribution are returned with supporting rows, reasons and warnings. Results are sorted by score then champion ID; at most three are returned.

## Bans

Unavailable and explicitly protected champions are excluded. At least 30 games are required for a row to support a ban.

- General threat: strongest positive role-rate difference from 50%, scaled by 10 and reliability, bounded to 5.
- Intended-pick threat: strongest observed same-role disadvantage for an intended pick, scaled by 20 and reliability, bounded to 10.
- Own-pool cost: subtract the banned champion's comfort in the supplied target player's pool.

Only positive total scores are returned. No evidence means no bans, not fabricated suggestions. The opponent's preferences are unknown. This first heuristic does not yet account for all five players' opportunity costs, pick priority, or strategic ban sequences. General role strength is descriptive, not causal counter evidence.

## Evaluation

Run from `backend/`:

```powershell
mvn -B '-Dtest=RecommendationEngineTest' test
```

Fixtures cover comfort fallback, exclusions, protected picks, sparse evidence, unresolved roles, explicit intended-pick counters, composition contributions, weak-baseline shrinkage, deterministic ties and duplicate evidence rejection.

Next: evaluate rankings against saved draft situations before adding team-history or strategic draft-value factors. No learned weights or win probabilities should be claimed from these fixtures.
