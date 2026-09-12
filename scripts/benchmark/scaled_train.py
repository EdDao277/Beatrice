"""Fixed CPU experiments on a verified compact pro-pick export; no test or live inputs."""
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

os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('OMP_NUM_THREADS', '2')
import lightgbm as lgb
import numpy as np

from linear_ranker import CONFIG, fit, score, transformed
from ml_features import FEATURE_NAMES, SCHEMA
from tree_ranker import PARAMETERS, ROUNDS, fit_tree, tree_score

VARIANTS = ('pool', 'pool_rules', 'pool_rules_stats')
BASELINES = tuple('inferred/' + name for name in VARIANTS)
METHODS = ('linear', 'tree', *BASELINES)
ARTIFACTS = ('contexts.jsonl.gz', 'labels.jsonl.gz', 'features.jsonl.gz', 'evidence.jsonl.gz',
             'snapshots.jsonl.gz', 'source-audit.jsonl.gz', 'exclusions.jsonl.gz',
             'timings.jsonl.gz', 'feature-schema.json', 'splits.json', 'report.json')
CODE = ('scaled_train.py', 'linear_ranker.py', 'tree_ranker.py', 'ml_features.py')
BOOTSTRAP_REPLICATES = 2000


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def rows(path, name):
    with gzip.open(path / (name + '.jsonl.gz'), 'rt', encoding='utf-8') as stream:
        for row in stream:
            yield json.loads(row)


def index(path, name, key='caseId'):
    result = {}
    for row in rows(path, name):
        identity = row[key]
        if identity in result:
            raise ValueError('Duplicate identity in ' + name)
        result[identity] = row
    return result


def verify(path):
    manifest = read(path / 'manifest.json')
    if (manifest.get('version') != 3
            or manifest.get('status') != 'COMPACT_OPENING_GAME_RESEARCH_EXPORT'
            or manifest.get('testUnscored') is not True
            or manifest.get('historyPolicy') != 'expanding_earlier_only'
            or manifest.get('historyLagDays') != 1 or manifest.get('labelEmbargoDays') != 7
            or manifest.get('sourceInputsVerifiedAfterExport') is not True):
        raise ValueError('Requires verified compact earlier-only opening-game export')
    if set(manifest['artifacts']) != set(ARTIFACTS):
        raise ValueError('Unexpected compact artifact contract')
    for name in ARTIFACTS:
        if sha(path / name) != manifest['artifacts'][name]:
            raise ValueError('Input hash mismatch: ' + name)
    schema = read(path / 'feature-schema.json')
    if (schema.get('features') != list(FEATURE_NAMES) or schema.get('version') != SCHEMA['version']
            or schema.get('signal') != 'pro_pick_imitation' or schema.get('datasetVersion') != 3
            or schema.get('baselines', {}).get('variants') != list(VARIANTS)):
        raise ValueError('Feature schema mismatch')
    return manifest


def validate_contexts(path, manifest):
    parts = read(path / 'splits.json')
    if set(parts) != {'warmup', 'training', 'validation', 'embargo', 'test'}:
        raise ValueError('Unexpected split names')
    all_ids = [game for group in parts.values() for game in group]
    if len(all_ids) != len(set(all_ids)):
        raise ValueError('Overlapping split membership')
    members = {name: set(ids) for name, ids in parts.items()}
    bounds = [datetime.fromisoformat(manifest[key]) for key in ('trainingStart', 'validationStart', 'testStart')]
    if not bounds[0] < bounds[1] < bounds[2] <= datetime(2026, 1, 1):
        raise ValueError('Invalid or unsealed test boundary')
    contexts, labels = index(path, 'contexts'), index(path, 'labels')
    if not contexts or contexts.keys() != labels.keys():
        raise ValueError('Context/label join mismatch')
    games, referenced = defaultdict(list), defaultdict(list)
    for key, context in contexts.items():
        split, game_id, label = context['split'], context['gameId'], labels[key]
        if split not in ('training', 'validation') or game_id not in members[split] or label['split'] != split:
            raise ValueError('Invalid case split or reserved-test membership')
        start, stop = (bounds[0], bounds[1]) if split == 'training' else (bounds[1], bounds[2])
        if not start <= datetime.fromisoformat(context['date']) < stop - timedelta(days=7):
            raise ValueError('Case violates time partition/embargo')
        if (context.get('protocol') != 'publisher-order-opening-game-v2'
                or context.get('poolSource') != 'pro_history' or len(context['playerIds']) != 5
                or len(set(context['playerIds'])) != 5):
            raise ValueError('Unsupported context contract')
        if not isinstance(label['championId'], str) or not label['championId'] or label['caseWeight'] != .1:
            raise ValueError('Invalid target/weight')
        games[game_id].append(context)
        referenced[context['snapshotId']].append(context)
    if any(len(group) != 10 or len({c['actionIndex'] for c in group}) != 10 for group in games.values()):
        raise ValueError('Expected all ten distinct decisions per game')
    audit = index(path, 'source-audit', 'gameId')
    if set(audit) != set(all_ids):
        raise ValueError('Source audit/split population mismatch')
    for game_id, group in games.items():
        source = audit[game_id]
        if (not source['eligible'] or source['gameNumber'] != 1 or source['reasons']
                or any(c['seriesCandidateId'] != source['seriesCandidateId'] for c in group)):
            raise ValueError('Unsupported source game or series join')
    seen, history_ids = set(), set()
    temporal_checks = Counter(snapshots=0, sourceMembershipChecks=0, sourceTimestampChecks=0,
                              sourceTimestampsUnavailable=0, currentOrFutureViolations=0)
    for snapshot in rows(path, 'snapshots'):
        sid = snapshot['snapshotId']
        if sid in seen or sid not in referenced:
            raise ValueError('Duplicate or unreferenced snapshot')
        unsigned = {key: value for key, value in snapshot.items() if key != 'snapshotId'}
        if hashlib.sha256(json.dumps(unsigned, sort_keys=True).encode()).hexdigest() != sid:
            raise ValueError('Snapshot identity does not match its content')
        seen.add(sid)
        cutoff = datetime.fromisoformat(snapshot['exclusiveCutoff'])
        source_ids = set(snapshot['sourceGameIds'])
        if len(source_ids) != len(snapshot['sourceGameIds']) or not source_ids <= set(audit):
            raise ValueError('Duplicate/unknown snapshot source')
        if source_ids & members['test']:
            raise ValueError('Reserved-test history in snapshot')
        latest = snapshot['latestObservation']
        if latest and datetime.fromisoformat(latest) >= cutoff:
            raise ValueError('Snapshot observation violates cutoff')
        for game_id in source_ids:
            source = audit[game_id]['sourceSeries']
            if source is None:
                temporal_checks['sourceTimestampsUnavailable'] += 1
            elif datetime.fromisoformat(source['date']) >= cutoff:
                raise ValueError('Future source game in snapshot')
            else:
                temporal_checks['sourceTimestampChecks'] += 1
        for context in referenced[sid]:
            expected = datetime.fromisoformat(context['date'][:10]) - timedelta(days=1)
            if (cutoff != expected or context['gameId'] in source_ids
                    or context['evidenceThrough'] != latest):
                raise ValueError('Current/future game snapshot leakage')
        history_ids.update(source_ids)
        temporal_checks.update(snapshots=1, sourceMembershipChecks=len(source_ids))
    if seen != referenced.keys():
        raise ValueError('Missing snapshot')
    temporal_checks['uniqueHistoricalSourceGames'] = len(history_ids)
    temporal_checks['auditedSourceGames'] = len(audit)
    temporal_checks['exportedOpeningGames'] = len(games)
    return contexts, labels, temporal_checks


def load(path):
    """Keep float32 candidate matrices in memory; large evidence remains a streamed artifact."""
    print('Verifying compact input hashes and temporal boundaries', flush=True)
    manifest = verify(path)
    contexts, labels, temporal_checks = validate_contexts(path, manifest)
    cases, checks = {}, Counter(candidateLegalityChecks=0, illegalCandidates=0)
    for row in rows(path, 'features'):
        key = row['caseId']
        if key in cases or key not in contexts:
            raise ValueError('Duplicate/unknown feature case')
        context, ids = contexts[key], row['championIds']
        if (row['split'] != context['split'] or row['snapshotId'] != context['snapshotId']
                or row['poolPolicy'] != 'inferred'):
            raise ValueError('Feature/context contract mismatch')
        if (not all(isinstance(champion, str) and champion for champion in ids)
                or ids != sorted(set(ids))
                or set(ids) & set(context['allyPicks'] + context['enemyPicks'] + context['bans'])):
            raise ValueError('Duplicate, unsorted or illegal candidate')
        raw = np.asarray(row['x'], dtype=np.float32)
        if not len(ids) and raw.shape == (0,):
            raw = raw.reshape(0, len(FEATURE_NAMES))
        if raw.shape != (len(ids), len(FEATURE_NAMES)) or not np.isfinite(raw).all():
            raise ValueError('Invalid numeric feature matrix')
        if (set(row['baselineScores']) != set(VARIANTS) or set(row['baselineRanks']) != set(VARIANTS)
                or bool(ids) == bool(row['abstention'])):
            raise ValueError('Incomplete baseline or abstention contract')
        scores, ranks = {}, {}
        for variant in VARIANTS:
            values, positions = row['baselineScores'][variant], row['baselineRanks'][variant]
            if (len(values) != len(ids) or not all(np.isfinite(values)) or len(positions) != len(ids)
                    or any(type(rank) is not int for rank in positions)):
                raise ValueError('Baseline/candidate alignment mismatch')
            expected = [0] * len(ids)
            for rank, candidate in enumerate(sorted(range(len(ids)), key=lambda i: (-values[i], ids[i])), 1):
                expected[candidate] = rank
            if positions != expected:
                raise ValueError('Baseline ranks disagree with scores and tie policy')
            scores['inferred/' + variant] = np.asarray(values, dtype=np.float64)
            ranks['inferred/' + variant] = np.asarray(positions, dtype=np.int16)
        target = labels[key]['championId']
        cases[key] = {'x': raw, 'ids': ids, 'target': ids.index(target) if target in ids else None,
                      'weight': .1, 'split': context['split'], 'gameId': context['gameId'],
                      'baselineScores': scores, 'baselineRanks': ranks, 'abstention': row['abstention']}
        checks['candidateLegalityChecks'] += len(ids)
        if len(cases) % 10000 == 0:
            print(f'Loaded {len(cases)} compact cases', flush=True)
    if cases.keys() != contexts.keys() or {c['split'] for c in cases.values()} != {'training', 'validation'}:
        raise ValueError('Missing feature case or development partition')
    report = read(path / 'report.json')
    exported_checks = report['checks']
    if (report.get('status') != manifest['status'] or exported_checks['cases'] != len(cases)
            or exported_checks['candidateLegalityChecks'] != checks['candidateLegalityChecks']
            or exported_checks['lineupCompletionChecks'] != checks['candidateLegalityChecks']
            or exported_checks['legalityViolations'] != 0 or exported_checks['impossibleLineupCandidates'] != 0):
        raise ValueError('Incomplete or failed exported legality/lineup checks')
    quality, seen = {split: Counter() for split in ('training', 'validation')}, set()
    for row in rows(path, 'evidence'):
        key = row['caseId']
        if key in seen or key not in cases:
            raise ValueError('Duplicate/unknown evidence case')
        case = cases[key]
        if [candidate['championId'] for candidate in row['candidates']] != case['ids']:
            raise ValueError('Evidence/candidate order mismatch')
        seen.add(key)
        for candidate in row['candidates']:
            entry = candidate['evidenceQuality']
            quality[case['split']].update({key: int(value) for key, value in entry.items()})
            quality[case['split']]['candidates'] += 1
            quality[case['split']]['missingPlayerHistoryCandidates'] += entry['observedPlayerCount'] == 0
        if len(seen) % 10000 == 0:
            print(f'Checked evidence alignment for {len(seen)} cases', flush=True)
    if seen != cases.keys() or any(dict(quality[s]) != report['evidenceQuality'][s] for s in quality):
        raise ValueError('Incomplete evidence joins or evidence quality counts')
    timings = index(path, 'timings')
    if timings.keys() != cases.keys():
        raise ValueError('Incomplete timing/context join')
    for key, timing in timings.items():
        if (timing['split'] != cases[key]['split']
                or any(not np.isfinite(timing[n]) or timing[n] < 0 for n in ('scorerMs', 'featuresAndChecksMs'))):
            raise ValueError('Invalid timing row')
    return {'manifest': manifest, 'contexts': contexts, 'labels': labels, 'cases': cases,
            'exportReport': report, 'temporalChecks': dict(temporal_checks),
            'evidenceQuality': quality, 'timings': timings}


def measure(observations):
    if not observations:
        raise ValueError('Cannot measure an empty cohort')
    n = len(observations)
    covered = sum(row['rank'] is not None for row in observations)
    abstentions = sum(row['count'] == 0 for row in observations)
    times = [row['latencyMs'] for row in observations]
    hits = {k: sum(row['rank'] is not None and row['rank'] <= k for row in observations) for k in (1, 3, 5)}
    return {'cases': n, 'candidateCoverage': covered / n, 'targetAbsentCases': n - covered,
            'targetAbsentRate': (n - covered) / n, 'abstentions': abstentions, 'abstentionRate': abstentions / n,
            **{f'top{k}Agreement': value / n for k, value in hits.items()},
            'top3AgreementWhenCovered': hits[3] / covered if covered else None,
            'mrr': sum(1 / row['rank'] if row['rank'] else 0 for row in observations) / n,
            'latencyMeanMs': float(np.mean(times)), 'latencyP95Ms': float(np.quantile(times, .95))}


def paired_comparison(left, right, contexts):
    """Use one resampling draw for all metrics and keep every game's decisions together."""
    if not left or left.keys() != right.keys():
        raise ValueError('Comparisons require identical nonempty case sets')
    games = defaultdict(list)
    for key in left:
        a, b = left[key]['rank'], right[key]['rank']
        games[contexts[key]['gameId']].append([
            *[float(a is not None and a <= k) - float(b is not None and b <= k) for k in (1, 3, 5)],
            (1 / a if a else 0) - (1 / b if b else 0)])
    if len({len(values) for values in games.values()}) != 1:
        raise ValueError('Game bootstrap requires the same number of decisions per whole game')
    delta = np.asarray([np.mean(games[key], axis=0) for key in sorted(games)])
    rng = np.random.default_rng(1729)
    draws = np.empty((BOOTSTRAP_REPLICATES, 4))
    # Batching limits temporary memory even with thousands of validation games.
    for start in range(0, BOOTSTRAP_REPLICATES, 100):
        size = min(100, BOOTSTRAP_REPLICATES - start)
        draw = rng.integers(0, len(delta), size=(size, len(delta)))
        draws[start:start + size] = delta[draw].mean(axis=1)
    return {'wholeGames': len(games), 'cases': len(left), 'replicates': BOOTSTRAP_REPLICATES,
            'seed': 1729, **{name: {'delta': float(delta[:, i].mean()),
                'pairedGameBootstrap95': np.quantile(draws[:, i], [.025, .975]).tolist()}
                for i, name in enumerate(('top1', 'top3', 'top5', 'mrr'))}}


def cohort_keys(context):
    allies, enemies = len(context['allyPicks']), len(context['enemyPicks'])
    stage = 'blind' if allies + enemies == 0 else 'late' if allies >= 3 else 'early'
    # Final roles are deliberately unavailable at prediction time for this schema.
    return ('stage/' + stage, 'patch/' + (context['patch'] or 'unknown'),
            'visiblePicks/' + str(allies + enemies), 'roles/unknown')


def rank_observation(ids, target, latency):
    return {'rank': ids.index(target) + 1 if target in ids else None,
            'count': len(ids), 'latencyMs': latency}


def summary_quality(counts):
    n = counts['candidates']
    result = dict(counts)
    for key in ('metaMissing', 'metaSmallSample', 'pairMissing', 'missingPlayerHistoryCandidates'):
        result[key + 'Rate'] = counts[key] / n if n else None
    result['pairObservationCoverage'] = counts['pairObservedCount'] / counts['pairPossibleCount'] if counts['pairPossibleCount'] else None
    result['pairSmallSampleRateAmongObserved'] = counts['pairSmallSampleCount'] / counts['pairObservedCount'] if counts['pairObservedCount'] else None
    return result


def retain_sample(samples, category, row, priority, limit=8):
    collection = samples[category]
    collection.append((priority, row['caseId'], row))
    collection.sort(key=lambda item: (item[0], item[1]))
    del collection[limit:]


def collect_samples(samples, key, case, context, rankings, labels, model, baseline):
    chosen = rankings[model]
    target = labels[key]['championId']
    rank = chosen['championIds'].index(target) + 1 if target in chosen['championIds'] else None
    comparison = rankings[baseline]['championIds']
    baseline_rank = comparison.index(target) + 1 if target in comparison else None
    margin = chosen['scores'][0] - chosen['scores'][1] if len(chosen['scores']) > 1 else None
    row = {'caseId': key, 'gameId': context['gameId'], 'patch': context['patch'],
           'cohorts': cohort_keys(context), 'targetChampionId': target, 'targetRank': rank,
           'baselineTargetRank': baseline_rank, 'learnedModel': model, 'comparisonBaseline': baseline,
           'topTwoScoreMargin': margin, 'marginMeaning': 'uncalibrated score difference; not confidence',
           'topCandidates': chosen['championIds'][:5], 'baselineTopCandidates': comparison[:5],
           'candidateCount': len(case['ids']), 'snapshotId': context['snapshotId'],
           'evidenceThrough': context['evidenceThrough'], 'roles': 'unknown at prediction time'}
    if rank is not None and rank <= 3 and baseline_rank is not None and baseline_rank > 10:
        retain_sample(samples, 'strong_ml_wins', row, -(baseline_rank - rank))
    if baseline_rank is not None and baseline_rank <= 3 and rank is not None and rank > 10:
        retain_sample(samples, 'baseline_wins', row, -(rank - baseline_rank))
    if rank is not None and baseline_rank is not None and rank > 5 and baseline_rank > 5:
        retain_sample(samples, 'shared_failures', row, -min(rank, baseline_rank))
    if margin is not None:
        retain_sample(samples, 'small_margin', row, margin)
    if rank is None:
        retain_sample(samples, 'missing_target', row, key)
    else:
        values = case['x'][case['target']]
        if values[2] > .2:
            retain_sample(samples, 'flex_uncertain', row, -float(values[2]))
        if values[4] < np.log1p(30):
            retain_sample(samples, 'rare_picks', row, float(values[4]))


def attach_sample_evidence(dataset, samples, cases, linear):
    grouped = {key: [row for _, _, row in values] for key, values in samples.items()}
    lookup = defaultdict(list)
    for examples in grouped.values():
        for row in examples:
            row['evidenceReference'] = {'artifact': 'evidence.jsonl.gz', 'caseId': row['caseId']}
            lookup[row['caseId']].append(row)
    for evidence in rows(dataset, 'evidence'):
        key = evidence['caseId']
        if key not in lookup:
            continue
        by_id = {candidate['championId']: candidate for candidate in evidence['candidates']}
        for example in lookup[key]:
            wanted = set(example['topCandidates'] + example['baselineTopCandidates'] + [example['targetChampionId']])
            example['evidence'] = [by_id[champion] for champion in sorted(wanted & by_id.keys())]
            if example['learnedModel'] == 'linear' and example['topCandidates']:
                champion = example['topCandidates'][0]
                i = cases[key]['ids'].index(champion)
                contribution = transformed(linear, cases[key]['x'][i:i + 1])[0] * np.asarray(linear['weights'])
                order = np.argsort(-np.abs(contribution))[:5]
                example['topCandidateLinearContributions'] = [
                    {'feature': FEATURE_NAMES[int(j)], 'contribution': float(contribution[j])} for j in order]
    return {'selection': 'Deterministic extreme examples; illustrative, not representative frequencies.',
            'flexMeaning': 'Target previously observed for multiple roster players; no final role labels are used.',
            'rareMeaning': 'Target has fewer than 30 earlier global observations.',
            'missingTargetMeaning': 'Target absent from earlier legal candidate set; never inserted for scoring.',
            'categories': grouped}


def run(dataset, output):
    if output.exists():
        raise FileExistsError(output)
    started = perf_counter()
    source_hashes = {name: sha(Path(__file__).with_name(name)) for name in CODE}
    manifest_hash = sha(dataset / 'manifest.json')
    loaded = load(dataset)
    manifest, cases, contexts, labels = (loaded[name] for name in ('manifest', 'cases', 'contexts', 'labels'))
    load_seconds = perf_counter() - started
    training = [case for case in cases.values() if case['split'] == 'training']
    covered = Counter(case['gameId'] for case in training if case['target'] is not None and len(case['ids']) >= 2)
    # Give every usable game total mass one even when some targets are missing.
    training = [{**case, 'weight': 1 / covered[case['gameId']] if covered[case['gameId']] else .1} for case in training]
    print(f'Fitting linear model on {len(training)} training cases; {sum(covered.values())} usable comparisons', flush=True)
    start = perf_counter()
    linear = fit(training)
    linear['featureNames'] = list(FEATURE_NAMES)
    fit_seconds = {'linear': perf_counter() - start}
    print('Fitting fixed 100-round, 15-leaf CPU LambdaRank model', flush=True)
    start = perf_counter()
    tree = fit_tree(training)
    fit_seconds['tree'] = perf_counter() - start
    output.mkdir(parents=True, exist_ok=False)
    write(output / 'linear.json', linear)
    # LightGBM stores byte offsets for its trees. Windows CRLF translation would
    # invalidate those offsets and can crash the native model loader on reload.
    (output / 'tree.txt').write_bytes(tree.encode('utf-8'))
    write(output / 'schema.json', {**SCHEMA, 'datasetVersion': 3,
          'matrixDtype': 'float32', 'treeNormalization': 'none; raw named numeric features'})
    reloaded_linear = read(output / 'linear.json')
    original_tree = lgb.Booster(model_str=tree)
    reloaded_tree = lgb.Booster(model_file=str(output / 'tree.txt'))
    # Verify the exact saved bytes on all distinct matrices during evaluation below.
    results = {split: {name: {} for name in METHODS} for split in ('training', 'validation')}
    evaluation_start = perf_counter()
    with (output / 'predictions.jsonl.gz').open('wb') as raw:
        with gzip.GzipFile(filename='', fileobj=raw, mode='wb', compresslevel=1, mtime=0) as stream:
            for count, (key, case) in enumerate(cases.items(), 1):
                rankings = {}
                for name in METHODS:
                    start = perf_counter()
                    scores = (score(reloaded_linear, case['x']) if name == 'linear' else
                              tree_score(reloaded_tree, case['x']) if name == 'tree' else case['baselineScores'][name])
                    order = sorted(range(len(case['ids'])), key=lambda i: (-scores[i], case['ids'][i]))
                    latency = (perf_counter() - start) * 1000
                    ids = [case['ids'][i] for i in order]
                    if name in ('linear', 'tree'):
                        original = score(linear, case['x']) if name == 'linear' else tree_score(original_tree, case['x'])
                        if not np.array_equal(scores, original):
                            raise ValueError('Persisted model changed predictions')
                    results[case['split']][name][key] = rank_observation(ids, labels[key]['championId'], latency)
                    rankings[name] = {'championIds': ids, 'scores': [float(scores[i]) for i in order]}
                row = {'caseId': key, 'split': case['split'], 'signal': 'pro_pick_imitation',
                       'candidateIds': case['ids'], 'abstention': case['abstention'], 'rankings': rankings,
                       'evidenceReference': {'artifact': 'evidence.jsonl.gz', 'caseId': key,
                                             'snapshotId': contexts[key]['snapshotId']}}
                stream.write((json.dumps(row, separators=(',', ':'), allow_nan=False) + '\n').encode())
                if count % 10000 == 0:
                    print(f'Evaluated and reloaded both models on {count} matched cases', flush=True)
    evaluation_seconds = perf_counter() - evaluation_start
    metrics = {split: {name: measure(list(records.values())) for name, records in methods.items()}
               for split, methods in results.items()}
    validation = metrics['validation']
    winner = max(('linear', 'tree'), key=lambda name: (validation[name]['top3Agreement'], validation[name]['mrr'], name == 'linear'))
    best_baseline = max(BASELINES, key=lambda name: (validation[name]['top3Agreement'], validation[name]['mrr'], name))
    comparisons = {model: {baseline: paired_comparison(results['validation'][model], results['validation'][baseline], contexts)
                          for baseline in BASELINES} for model in ('linear', 'tree')}
    comparisons['tree']['linear'] = paired_comparison(results['validation']['tree'], results['validation']['linear'], contexts)
    interval = comparisons[winner][best_baseline]['top3']['pairedGameBootstrap95']
    eligible = interval[0] > 0
    selected = {'modelType': winner, 'modelFile': 'linear.json' if winner == 'linear' else 'tree.txt',
                'signal': 'pro_pick_imitation', 'scoreMeaning': 'uncalibrated ranking preference',
                'selectionMetric': 'validation top3 agreement; MRR then linear simplicity breaks ties',
                'bestBaseline': best_baseline, 'deploymentEligible': eligible, 'offlineOnly': True,
                'reason': ('Validation top3 paired whole-game interval exceeds the strongest fixed baseline.' if eligible
                           else 'Learned winner retained for research; no positive lower-bound validation top3 advantage over the strongest fixed baseline.'),
                'testUnscored': True, 'validationUsedForParameterFitOrTuning': False}
    write(output / 'selected.json', selected)
    cohorts = {split: {} for split in results}
    for split, methods in results.items():
        groups = defaultdict(list)
        for key in methods['linear']:
            for cohort in cohort_keys(contexts[key]):
                groups[cohort].append(key)
        for cohort, keys in sorted(groups.items()):
            cohorts[split][cohort] = {name: measure([records[key] for key in keys]) for name, records in methods.items()}
    samples = {name: [] for name in ('strong_ml_wins', 'baseline_wins', 'shared_failures', 'small_margin',
                                    'missing_target', 'flex_uncertain', 'rare_picks')}
    for prediction in rows(output, 'predictions'):
        if prediction['split'] == 'validation':
            key = prediction['caseId']
            collect_samples(samples, key, cases[key], contexts[key], prediction['rankings'], labels, winner, best_baseline)
    write(output / 'error-analysis.json', attach_sample_evidence(dataset, samples, cases, linear))
    latency = {}
    for split, methods in results.items():
        keys = list(methods['linear'])
        latency[split] = {'exportedScorerMeanMs': float(np.mean([loaded['timings'][k]['scorerMs'] for k in keys])),
                          'exportedScorerP95Ms': float(np.quantile([loaded['timings'][k]['scorerMs'] for k in keys], .95)),
                          'exportedFeaturesAndChecksMeanMs': float(np.mean([loaded['timings'][k]['featuresAndChecksMs'] for k in keys])),
                          'exportedFeaturesAndChecksP95Ms': float(np.quantile([loaded['timings'][k]['featuresAndChecksMs'] for k in keys], .95)),
                          'derivedPipeline': {}}
        for name, records in methods.items():
            values = [loaded['timings'][key]['scorerMs'] + loaded['timings'][key]['featuresAndChecksMs'] + records[key]['latencyMs'] for key in keys]
            latency[split]['derivedPipeline'][name] = {'meanMs': float(np.mean(values)), 'p95Ms': float(np.quantile(values, .95))}
    export = loaded['exportReport']
    report = {'signal': 'pro_pick_imitation', 'testUnscored': True, 'reloadVerified': True,
              'metrics': metrics, 'cohorts': cohorts, 'validationComparison': comparisons, 'selected': selected,
              'checks': {**export['checks'], 'runnerCandidateLegalityChecks': export['checks']['candidateLegalityChecks'],
                         'runnerEvidenceCandidateAlignmentChecks': export['checks']['candidateLegalityChecks'],
                         'runnerMatchedMethodsPerCase': len(METHODS), **loaded['temporalChecks']},
              'evidenceQuality': {split: summary_quality(counts) for split, counts in loaded['evidenceQuality'].items()},
              'sourceCounts': {'partitions': manifest['selectedGames'], 'eligibleOpeningGames': export['eligibleOpeningGames'],
                               'exportedGames': export['exportedGames'], 'excluded': export['excluded']},
              'poolCoverage': {split: export['metrics'][split]['pool']['poolCoverage'] for split in results},
              'trainingMissingTargets': sum(c['target'] is None for c in training),
              'trainingCasesWithoutAlternatives': sum(len(c['ids']) < 2 for c in training),
              'trainingGamesWithoutComparisons': len({c['gameId'] for c in training} - set(covered)),
              'trainingWeighting': 'total weight one per game with usable labels; equal covered-case weight within game',
              'validationUsedForFitOrTuning': False, 'validationUsedForModelSelection': True,
              'configurations': {'linear': CONFIG, 'tree': {**PARAMETERS, 'num_boost_round': ROUNDS}},
              'fitSeconds': fit_seconds, 'loadAndValidationSeconds': load_seconds,
              'evaluationSeconds': evaluation_seconds, 'timing': latency,
              'timingBoundaries': {
                  'metricLatency': 'In-memory numeric scoring plus deterministic index sorting; excludes loading, feature construction, legality checks and serialization.',
                  'baselineMetricLatency': 'Reads already exported fixed scores plus sorting; not a fresh baseline scorer execution.',
                  'exportedScorer': 'Earlier export measured inferred candidate generation, feasibility and fixed-factor scoring.',
                  'derivedPipeline': 'Per-case sum of original exporter scorer/feature/check timing and current rank latency; component estimate, not measured live end-to-end latency.',
                  'reloadChecks': 'Fresh original/persisted model equality per case outside measured ranking timing.',
              },
              'featureRelevance': {'treeSplitGain': dict(zip(FEATURE_NAMES, reloaded_tree.feature_importance(importance_type='gain').tolist())),
                                   'meaning': 'Training split gain; descriptive and biased, not causal or validation permutation importance.'},
              'limits': [*manifest['limitations'],
                  'Validation selects between two fixed models; reported validation results are development estimates, not a final unbiased test.',
                  'Bootstrap resamples whole games, not series/team clusters; residual dependence can understate uncertainty.',
                  'All role cohorts are unknown at prediction time; later role assignments are not recovered for slicing.',
                  'LambdaRank uses within-group relevance weighting, while linear uses all alternative pairwise comparisons.',
                  'Pure query-constant context can have zero greedy tree split gain; stage interactions are supplied by the fixed schema.',
                  'Lineup witnesses were exhaustively checked by the hashed exporter; this compact runner independently rechecks unavailable champions and evidence alignment.',
                  'Float32 feature storage is new for this scaled run and can differ numerically from the prior float64 pilot.']}
    write(output / 'report.json', report)
    if verify(dataset) != manifest or sha(dataset / 'manifest.json') != manifest_hash:
        raise ValueError('Input changed during training; output is incomplete')
    if any(sha(Path(__file__).with_name(name)) != expected for name, expected in source_hashes.items()):
        raise ValueError('Implementation changed during training; output is incomplete')
    write(output / 'manifest.json', {'version': 1, 'signal': 'pro_pick_imitation', 'testUnscored': True,
          'status': 'OFFLINE_FIXED_CONFIG_DEVELOPMENT_COMPARISON', 'datasetDirectory': str(dataset.resolve()),
          'datasetManifestSha256': manifest_hash, 'datasetArtifacts': manifest['artifacts'],
          'inputProvenance': manifest['input'], 'exportCodeSha256': manifest['codeSha256'],
          'codeSha256': source_hashes, 'python': platform.python_version(), 'numpy': np.__version__,
          'lightgbm': lgb.__version__, 'configurations': report['configurations'], 'selected': selected,
          'artifacts': {path.name: sha(path) for path in sorted(output.iterdir()) if path.is_file()}})
    print(f'Finished fixed comparison in {perf_counter() - started:.1f}s; learned winner: {winner}', flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    report = run(args.dataset, args.output)
    print(json.dumps({'output': str(args.output), 'validation': report['metrics']['validation'],
                      'selected': report['selected']}, indent=2))


if __name__ == '__main__':
    main()
