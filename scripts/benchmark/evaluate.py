"""Offline replay diagnostics. No network, database connection, model fit, or UI calls."""
import argparse
from collections import Counter, defaultdict
from contextlib import ExitStack
import json
import gzip
import io
import math
from pathlib import Path
import platform
from time import perf_counter

from baseline import History, VARIANTS, WEIGHTS, recommend
from protocol import digest, load_prepared, partition, pick_cases


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def line(stream, value):
    stream.write(json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n')


def sample_indices(size, limit):
    """Evenly spaced whole games; no random selection or outcome-based sampling."""
    if limit is None or limit >= size:
        return set(range(size))
    if limit == 1:
        return {size // 2}
    return {i * (size - 1) // (limit - 1) for i in range(limit)}


def code_hashes():
    return {name: digest(Path(__file__).with_name(name).read_bytes())
            for name in ('evaluate.py', 'protocol.py', 'baseline.py')}


def legal(row, context, pools):
    """Independent output check: witness includes every required pick exactly once."""
    witness = row['completionWitness']
    picks = set(witness.values())
    required = set(context['allyPicks']) | {row['championId']}
    blocked = set(context['bans']) | set(context['enemyPicks'])
    return (set(witness) == set(context['playerIds']) and len(picks) == 5
            and required <= picks and not picks & blocked
            and row['championId'] not in context['allyPicks']
            and all(champ in pools[player] for player, champ in witness.items()))


class Metrics:
    def __init__(self):
        self.counts = Counter()
        self.latencies = []
        self.coverages = []

    def add(self, result, label, latency, violations):
        candidates = result['candidates']
        target = label['championId']
        self.counts['cases'] += 1
        self.counts['abstentions'] += not bool(candidates)
        self.counts['poolCovered'] += target in result['poolCandidates']
        self.counts['candidateCovered'] += any(c['championId'] == target for c in candidates)
        self.counts['top3Hits'] += any(c['championId'] == target for c in candidates[:3])
        self.counts['returnedCandidates'] += len(candidates)
        self.counts['legalityViolations'] += violations
        self.counts['smallSampleCandidates'] += sum('small_sample' in c['warnings'] for c in candidates)
        self.latencies.append(latency)
        self.coverages.extend(c['factorCoverage'] for c in candidates)

    def report(self):
        count = self.counts['cases']
        covered = self.counts['candidateCovered']
        ordered = sorted(self.latencies)
        return {**self.counts,
                'top3Agreement': self.counts['top3Hits'] / count if count else None,
                'top3AgreementWhenCovered': self.counts['top3Hits'] / covered if covered else None,
                'poolCoverage': self.counts['poolCovered'] / count if count else None,
                'candidateCoverage': covered / count if count else None,
                'meanFactorCoverage': sum(self.coverages) / len(self.coverages) if self.coverages else None,
                'latencyP50Ms': ordered[math.ceil(len(ordered) * .5) - 1] if ordered else None,
                'latencyP95Ms': ordered[math.ceil(len(ordered) * .95) - 1] if ordered else None}


def run(prepared, output, provisional=False, max_games=None,
        validation_start='2025-01-01', test_start='2026-01-01'):
    if not provisional:
        raise ValueError('Order/series semantics unverified: explicit --provisional-replay required')
    if max_games is not None and (type(max_games) is not int or max_games <= 0):
        raise ValueError('max-games must be positive')
    source_hashes = code_hashes()
    games, provenance = load_prepared(prepared)
    groups = partition(games, validation_start, test_start)
    if not groups['reference'] or not groups['validation']:
        raise ValueError('Nonempty reference and validation periods are required')
    history = History()
    for game in groups['reference']:
        history.observe(game)
    output.mkdir(parents=True, exist_ok=False)
    # A separate shared snapshot allows the next ML milestone to reuse the exact features.
    write_json(output / 'history.json', {
        'gameIds': sorted(history.game_ids), 'latestDate': history.latest_date,
        'patches': history.patches, 'players': history.players,
        'champions': {c: {'games': g, 'wins': w} for c, (g, w) in history.champions.items()},
        'allyPairs': [{'champions': list(pair), 'games': g, 'wins': w}
                      for pair, (g, w) in sorted(history.pairs.items())]})
    # Test membership only: never export or score its labels in this command.
    write_json(output / 'splits.json', {k: [g['gameId'] for g in v] for k, v in groups.items()})
    metrics = {v: defaultdict(Metrics) for v in VARIANTS}
    skipped = Counter()
    evaluated = 0
    eligible = []
    exclusions = []
    for game in groups['validation']:
        reason = None
        if not game['draftFieldsComplete']:
            reason = 'incomplete_draft'
        else:
            try:
                list(pick_cases(game))
            except ValueError as error:
                reason = str(error)
        if reason:
            skipped[reason] += 1
            exclusions.append({'gameId': game['gameId'], 'reason': reason})
        else:
            eligible.append(game)
    selected = sample_indices(len(eligible), max_games)
    with ExitStack() as stack:
        streams = {name: stack.enter_context((output / name).open('w', encoding='utf-8', newline='\n'))
                   for name in ('contexts.jsonl', 'labels.jsonl', 'timings.jsonl', 'exclusions.jsonl')}
        raw_predictions = stack.enter_context((output / 'predictions.jsonl.gz').open('wb'))
        compressed = stack.enter_context(gzip.GzipFile(filename='', mode='wb', fileobj=raw_predictions,
                                                       compresslevel=1, mtime=0))
        predictions = stack.enter_context(io.TextIOWrapper(compressed, encoding='utf-8', newline='\n'))
        for exclusion in exclusions:
            line(streams['exclusions.jsonl'], exclusion)
        for index, game in enumerate(eligible):
            if index not in selected:
                skipped['sample_limit'] += 1
                line(streams['exclusions.jsonl'], {'gameId': game['gameId'], 'reason': 'sample_limit'})
                continue
            cases = list(pick_cases(game))
            evaluated += 1
            for context, label in cases:
                context['evidenceThrough'] = history.latest_date
                line(streams['contexts.jsonl'], context)
                line(streams['labels.jsonl'], label)
                pools = dict(zip(context['playerIds'], history.pools(context['playerIds'])))
                stage = ('blind' if not context['allyPicks'] and not context['enemyPicks']
                         else 'late' if len(context['allyPicks']) >= 3 else 'early')
                for variant in VARIANTS:
                    start = perf_counter()
                    result = recommend(context, history, variant)
                    latency = (perf_counter() - start) * 1000
                    violations = sum(not legal(row, context, pools) for row in result['candidates'])
                    for cohort in ('all', stage, 'patch:' + context['patch'], 'league:' + context['league']):
                        metrics[variant][cohort].add(result, label, latency, violations)
                    line(predictions, {'caseId': context['caseId'], 'variant': variant, **result})
                    line(streams['timings.jsonl'], {'caseId': context['caseId'], 'variant': variant,
                                                  'latencyMs': latency})
            if evaluated % 100 == 0:
                print(f'Evaluated {evaluated} validation games', flush=True)
    report = {'status': 'PROVISIONAL_NOT_ML_READY', 'evaluatedGames': evaluated,
              'splits': {k: len(v) for k, v in groups.items()}, 'skipped': dict(skipped),
              'metrics': {v: {c: m.report() for c, m in cohorts.items()} for v, cohorts in metrics.items()}}
    write_json(output / 'report.json', report)
    if code_hashes() != source_hashes:
        raise ValueError('Benchmark source changed during evaluation; output is incomplete')
    artifacts = {p.name: digest(p.read_bytes()) for p in sorted(output.iterdir()) if p.is_file()}
    write_json(output / 'manifest.json', {
        'version': 1, 'algorithm': 'team-pool-uncertain-offline-v1',
        'status': 'PROVISIONAL_NOT_ML_READY', 'input': provenance,
        'validationStart': validation_start, 'testStart': test_start, 'embargoDays': 7,
        'historyPolicy': 'frozen_reference_only', 'evidenceThrough': history.latest_date,
        'maxGames': max_games, 'sampling': 'evenly_spaced_chronological_eligible_games',
        'weights': WEIGHTS, 'betaPrior': [25, 25], 'python': platform.python_version(),
        'codeSha256': source_hashes,
        'artifacts': artifacts,
        'limitations': [
            'Pick/ban columns assumed chronological; not independently verified.',
            'Series IDs/Fearless rules unavailable; seven-day embargo is not proof of series isolation.',
            'Roster identities assumed pre-draft known; no final roles or player/champion pairs in contexts.',
            'Observed pro pools are frequency proxies, not user comfort or complete playable pools.',
            'No historical composition traits: composition stays neutral; rules variant measures assignment flexibility only.',
            'Stats pool reference patches/leagues; no current-patch meta or causal interpretation.',
            'Ally pairs are role-agnostic associations; lane matchups and team-history remain neutral.',
            'Top-3 agreement is imitation, not win improvement. Score is not a probability.',
            'No model trained; test labels unscored. Training feature generation needs temporal snapshots.',
        ]})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--provisional-replay', action='store_true')
    parser.add_argument('--max-games', type=int)
    parser.add_argument('--validation-start', default='2025-01-01')
    parser.add_argument('--test-start', default='2026-01-01')
    args = parser.parse_args()
    report = run(args.prepared, args.output, args.provisional_replay, args.max_games,
                 args.validation_start, args.test_start)
    print(json.dumps({'status': report['status'], 'evaluatedGames': report['evaluatedGames'],
                      'output': str(args.output)}, indent=2))


if __name__ == '__main__':
    main()
