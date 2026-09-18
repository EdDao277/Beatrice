"""Boundary tests: withheld history, gates, no feature substitution, exact fallback."""
import unittest
import tempfile
from pathlib import Path
from collections import Counter
from datetime import datetime
import numpy as np
try:
    from freshness import policy_caps, adjusted, windows, eligible_day
except ImportError:
    policy_caps = adjusted = windows = eligible_day = None


class FreshnessTests(unittest.TestCase):
    def test_subset_loader_still_rejects_illegal_or_misaligned_features(self):
        from freshness import validated_feature
        c=dict(split='validation',snapshotId='x',allyPicks=['USED'],enemyPicks=[],bans=[])
        row=dict(split='validation',snapshotId='x',poolPolicy='inferred',championIds=['A'],x=[[0.]*33])
        self.assertEqual(validated_feature(row,c)['ids'],['A'])
        with self.assertRaises(ValueError): validated_feature(dict(row,championIds=['USED']),c)
        with self.assertRaises(ValueError): validated_feature(dict(row,x=[[0.]*32]),c)

    def test_bad_predictor_output_is_not_truncated_or_ranked(self):
        from freshness import safe_predict
        class Wrong:
            def num_feature(self): return 108
            def predict(self,*args,**kwargs): return np.array([1.])
        self.assertIsNone(safe_predict(Wrong(),np.zeros((2,108)),['A','B']))
        self.assertIsNone(safe_predict(None,np.zeros((2,108)),['A','B']))
        self.assertIsNone(safe_predict(Wrong(),np.full((1,108),np.nan),['A']))

    def test_withheld_base_features_remove_future_familiarity_and_outcomes(self):
        from freshness import HistoryCursor, features
        def game(day,win):
            return dict(gameId=day,date=day,patch='15.1',teams=[dict(result=win,
                players=[dict(playerId='p'+str(i),championId=c) for i,c in enumerate('ABCDE')])])
        cursor=HistoryCursor([game('2025-01-01',1),game('2025-01-10',0)])
        cursor.at(datetime(2025,1,10))
        self.assertEqual(cursor.history.champions['A'],[1,1])
        context=dict(playerIds=['p'+str(i) for i in range(5)],allyPicks=[],enemyPicks=[])
        table=windows([],datetime(2025,1,17),datetime(2025,1,10),'15.1')
        x=features(context,['A','NEW'],cursor,table,True)
        self.assertEqual(x.shape,(2,108))
        self.assertAlmostEqual(float(x[0,0]),np.log(2),places=6)
        self.assertAlmostEqual(float(x[0,3]),26/51,places=6)
        self.assertEqual(x[1,5],1.)
        self.assertTrue(np.all(x[:,[39,47,55]]==1))
        self.assertEqual(features(context,['A'],cursor,table,False)[0,0],0.)

    def test_real_java_matching_keeps_flex_and_saved_comfort(self):
        from freshness import compile_java, java_scores
        states=[dict(id='fixture',allyPicks=['A'],enemyPicks=['C'],bans=[],pools={
            'TOP':{'A':10,'B':8,'C':10},'MID':{'A':1}})]
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'classes';compile_java(target)
            output=java_scores(states,target)
        self.assertEqual(output,{'fixture':[{'id':'B','score':60.5}]})

    def test_gate_boundaries_and_season_not_recent(self):
        self.assertIsNotNone(policy_caps)
        e = dict(seen=True, global_games=30, age=7, g14=30, p14=5, g30=40, p30=5,
                 gp=30, season_games=30, season_population=100, last_season_age=90)
        self.assertEqual(policy_caps(e), {'A':2.5,'B':2.5,'C':2.5})
        self.assertEqual(policy_caps(dict(e,age=7.01,gp=0)), {'A':0,'B':1.25,'C':1.25})
        self.assertEqual(policy_caps(dict(e,p14=0,gp=0)), {'A':0,'B':.625,'C':.625})
        self.assertEqual(policy_caps(dict(e,p14=0,p30=0)), {'A':0,'B':0,'C':.5})
        self.assertEqual(policy_caps(dict(e,p14=0,p30=0,last_season_age=91)), {'A':0,'B':0,'C':0})
        self.assertEqual(policy_caps(dict(e,seen=False)), {'A':0,'B':0,'C':0})

    def test_percentile_keeps_cold_denominator_and_malformed_falls_back(self):
        self.assertIsNotNone(adjusted)
        base=[{'id':'A','score':80.},{'id':'B','score':80.},{'id':'C','score':76.}]
        out, bonus, failed=adjusted(base,{'A':0.,'B':1.,'C':2.},{'A':2.5,'B':1.25,'C':0})
        self.assertFalse(failed)
        self.assertEqual(bonus,{'A':0.,'B':.625,'C':0.})
        self.assertEqual(out[0],{'id':'B','score':80.625})
        for bad in ({'A':1.},{'A':0.,'B':float('nan'),'C':2.},None):
            self.assertEqual(adjusted(base,bad,{}),(base,{'A':0.,'B':0.,'C':0.},True))
        self.assertEqual(adjusted(base,dict.fromkeys('ABC',1.),dict.fromkeys('ABC',2.5))[0],base)

    def test_windows_age_against_prediction_not_download_date(self):
        self.assertIsNotNone(windows)
        def game(day,patch='15.1'):
            return {'date':day,'gameId':day,'patch':patch,'teams':[{'picks':['A'],'bans':['B']}]}
        games=[game('2025-01-02'),game('2025-01-10'),game('2025-01-16')]
        table=windows(games,datetime(2025,1,17),datetime(2025,1,10),'15.2')
        self.assertEqual(table.windows[0][0],1)
        self.assertEqual(table.vector('A')[0],1)
        self.assertEqual(table.vector('A')[22:24],[1.,1.])
        self.assertEqual(table.source_count,1)  # exclusive boundary; no Jan10 observation
        old=windows(games,datetime(2025,2,15),datetime(2025,1,10),'15.1')
        self.assertEqual(old.vector('A')[6],1.)
        self.assertEqual(old.vector('A')[14],1.)
        self.assertEqual(old.vector('A')[22],0.) # genuine same-patch history is still present

    def test_2026_scoring_boundary_rejected(self):
        self.assertIsNotNone(eligible_day)
        self.assertEqual(eligible_day('2025-02-01'),datetime(2025,2,1))
        with self.assertRaises(ValueError): eligible_day('2026-01-01')

if __name__=='__main__': unittest.main()
