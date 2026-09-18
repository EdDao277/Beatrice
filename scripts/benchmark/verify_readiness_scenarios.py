"""Replay saved observations for safety checks; never score the final test again.

Synthetic missing-evidence faults test the boundary, not model accuracy on new
champions. Original snapshot, model predictions, and scenario artifacts stay intact.
"""
import json

from saved_scenarios import ROOT, bounded
from scaled_train import read, sha


def verify():
    folder = ROOT / 'data/oracle/saved-team-readiness'
    manifest = read(folder / 'manifest.json')
    for name, expected in manifest['artifacts'].items():
        assert sha(folder / name) == expected, name
    for name, expected in manifest['codeSha256'].items():
        assert sha(ROOT / name) == expected, name
    observations = read(folder / 'observations.json')
    checks = 0
    all_missing = 0
    ties = 0
    comfort_losses = 0
    for row in observations:
        java, scores = row['java'], row['scores']
        if not java:
            assert row['bounded'] == []
            continue
        # Preserve Java exactly when every candidate lacks usable evidence.
        assert bounded(java, scores, {}) == java
        all_missing += 1
        if not row['syntheticPool']:
            for candidate in java:
                champion = candidate['id']
                gates = {**row['gates'], champion: False}
                # Even an arbitrarily strong raw ML preference must not override
                # this candidate's synthetic missing-evidence gate.
                fault_scores = {**scores, champion: max(scores.values()) + 1000.}
                result = bounded(java, fault_scores, gates)
                assert {r['id'] for r in result} == {r['id'] for r in java}
                assert next(r['score'] for r in result if r['id'] == champion) == candidate['score']
                checks += 1
        if 'bounded_top_changed' in row['flags']:
            top = row['bounded'][0]['id']
            ties += java[0]['score'] == next(r['score'] for r in java if r['id'] == top)
            comfort_losses += row['comfort'][top] < row['comfort'][java[0]['id']]
    result = {'status': 'VERIFIED', 'syntheticMissingEvidenceCandidateFaults': checks,
              'allMissingExactJavaFallbacks': all_missing,
              'boundedTopChangesWithOriginalJavaTie': ties,
              'boundedTopChangesWithLowerComfort': comfort_losses,
              'limitation': 'Boundary replay only; not natural cold-start model accuracy.',
              'sourceManifestSha256': sha(folder / 'manifest.json')}
    target = folder / 'safety-replay.json'
    if target.exists():
        assert read(target) == result
    else:
        with target.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, indent=2)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    verify()
