"""CPU LambdaRank experiment: relevance means recorded pro choice, not pick quality."""
import numpy as np
import lightgbm as lgb

PARAMETERS = {'objective': 'lambdarank', 'metric': 'ndcg', 'label_gain': [0, 1],
              'learning_rate': .05, 'num_leaves': 15, 'min_data_in_leaf': 20,
              'lambda_l2': 1., 'max_bin': 63, 'lambdarank_truncation_level': 10,
              'lambdarank_norm': True, 'deterministic': True, 'force_col_wise': True,
              'num_threads': 2, 'seed': 1729, 'verbosity': -1}
ROUNDS = 100


def fit_tree(cases):
    width = None
    for c in cases:
        x, target, weight = c['x'], c['target'], c['weight']
        if (x.ndim != 2 or not np.isfinite(x).all() or not np.isfinite(weight) or weight <= 0
                or (width is not None and x.shape[1] != width)
                or (target is not None and (type(target) is not int or not 0 <= target < len(x)))):
            raise ValueError('Invalid training group')
        width = x.shape[1]
    usable = [c for c in cases if c['target'] is not None and len(c['x']) >= 2]
    if not usable:
        raise ValueError('No covered training comparisons')
    x = np.concatenate([c['x'] for c in usable]).astype(np.float32)
    y = np.concatenate([np.arange(len(c['x'])) == c['target'] for c in usable]).astype(np.int32)
    weight = np.concatenate([np.full(len(c['x']), c['weight']) for c in usable])
    data = lgb.Dataset(x, label=y, weight=weight, group=[len(c['x']) for c in usable], free_raw_data=True)
    booster = lgb.train(PARAMETERS, data, num_boost_round=ROUNDS)
    return booster.model_to_string()


def tree_score(model, x, contributions=False):
    booster = lgb.Booster(model_str=model) if isinstance(model, str) else model
    if x.ndim != 2 or x.shape[1] != booster.num_feature() or not np.isfinite(x).all():
        raise ValueError('Invalid inference features')
    if not len(x):
        return np.empty((0, x.shape[1] + 1)) if contributions else np.empty(0)
    return booster.predict(x, pred_contrib=contributions, num_threads=2)
