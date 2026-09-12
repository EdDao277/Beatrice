import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import protocol


def game(game_id='one', date='2025-02-01 12:00:00'):
    teams = []
    for side, offset in [('BLUE', 0), ('RED', 5)]:
        picks = [f'C{i}' for i in range(offset, offset + 5)]
        teams.append({'side': side, 'result': int(side == 'BLUE'), 'teamId': side,
                      'firstPickRaw': str(int(side == 'BLUE')), 'picks': picks,
                      'bans': [f'B{i}' for i in range(offset, offset + 5)],
                      'players': [{'playerId': f'P{i}', 'championId': f'C{i}',
                                   'role': role} for i, role in zip(range(offset, offset + 5),
                                     ['TOP', 'JUNGLE', 'MID', 'BOT', 'SUPPORT'])]})
    return {'gameId': game_id, 'date': date, 'patch': '15.1', 'league': 'fixture',
            'draftFieldsComplete': True, 'teams': teams}


def prepared(path, games):
    payload = ''.join(json.dumps({'game': g, 'sources': ['a' * 64]}) + '\n' for g in games)
    (path / 'games.jsonl').write_bytes(payload.encode('utf-8'))
    report = {'version': 1, 'acceptedGames': len(games), 'gamesSha256':
              hashlib.sha256(payload.encode()).hexdigest(), 'sources': [{'sha256': 'a' * 64}]}
    (path / 'report.json').write_text(json.dumps(report), encoding='utf-8')


class ProtocolTests(unittest.TestCase):
    def test_first_pick_sees_only_first_six_bans(self):
        cases = list(protocol.pick_cases(game()))
        context, label = cases[0]
        self.assertEqual(context['allyPicks'], [])
        self.assertEqual(context['enemyPicks'], [])
        self.assertEqual(set(context['bans']), {'B0', 'B1', 'B2', 'B5', 'B6', 'B7'})
        self.assertEqual(label['championId'], 'C0')
        self.assertEqual(len(cases), 10)
        self.assertEqual(cases[6][0]['actionIndex'], 16)

    def test_final_roles_outcomes_and_row_order_cannot_change_context(self):
        original = game()
        changed = copy.deepcopy(original)
        for team in changed['teams']:
            team['result'] = 1 - team['result']
            champs = [p['championId'] for p in team['players']][::-1]
            for player, champ in zip(team['players'], champs):
                player['championId'] = champ
                player['role'] = 'UNKNOWN'
            team['players'].reverse()
        self.assertEqual([c for c, _ in protocol.pick_cases(original)],
                         [c for c, _ in protocol.pick_cases(changed)])

    def test_later_picks_and_bans_cannot_change_first_context(self):
        original = game()
        changed = copy.deepcopy(original)
        changed['teams'][1]['picks'][4] = 'NewChampion'
        changed['teams'][1]['bans'][4] = 'NewBan'
        self.assertEqual(next(protocol.pick_cases(original))[0],
                         next(protocol.pick_cases(changed))[0])

    def test_split_boundary_embargo_and_test_separation(self):
        games = [game('train', '2024-12-20 12:00:00'), game('gap', '2024-12-30 00:00:00'),
                 game('val'), game('gap2', '2025-12-31 00:00:00'),
                 game('test', '2026-01-01 00:00:00')]
        groups = protocol.partition(games, '2025-01-01', '2026-01-01')
        self.assertEqual({k: [g['gameId'] for g in v] for k, v in groups.items()},
                         {'reference': ['train'], 'embargo': ['gap', 'gap2'],
                          'validation': ['val'], 'test': ['test']})
        with self.assertRaises(ValueError):
            protocol.partition(games, '2026-01-01', '2025-01-01')

    def test_checksums_and_duplicate_ids_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            prepared(path, [game()])
            self.assertEqual(len(protocol.load_prepared(path)[0]), 1)
            with (path / 'games.jsonl').open('a') as stream:
                stream.write('\n')
            with self.assertRaises(ValueError):
                protocol.load_prepared(path)
            prepared(path, [game(), game()])
            with self.assertRaises(ValueError):
                protocol.load_prepared(path)

    def test_incomplete_and_wrong_first_pick_are_not_replayed(self):
        item = game()
        item['draftFieldsComplete'] = False
        self.assertEqual(list(protocol.pick_cases(item)), [])
        item['draftFieldsComplete'] = True
        item['teams'][0]['firstPickRaw'] = '0'
        with self.assertRaises(ValueError):
            list(protocol.pick_cases(item))


if __name__ == '__main__':
    unittest.main()
