"""Offline pick features from lagged, audited opening-game prevalence."""
from collections import Counter
from datetime import datetime, timedelta
from math import log1p

import numpy as np
from ml_features import FEATURE_NAMES

WINDOW_FEATURES = ('pick_rate', 'ban_rate', 'priority', 'pick_log', 'ban_log',
                   'games_log', 'window_missing', 'champion_unseen')
RECENCY_NAMES = tuple(f'{window}_{name}' for window in ('14d', '30d', 'patch')
                      for name in WINDOW_FEATURES) + ('priority_14d_minus_30d',)
EXTENDED_NAMES = tuple(FEATURE_NAMES) + RECENCY_NAMES + tuple(
    f'{stage}_{name}' for stage in ('blind', 'late') for name in RECENCY_NAMES)


def is_blind(context):
    return not context['allyPicks'] and not context['enemyPicks']


def route_blind(context, frozen, specialist):
    return specialist if is_blind(context) else frozen


class RecencyTable:
    def __init__(self, windows, source_count):
        self.windows = windows
        self.source_count = source_count
        self.cache = {}

    def vector(self, champion):
        if champion not in self.cache:
            values = []
            for games, picks, bans in self.windows:
                p, b = picks[champion], bans[champion]
                values.extend([p / games if games else 0., b / games if games else 0.,
                               (p + b) / games if games else 0., log1p(p), log1p(b),
                               log1p(games), float(not games), float(not (p + b))])
            values.append(values[2] - values[10])
            self.cache[champion] = values
        return self.cache[champion]


class RecencyHistory:
    def __init__(self, games):
        # Callers supply only audited openings. Outcomes and final roles are never read.
        self.games = sorted(games, key=lambda g: (g['date'], g['gameId']))
        if len({g['gameId'] for g in self.games}) != len(self.games):
            raise ValueError('Duplicate history game')
        self.day = None
        self.tables = {}

    def at(self, day, patch):
        when = datetime.fromisoformat(day)
        if when.tzinfo or when.time() != datetime.min.time() or when.year >= 2026:
            raise ValueError('Requires pre-2026 timezone-free prediction day')
        if self.day and when < self.day:
            raise ValueError('Cannot move history backwards')
        if when != self.day:
            self.tables = {}
        self.day = when
        if patch in self.tables:
            return self.tables[patch]
        cutoff = when - timedelta(days=1)
        earlier = [g for g in self.games if datetime.fromisoformat(g['date']) < cutoff]
        windows = []
        for days in (14, 30, None):
            selected = [g for g in earlier if (g['patch'] == patch if days is None
                        else datetime.fromisoformat(g['date']) >= cutoff - timedelta(days=days))]
            picks, bans = Counter(), Counter()
            for game in selected:
                picks.update({c for t in game['teams'] for c in t['picks'] if c})
                bans.update({c for t in game['teams'] for c in t['bans'] if c})
            windows.append((len(selected), picks, bans))
        table = RecencyTable(windows, len(earlier))
        self.tables[patch] = table
        return table


def extend(original, ids, context, table):
    if original.shape != (len(ids), len(FEATURE_NAMES)) or len(set(ids)) != len(ids):
        raise ValueError('Candidate feature alignment mismatch')
    recent = np.asarray([table.vector(c) for c in ids], dtype=np.float32).reshape(len(ids), len(RECENCY_NAMES))
    return np.concatenate((original, recent, recent * is_blind(context),
                           recent * (len(context['allyPicks']) >= 3)), axis=1)
