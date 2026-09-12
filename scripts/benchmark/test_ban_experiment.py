"""Ban replay must not expose future choices or relabel imitation as utility."""
import copy
import gzip
import importlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from test_protocol import game
from test_source_audit import source_fixture


def read_rows(path, name):
    with gzip.open(path / (name + '.jsonl.gz'), 'rt', encoding='utf-8') as stream:
        return [json.loads(line) for line in stream]


class BanExperimentTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('ban_experiment'), 'Ban experiment is not implemented')
        self.ban = importlib.import_module('ban_experiment')

    def test_phase_two_sees_only_the_six_preceding_picks_and_ordinal_bans(self):
        cases = list(self.ban.ban_cases(game()))
        self.assertEqual([c['actionIndex'] for c, _ in cases], [0, 1, 2, 3, 4, 5, 12, 13, 14, 15])
        self.assertEqual([l['championId'] for _, l in cases], ['B0', 'B5', 'B1', 'B6', 'B2', 'B7', 'B8', 'B3', 'B9', 'B4'])
        first, second_phase = cases[0][0], cases[6][0]
        self.assertEqual(first['bans'], [])
        self.assertEqual(first['enemyPicks'], [])
        self.assertEqual(second_phase['banPhase'], 'second')
        self.assertEqual(second_phase['allyPicks'], ['C5', 'C6', 'C7'])
        self.assertEqual(second_phase['enemyPicks'], ['C0', 'C1', 'C2'])
        self.assertEqual(second_phase['bans'], ['B0', 'B5', 'B1', 'B6', 'B2', 'B7'])
        self.assertEqual(first['enemyPlayerIds'], ['P5', 'P6', 'P7', 'P8', 'P9'])
        self.assertNotIn('won', cases[0][1])

    def test_future_choices_and_current_final_assignments_cannot_change_early_context(self):
        original = game()
        changed = copy.deepcopy(original)
        for team in changed['teams']:
            team['players'].reverse()
            team['result'] = 1 - team['result']
            team['picks'][4] += 'changed'
            team['bans'][4] += 'changed'
            for player in team['players']:
                player['role'] = 'UNKNOWN'
                player['championId'] = 'irrelevant-final-assignment'
        old = list(self.ban.ban_cases(original))
        new = list(self.ban.ban_cases(changed))
        self.assertEqual([c for c, _ in old[:6]], [c for c, _ in new[:6]])
        self.assertEqual(old[6][0], new[6][0])

    def test_earlier_ban_state_has_the_same_exclusive_day_cutoff(self):
        prior = game('prior', '2024-01-01 12:00:00')
        lagged = game('lagged', '2024-01-02 00:00:00')
        own = game('own', '2024-01-03 00:00:00')
        history = self.ban.BanHistory([prior, lagged, own])
        snapshot = history.advance('2024-01-03')
        self.assertEqual(snapshot['sourceGameIds'], ['prior'])
        self.assertEqual(history.ban_counts['B0'], 1)
        self.assertEqual(history.completed_games, 1)
        history.advance('2024-01-03')
        self.assertEqual(history.ban_counts['B0'], 1)
        history.advance('2024-01-04')
        self.assertEqual(history.ban_counts['B0'], 2)
        with self.assertRaises(ValueError):
            history.advance('2024-01-02')

    def test_candidates_require_prior_evidence_and_exclude_only_visible_and_explicit_protection(self):
        context, target = next(self.ban.ban_cases(game()))
        history = self.ban.BanHistory([game('prior', '2024-01-01 00:00:00')])
        history.advance('2025-02-01')
        result = self.ban.recommend(context, history)
        self.assertIn('B4', result['championIds'])  # A future ban is still legal now.
        self.assertNotIn('C0', result['championIds'])  # One prior pick is weak support.
        context.update(bans=['B0'], enemyPicks=['B5'], protectedPicks=['B1'], intendedPicks=['B2'])
        result = self.ban.recommend(context, history)
        self.assertFalse(set(result['championIds']) & {'B0', 'B5', 'B1', 'B2'})
        self.assertTrue(all(len(row) == len(self.ban.FEATURE_NAMES) for row in result['x']))
        empty = self.ban.recommend(context, self.ban.BanHistory([]))
        self.assertEqual(empty['championIds'], [])
        self.assertEqual(empty['abstention'], 'insufficient_prior_imitation_evidence')
        self.assertNotIn(target['championId'], empty['championIds'])

    def test_observed_familiarity_synergy_and_missing_evidence_remain_distinct(self):
        history = self.ban.BanHistory([game(str(i), '2024-01-01 00:00:00') for i in range(30)])
        history.advance('2025-02-01')
        context, _ = next(self.ban.ban_cases(game()))
        context['enemyPicks'] = ['C6']
        result = self.ban.recommend(context, history)
        evidence = {row['championId']: row for row in result['evidence']}
        self.assertEqual(evidence['C5']['enemyPlayerChampionGames']['P5'], 30)
        self.assertEqual(evidence['C5']['ownPlayerChampionGames']['P0'], 0)
        self.assertEqual(evidence['C5']['enemySynergy'][0]['games'], 30)
        self.assertTrue(evidence['B0']['missing']['championResults'])
        self.assertTrue(evidence['B0']['missing']['enemyFamiliarity'])
        self.assertEqual(evidence['B0']['enemySynergy'], [])
        self.assertEqual(evidence['B0']['supportReason'], 'earlier_ban_observation')
        self.assertFalse(evidence['B0']['productionThreatCertified'])

    def test_generic_linear_fit_is_labeled_as_ban_imitation_and_preserves_training_only_scaling(self):
        cases = [{'x': np.array([[0., 5.], [2., 5.], [1., 5.]]), 'target': 1, 'weight': 1.}]
        model = self.ban.fit(cases)
        self.assertEqual(model['signal'], 'pro_ban_imitation')
        self.assertEqual(model['active'], [True, False])
        scores = self.ban.score(json.loads(json.dumps(model)), cases[0]['x'])
        self.assertGreater(scores[1], scores[2])
        self.assertGreater(scores[2], scores[0])
        self.assertAlmostEqual(model['mean'][0], 1.)

    def test_missing_targets_stay_in_metrics_denominator(self):
        records = [{'rank': 1, 'count': 2, 'latencyMs': 1, 'missingEvidence': False},
                   {'rank': None, 'count': 0, 'latencyMs': 3, 'missingEvidence': True}]
        metrics = self.ban.measure(records)
        self.assertEqual(metrics['top1Agreement'], .5)
        self.assertEqual(metrics['candidateCoverage'], .5)
        self.assertEqual(metrics['targetAbsentRate'], .5)
        self.assertEqual(metrics['mrr'], .5)
        self.assertEqual(metrics['meanInferenceLatencyMs'], 2.)
        self.assertEqual(metrics['missingEvidenceRate'], .5)

    def test_full_fixture_exports_trains_replays_and_seals_test(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source_fixture(root, [game('warmup', '2024-01-01 00:00:00'),
                                  game('training', '2024-04-01 00:00:00'),
                                  game('validation', '2025-02-01 00:00:00'),
                                  game('test', '2026-02-01 00:00:00')])
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            report = self.ban.build(root, root, root / 'dataset')
            self.assertEqual(report['exportedGames'], {'training': 1, 'validation': 1})
            contexts = read_rows(root / 'dataset', 'contexts')
            labels = read_rows(root / 'dataset', 'labels')
            features = read_rows(root / 'dataset', 'features')
            self.assertEqual(len(contexts), 20)
            self.assertEqual([c['caseId'] for c in contexts], [l['caseId'] for l in labels])
            self.assertEqual([c['caseId'] for c in contexts], [f['caseId'] for f in features])
            self.assertEqual({c['gameId'] for c in contexts}, {'training', 'validation'})
            self.assertTrue(all('championId' not in c and 'won' not in c for c in contexts))
            self.assertTrue(all('target' not in f and 'won' not in f for f in features))
            snapshots = read_rows(root / 'dataset', 'snapshots')
            self.assertTrue(all('test' not in s['sourceGameIds'] for s in snapshots))
            fitted = self.ban.train(root / 'dataset', root / 'trained', max_negatives=3)
            self.assertTrue(fitted['testUnscored'])
            self.assertEqual(fitted['metrics']['validation']['linear']['cases'], 10)
            self.assertEqual(fitted['metrics']['validation']['ban_popularity']['cases'], 10)
            self.assertEqual(fitted['byPhase']['validation']['first']['linear']['cases'], 6)
            self.assertEqual(fitted['byPhase']['validation']['second']['linear']['cases'], 4)
            self.assertEqual(fitted['metrics']['validation']['linear']['illegalSuggestionRate'], 0.)
            model = json.loads((root / 'trained' / 'model.json').read_text())
            self.assertEqual(model['signal'], 'pro_ban_imitation')
            self.assertIn('sampled', model['configuration']['negativePolicy'])
            predictions = read_rows(root / 'trained', 'predictions')
            self.assertEqual(len(predictions), 20)
            self.assertTrue(all(p['signal'] == 'pro_ban_imitation' for p in predictions))
            self.assertTrue(all(Path(p['evidenceRef']['file']).resolve() ==
                                (root / 'dataset' / 'evidence.jsonl.gz').resolve() for p in predictions))
            self.assertEqual({p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}, before)
            with (root / 'dataset' / 'feature-schema.json').open('a') as stream:
                stream.write('\n')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                self.ban.train(root / 'dataset', root / 'tampered')


if __name__ == '__main__':
    unittest.main()
