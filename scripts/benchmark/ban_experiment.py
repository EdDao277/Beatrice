"""Separate earlier-only next-ban imitation research; production Java bans stay authoritative."""
import argparse
from collections import Counter, defaultdict
from contextlib import ExitStack
from datetime import datetime, timedelta
import gzip
import hashlib
from itertools import zip_longest
import json
import math
import os
from pathlib import Path
import platform
from time import perf_counter

os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('OMP_NUM_THREADS', '1')
import numpy as np

from baseline import posterior
from compact_dataset import compressed_stream, file_hash
from evaluate import line, sample_indices, write_json
from linear_ranker import fit as fit_linear, score
from source_audit import audit_sources
from temporal import EarlierHistory, dataset_partitions

SIGNAL = 'pro_ban_imitation'
PROTOCOL = 'publisher-ordinal-bans-conditional-standard-opening-game-v1'
FEATURE_NAMES = (
    'enemy_max_log_games', 'enemy_total_log_games', 'enemy_observed_fraction', 'enemy_missing',
    'own_max_log_games', 'own_total_log_games', 'own_observed_fraction', 'own_missing',
    'ban_log_count', 'ban_rate_per_completed_game', 'ban_missing',
    'champion_posterior_delta', 'champion_log_games', 'champion_reliability',
    'champion_missing', 'champion_small_sample',
    'enemy_synergy_mean_delta', 'enemy_synergy_max_delta', 'enemy_synergy_supported_fraction',
    'enemy_synergy_log_games', 'enemy_synergy_missing',
    'second_phase', 'red_side', 'action_fraction', 'visible_enemy_count',
    'late_enemy_familiarity', 'late_own_opportunity_proxy', 'late_ban_popularity',
)
SCHEMA = {
    'version': 1, 'signal': SIGNAL, 'featureNames': list(FEATURE_NAMES),
    'protocol': PROTOCOL, 'matrix': 'x[candidateIndex][featureIndex]',
    'candidateOrder': 'championIds ascending; names are not predictive features',
    'objective': 'next recorded professional ban, not causal ban utility',
    'rosterHistory': 'earlier observed familiarity for all five players; not saved comfort or capability',
    'championResults': 'earlier pooled results, Beta(25,25), reliability games/(games+50)',
    'enemySynergy': 'candidate plus currently visible enemy champions as potential allies; shrunk pair-minus-two-baselines',
    'ownOpportunityCost': 'earlier own-roster familiarity proxy; no future picks or saved pools',
    'candidateEvidence': 'at least one earlier ban or at least 30 earlier champion games',
    'supportMeaning': 'research imitation support, never production threat certification',
    'vocabulary': 'union of earlier played and earlier banned champion identities',
    'missingEvidence': 'explicit masks; missing synergy delta is neutral zero',
    'unsupported': ['historically versioned composition metadata', 'lane-specific matchup threats',
                    'authoritative saved comfort', 'known final roles', 'causal utility', 'calibrated confidence'],
    'excludedPredictionInputs': ['outcome', 'final champion-player assignment', 'future draft actions',
                                 'future or own-game observations', 'reserved-test observations'],
}
CODE_FILES = ('ban_experiment.py', 'linear_ranker.py', 'compact_dataset.py', 'ml_features.py',
              'source_audit.py', 'temporal.py', 'baseline.py', 'protocol.py', 'evaluate.py')


def code_hashes():
    return {name: file_hash(Path(__file__).with_name(name)) for name in CODE_FILES}


def ban_cases(game):
    """Replay documented team ordinals under the explicit conditional 20-action schedule."""
    if not game['draftFieldsComplete']:
        return
    teams = {team['side']: team for team in game['teams']}
    if (teams['BLUE']['firstPickRaw'] not in ('1', '1.0')
            or teams['RED']['firstPickRaw'] not in ('0', '0.0')):
        raise ValueError('Unconfirmed BLUE first-pick field')
    order = 'BLUE RED BLUE RED BLUE RED BLUE RED RED BLUE BLUE RED RED BLUE RED BLUE RED BLUE BLUE RED'.split()
    counts = {(side, kind): 0 for side in teams for kind in ('picks', 'bans')}
    visible = []
    for index, side in enumerate(order):
        kind = 'bans' if index < 6 or 12 <= index < 16 else 'picks'
        champion = teams[side][kind][counts[side, kind]]
        if not champion or champion in {action['championId'] for action in visible}:
            raise ValueError('Missing/duplicate champion in draft fields')
        if kind == 'bans':
            enemy = 'RED' if side == 'BLUE' else 'BLUE'
            context = {
                'caseId': f"{game['gameId']}:ban:{index}", 'gameId': game['gameId'],
                'date': game['date'], 'patch': game['patch'], 'league': game['league'],
                'side': side, 'actionIndex': index, 'banPhase': 'first' if index < 6 else 'second',
                'protocol': PROTOCOL,
                'playerIds': sorted(player['playerId'] for player in teams[side]['players']),
                'enemyPlayerIds': sorted(player['playerId'] for player in teams[enemy]['players']),
                'allyPicks': [a['championId'] for a in visible if a['kind'] == 'picks' and a['side'] == side],
                'enemyPicks': [a['championId'] for a in visible if a['kind'] == 'picks' and a['side'] != side],
                'bans': [a['championId'] for a in visible if a['kind'] == 'bans'],
                'protectedPicks': [], 'intendedPicks': [],
            }
            yield context, {'caseId': context['caseId'], 'championId': champion}
        visible.append({'side': side, 'kind': kind, 'championId': champion})
        counts[side, kind] += 1


class BanHistory(EarlierHistory):
    """Ban observations advance only for games already admitted by EarlierHistory."""
    def __init__(self, games):
        super().__init__(games)
        self.ban_counts = Counter()
        self.completed_games = 0

    def advance(self, day):
        previous = self.index
        snapshot = super().advance(day)
        for game in self.games[previous:self.index]:
            # Partial old histories can still supply an unordered prior ban observation.
            # Counting a champion once per game avoids malformed duplicate ban inflation.
            self.ban_counts.update({champion for team in game['teams'] for champion in team['bans'] if champion})
            self.completed_games += 1
        return snapshot


def blocked_champions(context):
    return {champion for key in ('allyPicks', 'enemyPicks', 'bans', 'protectedPicks', 'intendedPicks')
            for champion in context.get(key, [])}


def recommend(context, earlier):
    """Build legal research candidates without access to any target label."""
    history = earlier.history
    for key in ('playerIds', 'enemyPlayerIds'):
        ids = context[key]
        if len(ids) != 5 or len(set(ids)) != 5 or not all(ids):
            raise ValueError('Five distinct known players required on each roster')
    blocked = blocked_champions(context)
    vocabulary = set(history.champions) | set(earlier.ban_counts)
    candidates, vectors, evidence, popular, missing = [], [], [], [], []
    phase = int(context['banPhase'] == 'second')
    for champion in sorted(vocabulary - blocked):
        games, wins = history.champions.get(champion, (0, 0))
        bans = earlier.ban_counts.get(champion, 0)
        if not bans and games < 30:
            continue
        own = {player: history.players.get(player, {}).get(champion, 0) for player in context['playerIds']}
        enemy = {player: history.players.get(player, {}).get(champion, 0) for player in context['enemyPlayerIds']}
        own_total, enemy_total = sum(own.values()), sum(enemy.values())
        meta_rate = posterior(games, wins)
        pairs, deltas = [], []
        for visible in context['enemyPicks']:
            pair_games, pair_wins = history.pairs.get(tuple(sorted((champion, visible))), (0, 0))
            other_games, other_wins = history.champions.get(visible, (0, 0))
            if not pair_games or not games or not other_games:
                continue
            support = min(pair_games, games, other_games)
            delta = (posterior(pair_games, pair_wins) - (meta_rate + posterior(other_games, other_wins)) / 2) * support / (support + 50)
            deltas.append(delta)
            pairs.append({'visibleEnemyChampionId': visible, 'games': pair_games, 'wins': pair_wins,
                          'support': support, 'smallSample': support < 30, 'shrunkDelta': delta,
                          'candidateBaseline': {'games': games, 'wins': wins},
                          'enemyBaseline': {'games': other_games, 'wins': other_wins}})
        masks = {'enemyFamiliarity': not enemy_total, 'ownFamiliarity': not own_total,
                 'championResults': not games, 'banFrequency': not bans, 'enemySynergy': not pairs,
                 'compositionMetadata': True, 'laneMatchup': True, 'authoritativeComfort': True,
                 'calibratedConfidence': True}
        enemy_log, own_log, ban_log = math.log1p(enemy_total), math.log1p(own_total), math.log1p(bans)
        values = [math.log1p(max(enemy.values())), enemy_log, sum(v > 0 for v in enemy.values()) / 5, int(not enemy_total),
                  math.log1p(max(own.values())), own_log, sum(v > 0 for v in own.values()) / 5, int(not own_total),
                  ban_log, bans / max(1, earlier.completed_games), int(not bans),
                  meta_rate - .5, math.log1p(games), games / (games + 50), int(not games), int(games < 30),
                  sum(deltas) / len(deltas) if deltas else 0., max(deltas) if deltas else 0.,
                  sum(p['support'] >= 30 for p in pairs) / max(1, len(context['enemyPicks'])),
                  math.log1p(sum(p['games'] for p in pairs)), int(not pairs), phase, int(context['side'] == 'RED'),
                  context['actionIndex'] / 19, len(context['enemyPicks']), phase * enemy_log, phase * own_log, phase * ban_log]
        if len(values) != len(FEATURE_NAMES) or not all(math.isfinite(v) for v in values):
            raise ValueError('Invalid ban feature vector')
        candidates.append(champion)
        vectors.append(values)
        popular.append(bans)
        # This measures missing supported groups, not the constant unsupported product groups.
        missing.append(bool(not games or not enemy_total or not own_total
                            or (context['enemyPicks'] and not pairs)))
        evidence.append({'championId': champion, 'enemyPlayerChampionGames': enemy,
                         'ownPlayerChampionGames': own, 'ownOpportunityCostSource': 'prior_pro_familiarity_proxy',
                         'banFrequency': {'gamesBanned': bans, 'completedGames': earlier.completed_games},
                         'championResults': {'games': games, 'wins': wins, 'posterior': meta_rate,
                                             'reliability': games / (games + 50), 'smallSample': games < 30},
                         'enemySynergy': pairs, 'missing': masks,
                         'supportReason': 'earlier_ban_observation' if bans else 'at_least_30_earlier_champion_games',
                         'productionThreatCertified': False})
    return {'championIds': candidates, 'x': vectors, 'baselineScores': popular,
            'missingEvidence': missing, 'evidence': evidence,
            'abstention': None if candidates else 'insufficient_prior_imitation_evidence'}


def fit(cases):
    """Generic feature-width linear fitter with a separate, explicit ban signal contract."""
    model = fit_linear(cases)
    model.update(signal=SIGNAL, scoreMeaning='uncalibrated next-ban imitation preference; not threat utility')
    return model


def measure(records):
    n = len(records)
    if not n:
        raise ValueError('Cannot measure empty cohort')
    ranks = [row['rank'] for row in records]
    returned = sum(row['count'] for row in records)
    absent = sum(rank is None for rank in ranks)
    latency = [row['latencyMs'] for row in records]
    return {'cases': n, 'candidateCoverage': 1 - absent / n, 'targetAbsentCases': absent,
            'targetAbsentRate': absent / n, 'targetUnavailableRate': absent / n,
            **{f'top{k}Agreement': sum(rank is not None and rank <= k for rank in ranks) / n for k in (1, 3, 5)},
            'mrr': sum(1 / rank if rank else 0 for rank in ranks) / n,
            'abstentions': sum(row['count'] == 0 for row in records), 'returnedCandidates': returned,
            'illegalSuggestionRate': sum(row.get('illegal', 0) for row in records) / returned if returned else 0.,
            'missingEvidenceRate': sum(row['missingEvidence'] for row in records) / n,
            'meanInferenceLatencyMs': float(np.mean(latency)), 'p95InferenceLatencyMs': float(np.quantile(latency, .95)),
            'impossibleLineupRate': None, 'impossibleLineupMeaning': 'not applicable to ban imitation',
            'meanEndToEndLatencyMs': float(np.mean([r.get('featureMs', 0) + r['latencyMs'] for r in records]))}


def build(prepared, raw_dir, output, max_training=None, max_validation=None,
          training_start='2024-04-01', validation_start='2025-01-01', test_start='2026-01-01'):
    for limit in (max_training, max_validation):
        if limit is not None and (type(limit) is not int or limit <= 0):
            raise ValueError('Sample limits must be positive integers')
    if output.exists():
        raise FileExistsError(output)
    started, hashes = perf_counter(), code_hashes()
    games, audit, provenance = audit_sources(prepared, raw_dir)
    inputs = {prepared / 'games.jsonl': provenance['gamesSha256'], prepared / 'report.json': provenance['reportSha256']}
    inputs.update({raw_dir / item['filename']: item['sha256'] for item in provenance['rawSources']})
    parts = dataset_partitions(games, training_start, validation_start, test_start)
    selected, eligible_counts, exclusions = {}, {}, []
    for split, limit in (('training', max_training), ('validation', max_validation)):
        eligible = [game for game in parts[split] if audit[game['gameId']]['eligible']]
        if not eligible:
            raise ValueError('No supported opening games in ' + split)
        eligible_counts[split] = len(eligible)
        keep = sample_indices(len(eligible), limit)
        selected[split] = [game for i, game in enumerate(eligible) if i in keep]
        selected_ids = {game['gameId'] for game in selected[split]}
        for game in parts[split]:
            reasons = audit[game['gameId']]['reasons'] or ([] if game['gameId'] in selected_ids else ['sample_limit'])
            if reasons:
                exclusions.append({'gameId': game['gameId'], 'split': split, 'reasons': reasons})
        print(f"BAN {split}: selected {len(selected[split])}/{len(eligible)} eligible opening games", flush=True)
    test_ids = {game['gameId'] for game in parts['test']}
    earlier = BanHistory([game for game in games if game['gameId'] not in test_ids])
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / 'splits.json', {split: [game['gameId'] for game in cohort] for split, cohort in parts.items()})
    write_json(output / 'feature-schema.json', SCHEMA)
    checks = Counter(cases=0, candidateLegalityChecks=0, illegalCandidates=0, targetAbsentCases=0, abstentions=0)
    exported, snapshots = Counter(), set()
    with ExitStack() as stack:
        streams = {name: compressed_stream(stack, output / (name + '.jsonl.gz'))
                   for name in ('contexts', 'labels', 'features', 'evidence', 'snapshots', 'source-audit', 'exclusions')}
        for row in audit.values():
            line(streams['source-audit'], {**row, 'banOrderSemantics': 'publisher_documented_team_ordinal',
                                          'crossTeamSchedule': 'conditional_standard20_not_individually_certified'})
        for row in exclusions:
            line(streams['exclusions'], row)
        for split in ('training', 'validation'):
            for game in selected[split]:
                snapshot = earlier.advance(game['date'][:10])
                if snapshot['snapshotId'] not in snapshots:
                    snapshots.add(snapshot['snapshotId'])
                    line(streams['snapshots'], snapshot)
                for context, label in ban_cases(game):
                    context.update(split=split, snapshotId=snapshot['snapshotId'],
                                   evidenceThrough=earlier.history.latest_date,
                                   seriesCandidateId=audit[game['gameId']]['seriesCandidateId'])
                    before = perf_counter()
                    result = recommend(context, earlier)
                    feature_ms = (perf_counter() - before) * 1000
                    illegal = len(set(result['championIds']) & blocked_champions(context))
                    if illegal or len(set(result['championIds'])) != len(result['championIds']):
                        raise ValueError('Illegal/duplicate ban candidate')
                    checks.update(cases=1, candidateLegalityChecks=len(result['championIds']), illegalCandidates=illegal,
                                  targetAbsentCases=int(label['championId'] not in result['championIds']),
                                  abstentions=int(not result['championIds']))
                    line(streams['contexts'], context)
                    line(streams['labels'], {**label, 'split': split, 'caseWeight': .1})
                    line(streams['features'], {key: result[key] for key in (
                        'championIds', 'x', 'baselineScores', 'missingEvidence', 'abstention')} | {
                        'caseId': context['caseId'], 'snapshotId': snapshot['snapshotId'], 'split': split, 'featureMs': feature_ms})
                    line(streams['evidence'], {'caseId': context['caseId'], 'candidates': result['evidence']})
                exported[split] += 1
                if exported[split] % 100 == 0:
                    print(f"BAN {split}: {exported[split]}/{len(selected[split])}; {perf_counter() - started:.1f}s", flush=True)
    if hashes != code_hashes():
        raise ValueError('Code changed during ban export; output is incomplete')
    for path, expected in inputs.items():
        if file_hash(path) != expected:
            raise ValueError('Input changed during ban export; output is incomplete: ' + str(path))
    report = {'signal': SIGNAL, 'exportedGames': dict(exported), 'eligibleOpeningGames': eligible_counts,
              'checks': dict(checks), 'elapsedSeconds': perf_counter() - started, 'testUnscored': True}
    write_json(output / 'report.json', report)
    write_json(output / 'manifest.json', {
        'version': 1, 'status': 'BAN_IMITATION_OPENING_GAME_EXPORT', 'signal': SIGNAL,
        'input': provenance, 'codeSha256': hashes,
        'artifacts': {path.name: file_hash(path) for path in sorted(output.iterdir()) if path.is_file()},
        'trainingStart': training_start, 'validationStart': validation_start, 'testStart': test_start,
        'labelEmbargoDays': 7, 'historyLagDays': 1, 'historyPolicy': 'expanding_earlier_only',
        'historyPopulation': 'all_prepared_earlier_games_except_reserved_test',
        'validationProtocol': 'earlier_validation_observations_after_lag_no_parameter_fit',
        'maxTrainingGames': max_training, 'maxValidationGames': max_validation,
        'sampling': 'all_eligible_unless_explicit_evenly_spaced_limit', 'testUnscored': True,
        'selectedGames': dict(exported), 'python': platform.python_version(),
        'protocol': PROTOCOL, 'sourceInputsVerifiedAfterExport': True,
        'limitations': ['Team-relative ban ordinals documented; standard cross-team schedule conditional.',
                       'Opening games only; event-specific chronology and availability not independently certified.',
                       'Pro observations are proxies, not authoritative saved pools or user comfort.',
                       'Candidate support is imitation evidence, not proof of a positive production threat.',
                       'No role/composition metadata invented; no future intended pick inferred.',
                       'Recorded ban agreement is not causal utility or win probability.']})
    return report


def rows(folder, name):
    with gzip.open(folder / (name + '.jsonl.gz'), 'rt', encoding='utf-8') as stream:
        for value in stream:
            yield json.loads(value)


def verify_dataset(dataset):
    manifest = json.loads((dataset / 'manifest.json').read_text(encoding='utf-8'))
    if (manifest.get('version') != 1 or manifest.get('status') != 'BAN_IMITATION_OPENING_GAME_EXPORT'
            or manifest.get('signal') != SIGNAL or manifest.get('testUnscored') is not True
            or manifest.get('historyPolicy') != 'expanding_earlier_only' or manifest.get('historyLagDays') != 1):
        raise ValueError('Requires an earlier-only ban imitation export')
    required = {name + '.jsonl.gz' for name in ('contexts', 'labels', 'features', 'evidence', 'snapshots', 'source-audit', 'exclusions')}
    required.update(('feature-schema.json', 'splits.json', 'report.json'))
    for name in required:
        if file_hash(dataset / name) != manifest['artifacts'].get(name):
            raise ValueError('Input hash mismatch: ' + name)
    if json.loads((dataset / 'feature-schema.json').read_text(encoding='utf-8')) != SCHEMA:
        raise ValueError('Incompatible ban feature schema')
    parts = json.loads((dataset / 'splits.json').read_text(encoding='utf-8'))
    all_ids = [game_id for ids in parts.values() for game_id in ids]
    if len(all_ids) != len(set(all_ids)):
        raise ValueError('Overlapping partitions')
    bounds = [datetime.fromisoformat(manifest[key]) for key in ('trainingStart', 'validationStart', 'testStart')]
    if not bounds[0] < bounds[1] < bounds[2] <= datetime(2026, 1, 1):
        raise ValueError('Invalid or unsealed test boundary')
    snapshots = {}
    for snapshot in rows(dataset, 'snapshots'):
        sid = snapshot['snapshotId']
        cutoff = datetime.fromisoformat(snapshot['exclusiveCutoff'])
        ids = set(snapshot['sourceGameIds'])
        if (sid in snapshots or ids.intersection(parts['test'])
                or snapshot['latestObservation'] and datetime.fromisoformat(snapshot['latestObservation']) >= cutoff):
            raise ValueError('Invalid snapshot or reserved-test history')
        snapshots[sid] = (cutoff, ids)
    return manifest, parts, bounds, snapshots


def joined_cases(dataset, verified):
    _, parts, bounds, snapshots = verified
    seen, counts, seen_snapshots = set(), defaultdict(set), set()
    streams = (rows(dataset, name) for name in ('contexts', 'labels', 'features'))
    for context, label, feature in zip_longest(*streams):
        if any(row is None for row in (context, label, feature)):
            raise ValueError('Incomplete context/label/feature join')
        key, split, game_id = context['caseId'], context['split'], context['gameId']
        if (key in seen or key != label['caseId'] or key != feature['caseId']
                or split not in ('training', 'validation') or label['split'] != split or feature['split'] != split
                or game_id not in parts[split] or context['protocol'] != PROTOCOL or label['caseWeight'] != .1):
            raise ValueError('Invalid case join/split/protocol')
        seen.add(key)
        counts[game_id].add(context['actionIndex'])
        if context['banPhase'] != ('first' if context['actionIndex'] < 6 else 'second'):
            raise ValueError('Invalid ban phase')
        day = datetime.fromisoformat(context['date'])
        start, stop = (bounds[0], bounds[1]) if split == 'training' else (bounds[1], bounds[2])
        if not start <= day < stop - timedelta(days=7):
            raise ValueError('Case violates partition embargo')
        sid = context['snapshotId']
        if sid not in snapshots or sid != feature['snapshotId']:
            raise ValueError('Missing or mismatched snapshot')
        seen_snapshots.add(sid)
        cutoff, source_ids = snapshots[sid]
        if cutoff != datetime.fromisoformat(context['date'][:10]) - timedelta(days=1) or game_id in source_ids:
            raise ValueError('Own-game or future history leakage')
        ids = feature['championIds']
        x = np.asarray(feature['x'], dtype=float).reshape(-1, len(FEATURE_NAMES))
        if (len(ids) != len(set(ids)) or ids != sorted(ids) or set(ids) & blocked_champions(context)
                or len(x) != len(ids) or not np.isfinite(x).all()
                or len(feature['baselineScores']) != len(ids) or len(feature['missingEvidence']) != len(ids)):
            raise ValueError('Invalid/illegal candidate matrix')
        target = label['championId']
        yield context, feature, {'x': x, 'ids': ids, 'target': ids.index(target) if target in ids else None,
                                'targetId': target, 'weight': .1, 'gameId': game_id, 'split': split}
    if not seen or seen_snapshots != snapshots.keys() or any(indices != {0, 1, 2, 3, 4, 5, 12, 13, 14, 15} for indices in counts.values()):
        raise ValueError('Expected ten distinct ban decisions per whole game and all snapshots referenced')


def train(dataset, output, max_negatives=16):
    if type(max_negatives) is not int or max_negatives < 1:
        raise ValueError('Negative limit must be positive')
    if output.exists():
        raise FileExistsError(output)
    before, hashes = perf_counter(), code_hashes()
    manifest_hash = file_hash(dataset / 'manifest.json')
    verified = verify_dataset(dataset)
    training, covered, games = [], Counter(), set()
    missing_targets, without_alternatives, original_comparisons = 0, 0, 0
    for context, _, case in joined_cases(dataset, verified):
        if case['split'] != 'training':
            continue
        games.add(case['gameId'])
        missing_targets += case['target'] is None
        without_alternatives += len(case['ids']) < 2
        if case['target'] is None or len(case['ids']) < 2:
            continue
        alternatives = [i for i in range(len(case['ids'])) if i != case['target']]
        original_comparisons += len(alternatives)
        # Uniform negatives are comparisons, never labels that those bans are bad.
        # Derive the seed per case so sampling is stable across batching and process order.
        seed = int(hashlib.sha256(context['caseId'].encode()).hexdigest()[:16], 16)
        rng = np.random.default_rng(seed)
        negative = sorted(rng.choice(alternatives, size=min(max_negatives, len(alternatives)), replace=False).tolist())
        selected = [case['target'], *negative]
        training.append({'x': case['x'][selected], 'target': 0, 'weight': .1, 'gameId': case['gameId']})
        covered[case['gameId']] += 1
    for case in training:
        case['weight'] = 1 / covered[case['gameId']]
    print(f"BAN fit: {len(training)} covered actions, {len(covered)} games, <= {max_negatives} negatives/action", flush=True)
    fitting = perf_counter()
    model = fit(training)
    fit_seconds = perf_counter() - fitting
    del training
    model.update(featureNames=list(FEATURE_NAMES), schemaVersion=SCHEMA['version'],
                 negativeSampling={'policy': 'uniform_without_replacement_per_case', 'limit': max_negatives,
                                   'seed': 'first 16 SHA256 hex digits of caseId',
                                   'fullCandidateComparisons': original_comparisons,
                                   'normalizationPopulation': 'training target and uniformly sampled alternatives only'})
    model['configuration']['negativePolicy'] = 'uniformly sampled alternatives; equal mass per covered case and game'
    model = json.loads(json.dumps(model, allow_nan=False))
    output.mkdir(parents=True, exist_ok=False)
    records = {split: {name: [] for name in ('linear', 'ban_popularity')} for split in ('training', 'validation')}
    phases = {split: {phase: {name: [] for name in ('linear', 'ban_popularity')} for phase in ('first', 'second')}
              for split in records}
    by_game, examples = defaultdict(list), {kind: [] for kind in ('linear_wins', 'baseline_wins', 'both_miss', 'target_absent', 'low_margin')}
    with ExitStack() as stack:
        predictions = compressed_stream(stack, output / 'predictions.jsonl.gz')
        for context, feature, case in joined_cases(dataset, verified):
            split, ids, target = case['split'], case['ids'], case['targetId']
            ranked, results, scores = {}, {}, {}
            for name in ('linear', 'ban_popularity'):
                timing = perf_counter()
                values = score(model, case['x']) if name == 'linear' else np.asarray(feature['baselineScores'], dtype=float)
                order = sorted(range(len(ids)), key=lambda i: (-values[i], ids[i]))
                latency = (perf_counter() - timing) * 1000
                ranked[name] = [ids[i] for i in order]
                scores[name] = (values, order)
                result = {'rank': ranked[name].index(target) + 1 if target in ids else None,
                          'count': len(ids), 'latencyMs': latency, 'featureMs': feature['featureMs'],
                          'missingEvidence': not order or feature['missingEvidence'][order[0]],
                          'illegal': len(set(ranked[name]) & blocked_champions(context))}
                results[name] = result
                records[split][name].append(result)
                phases[split][context['banPhase']][name].append(result)
            values, order = scores['linear']
            line(predictions, {'caseId': context['caseId'], 'split': split, 'signal': SIGNAL,
                               'scoreMeaning': model['scoreMeaning'], 'confidence': None,
                               'abstention': feature['abstention'], 'evidenceRef': {'file': str((dataset / 'evidence.jsonl.gz').resolve()), 'caseId': context['caseId']},
                               'candidates': [{'championId': ids[i], 'rank': rank, 'score': float(values[i])}
                                              for rank, i in enumerate(order, 1)],
                               'baselineOrder': ranked['ban_popularity']})
            if split == 'validation':
                a, b = results['linear']['rank'], results['ban_popularity']['rank']
                a_hit, b_hit = a is not None and a <= 3, b is not None and b <= 3
                by_game[case['gameId']].append(int(a_hit) - int(b_hit))
                margin = float(values[order[0]] - values[order[1]]) if len(order) > 1 else None
                kinds = (['target_absent'] if a is None else ['linear_wins'] if a_hit and not b_hit
                         else ['baseline_wins'] if b_hit and not a_hit else ['both_miss'] if not a_hit and not b_hit else [])
                if margin is not None and margin < .05:
                    kinds.append('low_margin')
                for kind in kinds:
                    if len(examples[kind]) < 10:
                        examples[kind].append({'caseId': context['caseId'], 'gameId': case['gameId'],
                                               'banPhase': context['banPhase'], 'patch': context['patch'],
                                               'target': target, 'linearRank': a, 'baselineRank': b,
                                               'linearTop5': ranked['linear'][:5], 'baselineTop5': ranked['ban_popularity'][:5],
                                               'scoreMargin': margin, 'visibleEnemies': context['enemyPicks'],
                                               'evidenceRef': context['caseId']})
    delta = np.asarray([np.mean(values) for values in by_game.values()])
    if not len(delta):
        raise ValueError('Validation decisions required')
    rng = np.random.default_rng(1729)
    bootstrap = [float(rng.choice(delta, len(delta), replace=True).mean()) for _ in range(2000)]
    report = {'signal': SIGNAL, 'testUnscored': True,
              'metrics': {split: {name: measure(rows_) for name, rows_ in methods.items()} for split, methods in records.items()},
              'byPhase': {split: {phase: {name: measure(rows_) for name, rows_ in methods.items()}
                                  for phase, methods in phase_map.items()} for split, phase_map in phases.items()},
              'validationComparison': {'top3Delta': float(delta.mean()), 'wholeGames': len(delta),
                                       'pairedGameBootstrap95': np.quantile(bootstrap, [.025, .975]).tolist()},
              'trainingGames': len(games), 'trainingGamesWithoutComparisons': len(games - covered.keys()),
              'trainingMissingTargets': missing_targets, 'trainingCasesWithoutAlternatives': without_alternatives,
              'fitSeconds': fit_seconds, 'elapsedSeconds': perf_counter() - before,
              'validationUsedForFitOrTuning': False, 'bestArtifact': 'model.json',
              'deploymentRecommendation': 'Retain Java evidence-bans-v1; this artifact measures imitation, not ban utility.',
              'latencyMeaning': 'inference includes model/scalar-prior scoring and sorting; end-to-end adds original evidence construction',
              'missingEvidenceMeaning': 'top-ranked candidate lacks own/opponent familiarity, champion results, or applicable visible-enemy pair evidence; abstention counts missing',
              'limitations': ['Fixed linear configuration and deterministic sampled training negatives; all legal candidates evaluated.',
                             'Training normalization uses sampled training rows only; no validation normalization.',
                             'Ban ordinals documented; per-event full chronology and champion availability not certified.',
                             'Pooled earlier patches/leagues; own-roster familiarity is an opportunity proxy, not saved comfort.',
                             'No calibrated confidence, causal utility, production threat certification, or win claim.',
                             'Bootstrap clusters by game, not team or verified series; uncertainty may be understated.']}
    if code_hashes() != hashes or file_hash(dataset / 'manifest.json') != manifest_hash or verify_dataset(dataset)[0] != verified[0]:
        raise ValueError('Input/code changed during training; output is incomplete')
    write_json(output / 'model.json', model)
    write_json(output / 'schema.json', SCHEMA)
    write_json(output / 'report.json', report)
    write_json(output / 'error-analysis.json', {'signal': SIGNAL, 'sampling': 'first ten chronological examples per category', 'examples': examples})
    write_json(output / 'manifest.json', {'version': 1, 'signal': SIGNAL, 'testUnscored': True,
               'datasetManifestSha256': manifest_hash, 'datasetArtifacts': verified[0]['artifacts'], 'codeSha256': hashes,
               'python': platform.python_version(), 'numpy': np.__version__,
               'artifacts': {path.name: file_hash(path) for path in sorted(output.iterdir()) if path.is_file()}})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    build_parser = commands.add_parser('build')
    build_parser.add_argument('--prepared', required=True, type=Path)
    build_parser.add_argument('--raw-dir', required=True, type=Path)
    build_parser.add_argument('--output', required=True, type=Path)
    build_parser.add_argument('--max-training-games', type=int)
    build_parser.add_argument('--max-validation-games', type=int)
    build_parser.add_argument('--training-start', default='2024-04-01')
    build_parser.add_argument('--validation-start', default='2025-01-01')
    build_parser.add_argument('--test-start', default='2026-01-01')
    train_parser = commands.add_parser('train')
    train_parser.add_argument('--dataset', required=True, type=Path)
    train_parser.add_argument('--output', required=True, type=Path)
    train_parser.add_argument('--max-negatives', type=int, default=16)
    args = parser.parse_args()
    if args.command == 'build':
        report = build(args.prepared, args.raw_dir, args.output, args.max_training_games, args.max_validation_games,
                       args.training_start, args.validation_start, args.test_start)
    else:
        report = train(args.dataset, args.output, args.max_negatives)
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
