"""Offline saved-pool comparison and capped-signal prototype; never a live adapter."""
import json
import math
import random
from pathlib import Path
import subprocess
from time import perf_counter
from datetime import datetime, timedelta
from collections import Counter

from readiness import FinalHistory, MODEL_HASH, completed_report
from recency_features import extend
from ml_features import vector
from protocol import load_prepared
from temporal import EarlierHistory
from scaled_train import read, write, sha, rows
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
JAVA = ROOT / 'backend/src/main/java/com/beatrice/backend/recommendation'


def compile_java(classes):
    classes.mkdir(parents=True, exist_ok=True)
    subprocess.run(['javac', '-d', str(classes), str(JAVA / 'RecommendationEngine.java'),
                    str(JAVA / 'WeightedRecommendations.java'),
                    str(Path(__file__).with_name('java') / 'ReadinessScorer.java')], check=True, capture_output=True)


def java_rank(scenarios, classes):
    lines = []
    for s in scenarios:
        lines.append('\t'.join(['S', s['id'], s['role'], ','.join(s['desired']),
                                ','.join(s['covered']), ','.join(s['unavailable'])]))
        for c in s['pool']:
            lines.append('\t'.join(['P', c['id'], str(c['comfort']), ','.join(c['traits']), '1' if c['known'] else '0']))
        lines.append('END')
    process = subprocess.run(['java', '-cp', str(classes), 'ReadinessScorer'], input='\n'.join(lines)+'\n',
                             text=True, capture_output=True, check=True, timeout=120)
    result = {s['id']: [] for s in scenarios}
    done = set()
    for line in process.stdout.splitlines():
        p = line.split('\t')
        if p[0] == 'DONE':
            done.add(p[1])
        else:
            result[p[1]].append({'id': p[2], 'score': float(p[3])})
    if done != result.keys():
        raise ValueError('Java did not return every scenario')
    return result


def bounded(java, scores, gates, cap=2.5):
    """Research-only: fail closed, never introduce/remove candidates or penalize unknowns."""
    if not 0 <= cap <= 2.5:
        raise ValueError('Offline influence exceeds fixed safety cap')
    if not scores or set(scores) != {r['id'] for r in java} or any(not math.isfinite(v) for v in scores.values()):
        return java
    if len(scores) < 2 or max(scores.values()) == min(scores.values()):
        return java
    # Ranking preference is uncalibrated. Positive-only percentile bonus bounds influence
    # without subtracting points from cold-start champions or claiming probability.
    ordered = sorted(scores, key=lambda c: (scores[c], c))
    bonus = {c: cap * i / (len(ordered)-1) if gates.get(c, False) else 0.
             for i, c in enumerate(ordered)}
    adjusted = [{**r, 'score': r['score'] + bonus[r['id']]} for r in java]
    return sorted(adjusted, key=lambda r: (-r['score'], r['id']))


def metadata_traits(snapshot):
    result = {}
    for row in snapshot['metadata']:
        raw = row['raw_metadata']
        tags = set()
        for field in ('utility_tags', 'comp_tags'):
            value = raw.get(field)
            tags.update(value if isinstance(value, list) else
                        (t.strip() for t in str(value or '').strip('{}[]').replace('"', '').split(',') if t.strip()))
        damage = raw.get('damage_type')
        if damage in ('AP', 'Mixed'): tags.add('AP')
        if damage in ('AD', 'Mixed'): tags.add('AD')
        known = raw.get('utility_tags') is not None and raw.get('comp_tags') is not None and damage in ('AP', 'AD', 'Mixed', 'True')
        result[row['champion_id']] = {'traits': sorted(tags) if known else [], 'known': known}
    return result


def realized_composition(category, ally_traits):
    if len(ally_traits) < 3:
        return False
    if category in ('heavyAP', 'heavyAD'):
        damage = category[5:]
        opposite = 'AD' if damage == 'AP' else 'AP'
        return sum(damage in t and opposite not in t for t in ally_traits) >= 3
    if category.startswith('no'):
        return all(category[2:] not in t for t in ally_traits)
    return False


def scenarios(snapshot, support, training_seen=None):
    """Seeded valid draft prefixes; stress-pool copies never modify the saved roster."""
    rng = random.Random(1729)
    catalog = sorted(c['id'] for c in snapshot['catalog']['champions'])
    names = {c['name'].casefold(): c['id'] for c in snapshot['catalog']['champions']}
    traits = metadata_traits(snapshot)
    result = []
    categories = ('real', 'flex', 'narrow', 'offmeta', 'sparse', 'unseen',
                  'heavyAP', 'heavyAD', 'noFrontline', 'noEngage', 'noPeel', 'empty')
    for team in snapshot['teams']:
        pools = [[{'id': names[c['name'].casefold()], 'comfort': c['comfort'],
                   **traits.get(names[c['name'].casefold()], {'traits': [], 'known': False})}
                  for c in p['champions']] for p in team['players']]
        for actor, player in enumerate(team['players']):
            for category in categories:
                pool = list(pools[actor])
                if category == 'narrow': pool = sorted(pool, key=lambda c: (-c['comfort'], c['id']))[:1]
                if category == 'offmeta': pool = sorted(pool, key=lambda c: (support.get(c['id'], 0), c['id']))[:4]
                if category in ('sparse', 'unseen'):
                    candidates = [c for c in catalog if (c not in training_seen if category == 'unseen' and training_seen is not None
                                  else support.get(c, 0) < (30 if category == 'sparse' else 1))]
                    if candidates:
                        c = candidates[0]
                        pool = [p for p in pool if p['id'] != c] + [{'id': c, 'comfort': 8,
                               **traits.get(c, {'traits': [], 'known': False})}]
                if category == 'empty': pool = []
                for mode in ('RANKED', 'TOURNAMENT'):
                    for side in ('BLUE', 'RED'):
                        for stage in ('blind', 'early', 'late'):
                            for repeat in range(2):
                                desired = (['AD'] if category == 'heavyAP' else ['AP'] if category == 'heavyAD' else
                                           [category[2:]] if category.startswith('no') else [])
                                full_allies, used = [], set()
                                for other in range(5):
                                    if other == actor: continue
                                    available = [c['id'] for c in pools[other] if c['id'] not in used]
                                    rng.shuffle(available)
                                    def prefer(c):
                                        tags = set(traits.get(c, {}).get('traits', []))
                                        return (0 if category == 'heavyAP' and 'AP' in tags and 'AD' not in tags else
                                                0 if category == 'heavyAD' and 'AD' in tags and 'AP' not in tags else
                                                0 if category.startswith('no') and category[2:] not in tags else 1)
                                    available.sort(key=prefer)
                                    if not available: break
                                    full_allies.append(available[0]); used.add(available[0])
                                if len(full_allies) != 4: continue
                                # The future fifth ally is only scaffolding; this prefix stops before that pick.
                                fifth = next(c for c in catalog if c not in used)
                                full_allies.append(fifth); used.add(fifth)
                                enemies = rng.sample([c for c in catalog if c not in used], 5)
                                used.update(enemies)
                                bans = rng.sample([c for c in catalog if c not in used], 10)
                                pick_sides = 'BLUE RED RED BLUE BLUE RED RED BLUE BLUE RED'.split()
                                prefix_picks = 0 if stage == 'blind' else (3 if side == 'BLUE' else 1) if stage == 'early' else (8 if side == 'BLUE' else 9)
                                count = {'BLUE': 0, 'RED': 0}
                                actions = []
                                if mode == 'RANKED':
                                    actions = [{'side': 'BLUE' if i < 5 else 'RED', 'kind': 'BAN', 'championId': c} for i, c in enumerate(bans)]
                                else:
                                    actions = [{'side': 'BLUE' if i % 2 == 0 else 'RED', 'kind': 'BAN', 'championId': c} for i, c in enumerate(bans[:6])]
                                for i, pick_side in enumerate(pick_sides[:prefix_picks]):
                                    if mode == 'TOURNAMENT' and i == 6:
                                        actions.extend({'side': 'RED' if j % 2 == 0 else 'BLUE', 'kind': 'BAN', 'championId': c} for j, c in enumerate(bans[6:]))
                                    choices = full_allies if pick_side == side else enemies
                                    actions.append({'side': pick_side, 'kind': 'PICK', 'championId': choices[count[pick_side]]})
                                    count[pick_side] += 1
                                allies = [a['championId'] for a in actions if a['kind'] == 'PICK' and a['side'] == side]
                                visible_enemies = [a['championId'] for a in actions if a['kind'] == 'PICK' and a['side'] != side]
                                covered = sorted({t for c in allies for t in traits.get(c, {}).get('traits', [])})
                                all_known = all(traits.get(c, {}).get('known', False) for c in allies)
                                result.append({'id': f"s{len(result):04}", 'teamId': team['id'], 'role': player['role'],
                                    'category': category, 'syntheticPool': category in ('narrow', 'offmeta', 'sparse', 'unseen', 'empty'),
                                    'mode': mode, 'side': side, 'stage': stage, 'actions': actions,
                                    'planningBeforeFirstPick': stage == 'blind' and side == 'RED',
                                    'allies': allies, 'enemies': visible_enemies,
                                    'pool': [dict(c, known=c['known'] and all_known) for c in pool],
                                    'compositionStressRealized': all_known and realized_composition(category, [set(traits.get(c, {}).get('traits', [])) for c in allies]),
                                    'desired': desired, 'covered': covered,
                                    'unavailable': [a['championId'] for a in actions],
                                    'flexPoolIds': sorted(c['id'] for c in pool if sum(any(p['id'] == c['id'] for p in row) for row in pools) > 1)})
    return result


class OfflineModel:
    def __init__(self, path, expected_hash):
        self.model = None
        try:
            if sha(path) != expected_hash:
                return
            import lightgbm as lgb
            model = lgb.Booster(model_file=str(path))
            if model.num_feature() == 108:
                self.model = model
        except Exception:
            pass

    def predict(self, x):
        try:
            if self.model is None or not isinstance(x, np.ndarray) or x.ndim != 2 or x.shape[1] != 108 or not np.isfinite(x).all():
                return None
            from tree_ranker import tree_score
            values = tree_score(self.model, x)
            return values if np.isfinite(values).all() else None
        except Exception:
            return None


def evidence_for(history, champion, allies, players):
    games, wins = history.champions.get(champion, (0, 0))
    pairs = []
    for ally in allies:
        n, w = history.pairs.get(tuple(sorted((champion, ally))), (0, 0))
        an, aw = history.champions.get(ally, (0, 0))
        if n and games and an:
            pairs.append({'ally': ally, 'games': n, 'wins': w, 'allyBaseline': {'games': an, 'wins': aw}})
    return {'playerChampionEvidence': {p: 0 for p in players},
            'evidence': {'meta': {'games': games, 'wins': wins} if games else None, 'allyPairs': pairs}}


def run():
    output = ROOT / 'data/oracle/saved-team-readiness'
    if (output / 'report.json').exists():
        raise FileExistsError('Scenario report already exists; do not tune against it')
    final = completed_report(ROOT / 'data/oracle/final-2026-readiness')
    snapshot_path = output / 'snapshot.json'
    snapshot = read(snapshot_path)
    # Fix the as-of day to the captured snapshot, never the wall clock on a rerun.
    day = snapshot['capturedAt'][:10]
    games, provenance = load_prepared(ROOT / 'data/oracle/prepared-2026-09-08-reviewed')
    compact = ROOT / 'data/oracle/compact-2026-09-11-resumable'
    cm = read(compact / 'manifest.json')
    if provenance['gamesSha256'] != cm['input']['gamesSha256']:
        raise ValueError('Professional history provenance changed')
    audit = {r['gameId']: r for r in rows(compact, 'source-audit')}
    temporal = EarlierHistory(games)
    history_snapshot = temporal.advance(day)
    history = temporal.history
    recent = FinalHistory([g for g in games if audit[g['gameId']]['eligible']])
    patch = '.'.join(snapshot['catalog']['version'].split('.')[:2])
    # Training exposure is explicit; it is not a hard champion-availability filter.
    last_training = max(r['date'] for r in rows(compact, 'contexts') if r['split'] == 'training')[:10]
    train_cutoff = datetime.fromisoformat(last_training) - timedelta(days=1)
    training_seen = {p['championId'] for g in games if datetime.fromisoformat(g['date']) < train_cutoff
                     for t in g['teams'] for p in t['players']}
    suite = scenarios(snapshot, {c: n for c, (n, _) in history.champions.items()}, training_seen)
    write(output / 'scenarios.json', suite)
    compile_java(output / 'java-classes')
    java = java_rank(suite, output / 'java-classes')
    model_path = ROOT / 'data/oracle/blind-2026-09-14-reviewed/recency_tree.txt'
    model = OfflineModel(model_path, MODEL_HASH)
    if model.model is None:
        raise ValueError('Approved model could not be loaded')
    table = recent.at(day, patch)
    results, totals = [], Counter()
    players = ['saved:' + str(i) for i in range(5)]
    for s in suite:
        ranked = java[s['id']]
        ids = [r['id'] for r in ranked]
        if len(set(ids)) != len(ids) or set(ids) != {c['id'] for c in s['pool']} - set(s['unavailable']):
            raise ValueError('Java candidate boundary mismatch')
        context = {'playerIds': players, 'allyPicks': s['allies'], 'enemyPicks': s['enemies']}
        start = perf_counter()
        x = np.asarray([vector(context, evidence_for(history, c, s['allies'], players)) for c in ids], dtype=np.float32).reshape(-1, 33)
        extended = extend(x, ids, context, table)
        values = model.predict(extended)
        ms = (perf_counter()-start)*1000
        scores = dict(zip(ids, map(float, values))) if values is not None else None
        ml = sorted(ids, key=lambda c: (-scores[c], c)) if scores else []
        support = {c: {'globalGames': history.champions.get(c, [0, 0])[0],
                       'recent30Picks': round(math.expm1(table.vector(c)[11])),
                       'patchGames': round(math.expm1(table.vector(c)[21])),
                       'priority30': table.vector(c)[10], 'seenInTrainingHistory': c in training_seen} for c in ids}
        evidence_gates = {c: e['seenInTrainingHistory'] and e['globalGames'] >= 30
                    and e['recent30Picks'] >= 5 and e['patchGames'] >= 30 for c, e in support.items()}
        gates = {c: final['acceptance']['passed'] and good for c, good in evidence_gates.items()}
        adjusted = bounded(ranked, scores, gates)
        if {r['id'] for r in adjusted} != set(ids):
            raise ValueError('ML introduced or removed a Java candidate')
        for r in adjusted:
            before = next(j['score'] for j in ranked if j['id'] == r['id'])
            if not 0 <= r['score']-before <= 2.5000001 or (not gates[r['id']] and r['score'] != before):
                raise ValueError('ML cap/zero-evidence gate violated')
        comfort = {c['id']: c['comfort'] for c in s['pool']}
        flags = []
        if ids and ml:
            top, jtop = ml[0], ids[0]
            if jtop not in ml[:5]: flags.append('java_top_outside_ml_top5')
            if not evidence_gates[top]: flags.append('ml_top_weak_or_unsupported')
            if comfort[jtop] - comfort[top] >= 3: flags.append('comfort_conflict')
            if comfort[jtop] - comfort[top] >= 3 and support[top]['priority30'] > 2 * support[jtop]['priority30']:
                flags.append('priority_over_comfort')
            if any(e['globalGames'] < 30 or not e['seenInTrainingHistory'] for e in support.values()):
                flags.append('rare_or_unseen_candidate')
            if ids[0] != adjusted[0]['id']: flags.append('bounded_top_changed')
        totals.update(flags)
        totals.update(scenarios=1, empty=int(not ids), candidates=len(ids), gatedCandidates=sum(gates.values()),
                      coldCandidates=sum(e['globalGames'] == 0 for e in support.values()))
        results.append({'id': s['id'], 'category': s['category'], 'stage': s['stage'], 'role': s['role'],
            'syntheticPool': s['syntheticPool'], 'java': ranked, 'ml': ml, 'bounded': adjusted,
            'compositionStressRealized': s['compositionStressRealized'],
            'flexCandidates': sorted(set(ids) & set(s['flexPoolIds'])),
            'scores': scores, 'support': support, 'gates': gates, 'comfort': comfort, 'flags': flags,
            'featureAndScoringMs': ms})
    write(output / 'observations.json', results)
    by_category = {}
    for category in sorted({s['category'] for s in suite}):
        group = [r for r in results if r['category'] == category]
        by_category[category] = {'cases': len(group), 'nonempty': sum(bool(r['java']) for r in group),
            'realizedCompositionStress': sum(r['compositionStressRealized'] for r in group),
            'withFlexCandidate': sum(bool(r['flexCandidates']) for r in group),
            **{f: sum(f in r['flags'] for r in group) for f in ('java_top_outside_ml_top5', 'comfort_conflict',
                'ml_top_weak_or_unsupported', 'priority_over_comfort', 'rare_or_unseen_candidate', 'bounded_top_changed')}}
    report = {'status': 'OFFLINE_SCENARIOS_COMPLETE_NO_ACTIVATION', 'totals': dict(totals), 'categories': by_category,
              'asOfDay': day, 'patch': patch, 'historyLatest': history_snapshot['latestObservation'],
              'snapshotSha256': sha(snapshot_path), 'modelSha256': MODEL_HASH,
              'finalGeneralizationPassed': final['acceptance']['passed'],
              'safetyViolations': 0, 'latencyP95Ms': float(np.quantile([r['featureAndScoringMs'] for r in results], .95)),
              'gatePolicy': 'global>=30, 30-day picks>=5, same-patch games>=30, training exposure, final-test acceptance; otherwise zero',
              'cap': 2.5, 'capMeaning': 'positive-only 0..2.5 total-score points; no negative cold-start penalty',
              'limits': ['Java role-specific per-player generator, not a new team-wide solver.',
                         'Java default no selected statistical dataset: comfort and known requested composition only.',
                         'No professional-ID linkage for saved players: ML familiarity features all missing, not comfort-as-count.',
                         'Synthetic partial drafts have no objective best-pick labels or win-rate evidence.',
                         'No automatic role inference; late means visible picks, not a certified lane counterpick.']}
    write(output / 'report.json', report)
    write(output / 'manifest.json', {'snapshotSha256': sha(snapshot_path), 'modelSha256': MODEL_HASH,
          'codeSha256': {str(p.relative_to(ROOT)): sha(p) for p in [Path(__file__),
              Path(__file__).with_name('java') / 'ReadinessScorer.java', JAVA / 'RecommendationEngine.java', JAVA / 'WeightedRecommendations.java']},
          'artifacts': {p.name: sha(p) for p in output.iterdir() if p.is_file() and p.name != 'manifest.json'}})
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    run()
