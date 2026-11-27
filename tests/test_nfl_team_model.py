import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
from nfl_team_model import annotate, outcome, fit

class NFLModelTest(unittest.TestCase):
    def test_outcome(self):
        for line in (0, -3, -2.5):
            win,push=outcome(4,line)
            other,other_push=outcome(-4,-line)
            self.assertAlmostEqual(win+other+push,1)
            self.assertAlmostEqual(push,other_push)
            self.assertEqual(push==0,line==-2.5)
    def test_model(self):
        now=datetime(2026,11,26,tzinfo=timezone.utc)
        games=[(now-timedelta(days=7*(i+1)),"A","B",14,False) for i in range(8)]
        row=dict(home="A",away="B",team="A",market="h2h",line=None)
        annotate([row],games,now)
        self.assertGreater(row["model_probability"],.5)
        self.assertEqual(fit(games,now),fit(games+[(now,"A","B",-80,False)],now))
        missing=dict(home="A",away="C",team="A",market="h2h",line=None)
        annotate([missing],games,now)
        self.assertNotIn("model_probability",missing)
