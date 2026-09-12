"""A tiny nonlinear fixture tests ranking, persistence and input guards."""
import unittest
import numpy as np

from tree_ranker import fit_tree, tree_score


class TreeTests(unittest.TestCase):
    def test_tree_learns_interaction_and_roundtrips(self):
        # XNOR preferences require both positive and negative coefficients for each
        # feature, so no linear ranker can satisfy all four strict inequalities.
        # Both features vary within queries. A query-constant context has exactly
        # zero LambdaRank root gain and is unsuitable for testing greedy trees;
        # real stage contexts are already expanded as interactions in ml_features.
        cases = []
        for _ in range(60):
            cases.extend([{'x': np.array([[1., 1.], [1., 0.], [0., 1.]]), 'target': 0, 'weight': .2},
                          {'x': np.array([[0., 0.], [1., 0.], [0., 1.]]), 'target': 0, 'weight': .1}])
        model = fit_tree(cases)
        for case in cases[:2]:
            scores = tree_score(model, case['x'])
            self.assertGreater(scores[0], max(scores[1:]))
        self.assertEqual(model, fit_tree(cases))

    def test_missing_targets_are_not_injected(self):
        with self.assertRaises(ValueError):
            fit_tree([{'x': np.array([[1., 2.]]), 'target': None, 'weight': .1}])

    def test_invalid_uncovered_groups_cannot_bypass_input_guards(self):
        valid = {'x': np.array([[1., 2.], [2., 3.]]), 'target': 0, 'weight': .1}
        for broken in ({'x': np.array([[np.nan, 2.]]), 'target': None, 'weight': .1},
                       {'x': np.array([[1., 2.]]), 'target': None, 'weight': -1},
                       {'x': np.array([1., 2.]), 'target': None, 'weight': .1}):
            with self.subTest(broken=broken), self.assertRaises(ValueError):
                fit_tree([valid, broken])


if __name__ == '__main__':
    unittest.main()
