"""Operational smoke checks only: GET saved data and POST unsaved recommendations."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import statistics
import sys
from time import perf_counter

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/benchmark'))
from measure_guarded_http import call,lineup

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()

def check_ranking(event,offline):
    bases=event['javaRanking'];final=event['finalRanking']
    expected={r['championId']:r['score'] for r in bases}
    assert len(final)==len(bases) and {r['championId'] for r in final}==set(expected)
    for row in final:
        assert row['javaScore']==expected[row['championId']]
        assert 0<=row['mlBonus']<=2.5
        assert row['score']==row['javaScore']+row['mlBonus']
        if offline:assert row['mlBonus']==0 and row['score']==row['javaScore']
    if offline:assert [r['championId'] for r in final]==[r['championId'] for r in bases]

def diagnostic(folder,request_id):
    for path in folder.glob('picks*.jsonl'):
        for line in path.read_text().splitlines():
            event=json.loads(line)
            if event.get('requestId')==request_id and event.get('event')=='recommendation':return event
    raise AssertionError('Missing recommendation diagnostics')

def snapshot(base):
    teams=call(base,'/api/teams')
    games={str(t['id']):call(base,f"/api/teams/{t['id']}/games") for t in teams}
    return {'teams':teams,'games':games}

def cases(teams,catalog):
    names={c['name'].casefold():c['id'] for c in catalog['champions']}
    for team in teams:
        pools=[sorted({names[c['name'].casefold()] for c in p['champions'] if c['name'].casefold() in names}) for p in team['players']]
        own=lineup(pools)
        if not own:continue
        enemy=sorted(set(names.values())-set(own))[:3]
        bans=[dict(kind='BAN',side=side,championId=None) for side in ('BLUE','RED')*3]
        picks=[dict(kind='PICK',side=side,championId=champion) for side,champion in
               [('BLUE',own[0]),('RED',enemy[0]),('RED',enemy[1]),('BLUE',own[1]),('BLUE',own[2]),('RED',enemy[2])]]
        for name,side,actions in [('blind_blue','BLUE',[]),('blind_red','RED',[]),('early','BLUE',bans+picks[:1]),('late','BLUE',bans+picks)]:
            yield {'teamId':team['id'],'case':name,'pools':pools,
                   'body':dict(format='TOURNAMENT',side=side,patch=catalog['version'],actions=actions)}

def run(label,port,output,diagnostics):
    if output.exists():raise FileExistsError('Use a new output file; verification receipts are not overwritten')
    base=f'http://127.0.0.1:{port}';before=snapshot(base)
    prior=None
    if label=='offline':
        prior=json.loads((output.parent/'online.json').read_text())
        assert digest(before)==prior['savedStateSha256']
        fixtures=[r['fixture'] for r in prior['cases']]
    else:fixtures=list(cases(before['teams'],call(base,'/api/champions')))
    assert fixtures,'No saved roster with a complete legal lineup'
    pointer=json.loads((ROOT/'data/oracle/history-bundles/active.json').read_text())
    reports=[]
    for fixture in fixtures:
        measurements=[];events=[];responses=[]
        for iteration in range(12):
            start=perf_counter()
            reply=call(base,f"/api/teams/{fixture['teamId']}/draft/picks",fixture['body'])
            measurements.append((perf_counter()-start)*1000)
            event=diagnostic(diagnostics,reply['requestId'])
            check_ranking(event,label=='offline' or event['gateResult']!='VALID')
            legal=set().union(*map(set,fixture['pools']))
            unavailable={a['championId'] for a in fixture['body']['actions'] if a['championId']}
            assert {r['championId'] for r in event['javaRanking']}<=legal-unavailable
            allies=[a['championId'] for a in fixture['body']['actions'] if a['kind']=='PICK' and a['side']==fixture['body']['side']]
            for candidate in event['javaRanking']:
                # Independent backtracking over pool membership, never inferred roles.
                wanted=allies+[candidate['championId']]
                possibilities=[[str(i) for i,pool in enumerate(fixture['pools']) if c in pool] for c in wanted]
                assert lineup(possibilities) is not None
            assert [r['championId'] for r in reply['picks']]==[r['championId'] for r in event['finalRanking'][:3]]
            if event['gateResult']=='VALID':
                assert event['historyBundleVersion']==pointer['version']
                assert event['historyBundleSha256']==pointer['sha256']
                assert len(event['historySnapshotId'])==64
            if label=='offline':assert event['gateResult']=='ML_UNAVAILABLE'
            events.append(event);responses.append(reply)
        valid=[(event,response) for event,response in zip(events,responses) if event['gateResult']=='VALID']
        if label=='online':assert valid,'No successful guarded inference for this case'
        chosen,response=valid[-1] if valid else (events[-1],responses[-1])
        warm=sorted(measurements[1:])
        report=dict(fixture=fixture,firstMs=measurements[0],warmMedianMs=statistics.median(warm),warmP95Ms=warm[-1],
            gateCounts=dict(Counter(e['gateResult'] for e in events)),inferenceLatenciesMs=[e['inferenceLatencyMs'] for e in events],
            diagnostic=chosen,response=response)
        if label=='offline':
            previous=prior['cases'][len(reports)]['diagnostic']
            assert previous['javaRanking']==chosen['javaRanking'],'Java bases changed between online/offline checks'
        reports.append(report)
    assert snapshot(base)==before,'Saved team/game state changed'
    result=dict(at=datetime.now(timezone.utc).isoformat(),label=label,savedStateSha256=digest(before),
        savedTeamsAndGamesUnchanged=True,exactWholeCandidateFallback=label=='offline',cases=reports)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x') as stream:json.dump(result,stream,indent=2)
    print(json.dumps({'label':label,'cases':len(reports),'unchanged':True,'gates':[r['gateCounts'] for r in reports]},indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('label',choices=('online','offline'))
    parser.add_argument('--port',type=int,default=8081)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--diagnostics',type=Path,default=ROOT/'data/history-refresh-verification/diagnostics')
    args=parser.parse_args();run(args.label,args.port,args.output,args.diagnostics)
