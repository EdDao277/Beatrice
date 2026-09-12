import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from compact_dataset import build
from test_compact_dataset import rows
from test_protocol import game
from test_source_audit import source_fixture


class ResumeTests(unittest.TestCase):
    def test_global_sample_limit_and_code_changes_are_auditable(self):
        import resume_dataset as resume
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source_fixture(root, [game('train', '2024-04-01 00:00:00'),
                                  game('validation1', '2025-02-01 00:00:00'),
                                  game('validation2', '2025-03-01 00:00:00')])
            resume.build(root, root, root / 'out', workers=1, chunk_games=1, max_validation=1)
            report = json.loads((root / 'out' / 'report.json').read_text())
            self.assertEqual(report['selectedGames'], {'training': 1, 'validation': 1})
            self.assertEqual(report['excluded']['validation'], {'sample_limit': 1})
            self.assertEqual(len(rows(root / 'out' / 'exclusions.jsonl.gz')), 1)
            self.assertEqual(resume.verify(root / 'out')['maxValidationGames'], 1)
            from scaled_train import load
            load(root / 'out')
            hashes = resume.compact.code_hashes()
            with patch.object(resume.compact, 'code_hashes', return_value={**hashes, 'baseline.py': 'changed'}):
                with self.assertRaisesRegex(ValueError, 'changed'):
                    resume.build(root, root, root / 'out', workers=1, chunk_games=1, max_validation=1)

    def test_partial_publication_can_finish_without_overwriting_files(self):
        import resume_dataset as resume
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source_fixture(root, [game('train', '2024-04-01 00:00:00'),
                                  game('validation', '2025-02-01 00:00:00')])
            original = Path.rename
            def interrupt(path, target):
                if target.name == 'snapshots.jsonl.gz':
                    raise RuntimeError('publication interrupted')
                return original(path, target)
            with patch.object(Path, 'rename', interrupt):
                with self.assertRaisesRegex(RuntimeError, 'publication interrupted'):
                    resume.build(root, root, root / 'out', workers=1)
            published = {p: p.stat().st_mtime_ns for p in (root / 'out').iterdir() if p.is_file()}
            resume.build(root, root, root / 'out', workers=1)
            self.assertEqual(published, {p: p.stat().st_mtime_ns for p in published})
            resume.verify(root / 'out')

    def test_corrupt_completed_shard_is_rejected(self):
        import resume_dataset as resume
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source_fixture(root, [game('train', '2024-04-01 00:00:00'),
                                  game('validation', '2025-02-01 00:00:00')])
            with patch.object(resume, 'merge', side_effect=RuntimeError('interrupted')):
                with self.assertRaises(RuntimeError):
                    resume.build(root, root, root / 'out', workers=1)
            artifact = next((root / 'out' / '_shards').glob('000000-*/features.jsonl.gz'))
            artifact.write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                resume.build(root, root, root / 'out', workers=1)

    def test_resume_preserves_cases_and_completed_shards(self):
        self.assertIsNotNone(importlib.util.find_spec('resume_dataset'), 'resumable exporter missing')
        import resume_dataset as resume
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source_fixture(root, [game('warmup', '2024-01-01 00:00:00'),
                                  game('train1', '2024-04-01 00:00:00'),
                                  game('train2', '2024-05-01 00:00:00'),
                                  game('validation', '2025-02-01 00:00:00')])
            build(root, root, root / 'plain')
            # Fail at merge after real workers have committed their shard manifests.
            with patch.object(resume, 'merge', side_effect=RuntimeError('interrupted')):
                with self.assertRaisesRegex(RuntimeError, 'interrupted'):
                    resume.build(root, root, root / 'out', workers=2, chunk_games=1)
            committed = {p: p.stat().st_mtime_ns for p in (root / 'out' / '_shards').rglob('manifest.json')}
            self.assertEqual(len(committed), 2)
            unfinished = root / 'out' / '_shards' / '000000-abandoned'
            unfinished.mkdir()
            (unfinished / 'features.jsonl.gz').write_bytes(b'incomplete')
            resume.build(root, root, root / 'out', workers=2, chunk_games=1)
            self.assertEqual(committed, {p: p.stat().st_mtime_ns for p in committed})
            self.assertTrue(unfinished.exists())
            for name in ('contexts', 'features', 'labels', 'evidence'):
                actual = sorted(rows(root / 'out' / (name + '.jsonl.gz')), key=lambda r: r['caseId'])
                expected = sorted(rows(root / 'plain' / (name + '.jsonl.gz')), key=lambda r: r['caseId'])
                self.assertEqual(actual, expected)
                self.assertEqual(len(actual), 30)
                self.assertEqual(len({r['caseId'] for r in actual}), 30)
            from scaled_train import verify, load
            verify(root / 'out')
            load(root / 'out')
            with (root / 'games.jsonl').open('a') as stream:
                stream.write('\n')
            with self.assertRaisesRegex(ValueError, 'changed|mismatch'):
                resume.build(root, root, root / 'out', workers=2, chunk_games=1)


if __name__ == '__main__':
    unittest.main()
