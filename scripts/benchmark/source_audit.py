"""Attach source series fields without changing the existing database-import payloads."""
from collections import defaultdict
import csv
from datetime import datetime
import json
from pathlib import Path

from protocol import digest, load_prepared, pick_cases

FIELDS = ('game', 'year', 'split', 'playoffs', 'url', 'league', 'date')
SOURCES = {
    'pickOrder': 'https://lol.timsevenhuysen.com/2024/02/void-grubs-and-pick-order-in-the-csvs/',
    'seriesField': 'https://lol.timsevenhuysen.com/matchdata/match-data-dictionary/',
    'fearlessOpeningGame': 'https://lolesports.com/en-GB/news/lol-esports-in-2025',
    'fearlessVariant': 'https://lolesports.com/en-US/news/introducing-the-2024-north-american-challengers-league',
}


def classify(games, metadata):
    audit, groups = {}, defaultdict(list)
    for game in games:
        game_id = game['gameId']
        values = {json.dumps(v, sort_keys=True) for v in metadata.get(game_id, [])}
        reasons = []
        source = json.loads(next(iter(values))) if len(values) == 1 else None
        if source is None:
            reasons.append('conflicting_source_metadata' if values else 'missing_source_metadata')
        number = None
        if source is not None:
            if source['date'] != game['date'] or source['league'] != game['league'] or source['year'] != game['date'][:4]:
                reasons.append('source_identity_mismatch')
            if source['game'].isdigit() and 1 <= int(source['game']) <= 9:
                number = int(source['game'])
            else:
                reasons.append('unknown_game_number')
            if source['playoffs'] not in ('0', '1'):
                reasons.append('unknown_stage')
        if number is not None and number != 1:
            reasons.append('later_game_rules_unverified')
        team_ids = sorted(t['teamId'] for t in game['teams'])
        if not all(team_ids) or len(set(team_ids)) != 2:
            reasons.append('invalid_team_identity')
        player_ids = [p['playerId'] for t in game['teams'] for p in t['players']]
        if not all(player_ids) or len(set(player_ids)) != 10:
            reasons.append('invalid_player_identity')
        if not game['draftFieldsComplete']:
            reasons.append('incomplete_draft')
        elif any(len(t['picks']) != 5 or len(t['bans']) != 5 or
                 set(t['picks']) != {p['championId'] for p in t['players']} for t in game['teams']):
            reasons.append('pick_lineup_mismatch')
        else:
            try:
                list(pick_cases(game))
            except ValueError as error:
                reasons.append('invalid_draft:' + str(error))
        # This is a conservative grouping aid, never an invented official series ID.
        group_id = 'ungrouped:' + game_id
        if source and all(team_ids) and len(set(team_ids)) == 2:
            key = [source[k] for k in ('league', 'year', 'split', 'playoffs')]
            key += [game['date'][:10], *team_ids]
            group_id = 'team-date:' + digest(json.dumps(key).encode())[:24]
            groups[group_id].append((game_id, number, datetime.fromisoformat(game['date'])))
        audit[game_id] = {'gameId': game_id, 'sourceSeries': source,
                         'seriesCandidateId': group_id, 'seriesStatus': 'inferred_team_date_group',
                         'gameNumber': number, 'rulePolicy': 'opening-game-only-v1',
                         'pickOrderSemantics': 'publisher_documented_team_order', 'reasons': reasons}
    for members in groups.values():
        numbers = [number for _, number, _ in members]
        if None in numbers or len(set(numbers)) != len(numbers):
            for game_id, _, _ in members:
                audit[game_id]['reasons'].append('ambiguous_series_group')
        else:
            by_number = sorted(members, key=lambda row: row[1])
            if any(left[2] >= right[2] for left, right in zip(by_number, by_number[1:])):
                for game_id, _, _ in members:
                    audit[game_id]['reasons'].append('contradictory_series_chronology')
    for row in audit.values():
        row['reasons'] = sorted(set(row['reasons']))
        row['eligible'] = not row['reasons']
    return audit


def audit_sources(prepared, raw_dir):
    games, provenance = load_prepared(prepared)
    report_bytes = (prepared / 'report.json').read_bytes()
    if digest(report_bytes) != provenance['reportSha256']:
        raise ValueError('Prepared manifest changed during reading')
    report = json.loads(report_bytes)
    metadata = defaultdict(set)
    wanted = {g['gameId'] for g in games}
    raw_sources = []
    for source in report['sources']:
        filename = source['filename']
        if Path(filename).name != filename:
            raise ValueError('Source filename must be a basename')
        path = raw_dir / filename
        raw = path.read_bytes()
        if digest(raw) != source['sha256']:
            raise ValueError('Original CSV checksum mismatch: ' + filename)
        # Parse the same bytes we hashed; no changes to the original exports.
        import io
        reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig'), newline=''))
        if not {'gameid', *FIELDS} <= set(reader.fieldnames or []):
            raise ValueError('Missing series source columns: ' + filename)
        for row in reader:
            if None in row or any(v is None for v in row.values()):
                raise ValueError('Malformed source CSV')
            game_id = row['gameid'].strip()
            if game_id in wanted:
                metadata[game_id].add(json.dumps({k: row[k].strip() for k in FIELDS}, sort_keys=True))
        raw_sources.append({'filename': filename, 'sha256': source['sha256']})
    decoded = {key: [json.loads(v) for v in sorted(values)] for key, values in metadata.items()}
    return games, classify(games, decoded), {**provenance, 'rawSources': raw_sources, 'documentation': SOURCES}
