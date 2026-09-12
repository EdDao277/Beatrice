import copy
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from baseline import History, VARIANTS, recommend
from compact_dataset import build, compact_case
from ml_features import FEATURE_NAMES, vector
from protocol import pick_cases
from test_protocol import game
from test_source_audit import source_fixture


def rows(path):
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        return [json.loads(row) for row in stream]


class CompactDatasetTests(unittest.TestCase):
    def test_three_derived_rankings_match_independent_baseline_calls(self):
        history = History()
        for i in range(4):
            item = game('history' + str(i), '2024-01-01 00:00:00')
            if i % 2:
                for team in item['teams']:
                    team['result'] = 1 - team['result']
                    champions = [p['championId'] for p in team['players']]
                    for player, champion in zip(team['players'], champions[1:] + champions[:1]):
                        player['championId'] = champion
            history.observe(item)
        context, _ = list(pick_cases(game()))[7]
        context.update(split='validation', snapshotId='fixture')
        result = recommend(context, history, 'pool_rules_stats', pool_policy='inferred')
        features, evidence, checks = compact_case(context, result, history)
        self.assertEqual(features['championIds'], sorted(c['championId'] for c in result['candidates']))
        by_id = {c['championId']: c for c in result['candidates']}
        self.assertEqual(features['x'], [vector(context, by_id[c]) for c in features['championIds']])
        self.assertTrue(all(len(x) == len(FEATURE_NAMES) for x in features['x']))
        for variant in VARIANTS:
            expected = recommend(context, history, variant, pool_policy='inferred')['candidates']
            positions = {c['championId']: (i + 1, c['score']) for i, c in enumerate(expected)}
            self.assertEqual(features['baselineScores'][variant], [positions[c][1] for c in features['championIds']])
            self.assertEqual(features['baselineRanks'][variant], [positions[c][0] for c in features['championIds']])
        self.assertEqual(checks['candidateLegalityChecks'], len(by_id))
        self.assertEqual(checks['impossibleLineupCandidates'], 0)
        self.assertTrue(all('completionWitness' not in c for c in evidence['candidates']))
        self.assertTrue(all(c['evidenceQuality']['metaSmallSample'] for c in evidence['candidates']))

    def test_illegal_or_impossible_completion_cannot_be_exported(self):
        history = History()
        history.observe(game('history', '2024-01-01 00:00:00'))
        context, _ = next(pick_cases(game()))
        context.update(split='validation', snapshotId='fixture')
        result = recommend(context, history, 'pool_rules_stats', pool_policy='inferred')
        broken = copy.deepcopy(result)
        broken['candidates'][0]['completionWitness']['P0'] = context['bans'][0]
        with self.assertRaisesRegex(ValueError, 'candidate completion'):
            compact_case(context, broken, history)
        broken = copy.deepcopy(result)
        broken['candidates'][0]['completionWitness'].pop('P0')
        with self.assertRaisesRegex(ValueError, 'candidate completion'):
            compact_case(context, broken, history)

    def test_missing_evidence_has_explicit_masks_and_zero_counts(self):
        history = History()
        history.observe(game('history', '2024-01-01 00:00:00'))
        context, _ = next(pick_cases(game()))
        context.update(split='validation', snapshotId='fixture')
        context['playerIds'] = ['NEW' + str(i) for i in range(5)]
        result = recommend(context, history, 'pool_rules_stats', pool_policy='inferred')
        features, evidence, _ = compact_case(context, result, history)
        self.assertTrue(features['championIds'])
        for candidate in evidence['candidates']:
            quality = candidate['evidenceQuality']
            self.assertEqual(quality['observedPlayerCount'], 0)
            self.assertTrue(quality['pairMissing'])
            self.assertEqual(quality['pairObservedCount'], 0)
            self.assertEqual(quality['pairPossibleCount'], 0)
        self.assertTrue(all(x[:3] == [0, 0, 0] for x in features['x']))

    def test_empty_history_exports_auditable_abstention_without_target_injection(self):
        context, label = next(pick_cases(game()))
        context.update(split='training', snapshotId='fixture')
        history = History()
        result = recommend(context, history, 'pool_rules_stats', pool_policy='inferred')
        features, evidence, checks = compact_case(context, result, history)
        self.assertEqual(features['championIds'], [])
        self.assertEqual(features['x'], [])
        self.assertEqual(features['abstention'], 'no_feasible_pool_completion')
        self.assertNotIn(label['championId'], features['championIds'])
        self.assertEqual(evidence['candidates'], [])
        self.assertEqual(checks['candidateLegalityChecks'], 0)
        self.assertTrue(all(not scores for scores in features['baselineScores'].values()))

    def test_all_games_export_once_per_case_with_auditable_temporal_artifacts(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source_fixture(root, [game('warmup', '2024-01-01 00:00:00'),
                                  game('train1', '2024-04-01 00:00:00'),
                                  game('train2', '2024-05-01 00:00:00'),
                                  game('validation', '2025-02-01 00:00:00'),
                                  game('test', '2026-02-01 00:00:00')])
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            # Spy on the real scorer: its call count is the efficiency contract.
            with patch('compact_dataset.recommend', wraps=recommend) as scorer:
                report = build(root, root, root / 'out')
            self.assertEqual(scorer.call_count, 30)
            self.assertTrue(all(call.kwargs == {'pool_policy': 'inferred'} for call in scorer.call_args_list))
            self.assertEqual(report['exportedGames'], {'training': 2, 'validation': 1})
            self.assertEqual(report['checks']['candidateLegalityChecks'], 165)
            self.assertEqual(report['checks']['legalityViolations'], 0)
            self.assertEqual(report['checks']['impossibleLineupCandidates'], 0)
            self.assertEqual({p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}, before)
            contexts = rows(root / 'out' / 'contexts.jsonl.gz')
            features = rows(root / 'out' / 'features.jsonl.gz')
            evidence = rows(root / 'out' / 'evidence.jsonl.gz')
            labels = rows(root / 'out' / 'labels.jsonl.gz')
            self.assertEqual([c['caseId'] for c in contexts], [f['caseId'] for f in features])
            self.assertEqual([c['caseId'] for c in contexts], [e['caseId'] for e in evidence])
            self.assertEqual([c['caseId'] for c in contexts], [label['caseId'] for label in labels])
            self.assertTrue(all('won' not in f and 'targetChampion' not in f for f in features))
            self.assertTrue(all('role' not in json.dumps(c) for c in contexts))
            self.assertEqual({c['gameId'] for c in contexts}, {'train1', 'train2', 'validation'})
            snapshots = rows(root / 'out' / 'snapshots.jsonl.gz')
            self.assertEqual(snapshots[0]['sourceGameIds'], ['warmup'])
            self.assertEqual(snapshots[-1]['sourceGameIds'], ['train1', 'train2', 'warmup'])
            self.assertTrue(all('test' not in s['sourceGameIds'] for s in snapshots))
            manifest = json.loads((root / 'out' / 'manifest.json').read_text())
            self.assertEqual(manifest['version'], 3)
            self.assertEqual(manifest['status'], 'COMPACT_OPENING_GAME_RESEARCH_EXPORT')
            self.assertTrue(manifest['testUnscored'])
            self.assertIn('feature-schema.json', manifest['artifacts'])
            self.assertIn('compact_dataset.py', manifest['codeSha256'])
            self.assertEqual(report['metrics']['validation']['pool']['cases'], 10)
            with self.assertRaises(FileExistsError):
                build(root, root, root / 'out')

    def test_own_outcome_and_final_roles_do_not_change_own_features(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            validation = game('validation', '2025-02-01 00:00:00')
            games = [game('warmup', '2024-01-01 00:00:00'),
                     game('train', '2024-04-01 00:00:00'), validation]
            source_fixture(root, games)
            build(root, root, root / 'before')
            for team in validation['teams']:
                team['result'] = 1 - team['result']
                team['players'].reverse()
                for player in team['players']:
                    player['role'] = 'UNKNOWN'
            source_fixture(root, games)
            build(root, root, root / 'after')
            for name in ('features', 'contexts', 'evidence'):
                self.assertEqual(rows(root / 'before' / (name + '.jsonl.gz')),
                                 rows(root / 'after' / (name + '.jsonl.gz')))
            self.assertNotEqual(rows(root / 'before' / 'labels.jsonl.gz'), rows(root / 'after' / 'labels.jsonl.gz'))

    def test_explicit_limits_and_input_mutation_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source_fixture(root, [game('warmup', '2024-01-01 00:00:00'),
                                  game('train1', '2024-04-01 00:00:00'),
                                  game('train2', '2024-05-01 00:00:00'), game('validation')])
            report = build(root, root, root / 'limited', max_training=1)
            self.assertEqual(report['exportedGames']['training'], 1)
            self.assertEqual(report['excluded']['training']['sample_limit'], 1)
            for limit in (0, -1, True):
                with self.assertRaises(ValueError):
                    build(root, root, root / 'invalid', max_training=limit)

            def mutate_source(*args, **kwargs):
                result = recommend(*args, **kwargs)
                with (root / 'source.csv').open('a') as stream:
                    stream.write('\n')
                return result

            with patch('compact_dataset.recommend', side_effect=mutate_source):
                with self.assertRaisesRegex(ValueError, 'Input changed'):
                    build(root, root, root / 'tampered')
            self.assertFalse((root / 'tampered' / 'manifest.json').exists())


if __name__ == '__main__':
    unittest.main()
