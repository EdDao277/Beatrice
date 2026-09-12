import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import numpy as np

from ml_features import FEATURE_NAMES, SCHEMA
from test_ml_features import candidate
from train_ranker import sha
from inference import Ranker


def model_folder(root):
    n = len(FEATURE_NAMES)
    values = {'linear.json': {'version': 1, 'signal': 'pro_pick_imitation',
                             'featureNames': list(FEATURE_NAMES), 'weights': [0.] * n,
                             'mean': [0.] * n, 'scale': [1.] * n, 'active': [True] * n},
              'schema.json': SCHEMA,
              'selected.json': {'signal': 'pro_pick_imitation', 'modelType': 'linear',
                                'modelFile': 'linear.json', 'deploymentEligible': True}}
    for name, value in values.items():
        (root / name).write_text(json.dumps(value), encoding='utf-8')
    (root / 'manifest.json').write_text(json.dumps({'artifacts': {n: sha(root / n) for n in values}}))


def request():
    champs = ['C0', 'C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'C7']
    rows = []
    for name in champs:
        row = candidate(); row['championId'] = name; rows.append(row)
    return {'requestId': 'test', 'evidenceAsOf': '2025-01-01T00:00:00',
            'decisionTime': '2025-01-02T00:00:00', 'availableChampionIds': champs[:-1],
            'context': {'playerIds': list('abcde'), 'allyPicks': [], 'enemyPicks': [], 'bans': ['C0'],
                        'savedPools': {p: dict.fromkeys(['C1', 'C2', 'C3', 'C5', 'C6'], 8) for p in 'abcde'}},
            'candidates': rows}


class InferenceTests(unittest.TestCase):
    def test_tree_artifact_obeys_pools_and_empty_candidate_contract(self):
        from tree_ranker import fit_tree
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); model_folder(root)
            x = np.zeros((3, len(FEATURE_NAMES)), dtype=np.float32)
            x[:, 0] = [0, 1, 2]
            model = fit_tree([{'x': x, 'target': 2, 'weight': 1.} for _ in range(30)])
            (root / 'tree.txt').write_bytes(model.encode('utf-8'))
            selected = {'signal': 'pro_pick_imitation', 'modelType': 'tree',
                        'modelFile': 'tree.txt', 'deploymentEligible': True, 'offlineOnly': True}
            (root / 'selected.json').write_text(json.dumps(selected))
            manifest = json.loads((root / 'manifest.json').read_text())
            manifest['artifacts'].update({n: sha(root / n) for n in ('tree.txt', 'selected.json')})
            (root / 'manifest.json').write_text(json.dumps(manifest))
            engine = Ranker(root)
            req = request(); req['allowResearchModel'] = True
            result = engine.rank(req)
            self.assertEqual({c['championId'] for c in result['candidates']}, {'C1', 'C2', 'C3', 'C5', 'C6'})
            for c in result['candidates']:
                self.assertAlmostEqual(sum(c['featureContributions'].values()) + c['modelBias'], c['score'])
                self.assertEqual(len(set(c['completionWitness'].values())), 5)
            req['context']['savedPools']['a'] = {}
            self.assertEqual(engine.rank(req)['candidates'], [])

    def test_saved_pools_legality_and_catalog_are_hard_constraints(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); model_folder(root)
            result = Ranker(root).rank(request())
            self.assertEqual([r['championId'] for r in result['candidates']], ['C1', 'C2', 'C3', 'C5', 'C6'])
            for row in result['candidates']:
                self.assertIsNone(row['modelConfidence'])
                self.assertEqual(len(set(row['completionWitness'].values())), 5)
                self.assertEqual(row['savedComfort'], dict.fromkeys('abcde', 8))
                self.assertIn('composition', row['missingInformation'])
                self.assertAlmostEqual(sum(row['featureContributions'].values()) + row['modelBias'], row['score'])

    def test_incomplete_pool_abstains_instead_of_widening(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); model_folder(root)
            req = request(); req['context']['savedPools']['a'] = {}
            result = Ranker(root).rank(req)
            self.assertEqual(result['candidates'], [])
            self.assertEqual(result['abstention'], 'no_feasible_saved_pool_candidate')

    def test_future_evidence_and_invalid_ratings_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); model_folder(root)
            engine = Ranker(root)
            req = request(); req['evidenceAsOf'] = '2026-01-01T00:00:00'
            with self.assertRaises(ValueError): engine.rank(req)
            req = request(); req['context']['savedPools']['a']['C1'] = 11
            with self.assertRaises(ValueError): engine.rank(req)

    def test_tampered_model_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); model_folder(root)
            (root / 'linear.json').write_text('{}')
            with self.assertRaises(ValueError): Ranker(root)

    def test_scaled_schema_metadata_is_compatible(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); model_folder(root)
            expanded = {**SCHEMA, 'datasetVersion': 3, 'matrixDtype': 'float32',
                        'treeNormalization': 'none; raw named numeric features'}
            (root / 'schema.json').write_text(json.dumps(expanded), encoding='utf-8')
            manifest = json.loads((root / 'manifest.json').read_text())
            manifest['artifacts']['schema.json'] = sha(root / 'schema.json')
            (root / 'manifest.json').write_text(json.dumps(manifest))
            self.assertEqual(len(Ranker(root).rank(request())['candidates']), 5)

    def test_offline_model_requires_override_even_with_validation_advantage(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); model_folder(root)
            selected = json.loads((root / 'selected.json').read_text())
            selected.update(offlineOnly=True, deploymentEligible=True)
            (root / 'selected.json').write_text(json.dumps(selected))
            manifest = json.loads((root / 'manifest.json').read_text())
            manifest['artifacts']['selected.json'] = sha(root / 'selected.json')
            (root / 'manifest.json').write_text(json.dumps(manifest))
            req = request(); req.pop('allowResearchModel', None)
            with self.assertRaises(ValueError):
                Ranker(root).rank(req)
            req['allowResearchModel'] = True
            self.assertEqual(len(Ranker(root).rank(req)['candidates']), 5)

    def test_jsonl_process_recovers_after_bad_request(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); model_folder(root)
            result = subprocess.run([sys.executable, str(Path(__file__).with_name('inference.py')),
                                     '--model-dir', str(root)], input='bad json\n' + json.dumps(request()) + '\n',
                                    capture_output=True, text=True, check=True)
            lines = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertEqual(lines[0]['error'], 'invalid_request')
            self.assertEqual(lines[1]['requestId'], 'test')
            self.assertEqual(len(lines[1]['candidates']), 5)

    def test_malformed_containers_and_numbers_do_not_kill_process(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); model_folder(root)
            bad_pool = request(); bad_pool['context']['savedPools'] = list('abcde')
            nan = request(); nan['requestId'] = float('nan')
            huge = request(); huge['candidates'][1]['playerChampionEvidence']['a'] = 10 ** 400
            for bad in (bad_pool, nan, huge, [], {'context': []}):
                with self.subTest(bad=type(bad).__name__):
                    completed = subprocess.run([sys.executable, str(Path(__file__).with_name('inference.py')),
                                                '--model-dir', str(root)],
                                               input=json.dumps(bad) + '\n' + json.dumps(request()) + '\n',
                                               capture_output=True, text=True)
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    lines = [json.loads(line) for line in completed.stdout.splitlines()]
                    self.assertEqual(lines[0]['error'], 'invalid_request')
                    self.assertEqual(len(lines[1]['candidates']), 5)

    def test_returned_pair_delta_matches_scoring_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); model_folder(root)
            req = request(); req['context']['allyPicks'] = ['C1']
            row = req['candidates'][2]
            row['evidence'] = {'meta': {'games': 100, 'wins': 50}, 'allyPairs': [
                {'ally': 'C1', 'games': 20, 'wins': 10, 'delta': 999,
                 'allyBaseline': {'games': 100, 'wins': 50}}]}
            result = Ranker(root).rank(req)
            c2 = next(c for c in result['candidates'] if c['championId'] == 'C2')
            self.assertEqual(c2['synergyEvidence'][0]['delta'], 0)


if __name__ == '__main__': unittest.main()
