"""Export opening-game training/validation examples and compare temporal baselines offline."""
import argparse
from collections import Counter, defaultdict
from contextlib import ExitStack
import gzip
import io
import json
from pathlib import Path
import platform
from time import perf_counter

from baseline import VARIANTS, WEIGHTS, recommend
from evaluate import Metrics, legal, line, sample_indices, write_json
from protocol import digest, pick_cases
from source_audit import audit_sources
from temporal import EarlierHistory, dataset_partitions


def code_hashes():
    return {name: digest(Path(__file__).with_name(name).read_bytes()) for name in (
        'build_dataset.py', 'source_audit.py', 'temporal.py', 'baseline.py', 'protocol.py', 'evaluate.py')}


def compressed_stream(stack, path):
    raw = stack.enter_context(path.open('wb'))
    zipped = stack.enter_context(gzip.GzipFile(filename='', mode='wb', fileobj=raw, compresslevel=1, mtime=0))
    return stack.enter_context(io.TextIOWrapper(zipped, encoding='utf-8', newline='\n'))


def feature_record(context, result):
    """Positive/negative targets are joined later from labels, never while building features."""
    candidates = []
    for row in result['candidates']:
        candidates.append({key: row[key] for key in (
            'championId', 'factors', 'factorCoverage', 'evidence', 'playerChampionEvidence', 'observedPlayers')})
    return {'caseId': context['caseId'], 'snapshotId': context['snapshotId'],
            'split': context['split'], 'poolPolicy': 'inferred',
            'candidates': candidates}


def build(prepared, raw_dir, output, max_training=None, max_validation=None,
          training_start='2024-04-01', validation_start='2025-01-01', test_start='2026-01-01'):
    for value in (max_training, max_validation):
        if value is not None and (type(value) is not int or value <= 0):
            raise ValueError('Sample limits must be positive integers')
    source_hashes = code_hashes()
    games, audit, provenance = audit_sources(prepared, raw_dir)
    parts = dataset_partitions(games, training_start, validation_start, test_start)
    selected, exclusions = {}, []
    excluded = {s: Counter() for s in ('training', 'validation')}
    for split, limit in (('training', max_training), ('validation', max_validation)):
        eligible = [g for g in parts[split] if audit[g['gameId']]['eligible']]
        if not eligible:
            raise ValueError('No supported opening games in ' + split)
        keep = sample_indices(len(eligible), limit)
        selected[split] = [g for index, g in enumerate(eligible) if index in keep]
        selected_ids = {g['gameId'] for g in selected[split]}
        for game in parts[split]:
            reasons = audit[game['gameId']]['reasons'] or ([] if game['gameId'] in selected_ids else ['sample_limit'])
            if reasons:
                excluded[split].update(reasons)
                exclusions.append({'gameId': game['gameId'], 'split': split, 'reasons': reasons})
    # The test period cannot enter any historical snapshot, even if a caller changes iteration order.
    test_ids = {g['gameId'] for g in parts['test']}
    temporal = EarlierHistory([g for g in games if g['gameId'] not in test_ids])
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / 'splits.json', {split: [g['gameId'] for g in rows] for split, rows in parts.items()})
    metrics = {s: {p: {v: defaultdict(Metrics) for v in VARIANTS} for p in ('observed', 'inferred')}
               for s in ('training', 'validation')}
    abstentions = {s: {p: Counter() for p in ('observed', 'inferred')} for s in ('training', 'validation')}
    exported = Counter()
    snapshot_ids = set()
    with ExitStack() as stack:
        streams = {name: compressed_stream(stack, output / (name + '.jsonl.gz')) for name in (
            'contexts', 'labels', 'features', 'predictions', 'snapshots', 'source-audit', 'exclusions', 'timings')}
        for game_id in sorted(audit):
            line(streams['source-audit'], audit[game_id])
        for exclusion in exclusions:
            line(streams['exclusions'], exclusion)
        for split in ('training', 'validation'):
            for game in selected[split]:
                snapshot = temporal.advance(game['date'][:10])
                if snapshot['snapshotId'] not in snapshot_ids:
                    snapshot_ids.add(snapshot['snapshotId'])
                    line(streams['snapshots'], snapshot)
                history = temporal.history
                for context, label in pick_cases(game):
                    context.update({'split': split, 'snapshotId': snapshot['snapshotId'],
                                    'evidenceThrough': history.latest_date, 'poolSource': 'pro_history',
                                    'seriesCandidateId': audit[game['gameId']]['seriesCandidateId'],
                                    'protocol': 'publisher-order-opening-game-v2'})
                    line(streams['contexts'], context)
                    line(streams['labels'], {**label, 'split': split, 'caseWeight': 0.1})
                    stage = ('blind' if not context['allyPicks'] and not context['enemyPicks']
                             else 'late' if len(context['allyPicks']) >= 3 else 'early')
                    for policy in ('observed', 'inferred'):
                        domains = history.pools(context['playerIds']) if policy == 'observed' else [
                            set(history.champions) | set(context['allyPicks']) for _ in context['playerIds']]
                        pools = dict(zip(context['playerIds'], domains))
                        for variant in VARIANTS:
                            start = perf_counter()
                            result = recommend(context, history, variant, pool_policy=policy)
                            latency = (perf_counter() - start) * 1000
                            violations = sum(not legal(c, context, pools) for c in result['candidates'])
                            if violations:
                                raise ValueError('Invalid candidate completion; output is incomplete')
                            for cohort in ('all', stage, 'patch:' + game['patch']):
                                metrics[split][policy][variant][cohort].add(result, label, latency, violations)
                            if variant == 'pool':
                                abstentions[split][policy][result['abstention'] or 'returned_candidates'] += 1
                            line(streams['predictions'], {'caseId': context['caseId'], 'split': split,
                                 'policy': policy, 'variant': variant, **result})
                            line(streams['timings'], {'caseId': context['caseId'], 'policy': policy,
                                                     'variant': variant, 'latencyMs': latency})
                            if policy == 'inferred' and variant == 'pool_rules_stats':
                                line(streams['features'], feature_record(context, result))
                exported[split] += 1
                if exported[split] % 25 == 0:
                    print(f'{split}: exported {exported[split]}/{len(selected[split])} games', flush=True)
    report = {'status': 'OPENING_GAME_RESEARCH_EXPORT', 'exportedGames': dict(exported),
              'partitions': {s: len(rows) for s, rows in parts.items()},
              'eligibleOpeningGames': sum(row['eligible'] for row in audit.values()),
              'excluded': {s: dict(rows) for s, rows in excluded.items()}, 'abstentions': abstentions,
              'metrics': {s: {p: {v: {c: m.report() for c, m in cohorts.items()} for v, cohorts in variants.items()}
                              for p, variants in policies.items()} for s, policies in metrics.items()}}
    write_json(output / 'report.json', report)
    if source_hashes != code_hashes():
        raise ValueError('Source changed during export; output is incomplete')
    artifacts = {p.name: digest(p.read_bytes()) for p in sorted(output.iterdir()) if p.is_file()}
    write_json(output / 'manifest.json', {
        'version': 2, 'status': report['status'], 'input': provenance, 'codeSha256': source_hashes,
        'artifacts': artifacts, 'python': platform.python_version(), 'weights': WEIGHTS,
        'trainingStart': training_start, 'validationStart': validation_start, 'testStart': test_start,
        'labelEmbargoDays': 7, 'historyLagDays': 1, 'historyPolicy': 'expanding_earlier_only',
        'historyPopulation': 'all_prepared_earlier_pro_games_including_later_series_games',
        'validationProtocol': 'prequential_prior_validation_outcomes_available_after_lag_no_parameter_fit',
        'testUnscored': True, 'maxTrainingGames': max_training, 'maxValidationGames': max_validation,
        'sampling': 'evenly_spaced_whole_eligible_games_per_split',
        'featureContract': 'context + candidate features, keyed by caseId; labels never supplied to scorer',
        'limitations': [
            'Opening games only. Later-game standard/soft/hard Fearless rules are not inferred.',
            'Series candidate IDs are inferred from teams/date, not official series identifiers; cross-midnight series need further audit.',
            'Publisher field definitions verified; individual records structurally checked, not manually VOD-verified.',
            'History uses source match dates with a one-day lag, not original API availability timestamps.',
            'Champion vocabulary comes from earlier observations, not a historically complete champion-availability catalog.',
            'Inferred familiarity uses 50+50*n/(n+10); observed baseline retains relative-frequency scoring. This is a policy bundle comparison.',
            'Saved pools remain hard constraints; no saved user data is read or changed by this export.',
            'Composition and lane matchups remain neutral. Historical stats pool patches/leagues and draft formats.',
            'Top-three agreement is not win improvement. No model is trained by this command.',
        ]})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared', required=True, type=Path)
    parser.add_argument('--raw-dir', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--max-training-games', type=int)
    parser.add_argument('--max-validation-games', type=int)
    parser.add_argument('--training-start', default='2024-04-01')
    parser.add_argument('--validation-start', default='2025-01-01')
    parser.add_argument('--test-start', default='2026-01-01')
    args = parser.parse_args()
    report = build(args.prepared, args.raw_dir, args.output, args.max_training_games, args.max_validation_games,
                   args.training_start, args.validation_start, args.test_start)
    print(json.dumps({'output': str(args.output), 'exportedGames': report['exportedGames'],
                      'status': report['status']}, indent=2))


if __name__ == '__main__':
    main()
