"""Earlier-only history with day-level availability lag and immutable snapshot identities."""
from datetime import datetime, timedelta
import json

from baseline import History
from protocol import digest, partition


class EarlierHistory:
    def __init__(self, games):
        self.games = sorted(games, key=lambda g: (datetime.fromisoformat(g['date']), g['gameId']))
        self.index = 0
        self.history = History()
        self.current_day = None
        self.chain = '0' * 64

    def advance(self, day):
        when = datetime.fromisoformat(day)
        if when.time() != datetime.min.time() or when.tzinfo:
            raise ValueError('Snapshot must be a timezone-free calendar day')
        if self.current_day and when < self.current_day:
            raise ValueError('Cannot move history backwards')
        self.current_day = when
        cutoff = when - timedelta(days=1)
        while self.index < len(self.games):
            game = self.games[self.index]
            if datetime.fromisoformat(game['date']) >= cutoff:
                break
            self.history.observe(game)
            self.chain = digest((self.chain + json.dumps(game, sort_keys=True, separators=(',', ':'))).encode())
            self.index += 1
        snapshot = {'predictionDay': day, 'exclusiveCutoff': cutoff.isoformat(),
                    'latestObservation': self.history.latest_date, 'historyDigest': self.chain,
                    'sourceGameIds': sorted(self.history.game_ids), 'patches': dict(self.history.patches)}
        snapshot['snapshotId'] = digest(json.dumps(snapshot, sort_keys=True).encode())
        return snapshot


def dataset_partitions(games, training_start, validation_start, test_start):
    training = datetime.fromisoformat(training_start)
    validation = datetime.fromisoformat(validation_start)
    if datetime.fromisoformat(test_start) > datetime(2026, 1, 1):
        raise ValueError('The reserved 2026 test period cannot be moved into development data')
    if training >= validation or training.tzinfo:
        raise ValueError('Training must start before validation')
    old = partition(games, validation_start, test_start)
    return {'warmup': [g for g in old['reference'] if datetime.fromisoformat(g['date']) < training],
            'training': [g for g in old['reference'] if datetime.fromisoformat(g['date']) >= training],
            'validation': old['validation'], 'embargo': old['embargo'], 'test': old['test']}
