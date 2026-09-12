import gzip
import json
from pathlib import Path
import tempfile
import unittest

from build_dataset import build
from test_protocol import game
from test_source_audit import source_fixture


def read_rows(path):
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        return [json.loads(line) for line in stream]


class DatasetTests(unittest.TestCase):
    def test_exports_temporal_training_and_validation_without_test_labels(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source_fixture(root, [game('warmup', '2024-01-01 00:00:00'),
                                  game('train', '2024-04-01 00:00:00'),
                                  game('validation', '2025-02-01 00:00:00'),
                                  game('test', '2026-02-01 00:00:00')])
            report = build(root, root, root / 'out')
            self.assertEqual(report['exportedGames'], {'training': 1, 'validation': 1})
            contexts = read_rows(root / 'out' / 'contexts.jsonl.gz')
            labels = read_rows(root / 'out' / 'labels.jsonl.gz')
            features = read_rows(root / 'out' / 'features.jsonl.gz')
            snapshots = read_rows(root / 'out' / 'snapshots.jsonl.gz')
            self.assertEqual(len(contexts), 20)
            self.assertEqual(len(labels), 20)
            self.assertEqual(len(features), 20)
            self.assertEqual(snapshots[0]['sourceGameIds'], ['warmup'])
            self.assertEqual(snapshots[1]['sourceGameIds'], ['train', 'warmup'])
            self.assertEqual({c['gameId'] for c in contexts}, {'train', 'validation'})
            self.assertTrue(all('won' not in f and 'targetChampion' not in f for f in features))
            self.assertEqual(report['metrics']['validation']['inferred']['pool']['all']['cases'], 10)
            self.assertEqual(report['metrics']['validation']['inferred']['pool']['all']['legalityViolations'], 0)
            manifest = json.loads((root / 'out' / 'manifest.json').read_text())
            self.assertTrue(manifest['testUnscored'])
            self.assertIn('features.jsonl.gz', manifest['artifacts'])
            with self.assertRaises(FileExistsError):
                build(root, root, root / 'out')

    def test_held_out_result_changes_labels_but_not_its_features(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            validation = game('validation', '2025-02-01 00:00:00')
            games = [game('warmup', '2024-01-01 00:00:00'),
                     game('train', '2024-04-01 00:00:00'), validation]
            source_fixture(root, games)
            build(root, root, root / 'before')
            for team in validation['teams']:
                team['result'] = 1 - team['result']
            source_fixture(root, games)
            build(root, root, root / 'after')
            self.assertEqual(read_rows(root / 'before' / 'features.jsonl.gz'),
                             read_rows(root / 'after' / 'features.jsonl.gz'))
            self.assertNotEqual(read_rows(root / 'before' / 'labels.jsonl.gz'),
                                read_rows(root / 'after' / 'labels.jsonl.gz'))

    def test_later_games_are_not_training_labels_and_limits_are_explicit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source_fixture(root, [game('warmup', '2024-01-01 00:00:00'),
                                  game('train1', '2024-04-01 00:00:00'),
                                  game('train2', '2024-05-01 00:00:00'),
                                  game('validation')])
            report = build(root, root, root / 'out', max_training=1)
            self.assertEqual(report['exportedGames']['training'], 1)
            self.assertEqual(report['excluded']['training']['sample_limit'], 1)


if __name__ == '__main__':
    unittest.main()
