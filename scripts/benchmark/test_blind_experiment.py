"""Offline experiment training and frozen-artifact boundaries."""
from pathlib import Path
import tempfile
import unittest
import numpy as np

try:
    from blind_experiment import training_cases, verify_frozen
except ImportError:
    training_cases = verify_frozen = None


class BlindExperimentTests(unittest.TestCase):
    def test_rare_cohort_does_not_misclassify_rounded_thirty_observations(self):
        from blind_experiment import rarity_cohort
        for count, expected in ((0, 'new_or_absent'), (1, 'rare'), (29, 'rare'), (30, 'established'), (31, 'established')):
            c = {'target': 0, 'x': np.zeros((1, 33), dtype=np.float32)}
            c['x'][0, 4] = np.log1p(count)
            self.assertEqual(rarity_cohort(c), expected)
        self.assertEqual(rarity_cohort({'target': None}), 'new_or_absent')

    def test_real_export_frozen_comparison_and_saved_specialist_reload(self):
        from blind_experiment import run
        from scaled_train import run as frozen_run
        from test_scaled_train import dataset
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = dataset(root)
            frozen_run(data, root / 'frozen')
            registration = root / 'registration.md'
            registration.write_text('Fixed fixture experiment', encoding='utf-8')
            report = run(data, root / 'frozen', root, root / 'experiment', registration)
            self.assertTrue(report['testUnscored'])
            self.assertTrue(report['reloadVerified'])
            self.assertEqual(report['metrics']['overall']['tree']['cases'], 10)
            self.assertEqual(report['comparisons']['blind_specialist']['late']['top3']['delta'], 0.)
            self.assertEqual(report['comparisons']['blind_specialist']['late']['mrr']['delta'], 0.)

    def test_specialist_never_trains_on_validation_or_nonblind_and_weights_games(self):
        self.assertIsNotNone(training_cases)
        cases = {key: {'split': split, 'gameId': key, 'target': 0,
                       'ids': ['A', 'B'], 'x': np.zeros((2, 108)), 'weight': .1}
                 for key, split in [('blind', 'training'), ('late', 'training'), ('val', 'validation')]}
        contexts = {key: {'allyPicks': ['X'] if key == 'late' else [], 'enemyPicks': []}
                    for key in cases}
        chosen = training_cases(cases, contexts, specialist=True)
        self.assertEqual([c['gameId'] for c in chosen], ['blind'])
        self.assertEqual(chosen[0]['weight'], 1.)
        self.assertEqual(len(training_cases(cases, contexts, specialist=False)), 2)

    def test_frozen_verification_rejects_changed_model(self):
        self.assertIsNotNone(verify_frozen)
        from scaled_train import write, sha
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'tree.txt').write_bytes(b'original')
            write(root / 'manifest.json', {'datasetManifestSha256': 'data',
                  'artifacts': {'tree.txt': sha(root / 'tree.txt')}})
            verify_frozen(root, 'data')
            (root / 'tree.txt').write_bytes(b'changed')
            with self.assertRaises(ValueError):
                verify_frozen(root, 'data')


if __name__ == '__main__':
    unittest.main()
