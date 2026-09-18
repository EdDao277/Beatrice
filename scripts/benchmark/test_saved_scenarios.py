"""Exercise the real Java scorer and offline-only ML failure boundary."""
from pathlib import Path
import tempfile
import unittest

try:
    from saved_scenarios import java_rank, bounded, compile_java
except ImportError:
    java_rank = bounded = compile_java = None


class SavedScenarioTests(unittest.TestCase):
    def test_unknown_metadata_cannot_supply_traits_and_blind_is_not_damage_skew(self):
        from saved_scenarios import metadata_traits, realized_composition
        metadata = metadata_traits({'metadata': [{'champion_id': 'A', 'raw_metadata':
            {'utility_tags': '{Frontline}', 'damage_type': 'AP'}}]})
        self.assertEqual(metadata['A']['traits'], [])
        self.assertFalse(realized_composition('heavyAP', []))
        self.assertTrue(realized_composition('heavyAP', [{'AP'}, {'AP'}, {'AP'}, {'AD'}]))
        self.assertFalse(realized_composition('heavyAP', [{'AP', 'AD'}] * 4))
        self.assertFalse(realized_composition('noFrontline', [{'AP'}, {'Frontline'}, {'AP'}]))

    def test_missing_corrupt_model_and_nonfinite_features_fail_closed(self):
        from saved_scenarios import OfflineModel
        import numpy as np
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'missing.txt'
            self.assertIsNone(OfflineModel(path, 'fixed').predict(np.zeros((1, 108))))
            path.write_text('corrupt')
            self.assertIsNone(OfflineModel(path, 'fixed').predict(np.zeros((1, 108))))
        from saved_scenarios import ROOT
        from readiness import MODEL_HASH
        model = OfflineModel(ROOT / 'data/oracle/blind-2026-09-14-reviewed/recency_tree.txt', MODEL_HASH)
        self.assertIsNone(model.predict(np.full((1, 108), float('nan'))))
        self.assertIsNone(model.predict(np.zeros((1, 33))))
        self.assertIsNone(model.predict(None))

    def test_suite_is_reproducible_and_does_not_mutate_saved_pools(self):
        from saved_scenarios import scenarios
        import copy
        snapshot = {'teams': [{'id': 1, 'players': [
            {'role': role, 'champions': [{'name': f'C{i}', 'comfort': 8}, {'name': 'Flex', 'comfort': 7}]}
            for i, role in enumerate(('TOP', 'JUNGLE', 'MID', 'BOT', 'SUPPORT'))]}],
            'catalog': {'champions': [{'id': f'C{i}', 'name': f'C{i}'} for i in range(30)] + [{'id': 'Flex', 'name': 'Flex'}]},
            'metadata': []}
        original = copy.deepcopy(snapshot)
        first = scenarios(snapshot, {})
        self.assertEqual(first, scenarios(snapshot, {}))
        self.assertEqual(snapshot, original)
        self.assertTrue(first)
        self.assertTrue(all(not set(s['allies']) & set(s['enemies']) for s in first))
        self.assertTrue(all(len(set(s['unavailable'])) == len(s['unavailable']) for s in first))

    def test_java_excludes_unavailable_and_preserves_cold_candidates_and_full_rankings(self):
        self.assertIsNotNone(java_rank)
        with tempfile.TemporaryDirectory() as folder:
            classes = Path(folder)
            compile_java(classes)
            scenario = {'id': 'fixture', 'role': 'TOP', 'desired': ['Frontline'], 'covered': [],
                        'unavailable': ['BANNED'], 'pool': [
                            {'id': c, 'comfort': rating, 'traits': [], 'known': True}
                            for c, rating in [('A', 10), ('B', 9), ('C', 8), ('D', 7), ('COLD', 6), ('BANNED', 10)]]}
            ranked = java_rank([scenario], classes)['fixture']
            self.assertEqual([r['id'] for r in ranked], ['A', 'B', 'C', 'D', 'COLD'])
            self.assertAlmostEqual(ranked[0]['score'], 57.5)

    def test_ml_cannot_add_candidates_or_affect_weak_evidence_or_exceed_cap(self):
        self.assertIsNotNone(bounded)
        java = [{'id': 'A', 'score': 65.}, {'id': 'COLD', 'score': 64.}]
        self.assertEqual(bounded(java, None, {}), java)
        self.assertEqual(bounded(java, {'OUTSIDE': 100., 'A': 0.}, {'A': True}), java)
        self.assertEqual(bounded(java, {'A': float('nan'), 'COLD': 2.}, {'A': True}), java)
        self.assertEqual(bounded(java, {'A': 0., 'COLD': 100.}, {}), java)
        result = bounded(java, {'A': 100., 'COLD': 0.}, {'A': True}, cap=2.5)
        self.assertEqual({r['id'] for r in result}, {'A', 'COLD'})
        self.assertEqual(next(r['score'] for r in result if r['id'] == 'COLD'), 64.)
        self.assertTrue(all(abs(r['score'] - next(j['score'] for j in java if j['id'] == r['id'])) <= 2.5 for r in result))


if __name__ == '__main__':
    unittest.main()
