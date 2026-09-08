import unittest
import csv
import json
from pathlib import Path
import tempfile
from prepare import normalize_game, prepare, FIELDS


def fixture():
    rows = []
    for side in ('Blue', 'Red'):
        names = [side + str(i) for i in range(5)]
        base = dict(gameid='game1', date='2026-01-01 10:00:00', patch='16.01', league='Fixture', datacompleteness='complete', side=side, result='1' if side == 'Blue' else '0')
        for i, role in enumerate(('top', 'jng', 'mid', 'bot', 'sup')):
            rows.append(dict(base, position=role, champion=names[i]))
        rows.append(dict(base, position='team', **{f'pick{i+1}': n for i, n in enumerate(names)}, **{f'ban{i+1}': f'Ban{side}{i}' for i in range(5)}))
    aliases = {n.casefold(): n for n in [r.get('champion', '') for r in rows] + [f'Ban{s}{i}' for s in ('Blue', 'Red') for i in range(5)] if n}
    return rows, aliases


class OracleTests(unittest.TestCase):
    def test_file_audit_deduplicates_identical_games_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            rows, aliases = fixture()
            names = list(aliases.values())
            catalog = root / 'champion.json'
            catalog.write_text(json.dumps({'version': 'test', 'data': {n: {'id': n, 'name': n} for n in names}}))
            inputs = []
            for n in range(2):
                path = root / f'{n}.csv'
                with path.open('w', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=FIELDS)
                    writer.writeheader()
                    writer.writerows(rows)
                inputs.append(path)
            report = prepare(inputs, catalog, root / 'output')
            self.assertEqual(1, report['acceptedGames'])
            self.assertEqual(1, report['duplicateGames'])
            with self.assertRaises(FileExistsError):
                prepare(inputs, catalog, root / 'output')
            rows[0]['result'] = '0'
            with self.assertRaisesRegex(ValueError, 'No Oracle'):
                prepare([], catalog, root / 'missing')

    def test_normalizes_roles_and_excludes_post_game_features(self):
        rows, aliases = fixture()
        rows[0]['kills'] = '99'
        game = normalize_game(rows, aliases)
        self.assertTrue(game['draftFieldsComplete'])
        self.assertEqual('16.1', game['patch'])
        self.assertEqual('JUNGLE', game['teams'][0]['players'][1]['role'])
        self.assertNotIn('kills', str(game))

    def test_missing_order_keeps_lineup_but_not_draft_eligibility(self):
        rows, aliases = fixture()
        rows[5]['pick1'] = ''
        self.assertFalse(normalize_game(rows, aliases)['draftFieldsComplete'])

    def test_unknown_champion_and_duplicate_roles_reject(self):
        rows, aliases = fixture()
        rows[0]['champion'] = 'Unknown'
        with self.assertRaisesRegex(ValueError, 'unknown_champion'):
            normalize_game(rows, aliases)
        rows, aliases = fixture()
        rows[0]['position'] = 'mid'
        with self.assertRaisesRegex(ValueError, 'player_roles'):
            normalize_game(rows, aliases)

    def test_same_result_rejects(self):
        rows, aliases = fixture()
        for row in rows:
            row['result'] = '1'
        with self.assertRaisesRegex(ValueError, 'results'):
            normalize_game(rows, aliases)


if __name__ == '__main__':
    unittest.main()
