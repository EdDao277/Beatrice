"""Final-test guards are tested on invented/development dates, never held-out labels."""
from pathlib import Path
import tempfile
import unittest
import numpy as np
from recency_features import RecencyHistory
from test_recency_features import game

try:
    from readiness import FinalHistory, checkpoint, reserve, acceptance
except ImportError:
    FinalHistory = checkpoint = reserve = acceptance = None


class ReadinessTests(unittest.TestCase):
    def test_frozen_source_and_completed_report_tampering_are_rejected(self):
        from readiness import verify_hashes, completed_report
        from scaled_train import sha, write
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'feature.py').write_text('frozen')
            hashes = {'feature.py': sha(root / 'feature.py')}
            verify_hashes(root, hashes)
            (root / 'feature.py').write_text('modified')
            with self.assertRaises(ValueError):
                verify_hashes(root, hashes)
            write(root / 'receipt.json', {'fixed': True})
            write(root / 'report.json', {'passed': False})
            write(root / 'complete.json', {'receiptSha256': sha(root / 'receipt.json'),
                  'reportSha256': sha(root / 'report.json'), 'checkpointHashes': {}})
            self.assertFalse(completed_report(root)['passed'])
            write(root / 'report.json', {'passed': True})
            with self.assertRaises(ValueError):
                completed_report(root)

    def test_missing_window_and_unseen_champion_rates_are_distinct(self):
        from readiness import missing_counts
        x = np.zeros((2, 108), dtype=np.float32)
        x[:, 40] = 1  # neither champion observed, but the window has games
        self.assertEqual(missing_counts(x)['14d_champion_unseen'], 2)
        self.assertEqual(missing_counts(x)['14d_window_missing'], 0)

    def test_final_adapter_matches_frozen_features_and_lag_in_new_year(self):
        self.assertIsNotNone(FinalHistory)
        games = [game('old', '2024-12-01'), game('past', '2025-01-01'),
                 game('edge', '2025-01-15'), game('future', '2025-02-01')]
        frozen, final = RecencyHistory(games), FinalHistory(games)
        for day in ('2025-01-03', '2025-01-16', '2025-01-17'):
            for patch in ('15.1', 'new'):
                for champion in ('A', 'B', 'UNKNOWN'):
                    self.assertEqual(frozen.at(day, patch).vector(champion), final.at(day, patch).vector(champion))
        future = FinalHistory([game('yes', '2025-12-31'), game('no', '2026-01-01')])
        self.assertEqual(future.at('2026-01-02', '15.1').source_count, 1)
        with self.assertRaises(ValueError):
            frozen.at('2026-01-02', '15.1')

    def test_resume_rejects_changed_receipt_or_duplicate_game(self):
        self.assertIsNotNone(reserve)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'run'
            reserve(root, {'model': 'fixed', 'games': ['one']})
            checkpoint(root, 'one', {'observations': [1]})
            reserve(root, {'model': 'fixed', 'games': ['one']})
            with self.assertRaises(ValueError):
                reserve(root, {'model': 'changed', 'games': ['one']})
            with self.assertRaises(FileExistsError):
                checkpoint(root, 'one', {'observations': [2]})

    def test_acceptance_uses_lower_bounds_not_favorable_point_estimates(self):
        self.assertIsNotNone(acceptance)
        def comparison(lower):
            return {'top3': {'delta': .1, 'pairedGameBootstrap95': [lower, .2]},
                    'mrr': {'delta': .1, 'pairedGameBootstrap95': [lower, .2]}}
        self.assertTrue(acceptance({'blind': comparison(.01), 'overall': comparison(.01),
                                    'late': comparison(-.004)})['passed'])
        self.assertFalse(acceptance({'blind': comparison(0), 'overall': comparison(.01),
                                     'late': comparison(-.006)})['passed'])


if __name__ == '__main__':
    unittest.main()
