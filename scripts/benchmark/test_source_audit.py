import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from source_audit import audit_sources, classify
from test_protocol import game, prepared


def metadata(number='1'):
    return {'game': number, 'year': '2025', 'split': 'Spring', 'playoffs': '0',
            'url': '', 'league': 'fixture', 'date': '2025-02-01 12:00:00'}


def source_fixture(root, games):
    prepared(root, games)
    path = root / 'source.csv'
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=['gameid', *metadata()])
        writer.writeheader()
        for g in games:
            writer.writerow({'gameid': g['gameId'], **metadata(), 'date': g['date'], 'year': g['date'][:4]})
    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    data = (root / 'games.jsonl').read_bytes().replace(b'a' * 64, source_hash.encode())
    (root / 'games.jsonl').write_bytes(data)
    report = json.loads((root / 'report.json').read_text())
    report['sources'] = [{'filename': path.name, 'sha256': source_hash}]
    report['gamesSha256'] = hashlib.sha256(data).hexdigest()
    (root / 'report.json').write_text(json.dumps(report))


class SourceAuditTests(unittest.TestCase):
    def test_preserves_metadata_and_excludes_later_games(self):
        g = game()
        rows = classify([g], {'one': [metadata()]})
        self.assertTrue(rows['one']['eligible'])
        self.assertEqual(rows['one']['sourceSeries']['game'], '1')
        self.assertEqual(rows['one']['seriesStatus'], 'inferred_team_date_group')
        later = classify([g], {'one': [metadata('2')]})
        self.assertFalse(later['one']['eligible'])
        self.assertIn('later_game_rules_unverified', later['one']['reasons'])

    def test_conflicting_metadata_and_duplicate_numbers_fail_closed(self):
        g = game()
        rows = classify([g], {'one': [metadata(), metadata('2')]})
        self.assertIn('conflicting_source_metadata', rows['one']['reasons'])
        second = game('two', '2025-02-01 14:00:00')
        rows = classify([g, second], {'one': [metadata()],
                       'two': [{**metadata(), 'date': second['date']}]})
        self.assertFalse(rows['one']['eligible'])
        self.assertFalse(rows['two']['eligible'])
        self.assertIn('ambiguous_series_group', rows['one']['reasons'])

    def test_false_complete_flag_cannot_admit_mismatched_lineup(self):
        g = game()
        g['teams'][0]['picks'][0] = 'WrongChampion'
        rows = classify([g], {'one': [metadata()]})
        self.assertIn('pick_lineup_mismatch', rows['one']['reasons'])

    def test_series_numbers_must_agree_with_timestamps(self):
        later_number = game('second', '2025-02-01 12:00:00')
        first_number = game('first', '2025-02-01 14:00:00')
        rows = classify([later_number, first_number], {
            'second': [metadata('2')],
            'first': [{**metadata(), 'date': first_number['date']}]})
        self.assertFalse(rows['first']['eligible'])
        self.assertIn('contradictory_series_chronology', rows['first']['reasons'])

    def test_exact_source_join_and_tamper_rejection(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source_fixture(root, [game()])
            games, audit, provenance = audit_sources(root, root)
            self.assertEqual(len(games), 1)
            self.assertTrue(audit['one']['eligible'])
            self.assertEqual(len(provenance['rawSources']), 1)
            with (root / 'source.csv').open('a') as stream:
                stream.write('\n')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                audit_sources(root, root)


if __name__ == '__main__':
    unittest.main()
