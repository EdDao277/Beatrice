"""Hand-counted history boundaries; no live services or historical outcome labels."""
import unittest
import numpy as np

try:
    from recency_features import RecencyHistory, extend, route_blind
except ImportError:
    RecencyHistory = extend = route_blind = None


def game(identity, date, patch='15.1', pick='A', ban='B'):
    return {'gameId': identity, 'date': date, 'patch': patch,
            'teams': [{'picks': [pick], 'bans': [ban]}]}


class RecencyTests(unittest.TestCase):
    def test_future_mutations_cannot_change_features_and_empty_candidates_stay_empty(self):
        self.assertIsNotNone(RecencyHistory)
        past = game('past', '2025-01-01')
        before = RecencyHistory([past, game('future', '2025-01-05')]).at('2025-01-03', '15.1')
        after = RecencyHistory([past, game('future', '2025-01-05', pick='NEW', ban='A')]).at('2025-01-03', '15.1')
        self.assertEqual(before.vector('A'), after.vector('A'))
        empty = extend(np.empty((0, 33)), [], {'allyPicks': [], 'enemyPicks': []}, before)
        self.assertEqual(empty.shape, (0, 108))

    def test_cutoff_excludes_previous_day_and_future_and_window_keeps_left_boundary(self):
        self.assertIsNotNone(RecencyHistory)
        history = RecencyHistory([
            game('old', '2025-01-01'), game('left', '2025-01-02'),
            game('recent', '2025-01-15', pick='C'),
            game('excluded', '2025-01-16'), game('future', '2026-01-01')])
        table = history.at('2025-01-17', '15.1')
        a = table.vector('A')
        self.assertEqual(a[0], .5)  # two games in [Jan 2, Jan 16)
        self.assertEqual(a[1], 0.)
        self.assertEqual(table.vector('B')[1], 1.)
        self.assertEqual(a[8], 2 / 3)  # three games in the 30-day window
        self.assertEqual(a[16], 2 / 3)
        self.assertEqual(table.source_count, 3)

    def test_new_patch_and_champion_have_explicit_missingness_not_future_support(self):
        self.assertIsNotNone(RecencyHistory)
        table = RecencyHistory([game('past', '2025-01-01')]).at('2025-01-03', '15.2')
        x = table.vector('NEW')
        self.assertEqual(x[0:3], [0., 0., 0.])
        self.assertEqual(x[6:8], [0., 1.])
        self.assertEqual(x[22:24], [1., 1.])

    def test_history_rejects_backwards_time_and_deduplicates_within_game(self):
        self.assertIsNotNone(RecencyHistory)
        g = game('one', '2025-01-01'); g['teams'] *= 2
        history = RecencyHistory([g])
        self.assertEqual(history.at('2025-01-03', '15.1').vector('A')[0], 1.)
        with self.assertRaises(ValueError):
            history.at('2025-01-02', '15.1')

    def test_extension_keeps_rows_and_blind_route_never_changes_nonblind_scores(self):
        self.assertIsNotNone(extend)
        context = {'allyPicks': [], 'enemyPicks': []}
        table = RecencyHistory([]).at('2025-01-03', '15.1')
        original = np.zeros((2, 33), dtype=np.float32)
        expanded = extend(original, ['A', 'FLEX'], context, table)
        self.assertEqual(expanded.shape, (2, 108))
        np.testing.assert_array_equal(expanded[:, :33], original)
        frozen = np.array([2., 1.]); specialist = np.array([1., 3.])
        np.testing.assert_array_equal(route_blind(context, frozen, specialist), specialist)
        for ally, enemy in ((['A'], []), ([], ['X']), (['A'], ['X'])):
            np.testing.assert_array_equal(route_blind({'allyPicks': ally, 'enemyPicks': enemy},
                                                     frozen, specialist), frozen)


if __name__ == '__main__':
    unittest.main()
