import json
import gzip
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evaluate import run, sample_indices
from test_protocol import game, prepared


class EvaluationTests(unittest.TestCase):
    def test_requires_provisional_opt_in_without_creating_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaisesRegex(ValueError, 'provisional'):
                run(root, root / 'out')
            self.assertFalse((root / 'out').exists())

    def test_exports_separate_labels_and_leaves_test_unscored(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            prepared(root, [game('reference', '2024-10-01 00:00:00'), game('validation'),
                            game('test', '2026-02-01 00:00:00')])
            output = root / 'out'
            report = run(root, output, provisional=True)
            self.assertEqual(report['splits'], {'reference': 1, 'embargo': 0, 'validation': 1, 'test': 1})
            self.assertEqual(report['evaluatedGames'], 1)
            self.assertEqual(report['metrics']['pool']['all']['cases'], 10)
            self.assertEqual(report['metrics']['pool']['all']['top3Hits'], 10)
            self.assertEqual(report['metrics']['pool']['all']['legalityViolations'], 0)
            contexts = [json.loads(line) for line in (output / 'contexts.jsonl').read_text().splitlines()]
            labels = [json.loads(line) for line in (output / 'labels.jsonl').read_text().splitlines()]
            self.assertEqual(len(contexts), 10)
            self.assertEqual(len(labels), 10)
            self.assertTrue(all(c['gameId'] == 'validation' for c in contexts))
            self.assertTrue(all('won' not in c and 'championId' not in c for c in contexts))
            snapshot = json.loads((output / 'history.json').read_text())
            self.assertEqual(snapshot['gameIds'], ['reference'])
            self.assertEqual(snapshot['latestDate'], '2024-10-01 00:00:00')
            manifest = json.loads((output / 'manifest.json').read_text())
            self.assertEqual(manifest['status'], 'PROVISIONAL_NOT_ML_READY')
            self.assertIn('contexts.jsonl', manifest['artifacts'])
            with self.assertRaises(FileExistsError):
                run(root, output, provisional=True)

    def test_validation_outcome_cannot_change_scores(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            validation = game('validation')
            reference = game('reference', '2024-10-01 00:00:00')
            prepared(root, [reference, validation])
            run(root, root / 'before', provisional=True)
            for team in validation['teams']:
                team['result'] = 1 - team['result']
            prepared(root, [reference, validation])
            run(root, root / 'after', provisional=True)
            def scores(path):
                return gzip.decompress(path.read_bytes())
            self.assertEqual(scores(root / 'before' / 'predictions.jsonl.gz'),
                             scores(root / 'after' / 'predictions.jsonl.gz'))

    def test_sample_spans_the_period_without_sampling_prefixes_individually(self):
        self.assertEqual(sample_indices(10, 3), {0, 4, 9})
        self.assertEqual(sample_indices(10, 1), {5})
        self.assertEqual(sample_indices(3, 10), {0, 1, 2})

    def test_source_change_prevents_final_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            prepared(root, [game('reference', '2024-10-01 00:00:00'), game()])
            with patch('evaluate.code_hashes', side_effect=[{'source': 'before'}, {'source': 'after'}]):
                with self.assertRaisesRegex(ValueError, 'source changed'):
                    run(root, root / 'out', provisional=True)
            self.assertFalse((root / 'out' / 'manifest.json').exists())

    def test_missing_teammate_does_not_erase_known_pool_coverage(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            validation = game()
            validation['teams'][0]['players'][4]['playerId'] = 'unknown'
            prepared(root, [game('reference', '2024-10-01 00:00:00'), validation])
            report = run(root, root / 'out', provisional=True)
            totals = report['metrics']['pool']['all']
            self.assertEqual(totals['poolCovered'], 9)
            self.assertEqual(totals['candidateCovered'], 5)
            self.assertEqual(totals['abstentions'], 5)

    def test_limit_and_incomplete_games_are_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            incomplete = game('a', '2025-01-01 00:00:00')
            incomplete['draftFieldsComplete'] = False
            prepared(root, [game('reference', '2024-10-01 00:00:00'), incomplete,
                            game('b'), game('c', '2025-03-01 00:00:00')])
            report = run(root, root / 'out', provisional=True, max_games=1)
            self.assertEqual(report['evaluatedGames'], 1)
            self.assertEqual(report['skipped'], {'incomplete_draft': 1, 'sample_limit': 1})


if __name__ == '__main__':
    unittest.main()
