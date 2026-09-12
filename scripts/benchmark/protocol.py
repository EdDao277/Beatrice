"""Offline input and prediction-time boundary; never reconstruct roles from pick order."""
from datetime import datetime, timedelta
import hashlib
import json


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load_prepared(path):
    # Hash the exact bytes parsed, so a file changing between reads cannot pass verification.
    raw = (path / 'games.jsonl').read_bytes()
    manifest = (path / 'report.json').read_bytes()
    report = json.loads(manifest)
    if report.get('version') != 1 or digest(raw) != report.get('gamesSha256'):
        raise ValueError('Prepared batch version/checksum mismatch')
    known_sources = {s['sha256'] for s in report['sources']}
    games, seen = [], set()
    for line in raw.splitlines():
        record = json.loads(line)
        if not record.get('sources') or not set(record['sources']) <= known_sources:
            raise ValueError('Missing or unknown source provenance')
        game = record['game']
        if not game.get('gameId') or game['gameId'] in seen:
            raise ValueError('Missing or duplicate game ID')
        seen.add(game['gameId'])
        datetime.fromisoformat(game['date'])
        teams = game['teams']
        if len(teams) != 2 or {t['side'] for t in teams} != {'BLUE', 'RED'}:
            raise ValueError('Invalid sides')
        if any(t['result'] not in (0, 1) or len(t['players']) != 5 for t in teams):
            raise ValueError('Invalid lineup/result')
        if sum(t['result'] for t in teams) != 1:
            raise ValueError('Results must be opposite')
        champions = [p['championId'] for t in teams for p in t['players']]
        if len(set(champions)) != 10 or not all(champions):
            raise ValueError('Invalid champion identities')
        games.append(game)
    if len(games) != report['acceptedGames'] or not games:
        raise ValueError('Prepared game count mismatch/empty batch')
    return sorted(games, key=lambda g: (g['date'], g['gameId'])), {
        'gamesSha256': digest(raw), 'reportSha256': digest(manifest),
        'sources': sorted(known_sources)}


def partition(games, validation_start, test_start):
    validation, test = map(datetime.fromisoformat, (validation_start, test_start))
    if validation >= test or validation.tzinfo or test.tzinfo:
        raise ValueError('Cutoffs must be ordered, timezone-free source dates')
    groups = {key: [] for key in ('reference', 'embargo', 'validation', 'test')}
    for game in games:
        date = datetime.fromisoformat(game['date'])
        if date < validation - timedelta(days=7):
            key = 'reference'
        elif date < validation:
            key = 'embargo'
        elif date < test - timedelta(days=7):
            key = 'validation'
        elif date < test:
            key = 'embargo'
        else:
            key = 'test'
        groups[key].append(game)
    return groups


def pick_cases(game):
    """Provisional standard tournament schedule, NOT verified event reconstruction.

    Roster identities are assumed known before draft; sort them to remove the source's
    final-role row order. Labels are kept outside the scorer context.
    """
    if not game['draftFieldsComplete']:
        return
    teams = {t['side']: t for t in game['teams']}
    if teams['BLUE']['firstPickRaw'] not in ('1', '1.0') or teams['RED']['firstPickRaw'] not in ('0', '0.0'):
        raise ValueError('Unconfirmed BLUE first-pick field')
    order = 'BLUE RED BLUE RED BLUE RED BLUE RED RED BLUE BLUE RED RED BLUE RED BLUE RED BLUE BLUE RED'.split()
    counts = {(side, kind): 0 for side in teams for kind in ('picks', 'bans')}
    visible = []
    for index, side in enumerate(order):
        kind = 'bans' if index < 6 or 12 <= index < 16 else 'picks'
        champion = teams[side][kind][counts[side, kind]]
        if not champion or champion in {a['championId'] for a in visible}:
            raise ValueError('Missing/duplicate champion in draft fields')
        if kind == 'picks':
            context = {
                'caseId': f"{game['gameId']}:{index}", 'gameId': game['gameId'],
                'date': game['date'], 'patch': game['patch'], 'league': game['league'],
                'side': side, 'format': 'TOURNAMENT', 'actionIndex': index,
                'protocol': 'provisional-standard-tournament-v1',
                'playerIds': sorted(p['playerId'] for p in teams[side]['players']),
                'allyPicks': [a['championId'] for a in visible if a['kind'] == 'picks' and a['side'] == side],
                'enemyPicks': [a['championId'] for a in visible if a['kind'] == 'picks' and a['side'] != side],
                'bans': [a['championId'] for a in visible if a['kind'] == 'bans'],
            }
            label = {'caseId': context['caseId'], 'championId': champion, 'won': teams[side]['result']}
            yield context, label
        visible.append({'side': side, 'kind': kind, 'championId': champion})
        counts[side, kind] += 1
