"""Whitelisted prior-evidence features for pro-pick imitation, never win prediction."""
import math

BASE_NAMES = ('familiarity_max_log', 'familiarity_total_log', 'observed_fraction',
              'meta_rate', 'meta_games_log', 'meta_missing', 'pair_delta_mean',
              'pair_games_mean_log', 'pair_games_min_log', 'pair_coverage', 'pair_missing')
FEATURE_NAMES = BASE_NAMES + tuple(f'{stage}:{name}' for stage in ('blind', 'late') for name in BASE_NAMES)
SCHEMA = {'version': 1, 'signal': 'pro_pick_imitation', 'features': list(FEATURE_NAMES),
          'counts': 'log1p of earlier observations; no saved comfort ratings',
          'rates': 'Beta(25,25) posterior; missing meta=0.5 and missing pair delta=0, with masks',
          'stages': 'base applies everywhere; blind=no visible picks; late=at least 3 ally picks',
          'excluded': ['outcome', 'final roles', 'identities', 'candidate ordering',
                       'unavailable composition and enemy matchup evidence'],
          'normalization': 'training-only case-weighted mean/std; constant columns disabled; z clipped to [-8,8]'}


def count(value):
    if type(value) is not int or value < 0:
        raise ValueError('Evidence counts must be nonnegative integers')
    return value


def rate(row):
    games, wins = count(row['games']), count(row['wins'])
    if wins > games:
        raise ValueError('Wins exceed games')
    return (wins + 25) / (games + 50)


def vector(context, candidate):
    ids = context['playerIds']
    evidence = candidate['playerChampionEvidence']
    if len(ids) != 5 or len(set(ids)) != 5 or set(evidence) != set(ids):
        raise ValueError('Evidence must cover the exact five-player roster')
    counts = [count(evidence[p]) for p in ids]
    meta = candidate['evidence']['meta']
    meta_rate = .5 if meta is None else rate(meta)
    pairs = candidate['evidence']['allyPairs']
    allies = context['allyPicks']
    if len({p['ally'] for p in pairs}) != len(pairs) or any(p['ally'] not in allies for p in pairs):
        raise ValueError('Pair evidence must match distinct visible allies')
    if pairs and meta is None:
        raise ValueError('Pair evidence requires a candidate baseline')
    deltas = [rate(p) - (meta_rate + rate(p['allyBaseline'])) / 2 for p in pairs]
    games = [count(p['games']) for p in pairs]
    values = [math.log1p(max(counts)), math.log1p(sum(counts)), sum(n > 0 for n in counts) / 5,
              meta_rate, math.log1p(meta['games']) if meta else 0, float(meta is None),
              sum(deltas) / len(deltas) if deltas else 0,
              math.log1p(sum(games) / len(games)) if games else 0,
              math.log1p(min(games)) if games else 0,
              len(pairs) / len(allies) if allies else 0, float(not pairs)]
    # Context-only constants cancel in pairwise differences. Interactions let familiarity
    # and statistics matter differently for blind and late picks without champion IDs.
    blind = not allies and not context['enemyPicks']
    late = len(allies) >= 3
    return values + [v * blind for v in values] + [v * late for v in values]
