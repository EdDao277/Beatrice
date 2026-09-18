"""Versioned inference-history bundles; original training artifacts are never overwritten."""
import argparse
import contextlib
from datetime import datetime,timedelta,timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/benchmark'))
sys.path.insert(0,str(ROOT/'scripts/oracle'))
from prepare import prepare
from protocol import load_prepared
from source_audit import audit_sources, classify
from scaled_train import rows,sha,read

PREPARED=ROOT/'data/oracle/prepared-2026-09-08-reviewed'
COMPACT=ROOT/'data/oracle/compact-2026-09-11-resumable'
BUNDLES=ROOT/'data/oracle/history-bundles'
VERSION=re.compile(r'^[A-Za-z0-9._-]{1,100}$')
HASH=re.compile(r'^[a-f0-9]{64}$')

def canonical(value): return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(value): return hashlib.sha256(value).hexdigest()
def dump(path,value):
    with path.open('xb') as stream: stream.write(canonical(value))

def validate_time(text,now):
    value=datetime.fromisoformat(text)
    if value.tzinfo is not None or value>now.astimezone(timezone.utc).replace(tzinfo=None):
        raise ValueError('Future or ambiguous source timestamp')
    return value

def merge_games(old,new):
    original={g['gameId']:g for g in old};updated={g['gameId']:g for g in new}
    if len(updated)!=len(new) or len(original)!=len(old): raise ValueError('Duplicate game identity')
    for identity,g in original.items():
        if g['date'].startswith('2026') and identity not in updated:
            raise ValueError('Missing existing 2026 game: '+identity)
    identity_revisions(old,new)  # Only approved identity/display revisions may be ignored.
    for identity,g in updated.items():
        if not g['date'].startswith('2026'): raise ValueError('Refresh accepts 2026 source games only')
        if identity not in original: original[identity]=g
    return sorted(original.values(),key=lambda g:(g['date'],g['gameId']))

def identity_revisions(old,new):
    """Keep frozen records, but reject gameplay revisions rather than hiding them."""
    original={g['gameId']:g for g in old}
    changes=[]
    allowed=re.compile(r'^teams\[\d+\]\.(teamId|teamName|players\[\d+\]\.(playerId|playerName))$')
    def differences(left,right,path=''):
        if isinstance(left,dict) and isinstance(right,dict):
            result=[]
            for key in sorted(left.keys()|right.keys()):
                result.extend(differences(left.get(key),right.get(key),f'{path}.{key}' if path else key))
            return result
        if isinstance(left,list) and isinstance(right,list) and len(left)==len(right):
            return [p for i,(a,b) in enumerate(zip(left,right)) for p in differences(a,b,f'{path}[{i}]')]
        return [] if left==right else [path]
    for game in new:
        previous=original.get(game['gameId'])
        if previous is None:continue
        fields=sorted(differences(previous,game))
        if any(not allowed.fullmatch(field) for field in fields):
            raise ValueError('Historical gameplay conflict: '+game['gameId'])
        if fields:changes.append(dict(gameId=game['gameId'],fields=fields,
            retainedSha256=digest(canonical(previous)),upstreamSha256=digest(canonical(game))))
    return sorted(changes,key=lambda row:row['gameId'])

def merged_audit(games,original_audit,upstream_audit):
    for identity,row in original_audit.items():
        if identity in upstream_audit and upstream_audit[identity]['sourceSeries']!=row['sourceSeries']:
            raise ValueError('Existing source series metadata changed: '+identity)
    combined={**upstream_audit,**original_audit}
    # Classify the retained records, not revised upstream identities. New games
    # still participate in the complete chronology/series ambiguity checks.
    audited=classify(games,{k:[v['sourceSeries']] for k,v in combined.items() if v['sourceSeries'] is not None})
    for identity,row in original_audit.items():
        if audited[identity]['eligible']!=row['eligible']:
            raise ValueError('Retained audit eligibility changed: '+identity)
    return {**audited,**original_audit}

class HistoryManager:
    """Warm an isolated replacement; failed reloads never mutate the serving instance."""
    def __init__(self,loader,pointer):
        self._loader=loader
        self._pointer=Path(pointer)
        self._current=loader(None,None)
        self._attempted=None
        self.reload_status='original'
        self.refresh()

    @property
    def provenance(self):return self._current.provenance
    def rank(self,payload):return self._current.rank(payload)
    def is_ready(self):return self._current.is_ready()
    def warm(self):self._current.warm()
    def refresh(self):
        try:
            raw=self._pointer.read_bytes()
            if raw==self._attempted:return
            self._attempted=raw
            path,expected=resolve_pointer(self._pointer)
            replacement=self._loader(path,expected)
            if not replacement.is_ready():raise ValueError('Replacement not ready')
            if self._pointer.read_bytes()!=raw:raise ValueError('Pointer changed during reload')
            self._current=replacement
            self.reload_status='active'
        except FileNotFoundError:
            self.reload_status='retained'
        except Exception:
            self.reload_status='rejected'

def atomic_pointer(path,value,validate):
    """Publish one small pointer only after validation; preserve the previous bytes."""
    validate()
    path.parent.mkdir(parents=True,exist_ok=True)
    lock=path.parent/'activation.lock'
    handle=lock.open('x')
    try:
        with handle:
            if path.exists():
                previous=path.parent/'previous.json'
                _replace(previous,path.read_bytes())
            _replace(path,canonical(value))
    finally:
        lock.unlink()

def _replace(path,content):
    fd,name=tempfile.mkstemp(prefix='pointer-',suffix='.pending',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(content);stream.flush();os.fsync(stream.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name): os.unlink(name)

def counts(games,audit,at):
    cutoff=at.astimezone(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0,tzinfo=None)-timedelta(days=1)
    eligible=[g for g in games if audit[g['gameId']]['eligible']]
    lagged=[g for g in eligible if datetime.fromisoformat(g['date'])<cutoff]
    return dict(games=len(games),eligibleOpeningGames=len(eligible),eligibleDraftDecisions=10*len(eligible),
        laggedEligibleGames=len(lagged),laggedEligibleDecisions=10*len(lagged),
        latestSourceTimestamp=max(g['date'] for g in games),
        latestEligibleTimestamp=max((g['date'] for g in eligible),default=None),
        latestEligibleTimestampAfterLag=max((g['date'] for g in lagged),default=None),
        exclusiveLagCutoff=cutoff.isoformat())

def build(source,catalog,output):
    if not VERSION.fullmatch(output.name) or output.name in ('.','..'): raise ValueError('Invalid bundle version')
    output.mkdir(parents=True,exist_ok=False)
    (output/'source').mkdir()
    source_hash=sha(source)
    staged=output/'source'/source.name;shutil.copyfile(source,staged)
    shutil.copyfile(catalog,output/'champion.json')
    if sha(staged)!=source_hash or sha(source)!=source_hash: raise ValueError('Source changed while copied')
    report=prepare([staged],output/'champion.json',output/'import')
    if report['conflictingGames']: raise ValueError('Importer found conflicts')
    new,audit_new,_=audit_sources(output/'import',output/'source')
    original,provenance=load_prepared(PREPARED)
    games=merge_games(original,new)
    original_audit={r['gameId']:r for r in rows(COMPACT,'source-audit')}
    audit=merged_audit(games,original_audit,audit_new)
    now=datetime.now(timezone.utc)
    for g in games: validate_time(g['date'],now)
    for name,values in (('history.jsonl',games),('audit.jsonl',[audit[g['gameId']] for g in games])):
        with (output/name).open('xb') as stream:
            for value in values: stream.write(canonical(value)+b'\n')
    artifacts=['history.jsonl','audit.jsonl','champion.json','import/games.jsonl','import/report.json','source/'+source.name]
    manifest=dict(version=output.name,format='beatrice-history-v1',builtAt=now.isoformat(),
        modelVersion='recency-2026-09-14',schemaVersion='beatrice-pick-recency-108-v1',historyLagDays=1,
        frozenPrepared=provenance,frozenCompactSha256=sha(COMPACT/'manifest.json'),sourceFile=source.name,sourceSha256=source_hash,
        catalogSha256=sha(output/'champion.json'),artifacts={n:sha(output/n) for n in artifacts},
        counts=counts(games,audit,now),rejectedGames=report['rejected'],addedGames=len(games)-len(original),
        mergePolicy='retain-original-append-new-v1',ignoredIdentityRevisions=identity_revisions(original,new))
    dump(output/'manifest.json',manifest)
    validate_bundle(output,original,original_audit)
    print(json.dumps({'bundle':str(output),'manifestSha256':sha(output/'manifest.json'),**manifest['counts'],'addedGames':manifest['addedGames']},indent=2))
    return manifest

def validate_bundle(path,original,original_audit,expected_hash=None):
    """Parse the exact bytes hashed. Reject partial, corrupt or incompatible refreshes."""
    path=Path(path)
    raw=(path/'manifest.json').read_bytes();identity=digest(raw)
    if expected_hash and identity!=expected_hash: raise ValueError('Active bundle manifest hash mismatch')
    m=json.loads(raw)
    if (m['format']!='beatrice-history-v1' or m['version']!=path.name or not VERSION.fullmatch(m['version'])
        or m['historyLagDays']!=1 or m['schemaVersion']!='beatrice-pick-recency-108-v1' or m['modelVersion']!='recency-2026-09-14'
        or m['frozenCompactSha256']!=sha(COMPACT/'manifest.json')): raise ValueError('Bundle compatibility mismatch')
    required={'history.jsonl','audit.jsonl','champion.json','import/games.jsonl','import/report.json','source/'+m['sourceFile']}
    if Path(m['sourceFile']).name!=m['sourceFile'] or set(m['artifacts'])!=required: raise ValueError('Bundle artifact contract mismatch')
    blobs={}
    for name,expected in m['artifacts'].items():
        blob=(path/name).read_bytes()
        if not HASH.fullmatch(expected) or digest(blob)!=expected: raise ValueError('Corrupt bundle artifact: '+name)
        blobs[name]=blob
    if m['sourceSha256']!=digest(blobs['source/'+m['sourceFile']]) or m['catalogSha256']!=digest(blobs['champion.json']):
        raise ValueError('Source/catalog provenance mismatch')
    games=[json.loads(line) for line in blobs['history.jsonl'].splitlines()]
    audit_rows=[json.loads(line) for line in blobs['audit.jsonl'].splitlines()]
    audit={r['gameId']:r for r in audit_rows}
    if len(audit)!=len(audit_rows) or set(audit)!={g['gameId'] for g in games}: raise ValueError('Audit coverage mismatch')
    new,_=load_prepared(path/'import')
    # Hashes alone prove consistency, not that normalization matches the CSV.
    # Rebuild independently using the unchanged importer and staged catalog.
    with tempfile.TemporaryDirectory(prefix='beatrice-normalization-') as temporary:
        rebuilt=Path(temporary)/'import'
        with contextlib.redirect_stdout(io.StringIO()):
            prepare([path/'source'/m['sourceFile']],path/'champion.json',rebuilt)
        if any(sha(rebuilt/name)!=m['artifacts']['import/'+name] for name in ('games.jsonl','report.json')):
            raise ValueError('Source normalization mismatch')
    expected_games=merge_games(original,new)
    if games!=expected_games: raise ValueError('Bundle does not match normalized source plus frozen history')
    # Re-audit staged immutable source; do not trust the serialized eligibility booleans.
    normalized,audit_new,_=audit_sources(path/'import',path/'source')
    expected_audit=merged_audit(games,original_audit,audit_new)
    if audit!=expected_audit: raise ValueError('Audit mismatch')
    if m.get('mergePolicy')!='retain-original-append-new-v1' or m.get('ignoredIdentityRevisions')!=identity_revisions(original,new):
        raise ValueError('Identity revision provenance mismatch')
    catalog=json.loads(blobs['champion.json'])
    valid_ids={v['id'] for v in catalog['data'].values()}
    now=datetime.now(timezone.utc)
    for g in games:
        validate_time(g['date'],now)
        if not re.fullmatch(r'[0-9]{1,2}\.[0-9]{1,2}',g['patch']): raise ValueError('Invalid exact patch')
        ids=[p['championId'] for t in g['teams'] for p in t['players']]
        if len(ids)!=10 or len(set(ids))!=10 or not set(ids)<=valid_ids: raise ValueError('Champion normalization mismatch')
    _,provenance=load_prepared(PREPARED)
    if provenance!=m['frozenPrepared']: raise ValueError('Frozen training lineage changed')
    built_at=datetime.fromisoformat(m['builtAt'])
    if built_at.tzinfo is None or built_at>now:raise ValueError('Invalid rebuild timestamp')
    if m['counts']!=counts(games,audit,built_at) or m['addedGames']!=len(games)-len(original):
        raise ValueError('Bundle count/timestamp mismatch')
    if not any(r['eligible'] for r in audit.values()): raise ValueError('No eligible openings')
    return games,[g for g in games if audit[g['gameId']]['eligible']],dict(historyBundleVersion=m['version'],historyBundleSha256=identity)

def require_fresh_openings(games,now):
    cutoff=now.astimezone(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0,tzinfo=None)-timedelta(days=1)
    latest=max((g['date'] for g in games if datetime.fromisoformat(g['date'])<cutoff),default=None)
    if latest is None or datetime.fromisoformat(latest).replace(tzinfo=timezone.utc)<now-timedelta(days=7):
        raise ValueError('Refreshed eligible opening evidence is still stale; not activating')
    return latest

def resolve_pointer(pointer):
    value=json.loads(pointer.read_bytes())
    if set(value)!={'version','sha256'} or not VERSION.fullmatch(value['version']) or value['version'] in ('.','..') or not HASH.fullmatch(value['sha256']):
        raise ValueError('Invalid active history pointer')
    return pointer.parent/value['version'],value['sha256']

def validate_activation(bundle,expected):
    from service import RankService,EXPECTED_MODEL_VERSION,EXPECTED_SCHEMA_VERSION,EXPECTED_MODEL_HASH
    service=RankService.load(prepared_dir=PREPARED,compact_dir=COMPACT,model_dir=ROOT/'data/oracle/blind-2026-09-14-reviewed',history_bundle=bundle,history_hash=expected)
    latest_eligible=require_fresh_openings(service._recency.games,datetime.now(timezone.utc))
    patch=max(service._recency.games,key=lambda g:g['date'])['patch']
    ids=sorted(service._training_seen)[:2]
    result=service.rank(dict(requestId='activation-probe',schemaVersion=EXPECTED_SCHEMA_VERSION,modelVersion=EXPECTED_MODEL_VERSION,
        modelSha256=EXPECTED_MODEL_HASH,patch=patch,allyPicks=[],enemyPicks=[],candidateIds=ids))
    latest=datetime.fromisoformat(result['historyLatest'].replace('Z','+00:00'))
    if latest<datetime.now(timezone.utc)-timedelta(days=7): raise ValueError('Refreshed evidence is still stale; not activating')
    if result['historyBundleSha256']!=expected: raise ValueError('Warmed bundle identity mismatch')
    if sha(bundle/'manifest.json')!=expected: raise ValueError('Manifest changed during activation')
    return dict(**service.provenance,historySnapshotId=result['historySnapshotId'],
        latestEligibleTimestampAfterLag=latest_eligible,trainingExposureSha256=digest(canonical(sorted(service._training_seen))),
        trainingExposureChampions=len(service._training_seen),modelSha256=EXPECTED_MODEL_HASH,schemaVersion=EXPECTED_SCHEMA_VERSION)

def activate(bundle,pointer):
    bundle=Path(bundle).resolve();pointer=Path(pointer).resolve()
    if bundle.parent!=pointer.parent: raise ValueError('Bundle must be beside active pointer')
    expected=sha(bundle/'manifest.json')
    atomic_pointer(pointer,dict(version=bundle.name,sha256=expected),lambda:validate_activation(bundle,expected))
    print(json.dumps({'activeVersion':bundle.name,'activeSha256':expected}))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('build','validate','activate'))
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--source',type=Path,default=ROOT/'data/oracle/2026_LoL_esports_match_data_from_OraclesElixir.csv')
    parser.add_argument('--catalog',type=Path,default=ROOT/'data/ddragon/extracted/16.17.1/data/en_US/champion.json')
    parser.add_argument('--pointer',type=Path,default=BUNDLES/'active.json')
    args=parser.parse_args()
    if args.command=='build':build(args.source,args.catalog,args.bundle)
    elif args.command=='activate':activate(args.bundle,args.pointer)
    else:print(json.dumps(validate_activation(args.bundle,sha(args.bundle/'manifest.json')),indent=2))
