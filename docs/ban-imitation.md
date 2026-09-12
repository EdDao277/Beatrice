# Separate ban-imitation experiment

## What this learns

The pick and ban targets are different decisions. `scripts/benchmark/ban_experiment.py` learns **which champion professional teams ban next**, not whether removing that champion improves your team's win probability. It does not replace the live Java ban scorer or its evidence-backed abstention behavior.

Publisher documentation defines ban1 through ban5 as each team's chronological ban ordinals. We interleave them using the standard tournament schedule, restricted to eligible opening games. This avoids assuming that later series games used unrestricted drafting. It is not independent video verification of every event's format; historical champion availability is also not fully certified.

## Evidence and safeguards

- Replay each prefix using only visible earlier picks and bans.
- Use earlier-only history, with the same availability lag and embargo as the pick experiment.
- Build prior-ban frequency, own/opponent roster familiarity, champion statistics, and synergy with visible enemy picks. Unseen history stays missing rather than becoming a negative skill judgment.
- Exclude already picked/banned champions and explicitly protected champions. Never use a team's eventual pick as an input-time protected champion.
- Require prior-ban observation or at least 30 historical champion games for the research candidate set. Count the actual ban as a miss when absent; never inject the label into candidates.
- Keep 2026 unscored. Current champion metadata and maintained Riot tables are not retroactively joined to historical records.

## Training and evaluation

The fixed pairwise linear model compares the actual ban against up to 16 uniformly sampled alternatives per training decision. Sampling is reproducible from the case ID. Whole games have equal total training weight, with that weight divided among covered decisions. Normalization uses sampled training rows only. Evaluation ranks **all** available candidates, comparing with prior-ban popularity on exactly the same cases and candidates.

The report includes top-1/3/5 agreement, MRR, candidate coverage and missing targets, phase breakdowns, missing evidence, legality counts, latency, paired game-bootstrap uncertainty, and error examples. Scores are uncalibrated preferences, not confidence or threat estimates. Own-roster history is only an opportunity-cost proxy; it is not the user's authoritative saved comfort.

```powershell
.\.venv-ranker\Scripts\python.exe scripts/benchmark/ban_experiment.py build --prepared data/oracle/prepared-2026-09-08-reviewed --raw-dir data/oracle --output data/oracle/ban-2026-09-12-all
.\.venv-ranker\Scripts\python.exe scripts/benchmark/ban_experiment.py train --dataset data/oracle/ban-2026-09-12-all --output data/oracle/ban-ranker-2026-09-12-reviewed
```

Use new output directories. Only datasets with a complete, verified manifest may enter training. Prediction records point to the actual evidence artifact and case ID for inspection.

The completed September 12 export contains all 2,912 eligible training games and 4,203 validation games: 71,150 ban decisions and 11,193,788 candidate legality checks, with zero illegal candidates. Twenty-two targets are absent and remain evaluation misses. The earlier September 11 folder was interrupted and is preserved, but is not a valid training input.

## Completed full experiment: September 12

Artifacts: `data/oracle/ban-ranker-2026-09-12-reviewed/` contains the model, schema, predictions, comparison report, error samples, and a verified manifest. Model-manifest SHA-256: `56e47feb5496653efef84ea1a9c01a1fb16383604af85464ea57954a75047a23`.

Validation uses 4,203 games / 42,030 decisions, with identical candidates for both methods:

| Method | Top-1 | Top-3 | Top-5 | MRR |
| --- | --- | --- | --- | --- |
| Earlier ban popularity | 3.84% | 10.18% | 17.50% | 0.1228 |
| Linear ban imitation | 5.72% | 14.47% | 21.80% | 0.1566 |

Top-three improvement is **4.29 percentage points**, with a paired whole-game bootstrap 95% interval of **+3.94 to +4.65 points**. This is a positive development-set result, not an independent final-test result. Repeated teams and related series can make a game-clustered interval optimistic. The 2026 set remains unscored.

Both methods have 99.988% validation candidate coverage (five absent targets), zero illegal suggestions, and no empty-candidate abstentions. The linear model's top-ranked candidate lacks at least one tracked evidence component in 20.65% of validation cases. Missing evidence is retained, not silently discarded.

First-phase top-three agreement improves from 12.75% to 15.80%; second-phase agreement improves from 6.33% to 12.49%. However, first-phase top-five agreement barely changes (22.99% to 23.04%). Overall training top-three agreement is 20.31%, above validation's 14.47%; this gap warrants attention to season/patch shift and generalization rather than assuming training success transfers.

Optimization took 22.0 seconds. The full verified training/evaluation job took 506 seconds, mostly loading and evaluating artifacts. Validation rank-and-sort p95 was 0.52 ms. Mean estimated end-to-end time including original evidence construction was 6.70 ms; neither number includes Java/API/UI/network overhead.

### Concrete failure examples

- `LOLTMNT03_178705:ban:0`: Kalista was third under popularity but 24th under the model. Familiarity/context signals can move a real pro ban in the wrong direction.
- `LOLTMNT03_179647:ban:12`: Nocturne was 22nd under popularity and 66th under the model. A tiny top-two score margin (0.000197) does not indicate confidence, nor does it ensure the real choice is nearby.
- `LOLTMNT02_210695:ban:14`: Mel was absent from the historical candidate set on patch 15.3. This remains a miss and illustrates the cold-start limitation; the target was not added after observing the label.

Samples are the first ten chronological examples per category, not representative failure frequencies. Each case can be joined to the original structured evidence artifact.

**Recommendation:** retain this model as a pro-ban imitation research signal, but keep Java `evidence-bans-v1` for actual recommendations. The experiment does not establish threat utility, account for the user's real comfort, or justify replacing evidence-backed abstention.

Professional opponent rosters are known in this replay. In an unscoutable queue, Beatrice may not know the opposing players at draft time. Opponent-familiarity evidence must then remain missing; these results do not establish performance under that different information boundary.

**Next ban experiment:** test earlier-only rolling-window/patch-recency evidence against this frozen benchmark. Hypothesis: pooling old seasons makes bans slow to track meta shifts. Evaluate top-three/MRR and both phases on the same cases, tracking cold-start coverage separately. A possible failure is that shorter windows discard too much roster and rare-champion history. Do not tune against 2026.
