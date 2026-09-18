"""Two preregistered offline pick experiments; frozen comparators, no 2026 scoring."""
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
from time import perf_counter

from scaled_train import (load, read, write, sha, rows, measure, paired_comparison,
                          cohort_keys, rank_observation)
import lightgbm as lgb
import numpy as np
from linear_ranker import score
from tree_ranker import fit_tree, tree_score, PARAMETERS, ROUNDS
from protocol import load_prepared
from recency_features import RecencyHistory, extend, is_blind, EXTENDED_NAMES

FIXED = 'inferred/pool_rules_stats'
METHODS = (FIXED, 'linear', 'tree', 'recency_tree', 'blind_specialist')
CODE = ('blind_experiment.py', 'recency_features.py', 'scaled_train.py',
        'tree_ranker.py', 'linear_ranker.py', 'ml_features.py', 'protocol.py')


def verify_frozen(path, dataset_hash):
    manifest = read(path / 'manifest.json')
    if manifest['datasetManifestSha256'] != dataset_hash:
        raise ValueError('Frozen model belongs to a different dataset')
    for name, expected in manifest['artifacts'].items():
        if Path(name).name != name or sha(path / name) != expected:
            raise ValueError('Frozen artifact changed: ' + name)
    return manifest


def training_cases(cases, contexts, specialist):
    selected = [c for key, c in cases.items() if c['split'] == 'training'
                and (not specialist or is_blind(contexts[key]))]
    counts = Counter(c['gameId'] for c in selected if c['target'] is not None and len(c['ids']) >= 2)
    return [{**c, 'weight': 1 / counts[c['gameId']] if counts[c['gameId']] else 1.}
            for c in selected]


def rarity_cohort(case):
    if case['target'] is None:
        return 'new_or_absent'
    # Recover the integer support before comparing: float32 log(31) rounds down.
    count = round(float(np.expm1(float(case['x'][case['target'], 4]))))
    return 'new_or_absent' if count == 0 else 'rare' if count < 30 else 'established'


def run(dataset, frozen, prepared, output, registration):
    if output.exists():
        raise FileExistsError(output)
    started = perf_counter()
    dataset_hash, frozen_hash = sha(dataset / 'manifest.json'), sha(frozen / 'manifest.json')
    code_hashes = {name: sha(Path(__file__).with_name(name)) for name in CODE}
    registration_hash = sha(registration)
    frozen_manifest = verify_frozen(frozen, dataset_hash)
    print('Verifying and loading the completed compact dataset', flush=True)
    loaded = load(dataset)
    cases, contexts, labels = (loaded[name] for name in ('cases', 'contexts', 'labels'))
    games, provenance = load_prepared(prepared)
    if any(provenance[k] != loaded['manifest']['input'][k] for k in provenance):
        raise ValueError('Prepared history differs from the frozen export')
    eligible = {r['gameId'] for r in rows(dataset, 'source-audit') if r['eligible']}
    history = RecencyHistory([g for g in games if g['gameId'] in eligible and g['date'] < '2026-01-01'])
    # Validation is available to later snapshots, but never to either fitting call.
    feature_ms, rarity, missing = {}, {}, Counter()
    for number, key in enumerate(sorted(cases, key=lambda k: (contexts[k]['date'], k)), 1):
        c, context = cases[key], contexts[key]
        if c['split'] not in ('training', 'validation') or context['date'] >= '2026-01-01':
            raise ValueError('Sealed test case at scoring boundary')
        start = perf_counter()
        table = history.at(context['date'][:10], context['patch'])
        rarity[key] = rarity_cohort(c)
        c['x'] = extend(c['x'], c['ids'], context, table)
        feature_ms[key] = (perf_counter() - start) * 1000
        if c['split'] == 'validation':
            missing['candidates'] += len(c['ids'])
            for offset, window in ((33, '14d'), (41, '30d'), (49, 'patch')):
                missing[window + '_window_missing'] += int(c['x'][:, offset + 6].sum())
                missing[window + '_champion_unseen'] += int(c['x'][:, offset + 7].sum())
        if number % 10000 == 0:
            print(f'Extended earlier-only features: {number}/{len(cases)}', flush=True)
    output.mkdir(parents=True, exist_ok=False)
    write(output / 'protocol.json', {'registrationSha256': registration_hash,
          'features': list(EXTENDED_NAMES), 'config': {**PARAMETERS, 'rounds': ROUNDS},
          'routing': 'blind specialist iff both visible pick lists are empty; frozen tree otherwise',
          'historyPopulation': 'audited eligible pre-2026 opening games',
          'datasetManifestSha256': dataset_hash, 'frozenManifestSha256': frozen_hash})
    fit_seconds, models = {}, {}
    for name, specialist in (('recency_tree', False), ('blind_specialist', True)):
        training = training_cases(cases, contexts, specialist)
        print(f'Fitting {name}: {len(training)} training decisions', flush=True)
        start = perf_counter()
        model = fit_tree(training)
        fit_seconds[name] = perf_counter() - start
        (output / (name + '.txt')).write_bytes(model.encode('utf-8'))
        original = lgb.Booster(model_str=model)
        reloaded = lgb.Booster(model_file=str(output / (name + '.txt')))
        models[name] = (original, reloaded)
    del training
    print('Both models fitted; starting chronological validation comparison', flush=True)
    linear = read(frozen / 'linear.json')
    frozen_tree = lgb.Booster(model_file=str(frozen / 'tree.txt'))
    results = {name: {} for name in METHODS}
    validations = [key for key in cases if cases[key]['split'] == 'validation']
    with gzip.open(output / 'observations.jsonl.gz', 'wt', encoding='utf-8') as stream:
        for number, key in enumerate(validations, 1):
            c, context = cases[key], contexts[key]
            frozen_x = c['x'][:, :33]
            top = {}
            for name in METHODS:
                start = perf_counter()
                if name == 'blind_specialist' and not is_blind(context):
                    # Exact reuse, not a post-hoc choice: the frozen tree is the declared policy.
                    results[name][key] = dict(results['tree'][key])
                    top[name] = top['tree']
                    continue
                values = (c['baselineScores'][FIXED] if name == FIXED else
                          score(linear, frozen_x) if name == 'linear' else
                          tree_score(frozen_tree, frozen_x) if name == 'tree' else
                          tree_score(models[name][1], c['x']))
                order = sorted(range(len(c['ids'])), key=lambda i: (-values[i], c['ids'][i]))
                latency = (perf_counter() - start) * 1000
                ids = [c['ids'][i] for i in order]
                results[name][key] = rank_observation(ids, labels[key]['championId'], latency)
                top[name] = ids[:5]
                if name in models and not np.array_equal(values, tree_score(models[name][0], c['x'])):
                    raise ValueError('Saved model reload changed predictions')
            stream.write(json.dumps({'caseId': key, 'cohort': rarity[key], 'top5': top,
                                    'observations': {n: results[n][key] for n in METHODS}}) + '\n')
            if number % 5000 == 0:
                print(f'Validated {number}/{len(validations)} decisions', flush=True)
    groups = {'overall': validations}
    for stage in ('blind', 'early', 'late'):
        groups[stage] = [k for k in validations if cohort_keys(contexts[k])[0] == 'stage/' + stage]
    for rare in ('new_or_absent', 'rare', 'established'):
        groups[rare] = [k for k in validations if rarity[k] == rare]
    metrics = {group: {name: (measure([results[name][k] for k in keys]) if keys else
                             {'cases': 0, 'notEstimable': True}) for name in METHODS}
               for group, keys in groups.items()}
    # Frozen comparators must reproduce the existing full-validation benchmark, not a new subset.
    old = read(frozen / 'report.json')['metrics']['validation']
    for name in (FIXED, 'linear', 'tree'):
        for metric in ('top1Agreement', 'top3Agreement', 'top5Agreement', 'mrr'):
            if abs(metrics['overall'][name][metric] - old[name][metric]) > 1e-12:
                raise ValueError('Frozen validation metric mismatch: ' + name + '/' + metric)
    comparisons = {}
    for name in models:
        comparisons[name] = {}
        for group, reference in (('blind', 'linear'), ('overall', 'tree'), ('late', 'tree')):
            keys = groups[group]
            comparisons[name][group] = paired_comparison(
                {k: results[name][k] for k in keys}, {k: results[reference][k] for k in keys}, contexts)
    decisions = {}
    for name, comparison in comparisons.items():
        blind_ok = comparison['blind']['top3']['pairedGameBootstrap95'][0] > 0
        late_ok = comparison['late']['top3']['delta'] >= -.005 and comparison['late']['mrr']['delta'] >= -.005
        decisions[name] = {'blindGatePassed': blind_ok, 'lateGatePassed': late_ok,
                           'eligibleForShadowDiscussion': blind_ok and late_ok,
                           'overallTop3Delta': comparison['overall']['top3']['delta'],
                           'promoted': False}
    count = missing['candidates']
    report = {'testUnscored': True, 'liveIntegration': False, 'reloadVerified': True,
              'frozenMetricsReproduced': True, 'validationUsedForFitOrTuning': False,
              'metrics': metrics, 'comparisons': comparisons, 'decisions': decisions,
              'fitSeconds': fit_seconds, 'totalSeconds': perf_counter() - started,
              'newFeatureMissingness': {**dict(missing), 'rates': {
                  k: v / count for k, v in missing.items() if k != 'candidates'}},
              'originalEvidenceQuality': read(frozen / 'report.json')['evidenceQuality']['validation'],
              'addedFeatureLatencyMs': {'mean': float(np.mean([feature_ms[k] for k in validations])),
                                        'p95': float(np.quantile([feature_ms[k] for k in validations], .95)),
                                        'max': max(feature_ms[k] for k in validations)},
              'latencyBoundary': 'Ranking plus sorting, in-memory. Fixed scores cached; new history cached per day/patch. Feature time separate; no live API or startup.',
              'coverageDefinition': 'Frozen legal candidates unchanged; rare <30 original earlier global observations; new_or_absent = zero original observations or absent target. No target injection.',
              'limitations': ['Development validation already inspected in previous milestones; not independent final test.',
                             'Imitates professional choices, not objective quality or win probability.',
                             'Whole-game intervals do not fully capture repeated team/series dependence.',
                             'New prevalence uses audited openings; original features use all earlier prepared games.',
                             'Eventual saved user pools remain authoritative; no live inference adapter changed.']}
    write(output / 'report.json', report)
    if sha(dataset / 'manifest.json') != dataset_hash or sha(frozen / 'manifest.json') != frozen_hash:
        raise ValueError('Input manifest changed during experiment')
    if any(sha(Path(__file__).with_name(n)) != h for n, h in code_hashes.items()) or sha(registration) != registration_hash:
        raise ValueError('Experiment implementation or preregistration changed during run')
    write(output / 'manifest.json', {'status': 'COMPLETE_OFFLINE_BLIND_EXPERIMENT',
          'testUnscored': True, 'codeSha256': code_hashes, 'registrationSha256': registration_hash,
          'datasetManifestSha256': dataset_hash, 'frozenManifestSha256': frozen_hash,
          'artifacts': {p.name: sha(p) for p in output.iterdir() if p.is_file()}})
    print(json.dumps({'output': str(output), 'decisions': decisions, 'seconds': report['totalSeconds']}, indent=2), flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ('dataset', 'frozen', 'prepared', 'output', 'registration'):
        parser.add_argument('--' + argument, required=True, type=Path)
    run(**vars(parser.parse_args()))
