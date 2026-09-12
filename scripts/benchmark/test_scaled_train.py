"""Exercise compact training boundaries with real earlier-only export fixtures."""
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from compact_dataset import build
from test_protocol import game
from test_source_audit import source_fixture

try:
    from scaled_train import load, measure, paired_comparison, run
except ImportError:
    load = measure = paired_comparison = run = None


def dataset(root):
    source_fixture(root, [game('warmup', '2024-01-01 00:00:00'),
                         game('train', '2024-04-01 00:00:00'),
                         game('validation', '2025-02-01 00:00:00'),
                         game('test', '2026-02-01 00:00:00')])
    build(root, root, root / 'data')
    return root / 'data'


def mutate(path, name, change):
    artifact = path / name
    if name.endswith('.gz'):
        with gzip.open(artifact, 'rt', encoding='utf-8') as stream:
            value = [json.loads(row) for row in stream]
        change(value)
        with gzip.open(artifact, 'wt', encoding='utf-8') as stream:
            for row in value:
                stream.write(json.dumps(row) + '\n')
    else:
        value = json.loads(artifact.read_text(encoding='utf-8'))
        change(value)
        artifact.write_text(json.dumps(value), encoding='utf-8')
    manifest = json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
    manifest['artifacts'][name] = hashlib.sha256(artifact.read_bytes()).hexdigest()
    (path / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')


class ScaledTests(unittest.TestCase):
    def require_runner(self):
        self.assertIsNotNone(run, 'The compact training runner must exist')

    def test_real_export_models_reload_and_predictions_keep_matched_candidates(self):
        self.require_runner()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); data = dataset(root)
            loaded = load(data)
            self.assertTrue(all(c['x'].dtype == np.float32 for c in loaded['cases'].values()))
            report = run(data, root / 'model')
            for name in ('linear', 'tree', 'inferred/pool', 'inferred/pool_rules', 'inferred/pool_rules_stats'):
                self.assertEqual(report['metrics']['validation'][name]['cases'], 10)
            self.assertTrue(report['testUnscored'])
            self.assertTrue(report['reloadVerified'])
            self.assertEqual(report['checks']['candidateLegalityChecks'], 110)
            self.assertEqual(report['checks']['impossibleLineupCandidates'], 0)
            selected = json.loads((root / 'model' / 'selected.json').read_text())
            self.assertIn(selected['modelType'], ('linear', 'tree'))
            self.assertEqual(selected['signal'], 'pro_pick_imitation')
            manifest = json.loads((root / 'model' / 'manifest.json').read_text())
            for name, expected in manifest['artifacts'].items():
                self.assertEqual(hashlib.sha256((root / 'model' / name).read_bytes()).hexdigest(), expected)
            with gzip.open(root / 'model' / 'predictions.jsonl.gz', 'rt') as stream:
                for line in stream:
                    row = json.loads(line)
                    self.assertEqual(set(row['rankings']), {'linear', 'tree', 'inferred/pool',
                                                          'inferred/pool_rules', 'inferred/pool_rules_stats'})
                    self.assertTrue(all(sorted(r['championIds']) == row['candidateIds']
                                        for r in row['rankings'].values()))
            with self.assertRaises(FileExistsError):
                run(data, root / 'model')

    def test_validation_mutations_do_not_change_either_model(self):
        self.require_runner()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); data = dataset(root)
            run(data, root / 'before')
            def labels(rows):
                for row in rows:
                    if row['split'] == 'validation':
                        row['championId'] = 'MISSING_TARGET'
                        row['won'] = 1 - row['won']
            mutate(data, 'labels.jsonl.gz', labels)
            def features(rows):
                for row in rows:
                    if row['split'] == 'validation':
                        for values in row['x']:
                            values[0] += 3
            mutate(data, 'features.jsonl.gz', features)
            report = run(data, root / 'after')
            for name in ('linear.json', 'tree.txt'):
                self.assertEqual((root / 'before' / name).read_bytes(), (root / 'after' / name).read_bytes())
            self.assertEqual(report['metrics']['validation']['tree']['targetAbsentRate'], 1)
            self.assertEqual(report['metrics']['validation']['linear']['top3Agreement'], 0)

    def test_hash_schema_candidates_and_snapshot_leaks_are_rejected(self):
        self.require_runner()
        for mode in ('hash', 'schema', 'test_split', 'future_history', 'duplicate_case', 'rank',
                     'candidate', 'nonfinite', 'evidence_join', 'impossible'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as folder:
                root = Path(folder); data = dataset(root)
                if mode == 'hash':
                    (data / 'labels.jsonl.gz').write_bytes(b'corrupt')
                elif mode == 'schema':
                    mutate(data, 'feature-schema.json', lambda row: row['features'].reverse())
                elif mode == 'test_split':
                    mutate(data, 'contexts.jsonl.gz', lambda rows: rows[0].update(gameId='test'))
                elif mode == 'future_history':
                    mutate(data, 'snapshots.jsonl.gz', lambda rows: rows[0]['sourceGameIds'].append('validation'))
                elif mode == 'duplicate_case':
                    mutate(data, 'contexts.jsonl.gz', lambda rows: rows.append(rows[0]))
                elif mode == 'rank':
                    mutate(data, 'features.jsonl.gz', lambda rows: rows[0]['baselineRanks']['pool'].reverse())
                elif mode == 'candidate':
                    mutate(data, 'features.jsonl.gz', lambda rows: rows[0]['championIds'].__setitem__(0, 'B0'))
                elif mode == 'nonfinite':
                    mutate(data, 'features.jsonl.gz', lambda rows: rows[0]['x'][0].__setitem__(0, float('nan')))
                elif mode == 'evidence_join':
                    mutate(data, 'evidence.jsonl.gz', lambda rows: rows[0]['candidates'].reverse())
                else:
                    mutate(data, 'report.json', lambda row: row['checks'].update(impossibleLineupCandidates=1))
                with self.assertRaises(ValueError):
                    run(data, root / 'out')
                self.assertFalse((root / 'out').exists())

    def test_absence_and_abstention_stay_in_denominators(self):
        self.require_runner()
        result = measure([{'rank': 2, 'count': 4, 'latencyMs': 1},
                          {'rank': None, 'count': 0, 'latencyMs': 3}])
        self.assertEqual(result['top3Agreement'], .5)
        self.assertEqual(result['mrr'], .25)
        self.assertEqual(result['targetAbsentRate'], .5)
        self.assertEqual(result['abstentionRate'], .5)
        self.assertEqual(result['latencyMeanMs'], 2)

    def test_bootstrap_resamples_whole_games_and_is_deterministic(self):
        self.require_runner()
        contexts = {str(i): {'gameId': 'first' if i < 10 else 'second'} for i in range(20)}
        left = {str(i): {'rank': 1 if i < 10 else None} for i in range(20)}
        right = {str(i): {'rank': None} for i in range(20)}
        result = paired_comparison(left, right, contexts)
        self.assertEqual(result['wholeGames'], 2)
        self.assertEqual(result['top3']['delta'], .5)
        self.assertEqual(result['top3']['pairedGameBootstrap95'], [0, 1])
        self.assertEqual(result, paired_comparison(left, right, contexts))


if __name__ == '__main__':
    unittest.main()
