"""Offline freshness policy experiment. No training, service changes or 2026 scoring."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import random
import subprocess
from time import perf_counter

os.environ.setdefault('OMP_NUM_THREADS','2')
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
import lightgbm as lgb
import numpy as np
from baseline import History
from ml_features import vector
from recency_features import RecencyTable, extend, EXTENDED_NAMES
from protocol import load_prepared
from scaled_train import verify, validate_contexts, rows, sha, read
from saved_scenarios import evidence_for
from tree_ranker import tree_score

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'data/oracle'
MODEL=DATA/'blind-2026-09-14-reviewed'
COMPACT=DATA/'compact-2026-09-11-resumable'
HASH='ea447cdced1aa541446c50ef03c2ed96f06ecd94e4f50fb50514f17d85964ec5'
DELAYS=(1,7,10,14,21,30)


def eligible_day(day):
    value=datetime.fromisoformat(day)
    if value.tzinfo or value.time()!=datetime.min.time() or value.year!=2025:
        raise ValueError('Only 2025 midnight development predictions permitted')
    return value


def policy_caps(e):
    out=dict.fromkeys('ABC',0.)
    if not e['seen'] or e['global_games']<30: return out
    if e['age']<=7 and e['p30']>=5 and e['gp']>=30: out['A']=2.5
    if e['g14']>=30 and e['p14']>=5: out['B']=2.5 if e['gp']>=30 else 1.25
    elif e['g30']>=30 and e['p30']>=5: out['B']=1.25 if e['gp']>=30 else .625
    out['C']=out['B']
    if not out['C'] and e['season_games']>=30 and e['season_population']>=100 and e['last_season_age']<=90:
        out['C']=.5
    return out


def adjusted(base,scores,caps):
    zero={r['id']:0. for r in base}
    if (scores is None or set(scores)!=set(zero) or any(not math.isfinite(v) for v in scores.values())
        or any(not math.isfinite(v) or not 0<=v<=2.5 for v in caps.values())):
        return base,zero,True
    if len(scores)<2 or len(set(scores.values()))==1: return base,zero,False
    order=sorted(scores,key=lambda c:(scores[c],c))
    bonuses={c:caps.get(c,0.)*i/(len(order)-1) for i,c in enumerate(order)}
    result=sorted([{'id':r['id'],'score':r['score']+bonuses[r['id']]} for r in base],key=lambda r:(-r['score'],r['id']))
    return result,bonuses,False


def windows(games,when,boundary,patch):
    # Window anchor is prediction availability time, not last available source date.
    end=when-timedelta(days=1)
    retained=[g for g in games if datetime.fromisoformat(g['date'])<min(end,boundary)]
    output=[]
    for days in (14,30,None):
        chosen=[g for g in retained if (g['patch']==patch if days is None else datetime.fromisoformat(g['date'])>=end-timedelta(days=days))]
        picks,bans=Counter(),Counter()
        for game in chosen:
            picks.update({c for t in game['teams'] for c in t['picks'] if c})
            bans.update({c for t in game['teams'] for c in t['bans'] if c})
        output.append((len(chosen),picks,bans))
    return RecencyTable(output,len(retained))


class HistoryCursor:
    """Incremental withheld base history; never consumes a prediction or later game."""
    def __init__(self,games):
        self.games=sorted(games,key=lambda g:(g['date'],g['gameId']))
        self.index=0;self.history=History();self.boundary=None
        self.season=Counter();self.last={}

    def at(self,boundary):
        if self.boundary and boundary<self.boundary: raise ValueError('Backwards source boundary')
        self.boundary=boundary
        while self.index<len(self.games) and datetime.fromisoformat(self.games[self.index]['date'])<boundary:
            g=self.games[self.index]
            if g['date']>='2026': raise ValueError('2026 at observation boundary')
            self.history.observe(g)
            if g['date'].startswith('2025'):
                for t in g['teams']:
                    for p in t['players']:
                        self.season[p['championId']]+=1;self.last[p['championId']]=g['date']
            self.index+=1
        return self.history


def features(context,ids,cursor,table,professional):
    evidence=[evidence_for(cursor.history,c,context['allyPicks'],context['playerIds']) for c in ids]
    if professional:
        for c,e in zip(ids,evidence):
            e['playerChampionEvidence']={p:int(cursor.history.players.get(p,{}).get(c,0)) for p in context['playerIds']}
    base=np.asarray([vector(context,e) for e in evidence],dtype=np.float32).reshape(-1,33)
    result=extend(base,ids,context,table)
    if result.shape!=(len(ids),108) or not np.isfinite(result).all(): raise ValueError('Invalid frozen features')
    return result


def support(ids,when,cursor,table,seen,season_population):
    h=cursor.history
    age=(when-datetime.fromisoformat(h.latest_date)).total_seconds()/86400 if h.latest_date else float('inf')
    result={}
    for c in ids:
        last=cursor.last.get(c)
        result[c]=dict(seen=c in seen,global_games=h.champions.get(c,(0,0))[0],age=age,
            g14=table.windows[0][0],p14=table.windows[0][1][c],g30=table.windows[1][0],p30=table.windows[1][1][c],
            gp=table.windows[2][0],season_games=cursor.season[c],season_population=season_population,
            last_season_age=(when-datetime.fromisoformat(last)).total_seconds()/86400 if last else float('inf'))
    return result


def observation(order,target):
    rank=order.index(target)+1 if target in order else 0
    return [float(rank==1),float(0<rank<=3),1/rank if rank else 0.]


def safe_predict(model,x,ids):
    try:
        if x.shape!=(len(ids),108) or not np.isfinite(x).all() or model.num_feature()!=108: return None
        if not ids: return {}
        values=np.asarray(tree_score(model,x))
        if values.shape!=(len(ids),) or not np.isfinite(values).all(): return None
        return dict(zip(ids,map(float,values)))
    except Exception:
        return None


def stability(order,fresh):
    return [float(order[:1]==fresh[:1]),len(set(order[:3])&set(fresh[:3]))/max(1,min(3,len(fresh)))]


def save(path,value):
    with path.open('x',encoding='utf-8') as stream: json.dump(value,stream,indent=2,allow_nan=False)


def select_games(contexts):
    groups=defaultdict(set)
    for c in contexts.values():
        if c['split']=='validation':
            when=eligible_day(c['date'][:10]);groups[(when.month-1)//3].add(c['gameId'])
    return {g for ids in groups.values() for g in sorted(ids,key=lambda v:hashlib.sha256(('freshness-1729|'+v).encode()).hexdigest())[:128]}


def validated_feature(row,context):
    ids=row['championIds'];x=np.asarray(row['x'],dtype=np.float32).reshape(len(ids),-1) if ids else np.empty((0,33),dtype=np.float32)
    if (row['split']!=context['split'] or row['snapshotId']!=context['snapshotId'] or row['poolPolicy']!='inferred'
        or ids!=sorted(set(ids)) or set(ids)&set(context['allyPicks']+context['enemyPicks']+context['bans'])
        or x.shape!=(len(ids),33) or not np.isfinite(x).all()):
        raise ValueError('Illegal or misaligned frozen feature row')
    return {'ids':ids,'x':x}


def load_selected():
    # Full artifact hashes attest the already-audited export; do not rebuild unused baseline arrays.
    manifest=verify(COMPACT)
    contexts,labels,_=validate_contexts(COMPACT,manifest)
    selected=select_games(contexts)
    wanted={k for k,c in contexts.items() if c['split']=='validation' and c['gameId'] in selected}
    cases={}
    for row in rows(COMPACT,'features'):
        key=row['caseId']
        if key in wanted:
            if key in cases: raise ValueError('Duplicate selected case')
            cases[key]=validated_feature(row,contexts[key])
    if cases.keys()!=wanted: raise ValueError('Missing selected cases')
    print(f'Verified export; retained {len(cases)} selected validation decisions',flush=True)
    return dict(manifest=manifest,contexts=contexts,labels=labels,cases=cases)


def compile_java(folder):
    folder.mkdir()
    source=ROOT/'backend/src/main/java/com/beatrice/backend/recommendation'
    subprocess.run(['javac','-d',str(folder),*[str(source/(n+'.java')) for n in
        ('RecommendationEngine','WeightedRecommendations','TeamPickFeasibility')],str(Path(__file__).with_name('java')/'FreshnessScorer.java')],check=True,capture_output=True)


def java_scores(states,folder):
    lines=[]
    for s in states:
        lines.append('\t'.join(['S',s['id'],','.join(s['allyPicks']),','.join(s['allyPicks']+s['enemyPicks']+s['bans'])]))
        for role,pool in s['pools'].items():
            for c,comfort in pool.items(): lines.append('\t'.join(['P',role,c,str(comfort)]))
        lines.append('END')
    process=subprocess.run(['java','-cp',str(folder),'FreshnessScorer'],input='\n'.join(lines)+'\n',text=True,capture_output=True,check=True,timeout=60)
    result={s['id']:[] for s in states};done=set()
    for line in process.stdout.splitlines():
        p=line.split('\t')
        if p[0]=='DONE': done.add(p[1])
        else: result[p[1]].append({'id':p[2],'score':float(p[3])})
    if done!=set(result): raise ValueError('Incomplete Java output')
    return result


def saved_states(snapshot,contexts):
    rng=random.Random(1729);names={c['name'].casefold():c['id'] for c in snapshot['catalog']['champions']}
    anchors={}
    for c in sorted(contexts,key=lambda c:(c['date'],c['gameId'])):
        q=(int(c['date'][5:7])-1)//3;anchors.setdefault(q,c)
    states=[]
    def lineup(pools,used):
        if not pools: return used
        choices=sorted(set(pools[0])-set(used));rng.shuffle(choices)
        for c in choices:
            found=lineup(pools[1:],used+[c])
            if found: return found
        return None
    for team in snapshot['teams']:
        pools={p['role']:{names[c['name'].casefold()]:c['comfort'] for c in p['champions'] if c['name'].casefold() in names} for p in team['players']}
        for repeat in range(5):
            allies=lineup(list(pools.values()),[])
            if not allies: continue
            other=rng.sample(sorted(set(names.values())-set(allies)),15)
            for stage,n,m in (('blindBlue',0,0),('blindRed',0,0),('early',1,2),('late',3,3)):
                for q,a in anchors.items():
                    states.append(dict(id=f's{len(states):04}',date=a['date'],patch=a['patch'],stage=stage,
                        playerIds=['saved'+str(i) for i in range(5)],allyPicks=allies[:n],enemyPicks=other[:m],
                        bans=other[5:15],pools=pools,teamId=team['id']))
    return states


def summarized(rows):
    groups=defaultdict(list)
    for row in rows:
        for group in ('overall','patch/'+row['patchGroup'],'stage/'+row['stage']):
            groups[group].append(row)
    out={}
    for group,values in groups.items():
        metrics={}
        ages=[v['sourceAgeDays'] for v in values if v.get('sourceAgeDays') is not None]
        metrics['sourceAgeDays']={'min':min(ages,default=None),'median':float(np.median(ages)) if ages else None,'max':max(ages,default=None)}
        metrics['samePatchWindowMissingRate']=float(np.mean([v['samePatchMissing'] for v in values]))
        metrics['technicalFailures']=sum(v['technical'] for v in values)
        for name in ('metrics','stability','missing','javaStability'):
            if name in values[0]: metrics[name]=np.mean([v[name] for v in values],axis=0).tolist()
        if 'eligibility' in values[0]:
            counts=np.sum([v['eligibility'] for v in values],axis=0)
            metrics['candidateEligibilityCounts']=counts.tolist()
            metrics['candidateEligibilityRates']=(counts/max(1,counts.sum())).tolist()
            metrics['requestEligibilityRates']=np.mean([v['requestEligibility'] for v in values],axis=0).tolist()
            metrics['exactJavaFallbackRate']=float(np.mean([v['fallback'] for v in values]))
            metrics['technicalFailures']=sum(v['technical'] for v in values)
            metrics['seasonOnlyEligibleCandidates']=sum(v['seasonOnlyCandidates'] for v in values)
            bonuses=[b for v in values for b in v['bonuses']]
            metrics['bonus']={'mean':float(np.mean(bonuses)) if bonuses else 0.,
                'p50':float(np.quantile(bonuses,.5)) if bonuses else 0.,'p95':float(np.quantile(bonuses,.95)) if bonuses else 0.,
                'max':max(bonuses,default=0.),'zeroRate':sum(b==0 for b in bonuses)/max(1,len(bonuses))}
        out[group]={'requests':len(values),**metrics}
    for group in ('overall','patch/same','patch/different','patch/missing','stage/blind','stage/early','stage/late'):
        out.setdefault(group,{'requests':0,'notEstimable':True})
    return out


def run(output):
    if output.exists(): raise FileExistsError('Freshness run refuses overwrite')
    loaded=load_selected()
    games,provenance=load_prepared(DATA/'prepared-2026-09-08-reviewed')
    if provenance!= {k:loaded['manifest']['input'][k] for k in provenance}: raise ValueError('History provenance mismatch')
    games=[g for g in games if g['date']<'2026-01-01']
    audit={r['gameId'] for r in rows(COMPACT,'source-audit') if r['eligible']}
    audited=[g for g in games if g['gameId'] in audit]
    selected=select_games(loaded['contexts'])
    cases=[(k,c) for k,c in loaded['contexts'].items() if c['split']=='validation' and c['gameId'] in selected]
    cases.sort(key=lambda v:(v[1]['date'],v[0]))
    seen_cursor=HistoryCursor(games)
    train_last=max(c['date'] for c in loaded['contexts'].values() if c['split']=='training')[:10]
    seen=set(seen_cursor.at(datetime.fromisoformat(train_last)-timedelta(days=1)).champions)
    snapshot_path=DATA/'saved-team-readiness/snapshot.json';snapshot=read(snapshot_path)
    states=saved_states(snapshot,[c for _,c in cases])
    files=[ROOT/'docs/freshness-policy-protocol.md',Path(__file__),Path(__file__).with_name('java')/'FreshnessScorer.java',
        MODEL/'recency_tree.txt',MODEL/'manifest.json',MODEL/'protocol.json',COMPACT/'manifest.json',snapshot_path]
    files += [Path(__file__).with_name(n) for n in ('recency_features.py','ml_features.py','baseline.py','tree_ranker.py','saved_scenarios.py')]
    files += [ROOT/'backend/src/main/java/com/beatrice/backend/recommendation'/f'{n}.java' for n in ('TeamPickFeasibility','WeightedRecommendations','RecommendationEngine','PickModelClient')]
    files += [COMPACT/name for name in loaded['manifest']['artifacts']]
    files += [DATA/'prepared-2026-09-08-reviewed'/name for name in ('games.jsonl','report.json')]
    files += [Path(__file__).with_name(name) for name in ('protocol.py','scaled_train.py','temporal.py')]
    hashes={str(p.relative_to(ROOT)):sha(p) for p in files}
    if sha(MODEL/'recency_tree.txt')!=HASH or read(MODEL/'protocol.json')['features']!=list(EXTENDED_NAMES): raise ValueError('Frozen model/schema mismatch')
    for n in ('recency_features.py','ml_features.py'):
        if sha(Path(__file__).with_name(n))!=read(MODEL/'manifest.json')['codeSha256'][n]: raise ValueError('Frozen feature code changed')
    output.mkdir(parents=True)
    save(output/'receipt.json',dict(hashes=hashes,modelHash=HASH,features=list(EXTENDED_NAMES),games=sorted(selected),
        cases=[k for k,_ in cases],delays=list(DELAYS),createdAt=datetime.now().isoformat(),no2026Scored=True))
    compile_java(output/'java');bases=java_scores(states,output/'java')
    model=lgb.Booster(model_file=str(MODEL/'recency_tree.txt'))
    if model.num_feature()!=108: raise ValueError('Schema mismatch')
    fresh_raw={};fresh_saved={};results={};raw_all={};saved_all={}
    started=perf_counter()
    # One monotonic cursor per simulation; saved states and labels share time, not identities.
    items=[(c['date'][:10],k,'raw',c) for k,c in cases]+[(s['date'][:10],s['id'],'saved',s) for s in states]
    items.sort(key=lambda v:(v[0],v[1]))
    for delay in DELAYS:
        cursor=HistoryCursor(games);cache={};raw_rows=[];saved_rows={p:[] for p in 'ABC'};last_day=None
        with gzip.open(output/f'observations-{delay}.jsonl.gz','wt',encoding='utf-8') as stream:
            for number,(day,key,kind,c) in enumerate(items):
                when=eligible_day(day);boundary=when-timedelta(days=delay)
                cursor.at(boundary)
                if day!=last_day:
                    cache={};last_day=day
                    retained=[g for g in audited if datetime.fromisoformat(g['date'])<boundary]
                    latest=max(retained,key=lambda g:(g['date'],g['gameId'])) if retained else None
                    season_population=sum(g['date'].startswith('2025') for g in retained)
                if c['patch'] not in cache: cache[c['patch']]=windows(audited,when,boundary,c['patch'])
                table=cache[c['patch']]
                ids=loaded['cases'][key]['ids'] if kind=='raw' else [r['id'] for r in bases[key]]
                try:
                    x=features(c,ids,cursor,table,kind=='raw')
                except Exception:
                    x=None
                if delay==1 and kind=='raw' and (x is None or not np.allclose(x[:,:33],loaded['cases'][key]['x'],rtol=0,atol=1e-6)):
                    raise ValueError('Fresh base-feature reconstruction differs from frozen export: '+key)
                scores=safe_predict(model,x,ids)
                order=sorted(ids,key=lambda i:(-scores[i],i)) if scores is not None else []
                e=support(ids,when,cursor,table,seen,season_population)
                group='missing' if not latest else 'same' if latest['patch']==c['patch'] else 'different'
                stage='blind' if not c['allyPicks'] and not c['enemyPicks'] else 'late' if len(c['allyPicks'])>=3 else 'early'
                age=(when-datetime.fromisoformat(cursor.history.latest_date)).total_seconds()/86400 if cursor.history.latest_date else None
                common=dict(id=key,patchGroup=group,stage=stage,sourceAgeDays=age,samePatchMissing=not table.windows[2][0],technical=scores is None)
                if kind=='raw':
                    if delay==1: fresh_raw[key]=order
                    missing=[sum(v['global_games']==0 for v in e.values())/max(1,len(ids)),sum(not v['seen'] for v in e.values())/max(1,len(ids))]
                    missing += [float(x[:,i].mean()) if len(ids) and x is not None else 0. for i in (39,40,47,48,55,56)]
                    row=dict(common,gameId=c['gameId'],metrics=observation(order,loaded['labels'][key]['championId']),
                        stability=stability(order,fresh_raw[key]),missing=missing)
                    raw_rows.append(row);stream.write(json.dumps(dict(kind=kind,delay=delay,**row))+'\n')
                else:
                    all_caps={i:policy_caps(e[i]) for i in ids}
                    for p in 'ABC':
                        caps={i:all_caps[i][p] for i in ids};ranked,bonuses,failed=adjusted(bases[key],scores,caps)
                        if delay==1: fresh_saved[key,p]=[r['id'] for r in ranked]
                        final=[r['id'] for r in ranked];baseids=[r['id'] for r in bases[key]]
                        counts=[sum(v==2.5 for v in caps.values()),sum(0<v<2.5 for v in caps.values()),sum(v==0 for v in caps.values())]
                        tier=0 if counts[0] else 1 if counts[1] else 2
                        row=dict(common,eligibility=counts,requestEligibility=[int(tier==j) for j in range(3)],
                            fallback=ranked==bases[key],bonuses=list(bonuses.values()),
                            seasonOnlyCandidates=sum(all_caps[i]['B']==0 and caps[i]==.5 for i in ids),
                            evidence={i:{k:v for k,v in item.items() if k not in ('age','last_season_age')} for i,item in e.items()},
                            stability=stability(final,fresh_saved[key,p]),javaStability=stability(final,baseids))
                        row['technical']=failed
                        assert set(final)==set(baseids) and all(0<=b<=2.5 for b in bonuses.values())
                        saved_rows[p].append(row);stream.write(json.dumps(dict(kind=kind,policy=p,delay=delay,**row))+'\n')
                if number and number%1000==0: print(f'delay={delay}: {number}/{len(items)}',flush=True)
        raw_all[delay]=raw_rows;saved_all[delay]=saved_rows
        results[str(delay)]={'raw':summarized(raw_rows),'bounded':{p:summarized(v) for p,v in saved_rows.items()}}
        print(f'Completed delay={delay}',flush=True)
    # Cluster by historical game, preserving all ten correlated decisions.
    comparisons={}
    fresh={r['id']:r for r in raw_all[1]}
    for delay in DELAYS[1:]:
        comparisons[str(delay)]={}
        for group in ('overall','same','different','missing'):
            clustered=defaultdict(list)
            for r in raw_all[delay]:
                if group=='overall' or r['patchGroup']==group:
                    clustered[r['gameId']].append(np.array(r['metrics'])-np.array(fresh[r['id']]['metrics']))
            values=np.asarray([np.mean(v,axis=0) for v in clustered.values()])
            if not len(values): comparisons[str(delay)][group]={'games':0};continue
            rng=np.random.default_rng(1729)
            boot=np.asarray([values[rng.integers(0,len(values),len(values))].mean(axis=0) for _ in range(1000)])
            comparisons[str(delay)][group]={'games':len(values),'delta':values.mean(axis=0).tolist(),
                'paired95':np.quantile(boot,[.025,.975],axis=0).tolist(),
                'fullInfluenceGuardrail':bool(len(values)>=30 and values[:,1].mean()>=-.02 and values[:,2].mean()>=-.02)}
    if any(sha(ROOT/p)!=h for p,h in hashes.items()): raise ValueError('Input or code changed during run')
    save(output/'report.json',dict(status='COMPLETE_OFFLINE_FRESHNESS',results=results,comparisons=comparisons,
        seconds=perf_counter()-started,games=len(selected),decisions=len(cases),savedScenarios=len(states),
        metricsOrder=['top1','top3','mrr'],stabilityOrder=['top1Agreement','top3Overlap'],
        eligibilityOrder=['full','reduced','zero'],missingOrder=['zeroGlobal','trainingUnseen','14Window','14Champion','30Window','30Champion','patchWindow','patchChampion'],
        boundedAccuracy='Not estimable: synthetic saved-team states have no correct-pick labels',no2026Scored=True))
    print(json.dumps({'output':str(output),'seconds':perf_counter()-started,'games':len(selected),'decisions':len(cases)}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=DATA/'freshness-2025-2026-09-17')
    run(parser.parse_args().output)
