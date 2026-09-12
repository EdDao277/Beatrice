"""Run the real exporter and trainer on tiny chronological fixtures."""
import gzip
import json
from pathlib import Path
import tempfile
import unittest

from build_dataset import build
from protocol import digest
from test_protocol import game
from test_source_audit import source_fixture
from train_ranker import run, measure


def dataset(root):
    source_fixture(root, [game('warmup', '2024-01-01 00:00:00'),
                         game('train', '2024-04-01 00:00:00'),
                         game('validation', '2025-02-01 00:00:00'),
                         game('test', '2026-02-01 00:00:00')])
    build(root, root, root / 'data')
    return root / 'data'


def mutate(path, name, change):
    file = path / (name + '.jsonl.gz')
    with gzip.open(file, 'rt', encoding='utf-8') as stream:
        records = [json.loads(line) for line in stream]
    change(records)
    with gzip.open(file, 'wt', encoding='utf-8') as stream:
        for row in records:
            stream.write(json.dumps(row) + '\n')
    manifest = json.loads((path / 'manifest.json').read_text())
    manifest['artifacts'][file.name] = digest(file.read_bytes())
    (path / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')


class TrainingTests(unittest.TestCase):
    def test_real_export_trains_reloads_and_keeps_test_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); data = dataset(root)
            result = run(data, root / 'model')
            self.assertEqual(result['metrics']['validation']['ml']['cases'], 10)
            self.assertTrue(result['testUnscored'])
            self.assertTrue((root / 'model' / 'manifest.json').exists())
            with self.assertRaises(FileExistsError):
                run(data, root / 'model')

    def test_validation_changes_cannot_change_learned_parameters(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); data = dataset(root)
            run(data, root / 'before')
            def change_labels(rows):
                for r in rows:
                    if r['split'] == 'validation':
                        r['championId'] = 'UNSEEN'
                        r['won'] = 1 - r['won']
            mutate(data, 'labels', change_labels)
            def change_features(rows):
                for r in rows:
                    if r['split'] == 'validation':
                        for c in r['candidates']:
                            c['playerChampionEvidence'] = dict.fromkeys(c['playerChampionEvidence'], 999)
            mutate(data, 'features', change_features)
            report = run(data, root / 'after')
            self.assertEqual((root / 'before' / 'model.json').read_bytes(),
                             (root / 'after' / 'model.json').read_bytes())
            self.assertEqual(report['metrics']['validation']['ml']['candidateCoverage'], 0)
            self.assertEqual(report['metrics']['validation']['ml']['top3Agreement'], 0)

    def test_hash_mismatch_rejected_before_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); data = dataset(root)
            (data / 'labels.jsonl.gz').write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError, 'hash'):
                run(data, root / 'out')
            self.assertFalse((root / 'out').exists())

    def test_duplicate_join_and_test_membership_rejected(self):
        for mode in ('duplicate', 'test'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); data = dataset(root)
                def change(rows):
                    if mode == 'duplicate':
                        rows.append(rows[0])
                    else:
                        rows[0]['gameId'] = 'test'
                mutate(data, 'contexts', change)
                with self.assertRaises(ValueError):
                    run(data, root / 'out')

    def test_metrics_count_absent_targets_and_abstentions(self):
        result = measure([{'rank': 2, 'count': 4, 'latencyMs': 1},
                          {'rank': None, 'count': 0, 'latencyMs': 2}])
        self.assertEqual(result['top3Agreement'], .5)
        self.assertEqual(result['mrr'], .25)
        self.assertEqual(result['candidateCoverage'], .5)
        self.assertEqual(result['abstentions'], 1)


if __name__ == '__main__':
    unittest.main()
