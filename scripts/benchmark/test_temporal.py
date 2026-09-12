import copy
import unittest

from temporal import EarlierHistory, dataset_partitions
from test_protocol import game


class TemporalTests(unittest.TestCase):
    def test_reserved_test_year_cannot_be_moved_into_training_or_validation(self):
        with self.assertRaisesRegex(ValueError, '2026'):
            dataset_partitions([game()], '2024-04-01', '2025-01-01', '2027-01-01')

    def test_snapshot_excludes_current_previous_and_future_days(self):
        history = EarlierHistory([game('old', '2024-01-01 00:00:00'),
                                  game('previous', '2024-01-02 12:00:00'),
                                  game('current', '2024-01-03 00:00:00'),
                                  game('future', '2024-01-04 00:00:00')])
        first = history.advance('2024-01-03')
        self.assertEqual(first['sourceGameIds'], ['old'])
        self.assertEqual(history.history.players['P0']['C0'], 1)
        second = history.advance('2024-01-04')
        self.assertEqual(second['sourceGameIds'], ['old', 'previous'])
        self.assertEqual(first['sourceGameIds'], ['old'])
        self.assertNotEqual(first['snapshotId'], second['snapshotId'])
        with self.assertRaises(ValueError):
            history.advance('2024-01-03')

    def test_future_outcomes_do_not_affect_snapshot_identity_or_counts(self):
        old = game('old', '2024-01-01 00:00:00')
        future = game('future', '2024-06-01 00:00:00')
        changed = copy.deepcopy(future)
        for team in changed['teams']:
            team['result'] = 1 - team['result']
        before, after = EarlierHistory([old, future]), EarlierHistory([old, changed])
        self.assertEqual(before.advance('2024-02-01'), after.advance('2024-02-01'))
        self.assertEqual(before.history.champions, after.history.champions)

    def test_training_validation_and_test_membership_do_not_overlap(self):
        games = [game('warmup', '2024-01-01 00:00:00'), game('train', '2024-04-02 00:00:00'),
                 game('gap', '2024-12-30 00:00:00'), game('validation'),
                 game('test', '2026-01-01 00:00:00')]
        parts = dataset_partitions(games, '2024-04-01', '2025-01-01', '2026-01-01')
        self.assertEqual({k: [g['gameId'] for g in v] for k, v in parts.items()},
                         {'warmup': ['warmup'], 'training': ['train'], 'validation': ['validation'],
                          'embargo': ['gap'], 'test': ['test']})


if __name__ == '__main__':
    unittest.main()
