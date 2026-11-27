import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from team_rankings import rankings

class RankingTest(unittest.TestCase):
    def test_agreement_and_dedup(self):
        base=dict(event_id="1",home="A",away="B",start="2026-11-27T00:00:00Z",book="fanduel",market="h2h",line=None,odds=-110,market_probability=.5)
        a=dict(base,team="A",model_probability=.7,shadow_probability=.65,efficiency_probability=.6,projected_margin=5)
        b=dict(base,team="B",model_probability=.3,shadow_probability=.35,efficiency_probability=.4,projected_margin=-5)
        snapshot=dict(updated="2026-11-26T00:00:00Z",sports={"NBA":[a,b,dict(a,book="draftkings"),dict(b,book="draftkings")]})
        result=rankings(snapshot)["NBA"]["h2h"]
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]["lower_probability"],.6)
        self.assertEqual(result[0]["agreement"],3)
        self.assertEqual(result[0]["line_gap"],5)
        snapshot["sports"]["NBA"]=[dict(a,efficiency_probability=.4),dict(b,efficiency_probability=.6)]
        self.assertEqual(rankings(snapshot)["NBA"]["h2h"],[])
        snapshot["sports"]["NBA"]=[a,b]
        snapshot["updated"]="2026-11-28T00:00:00Z"
        self.assertEqual(rankings(snapshot)["NBA"]["h2h"],[])
