"""Refreshes must never replace active history before complete validation."""
from pathlib import Path
import tempfile
import unittest
import json
import contextlib
import csv
import gzip
import io
from unittest.mock import patch
import history_bundle as bundle

@contextlib.contextmanager
def built_fixture():
    """Tiny real CSV/import/audit chain, without real model or production artifacts."""
    from test_prepare import fixture
    from prepare import FIELDS
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);raw,aliases=fixture()
        for i,row in enumerate(raw):
            row.update(game='1',year='2026',split='Spring',playoffs='0',url='',
                teamid=row['side'],playerid='p'+str(i),firstPick='1' if row['side']=='Blue' else '0')
        catalog=root/'champion.json'
        catalog.write_text(json.dumps({'version':'fixture','data':{n:{'id':n,'name':n} for n in aliases.values()}}))
        def source(path,records):
            with path.open('w',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=[*FIELDS,'game','year','split','playoffs','url'])
                writer.writeheader();writer.writerows(records)
        old_source=root/'old.csv';source(old_source,raw)
        prepared=root/'frozen';compact=root/'compact';compact.mkdir()
        with contextlib.redirect_stdout(io.StringIO()):bundle.prepare([old_source],catalog,prepared)
        games,audit,_=bundle.audit_sources(prepared,root)
        (compact/'manifest.json').write_text('{}')
        with gzip.open(compact/'source-audit.jsonl.gz','wt') as stream:
            for row in audit.values():stream.write(json.dumps(row)+'\n')
        newer=json.loads(json.dumps(raw))
        for row in newer:row.update(gameid='new',date='2026-01-02 10:00:00')
        updated=root/'updated.csv';source(updated,raw+newer)
        target=root/'bundle-v1'
        with patch.object(bundle,'PREPARED',prepared),patch.object(bundle,'COMPACT',compact),contextlib.redirect_stdout(io.StringIO()):
            bundle.build(updated,catalog,target)
            yield target,games,audit
try:
    from history_bundle import atomic_pointer, merge_games, validate_time
except ImportError:
    atomic_pointer=merge_games=validate_time=None

class BundleTests(unittest.TestCase):
    def test_failed_model_warmup_does_not_publish_pointer(self):
        with built_fixture() as (target,_games,_audit):
            pointer=target.parent/'active.json'
            pointer.write_bytes(b'{"existing":"retained"}')
            with patch('service.RankService.load',side_effect=RuntimeError('model warmup failed')):
                with self.assertRaises(RuntimeError):bundle.activate(target,pointer)
            self.assertEqual(pointer.read_bytes(),b'{"existing":"retained"}')
            self.assertFalse((target.parent/'previous.json').exists())

    def test_full_bundle_rejects_corruption_and_contract_mutations(self):
        with built_fixture() as (target,games,audit):
            loaded,eligible,identity=bundle.validate_bundle(target,games,audit)
            self.assertEqual(len(loaded),2)
            self.assertEqual(len(eligible),2)
            manifest=(target/'manifest.json').read_bytes()
            for mutate in (lambda m:m['artifacts'].pop('history.jsonl'),
                           lambda m:m.update(historyLagDays=0),
                           lambda m:m.update(frozenCompactSha256='0'*64),
                           lambda m:m['counts'].update(games=999)):
                m=json.loads(manifest);mutate(m)
                (target/'manifest.json').write_bytes(bundle.canonical(m))
                with self.assertRaises(ValueError):bundle.validate_bundle(target,games,audit)
            (target/'manifest.json').write_bytes(manifest)
            with self.assertRaises(ValueError):bundle.validate_bundle(target,games,audit,'0'*64)
            with (target/'history.jsonl').open('ab') as stream:stream.write(b'corruption')
            with self.assertRaises(ValueError):bundle.validate_bundle(target,games,audit)

    def test_self_consistent_changed_gameplay_must_still_match_source_csv(self):
        with built_fixture() as (target,games,audit):
            path=target/'import/games.jsonl'
            records=[json.loads(line) for line in path.read_bytes().splitlines()]
            for record in records:
                if record['game']['gameId']=='new':
                    for team in record['game']['teams']:team['result']=1-team['result']
            path.write_bytes(b''.join(bundle.canonical(r)+b'\n' for r in records))
            report=json.loads((target/'import/report.json').read_bytes());report['gamesSha256']=bundle.sha(path)
            (target/'import/report.json').write_bytes(bundle.canonical(report))
            updated,_=bundle.load_prepared(target/'import')
            (target/'history.jsonl').write_bytes(b''.join(bundle.canonical(g)+b'\n' for g in updated))
            m=json.loads((target/'manifest.json').read_bytes())
            m['artifacts']={n:bundle.sha(target/n) for n in m['artifacts']}
            (target/'manifest.json').write_bytes(bundle.canonical(m))
            with self.assertRaisesRegex(ValueError,'normalization'):
                bundle.validate_bundle(target,games,audit)

    def test_fresh_ineligible_games_cannot_hide_stale_opening_evidence(self):
        from datetime import datetime,timezone
        from history_bundle import require_fresh_openings
        now=datetime(2026,9,18,tzinfo=timezone.utc)
        with self.assertRaises(ValueError):require_fresh_openings([{'date':'2026-09-01 10:00:00'}],now)
        self.assertEqual(require_fresh_openings([{'date':'2026-09-16 10:00:00'},{'date':'2026-09-17 10:00:00'}],now),'2026-09-16 10:00:00')

    def test_audit_uses_retained_identity_and_does_not_promote_corrected_old_game(self):
        from history_bundle import merged_audit, classify
        from test_protocol import game
        from test_source_audit import metadata
        original=game()
        original['teams'][0]['teamId']=''
        retained=classify([original],{'one':[metadata()]})
        corrected=game()
        upstream=classify([corrected],{'one':[metadata()]})
        self.assertFalse(retained['one']['eligible'])
        self.assertTrue(upstream['one']['eligible'])
        result=merged_audit([original],retained,upstream)
        self.assertEqual(result,retained)
        upstream['one']['sourceSeries']['game']='2'
        with self.assertRaises(ValueError):merged_audit([original],retained,upstream)

    def test_identity_revisions_are_logged_but_original_records_win(self):
        from history_bundle import identity_revisions
        old=[dict(gameId='old',date='2026-01-01',teams=[dict(teamId='team1',teamName='old',players=[dict(playerId='p1',playerName='old',championId='A')])])]
        revised=json.loads(json.dumps(old))
        revised[0]['teams'][0]['players'][0]['playerId']='p2'
        revised[0]['teams'][0]['teamName']='new'
        self.assertEqual(merge_games(old,revised),old)
        revisions=identity_revisions(old,revised)
        self.assertEqual(len(revisions),1)
        self.assertEqual(revisions[0]['gameId'],'old')
        self.assertEqual(revisions[0]['fields'],['teams[0].players[0].playerId','teams[0].teamName'])
        revised[0]['teams'][0]['players'][0]['championId']='B'
        with self.assertRaises(ValueError):merge_games(old,revised)

    def test_refresh_failure_keeps_running_snapshot_then_swaps_whole_instance(self):
        from history_bundle import HistoryManager
        with tempfile.TemporaryDirectory() as directory:
            pointer=Path(directory)/'active.json'
            class Instance:
                def __init__(self,name):self.name=name;self.provenance={'historyBundleVersion':name}
                def rank(self,payload):return self.name
                def is_ready(self):return True
                def warm(self):pass
            def loader(path,expected):
                if path and path.name=='bad':raise ValueError('bad snapshot')
                return Instance(path.name if path else 'original')
            manager=HistoryManager(loader,pointer)
            pointer.write_text(json.dumps({'version':'bad','sha256':'a'*64}))
            manager.refresh()
            self.assertEqual(manager.rank({}),'original')
            pointer.write_text(json.dumps({'version':'good','sha256':'b'*64}))
            manager.refresh()
            self.assertEqual(manager.rank({}),'good')

    def test_conflicting_or_missing_old_games_fail_without_mutation(self):
        self.assertIsNotNone(merge_games)
        old=[dict(gameId='old',date='2026-01-01',value=1)]
        self.assertEqual(merge_games(old,old+[dict(gameId='new',date='2026-09-15',value=2)]),old+[dict(gameId='new',date='2026-09-15',value=2)])
        for newer in ([],[dict(gameId='old',date='2026-01-01',value=2)]):
            with self.assertRaises(ValueError): merge_games(old,newer)
        self.assertEqual(old[0]['value'],1)

    def test_failed_validation_never_changes_active_pointer(self):
        self.assertIsNotNone(atomic_pointer)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);active=root/'active.json'
            active.write_text('{"previous":true}')
            def fail(): raise ValueError('invalid bundle')
            with self.assertRaises(ValueError): atomic_pointer(active,{'version':'new'},fail)
            self.assertEqual(active.read_text(),'{"previous":true}')
            atomic_pointer(active,{'version':'new'},lambda:None)
            self.assertEqual(json.loads(active.read_text()),{'version':'new'})
            self.assertEqual((root/'previous.json').read_text(),'{"previous":true}')

    def test_future_and_timezone_ambiguity_rejected(self):
        self.assertIsNotNone(validate_time)
        from datetime import datetime,timezone
        now=datetime(2026,9,17,tzinfo=timezone.utc)
        self.assertEqual(validate_time('2026-09-15T00:00:00',now).year,2026)
        with self.assertRaises(ValueError):validate_time('2026-09-18T00:00:00',now)
        with self.assertRaises(ValueError):validate_time('2026-09-15T00:00:00+05:00',now)

if __name__=='__main__': unittest.main()
