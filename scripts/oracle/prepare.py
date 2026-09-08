"""Read-only CSV preparation. Outputs are newly created; never updates champion metadata."""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

ROLES = {'top': 'TOP', 'jng': 'JUNGLE', 'jungle': 'JUNGLE', 'mid': 'MID', 'bot': 'BOT', 'adc': 'BOT', 'sup': 'SUPPORT', 'support': 'SUPPORT'}
ORDER = ('TOP', 'JUNGLE', 'MID', 'BOT', 'SUPPORT')
FIELDS = ('gameid', 'date', 'patch', 'league', 'datacompleteness', 'side', 'position', 'result', 'champion', 'playerid', 'playername', 'teamid', 'teamname', 'firstPick') + tuple(f'{kind}{i}' for kind in ('pick', 'ban') for i in range(1, 6))


def champion(value, aliases):
    key = re.sub(r'[^a-z0-9]', '', value.casefold())
    result = aliases.get(value.casefold()) or aliases.get(key)
    if not result:
        raise ValueError('unknown_champion:' + value)
    return result


def normalize_game(rows, aliases):
    """Final roles are labels for later analysis, never draft-time feature assignments."""
    if len(rows) != 12:
        raise ValueError('row_count')
    for field in ('gameid', 'date', 'patch', 'league'):
        if len({r.get(field, '') for r in rows}) != 1 or not rows[0].get(field):
            raise ValueError('inconsistent_' + field)
    if not re.fullmatch(r'\d{1,3}\.\d{1,3}', rows[0]['patch']):
        raise ValueError('invalid_patch')
    datetime.fromisoformat(rows[0]['date'])
    teams = []
    complete = True
    all_champions = set()
    for side in ('Blue', 'Red'):
        side_rows = [r for r in rows if r['side'] == side]
        players = [r for r in side_rows if r['position'] != 'team']
        team_rows = [r for r in side_rows if r['position'] == 'team']
        if len(players) != 5 or len(team_rows) != 1 or {ROLES.get(r['position'].casefold()) for r in players} != set(ORDER):
            raise ValueError('player_roles')
        if len({r['result'] for r in side_rows}) != 1 or side_rows[0]['result'] not in ('0', '1'):
            raise ValueError('results')
        normalized = [{'role': ROLES[r['position'].casefold()], 'championId': champion(r['champion'], aliases),
                       'playerId': r.get('playerid', ''), 'playerName': r.get('playername', '')} for r in players]
        normalized.sort(key=lambda p: ORDER.index(p['role']))
        ids = {p['championId'] for p in normalized}
        if len(ids) != 5 or all_champions.intersection(ids):
            raise ValueError('duplicate_champion')
        all_champions.update(ids)
        row = team_rows[0]
        picks = [champion(row[f'pick{i}'], aliases) if row.get(f'pick{i}') else None for i in range(1, 6)]
        bans = [champion(row[f'ban{i}'], aliases) if row.get(f'ban{i}') and row[f'ban{i}'].casefold() not in ('none', 'no ban') else None for i in range(1, 6)]
        # Missing sequence data is not fabricated from the final role-sorted lineup.
        complete &= None not in picks and set(picks) == ids and None not in bans
        teams.append({'side': side.upper(), 'result': int(row['result']), 'teamId': row.get('teamid', ''),
                      'teamName': row.get('teamname', ''), 'players': normalized, 'picks': picks, 'bans': bans,
                      'firstPickRaw': row.get('firstPick', '')})
    if sum(t['result'] for t in teams) != 1:
        raise ValueError('results')
    bans = [b for t in teams for b in t['bans'] if b]
    complete &= len(set(bans)) == len(bans) and not all_champions.intersection(bans)
    return {'gameId': rows[0]['gameid'], 'date': rows[0]['date'], 'patch': '.'.join(str(int(p)) for p in rows[0]['patch'].split('.')),
            'league': rows[0]['league'], 'completeness': sorted({r.get('datacompleteness', '') for r in rows}),
            'draftFieldsComplete': bool(complete), 'teams': teams}


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def prepare(inputs, catalog_path, output):
    if not inputs:
        raise ValueError('No Oracle CSV files found; nothing was written.')
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
    aliases = {}
    for entry in catalog['data'].values():
        for name in (entry['id'], entry['name']):
            aliases[re.sub(r'[^a-z0-9]', '', name.casefold())] = entry['id']
    if 'monkeyking' in aliases:
        aliases['wukong'] = aliases['monkeyking']
    output.mkdir(parents=True, exist_ok=False)
    report = {'version': 1, 'catalogVersion': catalog['version'], 'catalogSha256': sha(catalog_path), 'sources': [], 'rejected': {}, 'examples': {}, 'rejections': [], 'conflicts': [], 'duplicateGames': 0, 'conflictingGames': 0}
    rejected = Counter()
    games = {}
    conflicts = set()
    for path in inputs:
        groups = defaultdict(list)
        source = {'filename': path.name, 'sha256': sha(path), 'rows': 0, 'duplicateRows': 0, 'missingGameIdRows': 0}
        with path.open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            required = set(FIELDS) - {'firstPick', 'playerid', 'playername', 'teamid', 'teamname'}
            if not required.issubset(reader.fieldnames or []):
                raise ValueError(f'{path.name}: missing columns {sorted(required - set(reader.fieldnames or []))}')
            for row in reader:
                source['rows'] += 1
                if None in row or any(v is None for v in row.values()):
                    raise ValueError(f'{path.name}: malformed CSV at record {source["rows"]}')
                if not row['gameid'].strip():
                    source['missingGameIdRows'] += 1
                    report['rejections'].append({'sourceSha256': source['sha256'], 'record': source['rows'], 'reason': 'missing_game_id'})
                    continue
                item = {k: row.get(k, '').strip() for k in FIELDS}
                groups[item['gameid']].append(item)
        source['gameGroups'] = len(groups)
        if sha(path) != source['sha256']:
            raise ValueError(f'{path.name}: source changed during reading; discard this incomplete output batch')
        for game_id, raw in groups.items():
            unique = list({json.dumps(r, sort_keys=True): r for r in raw}.values())
            source['duplicateRows'] += len(raw) - len(unique)
            try:
                game = normalize_game(unique, aliases)
            except ValueError as error:
                reason = str(error).split(':')[0]
                rejected[reason] += 1
                report['rejections'].append({'sourceSha256': source['sha256'], 'gameId': game_id, 'reason': reason, 'detail': str(error)})
                report['examples'].setdefault(reason, [])
                if len(report['examples'][reason]) < 5:
                    report['examples'][reason].append({'gameId': game_id, 'detail': str(error)})
                continue
            if game_id in games:
                if games[game_id]['game'] != game:
                    conflicts.add(game_id)
                    report['conflicts'].append({'gameId': game_id, 'sourceSha256': source['sha256'], 'previousSources': list(games[game_id]['sources'])})
                else:
                    report['duplicateGames'] += 1
                    games[game_id]['sources'].append(source['sha256'])
            else:
                games[game_id] = {'game': game, 'sources': [source['sha256']]}
        report['sources'].append(source)
        print(f'Parsed {path.name}: {source["rows"]} rows, {source["gameGroups"]} game groups', flush=True)
    for game_id in conflicts:
        games.pop(game_id, None)
    report['conflictingGames'] = len(conflicts)
    report['rejected'] = dict(rejected)
    report['acceptedGames'] = len(games)
    report['completeDraftFieldGames'] = sum(r['game']['draftFieldsComplete'] for r in games.values())
    report['lineupOnlyGames'] = len(games) - report['completeDraftFieldGames']
    report['dateRange'] = [min((r['game']['date'] for r in games.values()), default=None), max((r['game']['date'] for r in games.values()), default=None)]
    report['patches'] = dict(sorted(Counter(r['game']['patch'] for r in games.values()).items()))
    with (output / 'games.jsonl').open('x', encoding='utf-8', newline='\n') as stream:
        for game_id in sorted(games):
            stream.write(json.dumps(games[game_id], sort_keys=True, ensure_ascii=True, separators=(',', ':')) + '\n')
    report['gamesSha256'] = sha(output / 'games.jsonl')
    (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('acceptedGames', 'completeDraftFieldGames', 'lineupOnlyGames', 'rejected', 'conflictingGames')}, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=Path('data/oracle'))
    parser.add_argument('--catalog', type=Path, default=Path('data/ddragon/extracted/16.17.1/data/en_US/champion.json'))
    parser.add_argument('--output', type=Path, required=True, help='New directory; existing directories are never overwritten')
    args = parser.parse_args()
    prepare(sorted(args.input.glob('*_LoL_esports_match_data_from_OraclesElixir.csv')), args.catalog, args.output)
