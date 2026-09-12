"""JSON-lines research adapter for a future backend subprocess. No HTTP or DB access."""
import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

from baseline import placements
from linear_ranker import score, transformed
from ml_features import FEATURE_NAMES, SCHEMA, vector, rate


def file_hash(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def validate_request(request):
    if not isinstance(request, dict) or not isinstance(request.get('context'), dict):
        raise ValueError('Request and context must be objects')
    # Enforce interoperable finite JSON numbers before numeric transforms or echoing IDs.
    pending = [request]
    while pending:
        value = pending.pop()
        if isinstance(value, dict): pending.extend(value.values())
        elif isinstance(value, list): pending.extend(value)
        elif type(value) is int and abs(value) > 2 ** 53: raise ValueError('Integer exceeds safe JSON range')
        elif type(value) is float and not math.isfinite(value): raise ValueError('Nonfinite JSON number')
    context = request['context']
    for key in ('playerIds', 'allyPicks', 'enemyPicks', 'bans'):
        values = context.get(key)
        if not isinstance(values, list) or any(not isinstance(v, str) or not v for v in values):
            raise ValueError('Expected string array: ' + key)
    available = request.get('availableChampionIds')
    if not isinstance(available, list) or any(not isinstance(v, str) or not v for v in available):
        raise ValueError('Available champions must be a string array')
    if not isinstance(context.get('savedPools'), dict) or not isinstance(request.get('candidates'), list):
        raise ValueError('Saved pools must be an object and candidates an array')
    for row in request['candidates']:
        if not isinstance(row, dict) or not isinstance(row.get('championId'), str):
            raise ValueError('Invalid candidate object')
        if not isinstance(row.get('playerChampionEvidence'), dict) or not isinstance(row.get('evidence'), dict):
            raise ValueError('Candidate evidence must be objects')
        pairs = row['evidence'].get('allyPairs')
        if not isinstance(pairs, list) or any(not isinstance(p, dict) or not isinstance(p.get('allyBaseline'), dict) for p in pairs):
            raise ValueError('Invalid ally pair evidence')
        meta = row['evidence'].get('meta')
        if meta is not None and not isinstance(meta, dict):
            raise ValueError('Invalid meta evidence')


def public_evidence(candidate):
    evidence = candidate['evidence']
    meta = evidence['meta']
    clean_meta = {k: meta[k] for k in ('games', 'wins')} if meta is not None else None
    pairs = []
    for pair in evidence['allyPairs']:
        baseline = {k: pair['allyBaseline'][k] for k in ('games', 'wins')}
        pairs.append({'ally': pair['ally'], 'games': pair['games'], 'wins': pair['wins'],
                      'allyBaseline': baseline, 'delta': rate(pair) - (rate(meta) + rate(baseline)) / 2})
    return clean_meta, pairs


class Ranker:
    def __init__(self, folder):
        manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
        def read(name):
            if Path(name).name != name:
                raise ValueError('Invalid model artifact path')
            content = (folder / name).read_bytes()
            if hashlib.sha256(content).hexdigest() != manifest['artifacts'].get(name):
                raise ValueError('Model artifact checksum mismatch')
            return content.decode('utf-8')
        self.selected = json.loads(read('selected.json'))
        schema = json.loads(read('schema.json'))
        if (self.selected['signal'] != 'pro_pick_imitation'
                or any(schema.get(key) != value for key, value in SCHEMA.items())):
            raise ValueError('Unsupported model signal/schema')
        self.dtype = np.float32 if schema.get('matrixDtype') == 'float32' else np.float64
        self.model_type = self.selected['modelType']
        content = read(self.selected['modelFile'])
        if self.model_type == 'linear':
            self.model = json.loads(content)
            if self.model.get('featureNames') != list(FEATURE_NAMES) or self.model.get('signal') != 'pro_pick_imitation':
                raise ValueError('Linear feature contract mismatch')
            score(self.model, np.zeros((1, len(FEATURE_NAMES))))
        elif self.model_type == 'tree':
            import lightgbm as lgb
            self.model = lgb.Booster(model_str=content)
            if self.model.num_feature() != len(FEATURE_NAMES):
                raise ValueError('Tree feature contract mismatch')
        else:
            raise ValueError('Unsupported model type')

    def rank(self, request):
        validate_request(request)
        if (self.selected.get('offlineOnly', False) or not self.selected.get('deploymentEligible', False)) and request.get('allowResearchModel') is not True:
            raise ValueError('Offline or ineligible model; explicit research override required')
        context = request['context']
        when = datetime.fromisoformat(request['decisionTime'])
        as_of = datetime.fromisoformat(request['evidenceAsOf'])
        if when.tzinfo != as_of.tzinfo or as_of > when:
            raise ValueError('Evidence must be available before decision time in the same timezone')
        # Timestamps are a caller contract, not proof of source correctness. The backend
        # must supply a trustworthy as-of snapshot; this process never fetches or invents it.
        ids = context['playerIds']
        pools = context['savedPools']
        if len(ids) != 5 or len(set(ids)) != 5 or not all(ids) or set(pools) != set(ids):
            raise ValueError('Exactly five explicitly saved pools required')
        if any(not isinstance(pool, dict) or any(not isinstance(c, str) or not c or type(r) is not int or not 1 <= r <= 10
                                                 for c, r in pool.items()) for pool in pools.values()):
            raise ValueError('Saved comfort ratings must be integers from 1 to 10')
        available = set(request['availableChampionIds'])
        allies, enemies, bans = context['allyPicks'], context['enemyPicks'], context['bans']
        if len(allies) > 5 or len(enemies) > 5 or len(set(allies + enemies)) != len(allies + enemies):
            raise ValueError('Invalid visible picks')
        if set(allies + enemies) & set(bans):
            raise ValueError('Visible pick is banned')
        candidates = request['candidates']
        if len({c['championId'] for c in candidates}) != len(candidates):
            raise ValueError('Duplicate evidence candidate')
        kept, vectors, witnesses, comfort = [], [], [], []
        rejected = {'unavailable': 0, 'noSavedPoolCompletion': 0}
        domains = [set(pools[p]) & available for p in ids]
        for c in sorted(candidates, key=lambda c: c['championId']):
            champion = c['championId']
            if champion not in available or champion in set(allies + enemies + bans):
                rejected['unavailable'] += 1
                continue
            options = placements(allies + [champion], domains, set(enemies + bans), champion)
            if not options:
                rejected['noSavedPoolCompletion'] += 1
                continue
            owner = min(options, key=lambda i: (-pools[ids[i]][champion], ids[i]))
            kept.append(c); vectors.append(vector(context, c))
            witnesses.append({ids[i]: value for i, value in options[owner].items()})
            comfort.append({ids[i]: pools[ids[i]][champion] for i in sorted(options)})
        x = np.array(vectors, dtype=self.dtype).reshape(-1, len(FEATURE_NAMES))
        if self.model_type == 'linear':
            scores = score(self.model, x)
            contributions = transformed(self.model, x) * np.asarray(self.model['weights'])
            biases = np.zeros(len(x))
        else:
            from tree_ranker import tree_score
            scores = tree_score(self.model, x)
            attribution = tree_score(self.model, x, contributions=True)
            contributions, biases = attribution[:, :-1], attribution[:, -1]
        ranked = []
        for rank, i in enumerate(sorted(range(len(kept)), key=lambda i: (-scores[i], kept[i]['championId'])), 1):
            c = kept[i]
            meta, pairs = public_evidence(c)
            missing = ['composition', 'role_specific_matchup', 'team_outcome_history', 'confirmed_lane_assignment']
            if c['evidence']['meta'] is None: missing.append('champion_statistics')
            if not c['evidence']['allyPairs']: missing.append('ally_pair_statistics')
            if not any(c['playerChampionEvidence'].values()): missing.append('observed_player_familiarity')
            ranked.append({'championId': c['championId'], 'rank': rank, 'score': float(scores[i]),
                           'signal': 'pro_pick_imitation', 'modelConfidence': None,
                           'playerFamiliarity': c['playerChampionEvidence'], 'savedComfort': comfort[i],
                           'synergyEvidence': pairs, 'metaEvidence': meta,
                           'compositionContribution': None, 'matchupEvidence': None,
                           'completionWitness': witnesses[i], 'missingInformation': missing,
                           'featureContributions': dict(zip(FEATURE_NAMES, contributions[i].tolist())),
                           'modelBias': float(biases[i])})
        return {'requestId': request.get('requestId'), 'signal': 'pro_pick_imitation',
                'scoreMeaning': 'uncalibrated pro-choice preference, not best pick or win probability',
                'evidenceAsOf': request['evidenceAsOf'], 'roles': 'unknown', 'candidates': ranked,
                'filtered': rejected, 'abstention': None if ranked else 'no_feasible_saved_pool_candidate',
                'deploymentEligible': self.selected.get('deploymentEligible', False),
                'domainShiftWarning': 'pro history and user teams are different populations'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir', type=Path, required=True)
    args = parser.parse_args()
    engine = Ranker(args.model_dir)
    # One request and one response per line; load the model once. Diagnostic tracebacks
    # must not corrupt stdout, which is reserved for the backend's JSON protocol.
    for line in sys.stdin:
        try:
            result = engine.rank(json.loads(line))
            encoded = json.dumps(result, allow_nan=False)
        except (ValueError, KeyError, TypeError, IndexError, OverflowError, RecursionError) as error:
            encoded = json.dumps({'error': 'invalid_request', 'message': str(error)[:256]})
        print(encoded, flush=True)


if __name__ == '__main__': main()
