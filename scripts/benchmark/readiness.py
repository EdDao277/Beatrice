"""One-shot, resumable 2026 final evaluation. Never imports a training entry point."""
import argparse
from collections import Counter
from datetime import datetime, timedelta
import gzip
import hashlib
import json
import os
from pathlib import Path
from time import perf_counter

os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('OMP_NUM_THREADS', '2')
import lightgbm as lgb
import numpy as np
from baseline import recommend
from compact_dataset import compact_case
from linear_ranker import score
from protocol import load_prepared, pick_cases
from recency_features import RecencyTable, extend
from temporal import EarlierHistory
from tree_ranker import tree_score
from scaled_train import sha, read, write, rows, measure, paired_comparison, cohort_keys, rank_observation

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data/oracle'
FINAL = DATA / 'final-2026-readiness'
MODEL_HASH = 'ea447cdced1aa541446c50ef03c2ed96f06ecd94e4f50fb50514f17d85964ec5'
METHODS = ('fixed', 'linear', 'tree', 'recency')


class FinalHistory:
    """Same frozen prevalence arithmetic, without weakening the training-only date guard."""
    def __init__(self, games):
        self.games = sorted(games, key=lambda g: (g['date'], g['gameId']))
        if len({g['gameId'] for g in games}) != len(games):
            raise ValueError('Duplicate history game')
        self.day, self.tables = None, {}

    def at(self, day, patch):
        when = datetime.fromisoformat(day)
        if when.tzinfo or when.time() != datetime.min.time() or (self.day and when < self.day):
            raise ValueError('Invalid or backwards history day')
        if when != self.day:
            self.tables = {}
        self.day = when
        if patch not in self.tables:
            cutoff = when - timedelta(days=1)
            earlier = [g for g in self.games if datetime.fromisoformat(g['date']) < cutoff]
            windows = []
            for days in (14, 30, None):
                selected = [g for g in earlier if (g['patch'] == patch if days is None else
                            datetime.fromisoformat(g['date']) >= cutoff - timedelta(days=days))]
                picks, bans = Counter(), Counter()
                for g in selected:
                    picks.update({c for t in g['teams'] for c in t['picks'] if c})
                    bans.update({c for t in g['teams'] for c in t['bans'] if c})
                windows.append((len(selected), picks, bans))
            self.tables[patch] = RecencyTable(windows, len(earlier))
        return self.tables[patch]


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def reserve(output, receipt):
    output.mkdir(parents=True, exist_ok=True)
    path = output / 'receipt.json'
    if path.exists():
        if read(path) != receipt:
            raise ValueError('Final-test receipt changed; cannot run or resume')
    else:
        with path.open('x', encoding='utf-8') as stream:
            json.dump(receipt, stream, sort_keys=True, indent=2)
    (output / 'games').mkdir(exist_ok=True)


def game_path(output, identity):
    return output / 'games' / (hashlib.sha256(identity.encode()).hexdigest() + '.json.gz')


def checkpoint(output, identity, value):
    path = game_path(output, identity)
    if path.exists():
        raise FileExistsError(path)
    payload = {'gameId': identity, 'sha256': hashlib.sha256(canonical(value)).hexdigest(), 'data': value}
    temporary = path.with_suffix('.pending')
    temporary.write_bytes(gzip.compress(canonical(payload), compresslevel=1, mtime=0))
    os.replace(temporary, path)


def restored(output, identity):
    payload = json.loads(gzip.decompress(game_path(output, identity).read_bytes()))
    if payload['gameId'] != identity or hashlib.sha256(canonical(payload['data'])).hexdigest() != payload['sha256']:
        raise ValueError('Corrupt final-test checkpoint')
    return payload['data']


def acceptance(comparisons):
    lower = lambda stage, metric: comparisons[stage][metric]['pairedGameBootstrap95'][0]
    checks = {'blindSuperiorToLinear': lower('blind', 'top3') > 0,
              'overallSuperiorToTree': lower('overall', 'top3') > 0,
              'lateTop3Noninferior': lower('late', 'top3') >= -.005,
              'lateMrrNoninferior': lower('late', 'mrr') >= -.005}
    return {**checks, 'passed': all(checks.values())}


def verify_hashes(folder, hashes):
    for name, expected in hashes.items():
        if Path(name).name != name or sha(folder / name) != expected:
            raise ValueError('Frozen artifact/source changed: ' + name)


def completed_report(output):
    complete = read(output / 'complete.json')
    verify_hashes(output, {'receipt.json': complete['receiptSha256'], 'report.json': complete['reportSha256']})
    verify_hashes(output / 'games', complete['checkpointHashes'])
    return read(output / 'report.json')


def missing_counts(x):
    return {window + '_' + kind: int(x[:, offset + j].sum())
            for window, offset in (('14d', 33), ('30d', 41), ('patch', 49))
            for kind, j in (('window_missing', 6), ('champion_unseen', 7))}


def final_test():
    output = FINAL
    compact = DATA / 'compact-2026-09-11-resumable'
    frozen = DATA / 'scaled-2026-09-12-reviewed'
    current = DATA / 'blind-2026-09-14-reviewed'
    prepared = DATA / 'prepared-2026-09-08-reviewed'
    protocol = ROOT / 'docs/offline-readiness-protocol.md'
    if sha(current / 'recency_tree.txt') != MODEL_HASH:
        raise ValueError('Not the approved frozen recency model')
    for folder in (current, frozen):
        manifest = read(folder / 'manifest.json')
        verify_hashes(folder, manifest['artifacts'])
        verify_hashes(Path(__file__).parent, manifest['codeSha256'])
    cm = read(compact / 'manifest.json')
    fm, rm = read(frozen / 'manifest.json'), read(current / 'manifest.json')
    if (fm['datasetManifestSha256'] != sha(compact / 'manifest.json') or
            rm['datasetManifestSha256'] != sha(compact / 'manifest.json') or
            rm['frozenManifestSha256'] != sha(frozen / 'manifest.json')):
        raise ValueError('Frozen lineage mismatch')
    verify_hashes(Path(__file__).parent, cm['codeSha256'])
    for name in ('source-audit.jsonl.gz', 'splits.json'):
        if sha(compact / name) != cm['artifacts'][name]:
            raise ValueError('Frozen audit/splits changed')
    audit = {r['gameId']: r for r in rows(compact, 'source-audit')}
    test_ids = read(compact / 'splits.json')['test']
    selected = sorted((i for i in test_ids if audit[i]['eligible']),
                      key=lambda i: (audit[i]['sourceSeries']['date'], i))
    code = ('readiness.py', 'recency_features.py', 'ml_features.py', 'baseline.py',
            'compact_dataset.py', 'temporal.py', 'protocol.py', 'tree_ranker.py',
            'linear_ranker.py', 'scaled_train.py', 'evaluate.py')
    receipt = {'modelSha256': MODEL_HASH, 'protocolSha256': sha(protocol),
               'preparedGamesSha256': cm['input']['gamesSha256'],
               'preparedReportSha256': cm['input']['reportSha256'],
               'compactManifestSha256': sha(compact / 'manifest.json'),
               'frozenManifestSha256': sha(frozen / 'manifest.json'),
               'recencyManifestSha256': sha(current / 'manifest.json'),
               'codeSha256': {n: sha(Path(__file__).with_name(n)) for n in code},
               'games': selected, 'seed': 1729, 'replicates': 2000,
               'history': 'prequential-exclusive-one-day-lag-no-parameter-fitting',
               'authorization': 'User approved offline production readiness final test'}
    reserve(output, receipt)
    if (output / 'complete.json').exists():
        print('Final test already completed. Reusing saved report; no evaluation repeated.', flush=True)
        return completed_report(output)
    print(f'Final test reserved: {len(selected)} eligible opening games; no training.', flush=True)
    games, provenance = load_prepared(prepared)
    if provenance['gamesSha256'] != receipt['preparedGamesSha256'] or provenance['reportSha256'] != receipt['preparedReportSha256']:
        raise ValueError('Prepared batch differs from frozen input')
    by_id = {g['gameId']: g for g in games}
    if not selected or any(by_id[i]['date'] < '2026-01-01' for i in selected):
        raise ValueError('Invalid final-test population')
    temporal = EarlierHistory(games)
    recent = FinalHistory([g for g in games if audit[g['gameId']]['eligible']])
    models = {'linear': read(frozen / 'linear.json'), 'tree': lgb.Booster(model_file=str(frozen / 'tree.txt')),
              'recency': lgb.Booster(model_file=str(current / 'recency_tree.txt'))}
    started = perf_counter()
    for number, identity in enumerate(selected, 1):
        if game_path(output, identity).exists():
            restored(output, identity)
            continue
        game = by_id[identity]
        snapshot = temporal.advance(game['date'][:10])
        table = recent.at(game['date'][:10], game['patch'])
        observations = []
        for context, label in pick_cases(game):
            context.update(split='test', snapshotId=snapshot['snapshotId'])
            start = perf_counter()
            result = recommend(context, temporal.history, 'pool_rules_stats', pool_policy='inferred')
            features, evidence, checks = compact_case(context, result, temporal.history)
            x = np.asarray(features['x'], dtype=np.float32).reshape(-1, 33)
            extended = extend(x, features['championIds'], context, table)
            feature_ms = (perf_counter() - start) * 1000
            records = {}
            ids = features['championIds']
            for name in METHODS:
                start = perf_counter()
                values = (features['baselineScores']['pool_rules_stats'] if name == 'fixed' else
                          score(models[name], x) if name == 'linear' else
                          tree_score(models[name], extended if name == 'recency' else x))
                order = sorted(range(len(ids)), key=lambda i: (-values[i], ids[i]))
                ranked = [ids[i] for i in order]
                records[name] = {**rank_observation(ranked, label['championId'], (perf_counter() - start) * 1000),
                                 'top5': ranked[:5]}
            target = ids.index(label['championId']) if label['championId'] in ids else None
            support = round(float(np.expm1(float(x[target, 4])))) if target is not None else 0
            observations.append({'caseId': context['caseId'], 'gameId': identity,
                'stage': cohort_keys(context)[0].split('/')[1], 'patch': game['patch'],
                'target': label['championId'], 'support': support, 'records': records,
                'featureMs': feature_ms, 'checks': dict(checks),
                'missing': missing_counts(extended),
                'sourceCutoff': snapshot['exclusiveCutoff'], 'latestObservation': snapshot['latestObservation']})
        if len(observations) != 10:
            raise ValueError('Incomplete test game')
        checkpoint(output, identity, observations)
        if number % 25 == 0:
            print(f'Final-test checkpoint {number}/{len(selected)}; {perf_counter()-started:.0f}s this invocation', flush=True)
    observations = [r for identity in selected for r in restored(output, identity)]
    results = {n: {r['caseId']: r['records'][n] for r in observations} for n in METHODS}
    contexts = {r['caseId']: {'gameId': r['gameId']} for r in observations}
    groups = {'overall': observations, **{s: [r for r in observations if r['stage'] == s] for s in ('blind', 'early', 'late')},
              'rare': [r for r in observations if 0 < r['support'] < 30],
              'new_or_absent': [r for r in observations if r['support'] == 0]}
    metrics = {s: {n: measure([r['records'][n] for r in group]) if group else {'cases': 0} for n in METHODS}
               for s, group in groups.items()}
    comparisons = {}
    for stage, reference in (('blind', 'linear'), ('overall', 'tree'), ('late', 'tree')):
        keys = [r['caseId'] for r in groups[stage]]
        comparisons[stage] = paired_comparison({k: results['recency'][k] for k in keys},
                                               {k: results[reference][k] for k in keys}, contexts)
    total_candidates = sum(r['records']['recency']['count'] for r in observations)
    report = {'status': 'FINAL_TEST_COMPLETE_NO_TUNING', 'games': len(selected), 'metrics': metrics,
              'comparisons': comparisons, 'acceptance': acceptance(comparisons),
              'candidateMissingRates': {w: sum(r['missing'][w] for r in observations) / total_candidates for w in observations[0]['missing']},
              'candidateChecks': sum(r['checks']['candidateLegalityChecks'] for r in observations),
              'featureLatencyP95Ms': float(np.quantile([r['featureMs'] for r in observations], .95)),
              'unsupportedTestGames': len(test_ids)-len(selected), 'retrained': False,
              'limits': ['Prequential test: earlier test outcomes update history after lag, never parameters.',
                         'Game bootstrap does not fully account for repeated teams/series.',
                         'Professional choice imitation is not saved-team pick quality.']}
    if any(sha(Path(__file__).with_name(n)) != h for n, h in receipt['codeSha256'].items()) or sha(protocol) != receipt['protocolSha256']:
        raise ValueError('Code/protocol changed during final test; stop without tuning')
    write(output / 'report.json', report)
    write(output / 'complete.json', {'receiptSha256': sha(output / 'receipt.json'),
          'reportSha256': sha(output / 'report.json'), 'checkpointHashes': {
              game_path(output, i).name: sha(game_path(output, i)) for i in selected}})
    print(json.dumps({'acceptance': report['acceptance'], 'games': len(selected)}, indent=2), flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--final', action='store_true', required=True)
    parser.parse_args()
    final_test()
