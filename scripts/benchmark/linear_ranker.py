"""Small regularized pairwise linear ranker. Outputs are NOT probabilities."""
import numpy as np

CONFIG = {'steps': 300, 'learningRate': .1, 'l2': .01, 'initialization': 'zeros',
          'negativePolicy': 'all alternatives; equal mass per case', 'clipZ': 8}


def make_pairs(cases):
    differences, masses = [], []
    for case in cases:
        x, target = case['x'], case['target']
        if target is None or len(x) < 2:
            continue
        negative = np.arange(len(x)) != target
        differences.append(x[target] - x[negative])
        masses.extend([case['weight'] / (len(x) - 1)] * (len(x) - 1))
    if not differences:
        raise ValueError('No covered training cases with alternatives')
    mass = np.asarray(masses, dtype=float)
    return np.concatenate(differences), mass / mass.sum()


def objective(weights, differences, mass, l2):
    margin = differences @ weights
    loss = mass @ np.logaddexp(0, -margin) + .5 * l2 * (weights @ weights)
    gradient = -(differences.T @ (mass * np.exp(-np.logaddexp(0, margin)))) + l2 * weights
    return float(loss), gradient


def transformed(model, x):
    x = np.asarray(x, dtype=float)
    mean, scale, weights = (np.asarray(model[k], dtype=float) for k in ('mean', 'scale', 'weights'))
    active = np.asarray(model['active'], dtype=bool)
    if (x.ndim != 2 or mean.ndim != 1 or x.shape[1] != len(mean)
            or any(a.shape != mean.shape for a in (scale, weights, active))
            or not all(np.isfinite(a).all() for a in (x, mean, scale, weights)) or (scale <= 0).any()):
        raise ValueError('Invalid feature matrix or model parameters')
    return np.clip((x - mean) / scale, -8, 8) * active


def score(model, x):
    return transformed(model, x) @ np.asarray(model['weights'])


def fit(cases):
    """Only training cases enter this function; validation is deliberately not an argument."""
    usable = []
    for c in cases:
        x, target, weight = c['x'], c['target'], c['weight']
        if x.ndim != 2 or not np.isfinite(x).all() or not np.isfinite(weight) or weight <= 0:
            raise ValueError('Invalid training case')
        if target is not None and (type(target) is not int or not 0 <= target < len(x)):
            raise ValueError('Invalid target index')
        if target is not None and len(x) >= 2:
            usable.append(c)
    if not usable:
        raise ValueError('No covered training cases with alternatives')
    all_x = np.concatenate([c['x'] for c in usable])
    # Candidate list size must not change a game's influence on preprocessing.
    row_mass = np.concatenate([np.full(len(c['x']), c['weight'] / len(c['x'])) for c in usable])
    row_mass /= row_mass.sum()
    mean = row_mass @ all_x
    variance = row_mass @ ((all_x - mean) ** 2)
    active = variance > 1e-12
    scale = np.where(active, np.sqrt(variance), 1)
    weights = np.zeros(all_x.shape[1])
    model = {'version': 1, 'signal': 'pro_pick_imitation', 'scoreMeaning': 'uncalibrated ranking preference',
             'mean': mean.tolist(), 'scale': scale.tolist(), 'active': active.tolist(),
             'weights': weights.tolist(), 'configuration': dict(CONFIG)}
    normalized = [{**c, 'x': transformed(model, c['x'])} for c in usable]
    differences, mass = make_pairs(normalized)
    trace = []
    for step in range(CONFIG['steps']):
        loss, gradient = objective(weights, differences, mass, CONFIG['l2'])
        if not np.isfinite(loss) or not np.isfinite(gradient).all():
            raise ValueError('Nonfinite optimization')
        if step % 50 == 0:
            trace.append(loss)
        weights -= CONFIG['learningRate'] * gradient
    trace.append(objective(weights, differences, mass, CONFIG['l2'])[0])
    model.update({'weights': weights.tolist(), 'lossTrace': trace,
                  'trainingCases': len(usable), 'trainingPairs': len(differences)})
    return model
