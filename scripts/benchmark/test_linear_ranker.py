"""Real numerical tests: direction, gradients, weighting and reload, not library mocks."""
import json
import unittest
import numpy as np

from linear_ranker import fit, score, objective, make_pairs


def case(values, target=0, weight=.1):
    return {'x': np.array(values, dtype=float), 'target': target, 'weight': weight}


class RankerTests(unittest.TestCase):
    def test_learns_direction_and_roundtrips_without_validation(self):
        cases = [case([[2, 1], [0, 1]]), case([[4, 1], [1, 1]])]
        model = fit(cases)
        self.assertGreater(model['weights'][0], 0)
        self.assertEqual(model['weights'][1], 0)
        loaded = json.loads(json.dumps(model))
        scores = score(loaded, np.array([[3, 999], [0, 1]]))
        self.assertGreater(scores[0], scores[1])
        self.assertEqual(model, fit(cases))
        self.assertLess(model['lossTrace'][-1], model['lossTrace'][0])

    def test_gradient_matches_finite_difference(self):
        d = np.array([[2., -1], [-3, 4]])
        weights = np.array([.2, -.3]); mass = np.array([.25, .75])
        _, gradient = objective(weights, d, mass, .01)
        for i in range(2):
            step = np.zeros(2); step[i] = 1e-6
            numeric = (objective(weights + step, d, mass, .01)[0] -
                       objective(weights - step, d, mass, .01)[0]) / 2e-6
            self.assertAlmostEqual(gradient[i], numeric, places=6)

    def test_each_case_has_equal_mass_regardless_of_alternatives(self):
        d, mass = make_pairs([case([[1], [0]]), case([[2], [0], [1]])])
        np.testing.assert_allclose(mass, [.5, .25, .25])
        np.testing.assert_allclose(d[:, 0], [1, 2, 1])

    def test_missing_target_is_not_injected_or_fitted(self):
        train = [case([[1], [0]])]
        self.assertEqual(fit(train), fit(train + [case([[999]], None)]))
        with self.assertRaises(ValueError):
            fit([case([[1]], None)])

    def test_nonfinite_training_and_bad_model_are_rejected(self):
        with self.assertRaises(ValueError):
            fit([case([[float('nan')], [0]])])
        with self.assertRaises(ValueError):
            score({'weights': [float('nan')], 'mean': [0], 'scale': [1], 'active': [True]}, np.array([[1]]))


if __name__ == '__main__':
    unittest.main()
