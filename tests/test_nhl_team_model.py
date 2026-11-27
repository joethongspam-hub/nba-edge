import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
from nhl_team_model import annotate, distribution, fit

class NHLModelTest(unittest.TestCase):
    def test_distribution(self):
        d=distribution(3,3)
        self.assertAlmostEqual(sum(d.values()),1)
        self.assertNotIn(0,d)
        self.assertAlmostEqual(sum(p for m,p in d.items() if m>0),.5)
        self.assertLess(sum(p for m,p in d.items() if m>1),.5)
    def test_model(self):
        now=datetime(2026,11,26,tzinfo=timezone.utc)
        games=[(now-timedelta(days=i+1),"A","B",5,1,False) for i in range(12)]
        rows=[dict(home="A",away="B",team="A",market="h2h",line=None),dict(home="A",away="B",team="A",market="spreads",line=-1.5)]
        annotate(rows,games,now)
        self.assertGreater(rows[0]["model_probability"],.5)
        self.assertLess(rows[1]["model_probability"],rows[0]["model_probability"])
        self.assertEqual(rows[1]["push_probability"],0)
        self.assertEqual(fit(games,now),fit(games+[(now,"A","B",0,20,False)],now))
        missing=dict(home="A",away="C",team="A",market="h2h",line=None)
        annotate([missing],games,now)
        self.assertNotIn("model_probability",missing)
