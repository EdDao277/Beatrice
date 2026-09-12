"""Catch accidental label/identity leakage and incorrect evidence transformations."""
import copy
import math
import unittest

from ml_features import FEATURE_NAMES, vector


def context():
    return {'playerIds': ['a', 'b', 'c', 'd', 'e'], 'allyPicks': [], 'enemyPicks': []}


def candidate():
    return {'championId': 'A', 'factors': {'comfort': 50, 'meta': 50, 'synergy': 50, 'draftValue': 50},
            'playerChampionEvidence': dict.fromkeys('abcde', 0), 'observedPlayers': [],
            'evidence': {'meta': None, 'allyPairs': []}}


class FeatureTests(unittest.TestCase):
    def test_unknown_is_flagged_not_mistaken_for_observed_neutral(self):
        c = candidate()
        x = dict(zip(FEATURE_NAMES, vector(context(), c)))
        self.assertEqual(x['meta_missing'], 1)
        self.assertEqual(x['pair_missing'], 1)
        self.assertEqual(x['familiarity_max_log'], 0)
        self.assertEqual(x['meta_rate'], .5)
        c['evidence']['meta'] = {'games': 50, 'wins': 25}
        y = dict(zip(FEATURE_NAMES, vector(context(), c)))
        self.assertEqual(y['meta_missing'], 0)
        self.assertAlmostEqual(y['meta_games_log'], math.log1p(50))

    def test_labels_ids_and_roster_order_do_not_change_features(self):
        ctx, row = context(), candidate()
        original = vector(ctx, row)
        ctx.update({'won': 1, 'gameId': 'future', 'playerIds': list(reversed(ctx['playerIds']))})
        row.update({'championId': 'OTHER', 'score': 999, 'targetChampion': 'OTHER'})
        self.assertEqual(vector(ctx, row), original)

    def test_stage_interactions_follow_visible_picks_not_final_roles(self):
        ctx, row = context(), candidate()
        row['playerChampionEvidence']['b'] = 9
        row['observedPlayers'] = ['b']
        x = dict(zip(FEATURE_NAMES, vector(ctx, row)))
        self.assertAlmostEqual(x['blind:familiarity_max_log'], math.log(10))
        ctx['allyPicks'] = ['X', 'Y', 'Z']
        x = dict(zip(FEATURE_NAMES, vector(ctx, row)))
        self.assertEqual(x['blind:familiarity_max_log'], 0)
        self.assertAlmostEqual(x['late:familiarity_max_log'], math.log(10))

    def test_invalid_counts_and_nonfinite_values_are_rejected(self):
        for bad in (-1, float('nan'), True):
            row = copy.deepcopy(candidate())
            row['playerChampionEvidence']['a'] = bad
            with self.assertRaises(ValueError):
                vector(context(), row)
        row = candidate()
        row['evidence']['meta'] = {'games': 2, 'wins': 3}
        with self.assertRaises(ValueError):
            vector(context(), row)


if __name__ == '__main__':
    unittest.main()
