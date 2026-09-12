"""Stream earlier-only opening-game features with one inferred scorer pass per case."""
import argparse
from collections import Counter
from contextlib import ExitStack
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import platform
from time import perf_counter

from baseline import VARIANTS, WEIGHTS, recommend
from evaluate import legal, line, sample_indices, write_json
from ml_features import FEATURE_NAMES, SCHEMA, vector
from source_audit import audit_sources
from temporal import EarlierHistory, dataset_partitions
from protocol import pick_cases


def file_hash(path):
    """Hash large artifacts without loading a second copy into memory."""
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def code_hashes():
    return {name: file_hash(Path(__file__).with_name(name)) for name in (
        'compact_dataset.py', 'source_audit.py', 'temporal.py', 'baseline.py',
        'protocol.py', 'evaluate.py', 'ml_features.py')}


def compressed_stream(stack, path):
    raw = stack.enter_context(path.open('wb'))
    zipped = stack.enter_context(gzip.GzipFile(filename='', mode='wb', fileobj=raw, compresslevel=1, mtime=0))
    return stack.enter_context(io.TextIOWrapper(zipped, encoding='utf-8', newline='\n'))


def compact_case(context, result, history):
    """Validate full lineup witnesses before keeping only aligned vectors and evidence."""
    candidates = sorted(result['candidates'], key=lambda row: row['championId'])
    champion_ids = [row['championId'] for row in candidates]
    if len(set(champion_ids)) != len(champion_ids):
        raise ValueError('Duplicate candidate identities')
    domain = set(history.champions) | set(context['allyPicks'])
    pools = {player: domain for player in context['playerIds']}
    checks = Counter(candidateLegalityChecks=0, lineupCompletionChecks=0,
                     legalityViolations=0, impossibleLineupCandidates=0)
    x, evidence = [], []
    scores = {variant: [] for variant in VARIANTS}
    for candidate in candidates:
        checks['candidateLegalityChecks'] += 1
        checks['lineupCompletionChecks'] += 1
        witness = candidate['completionWitness']
        required = set(context['allyPicks']) | {candidate['championId']}
        complete = (set(witness) == set(context['playerIds']) and len(set(witness.values())) == 5
                    and required <= set(witness.values()))
        checks['impossibleLineupCandidates'] += not complete
        checks['legalityViolations'] += not legal(candidate, context, pools)
        if checks['impossibleLineupCandidates'] or checks['legalityViolations']:
            raise ValueError('Invalid candidate completion; output is incomplete')
        values = vector(context, candidate)
        if len(values) != len(FEATURE_NAMES) or not all(math.isfinite(v) for v in values):
            raise ValueError('Invalid feature vector')
        x.append(values)
        for variant in VARIANTS:
            active = (set(WEIGHTS) if variant == 'pool_rules_stats' else
                      {'comfort', 'draftValue'} if variant == 'pool_rules' else {'comfort'})
            scores[variant].append(round(sum(
                (candidate['factors'][key] if key in active else 50.0) * weight / 100
                for key, weight in WEIGHTS.items()), 6))
        meta = candidate['evidence']['meta']
        pairs = candidate['evidence']['allyPairs']
        quality = {
            'metaMissing': meta is None,
            'metaSmallSample': meta is not None and meta['games'] < 30,
            'pairMissing': not pairs,
            'pairSmallSampleCount': sum(min(p['games'], p['allyBaseline']['games'], meta['games']) < 30
                                        for p in pairs),
            'pairObservedCount': len(pairs), 'pairPossibleCount': len(context['allyPicks']),
            'observedPlayerCount': sum(n > 0 for n in candidate['playerChampionEvidence'].values()),
        }
        evidence.append({**{key: candidate[key] for key in (
            'championId', 'factors', 'factorCoverage', 'evidence', 'playerChampionEvidence',
            'observedPlayers', 'warnings')}, 'evidenceQuality': quality})
    ranks = {}
    for variant, values in scores.items():
        order = sorted(range(len(values)), key=lambda i: (-values[i], champion_ids[i]))
        aligned = [0] * len(order)
        for rank, index in enumerate(order, 1):
            aligned[index] = rank
        ranks[variant] = aligned
    feature = {'caseId': context['caseId'], 'snapshotId': context['snapshotId'],
               'split': context['split'], 'poolPolicy': 'inferred', 'championIds': champion_ids,
               'x': x, 'baselineScores': scores, 'baselineRanks': ranks,
               'abstention': result['abstention']}
    return feature, {'caseId': context['caseId'], 'candidates': evidence}, checks


class StreamingMetrics:
    """Keep aggregate metrics constant-space; detailed timings are streamed separately."""
    def __init__(self):
        self.counts = Counter(cases=0, abstentions=0, poolCovered=0, candidateCovered=0,
                              top3Hits=0, returnedCandidates=0, legalityViolations=0)

    def add(self, features, target, observed, variant):
        ids = features['championIds']
        covered = target in ids
        self.counts.update(cases=1, abstentions=int(not ids), poolCovered=int(target in observed),
                           candidateCovered=int(covered), returnedCandidates=len(ids),
                           top3Hits=int(covered and features['baselineRanks'][variant][ids.index(target)] <= 3))

    def report(self):
        counts = self.counts
        return {**counts, 'top3Agreement': counts['top3Hits'] / counts['cases'] if counts['cases'] else None,
                'top3AgreementWhenCovered': counts['top3Hits'] / counts['candidateCovered']
                if counts['candidateCovered'] else None,
                'poolCoverage': counts['poolCovered'] / counts['cases'] if counts['cases'] else None,
                'candidateCoverage': counts['candidateCovered'] / counts['cases'] if counts['cases'] else None}


def build(prepared, raw_dir, output, max_training=None, max_validation=None,
          training_start='2024-04-01', validation_start='2025-01-01', test_start='2026-01-01',
          _selected_game_ids=None, _audited=None):
    for value in (max_training, max_validation):
        if value is not None and (type(value) is not int or value <= 0):
            raise ValueError('Sample limits must be positive integers')
    if output.exists():
        raise FileExistsError(output)
    started = perf_counter()
    source_hashes = code_hashes()
    games, audit, provenance = _audited if _audited is not None else audit_sources(prepared, raw_dir)
    inputs = {prepared / 'games.jsonl': provenance['gamesSha256'],
              prepared / 'report.json': provenance['reportSha256']}
    inputs.update({raw_dir / source['filename']: source['sha256'] for source in provenance['rawSources']})
    parts = dataset_partitions(games, training_start, validation_start, test_start)
    selected, exclusions, eligible_counts = {}, [], {}
    excluded = {split: Counter() for split in ('training', 'validation')}
    for split, limit in (('training', max_training), ('validation', max_validation)):
        eligible = [g for g in parts[split] if audit[g['gameId']]['eligible']]
        if not eligible:
            raise ValueError('No supported opening games in ' + split)
        eligible_counts[split] = len(eligible)
        keep = sample_indices(len(eligible), limit)
        selected[split] = [g for index, g in enumerate(eligible) if index in keep]
        if _selected_game_ids is not None:
            requested = set(_selected_game_ids[split])
            if not requested <= {g['gameId'] for g in selected[split]}:
                raise ValueError('Selected games must be eligible sampled games')
            selected[split] = [g for g in selected[split] if g['gameId'] in requested]
        selected_ids = {g['gameId'] for g in selected[split]}
        for game in parts[split]:
            reasons = audit[game['gameId']]['reasons'] or ([] if game['gameId'] in selected_ids else ['sample_limit'])
            if reasons:
                excluded[split].update(reasons)
                exclusions.append({'gameId': game['gameId'], 'split': split, 'reasons': reasons})
        print(f'{split}: selected {len(selected[split])}/{len(eligible)} eligible opening games', flush=True)
    test_ids = {g['gameId'] for g in parts['test']}
    temporal = EarlierHistory([g for g in games if g['gameId'] not in test_ids])
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / 'splits.json', {split: [g['gameId'] for g in rows] for split, rows in parts.items()})
    write_json(output / 'feature-schema.json', {
        **SCHEMA, 'datasetVersion': 3, 'matrix': 'x[candidateIndex][featureIndex]',
        'candidateOrder': 'championIds ascending lexical order; not a predictive feature',
        'baselines': {'variants': list(VARIANTS), 'scores': 'aligned to championIds',
                      'ranks': 'one-based aligned ranks; descending score then championId'},
        'evidenceArtifact': 'evidence.jsonl.gz; same caseId and candidate order',
        'smallSampleThreshold': 30, 'missingEvidence': 'explicit masks and observed/possible counts',
    })
    metrics = {split: {variant: StreamingMetrics() for variant in VARIANTS} for split in selected}
    checks = Counter(candidateLegalityChecks=0, lineupCompletionChecks=0,
                     legalityViolations=0, impossibleLineupCandidates=0, scorerCalls=0,
                     cases=0, targetAbsentCases=0)
    quality = {split: Counter() for split in selected}
    exported, snapshot_ids, abstentions = Counter(), set(), {split: Counter() for split in selected}
    stages = {split: Counter() for split in selected}
    scorer_ms, features_ms = 0.0, 0.0
    with ExitStack() as stack:
        streams = {name: compressed_stream(stack, output / (name + '.jsonl.gz')) for name in (
            'contexts', 'labels', 'features', 'evidence', 'snapshots', 'source-audit', 'exclusions', 'timings')}
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
                    start = perf_counter()
                    result = recommend(context, history, 'pool_rules_stats', pool_policy='inferred')
                    scoring = (perf_counter() - start) * 1000
                    start = perf_counter()
                    features, evidence, case_checks = compact_case(context, result, history)
                    feature_time = (perf_counter() - start) * 1000
                    checks.update(case_checks)
                    checks.update(cases=1, scorerCalls=1, targetAbsentCases=int(label['championId'] not in features['championIds']))
                    scorer_ms += scoring
                    features_ms += feature_time
                    for variant in VARIANTS:
                        metrics[split][variant].add(features, label['championId'], result['poolCandidates'], variant)
                    abstentions[split][result['abstention'] or 'returned_candidates'] += 1
                    stage = ('blind' if not context['allyPicks'] and not context['enemyPicks']
                             else 'late' if len(context['allyPicks']) >= 3 else 'early')
                    stages[split][stage] += 1
                    for candidate in evidence['candidates']:
                        quality[split].update({key: int(value) for key, value in candidate['evidenceQuality'].items()})
                        quality[split]['candidates'] += 1
                        quality[split]['missingPlayerHistoryCandidates'] += candidate['evidenceQuality']['observedPlayerCount'] == 0
                    line(streams['contexts'], context)
                    line(streams['labels'], {**label, 'split': split, 'caseWeight': 0.1})
                    line(streams['features'], features)
                    line(streams['evidence'], evidence)
                    line(streams['timings'], {'caseId': context['caseId'], 'split': split,
                         'scorerMs': scoring, 'featuresAndChecksMs': feature_time})
                exported[split] += 1
                if exported[split] % 25 == 0:
                    print(f'{split}: exported {exported[split]}/{len(selected[split])} games; '
                          f'{perf_counter() - started:.1f}s elapsed', flush=True)
    if source_hashes != code_hashes():
        raise ValueError('Source changed during export; output is incomplete')
    for path, expected_hash in inputs.items():
        if file_hash(path) != expected_hash:
            raise ValueError('Input changed during export: ' + str(path) + '; output is incomplete')
    report = {'status': 'COMPACT_OPENING_GAME_RESEARCH_EXPORT', 'exportedGames': dict(exported),
              'selectedGames': {s: len(rows) for s, rows in selected.items()},
              'eligibleOpeningGames': eligible_counts, 'partitions': {s: len(rows) for s, rows in parts.items()},
              'excluded': {s: dict(rows) for s, rows in excluded.items()}, 'checks': dict(checks),
              'evidenceQuality': quality, 'stageCounts': stages, 'abstentions': abstentions,
              'metrics': {s: {v: metric.report() for v, metric in variants.items()} for s, variants in metrics.items()},
              'timing': {'scorerTotalMs': scorer_ms, 'featuresAndChecksTotalMs': features_ms,
                         'elapsedSeconds': perf_counter() - started}}
    write_json(output / 'report.json', report)
    artifacts = {p.name: file_hash(p) for p in sorted(output.iterdir()) if p.is_file()}
    write_json(output / 'manifest.json', {
        'version': 3, 'status': report['status'], 'input': provenance, 'codeSha256': source_hashes,
        'artifacts': artifacts, 'python': platform.python_version(), 'weights': WEIGHTS,
        'trainingStart': training_start, 'validationStart': validation_start, 'testStart': test_start,
        'labelEmbargoDays': 7, 'historyLagDays': 1, 'historyPolicy': 'expanding_earlier_only',
        'historyPopulation': 'all_prepared_earlier_pro_games_including_later_series_games',
        'validationProtocol': 'prequential_prior_validation_outcomes_available_after_lag_no_parameter_fit',
        'testUnscored': True, 'maxTrainingGames': max_training, 'maxValidationGames': max_validation,
        'sampling': 'all_eligible_games_unless_explicit_evenly_spaced_limit',
        'selectedGames': {s: len(rows) for s, rows in selected.items()},
        'featureContract': 'features.x and championIds; separate contexts, labels and evidence keyed by caseId',
        'scorerPolicy': 'one inferred pool_rules_stats pass per case; three fixed scores reuse the same factors and candidates',
        'legalityPolicy': 'independent evaluate.legal and full five-player lineup checks before omitting witnesses',
        'sourceInputsVerifiedAfterExport': True,
        'limitations': [
            'Opening games only. Later-game standard/soft/hard Fearless rules are not inferred.',
            'Series candidate IDs use teams/date, not official series IDs; cross-midnight series need further audit.',
            'Publisher field definitions verified; records structurally checked, not manually VOD-verified.',
            'History uses match dates with a one-day lag, not original API availability timestamps.',
            'Vocabulary is earlier observed champions, not a historically complete champion-availability catalog.',
            'Inferred player capability is permissive; observed familiarity is evidence, not a hard saved pool.',
            'Saved teams and user pools are never read or changed by this export.',
            'Composition, lane matchups, and team history remain neutral; statistics pool patches/leagues/formats.',
            'Features and fixed scores are pro-pick imitation signals, not win probabilities or causal estimates.',
            'The reserved 2026 test period is unscored and cannot enter historical evidence.',
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
                      'status': report['status'], 'checks': report['checks']}, indent=2))


if __name__ == '__main__':
    main()
