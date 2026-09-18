import unittest
from verify_refresh import check_ranking

class VerificationTests(unittest.TestCase):
    def test_fallback_checks_entire_candidate_order_and_exact_scores(self):
        event={'javaRanking':[{'championId':'A','score':80.0},{'championId':'B','score':79.0}],
               'finalRanking':[{'championId':'A','javaScore':80.0,'mlBonus':0.0,'score':80.0},
                               {'championId':'B','javaScore':79.0,'mlBonus':0.0,'score':79.0}]}
        check_ranking(event,True)
        event['finalRanking'].reverse()
        with self.assertRaises(AssertionError):check_ranking(event,True)
        event['finalRanking'].reverse();event['finalRanking'][0]['mlBonus']=2.6
        with self.assertRaises(AssertionError):check_ranking(event,False)
        event['finalRanking'][0]['mlBonus']=0.0;event['finalRanking'][0]['championId']='OutsidePool'
        with self.assertRaises(AssertionError):check_ranking(event,False)

if __name__=='__main__':unittest.main()
