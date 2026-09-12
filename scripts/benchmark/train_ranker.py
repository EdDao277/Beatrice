"""Offline pro-pick imitation pilot. No live recommendation, API, database or GPU use."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
from time import perf_counter

# Small dense matrices do not need a BLAS thread per CPU core. Set before importing NumPy.
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('OMP_NUM_THREADS', '1')
import numpy as np

from linear_ranker import fit, score
from ml_features import SCHEMA, FEATURE_NAMES, vector

ARTIFACTS = ('contexts.jsonl.gz', 'features.jsonl.gz', 'labels.jsonl.gz', 'predictions.jsonl.gz',
             'snapshots.jsonl.gz', 'source-audit.jsonl.gz', 'splits.json', 'report.json',
             'exclusions.jsonl.gz', 'timings.jsonl.gz')
BASELINES = tuple(f'{p}/{v}' for p in ('observed', 'inferred')
                  for v in ('pool', 'pool_rules', 'pool_rules_stats'))


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')


def rows(path, name):
    with gzip.open(path / (name + '.jsonl.gz'), 'rt', encoding='utf-8') as f:
        for line in f:
            yield json.loads(line)


def index_rows(path, name):
    result = {}
    for row in rows(path, name):
        key = row['caseId']
        if key in result:
            raise ValueError('Duplicate case in ' + name)
        result[key] = row
    return result


def verify(path):
    manifest = json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
    if (manifest.get('version') != 2 or manifest.get('status') != 'OPENING_GAME_RESEARCH_EXPORT'
            or manifest.get('testUnscored') is not True
            or manifest.get('historyPolicy') != 'expanding_earlier_only'
            or manifest.get('historyLagDays') != 1):
        raise ValueError('Requires the reviewed earlier-only opening-game export')
    for name in ARTIFACTS:
        if sha(path / name) != manifest['artifacts'].get(name):
            raise ValueError('Input hash mismatch: ' + name)
    return manifest


def load(path):
    manifest = verify(path)
    parts = json.loads((path / 'splits.json').read_text(encoding='utf-8'))
    all_ids = [g for ids in parts.values() for g in ids]
    if len(all_ids) != len(set(all_ids)):
        raise ValueError('Overlapping split membership')
    bounds = [datetime.fromisoformat(manifest[k]) for k in ('trainingStart', 'validationStart', 'testStart')]
    if not bounds[0] < bounds[1] < bounds[2] <= datetime(2026, 1, 1):
        raise ValueError('Invalid or unsealed test boundary')
    contexts, labels = index_rows(path, 'contexts'), index_rows(path, 'labels')
    if contexts.keys() != labels.keys() or not contexts:
        raise ValueError('Context/label join mismatch')
    snapshot_cases = defaultdict(list)
    by_game = defaultdict(list)
    for key, c in contexts.items():
        split, game_id = c['split'], c['gameId']
        label = labels[key]
        if split not in ('training', 'validation') or game_id not in parts[split] or label['split'] != split:
            raise ValueError('Invalid case split or reserved-test membership')
        day = datetime.fromisoformat(c['date'])
        start, stop = (bounds[0], bounds[1]) if split == 'training' else (bounds[1], bounds[2])
        if not start <= day < stop - timedelta(days=7):
            raise ValueError('Case violates time partition/embargo')
        if c.get('protocol') != 'publisher-order-opening-game-v2' or c.get('poolSource') != 'pro_history':
            raise ValueError('Unsupported context contract')
        if not isinstance(label['championId'], str) or not label['championId'] or label['caseWeight'] != .1:
            raise ValueError('Invalid target/weight')
        snapshot_cases[c['snapshotId']].append(c)
        by_game[game_id].append(c)
    if any(len(cs) != 10 or len({c['actionIndex'] for c in cs}) != 10 for cs in by_game.values()):
        raise ValueError('Expected all ten distinct pick decisions per game')
    seen_snapshots = set()
    for s in rows(path, 'snapshots'):
        sid = s['snapshotId']
        if sid in seen_snapshots or sid not in snapshot_cases:
            raise ValueError('Duplicate or unreferenced snapshot')
        seen_snapshots.add(sid)
        cutoff = datetime.fromisoformat(s['exclusiveCutoff'])
        source_ids = set(s['sourceGameIds'])
        if source_ids.intersection(parts['test']):
            raise ValueError('Reserved-test history in snapshot')
        if s['latestObservation'] and datetime.fromisoformat(s['latestObservation']) >= cutoff:
            raise ValueError('Snapshot observation violates cutoff')
        for c in snapshot_cases[sid]:
            expected = datetime.fromisoformat(c['date'][:10]) - timedelta(days=1)
            if cutoff != expected or c['gameId'] in source_ids:
                raise ValueError('Current/future game snapshot leakage')
    if seen_snapshots != snapshot_cases.keys():
        raise ValueError('Missing snapshot')
    cases = {}
    for f in rows(path, 'features'):
        key = f['caseId']
        if key in cases or key not in contexts:
            raise ValueError('Duplicate/unknown feature case')
        c = contexts[key]
        if f['split'] != c['split'] or f['snapshotId'] != c['snapshotId'] or f['poolPolicy'] != 'inferred':
            raise ValueError('Feature/context contract mismatch')
        candidates = sorted(f['candidates'], key=lambda r: r['championId'])
        ids = [r['championId'] for r in candidates]
        blocked = set(c['allyPicks'] + c['enemyPicks'] + c['bans'])
        if len(ids) != len(set(ids)) or set(ids) & blocked:
            raise ValueError('Duplicate or illegal candidate')
        x = np.array([vector(c, row) for row in candidates], dtype=float).reshape(-1, len(FEATURE_NAMES))
        target = labels[key]['championId']
        cases[key] = {'x': x, 'ids': ids, 'target': ids.index(target) if target in ids else None,
                      'weight': .1, 'split': c['split'], 'gameId': c['gameId']}
    if cases.keys() != contexts.keys():
        raise ValueError('Missing feature cases')
    if {c['split'] for c in cases.values()} != {'training', 'validation'}:
        raise ValueError('Both development partitions required')
    return manifest, contexts, labels, cases


def observation(ids, target, latency=0):
    return {'rank': ids.index(target) + 1 if target in ids else None,
            'count': len(ids), 'latencyMs': latency}


def measure(observations):
    n = len(observations)
    if not n:
        raise ValueError('Cannot measure empty cohort')
    ranks = [o['rank'] for o in observations]
    return {'cases': n, 'candidateCoverage': sum(r is not None for r in ranks) / n,
            **{f'top{k}Agreement': sum(r is not None and r <= k for r in ranks) / n for k in (1, 3, 5)},
            'mrr': sum(1 / r if r else 0 for r in ranks) / n,
            'abstentions': sum(o['count'] == 0 for o in observations),
            'latencyP95Ms': float(np.quantile([o['latencyMs'] for o in observations], .95))}


def comparisons(records, contexts):
    """Paired resampling of whole games, not ten falsely independent draft decisions."""
    result = {}
    for name in BASELINES:
        games = defaultdict(list)
        for key, o in records['ml'].items():
            a, b = o['rank'], records[name][key]['rank']
            games[contexts[key]['gameId']].append(float(a is not None and a <= 3) - float(b is not None and b <= 3))
        delta = np.array([np.mean(games[g]) for g in sorted(games)])
        rng = np.random.default_rng(1729)
        bootstrap = np.array([np.mean(rng.choice(delta, size=len(delta), replace=True)) for _ in range(2000)])
        result[name] = {'top3Delta': float(delta.mean()), 'wholeGames': len(delta),
                        'pairedGameBootstrap95': np.quantile(bootstrap, [.025, .975]).tolist()}
    return result


def run(dataset, output):
    if output.exists():
        raise FileExistsError(output)
    source_paths = [Path(__file__).with_name(n) for n in ('train_ranker.py', 'linear_ranker.py', 'ml_features.py')]
    source_hashes = {p.name: sha(p) for p in source_paths}
    input_manifest_hash = sha(dataset / 'manifest.json')
    manifest, contexts, labels, cases = load(dataset)
    training = [c for c in cases.values() if c['split'] == 'training']
    covered = Counter(c['gameId'] for c in training if c['target'] is not None and len(c['ids']) >= 2)
    # A missing target supplies no honest pairwise label; reweight remaining cases within
    # that game, and explicitly report completely uncovered games rather than fabricating targets.
    training = [{**c, 'weight': 1 / covered[c['gameId']] if covered[c['gameId']] else .1} for c in training]
    print(f"Fitting on {len(training)} training cases ({sum(covered.values())} with comparisons)", flush=True)
    started = perf_counter()
    model = fit(training)
    fit_seconds = perf_counter() - started
    model['featureNames'] = list(FEATURE_NAMES)
    # Exercise the exact JSON persistence boundary before producing any evaluation.
    model = json.loads(json.dumps(model, allow_nan=False))
    results = {s: {n: {} for n in ('ml',) + BASELINES} for s in ('training', 'validation')}
    predictions = []
    for key, c in cases.items():
        started = perf_counter()
        scores = score(model, c['x'])
        order = sorted(range(len(scores)), key=lambda i: (-scores[i], c['ids'][i]))
        latency = (perf_counter() - started) * 1000
        ids = [c['ids'][i] for i in order]
        results[c['split']]['ml'][key] = observation(ids, labels[key]['championId'], latency)
        predictions.append({'caseId': key, 'split': c['split'], 'signal': 'pro_pick_imitation',
                            'candidates': [{'championId': c['ids'][i], 'score': float(scores[i])} for i in order]})
    for row in rows(dataset, 'predictions'):
        key, name = row['caseId'], row['policy'] + '/' + row['variant']
        if key not in cases or name not in BASELINES or row['split'] != cases[key]['split']:
            raise ValueError('Unknown baseline comparison row')
        target = results[row['split']][name]
        if key in target:
            raise ValueError('Duplicate baseline row')
        ids = [c['championId'] for c in row['candidates']]
        target[key] = observation(ids, labels[key]['championId'])
    for split, methods in results.items():
        for records in methods.values():
            if records.keys() != methods['ml'].keys():
                raise ValueError('Incomplete matched baseline comparison')
    metrics = {s: {n: measure(list(r.values())) for n, r in methods.items()} for s, methods in results.items()}
    for methods in metrics.values():
        for name, metric in methods.items():
            if name != 'ml':
                metric.pop('latencyP95Ms')  # Exported baselines are not being timed again here.
    report = {'signal': 'pro_pick_imitation', 'testUnscored': True, 'metrics': metrics,
              'validationComparison': comparisons(results['validation'], contexts),
              'trainingMissingTargets': sum(c['target'] is None for c in training),
              'trainingCasesWithoutAlternatives': sum(len(c['ids']) < 2 for c in training),
              'trainingGamesWithoutComparisons': len({c['gameId'] for c in training} - set(covered)),
              'fitSeconds': fit_seconds, 'validationUsedForFitOrTuning': False,
              'limits': ['Imitates recorded pro picks, not optimal picks or win probability.',
                         'Opening-game, small deterministic development sample; not a production model.',
                         'Unknown pro capability is permissive; not a substitute for authoritative saved pools.',
                         'No enemy matchup/role/composition features; counts pool older patches and leagues.',
                         'Bootstrap groups by game, not verified series/team; uncertainty may be understated.',
                         'Fixed single configuration; no validation hyperparameter search.']}
    if verify(dataset) != manifest or sha(dataset / 'manifest.json') != input_manifest_hash:
        raise ValueError('Inputs changed during training')
    if any(sha(p) != source_hashes[p.name] for p in source_paths):
        raise ValueError('Implementation changed during training')
    output.mkdir(parents=True, exist_ok=False)
    write(output / 'model.json', model)
    write(output / 'schema.json', SCHEMA)
    write(output / 'report.json', report)
    with (output / 'predictions.jsonl.gz').open('wb') as raw:
        with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as f:
            for row in predictions:
                f.write((json.dumps(row, sort_keys=True, allow_nan=False) + '\n').encode())
    write(output / 'manifest.json', {'version': 1, 'signal': 'pro_pick_imitation', 'testUnscored': True,
          'datasetManifestSha256': input_manifest_hash, 'datasetArtifacts': manifest['artifacts'],
          'codeSha256': source_hashes, 'python': platform.python_version(), 'numpy': np.__version__,
          'artifacts': {p.name: sha(p) for p in sorted(output.iterdir()) if p.is_file()}})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    report = run(args.dataset, args.output)
    print(json.dumps({'output': str(args.output), 'validation': report['metrics']['validation']['ml']}, indent=2))


if __name__ == '__main__':
    main()
