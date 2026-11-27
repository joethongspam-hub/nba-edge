import sys
import unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from team_optimization import candidates,forecasts,audit,DEFAULTS
from nba_team_model import annotate

class OptimizationTest(unittest.TestCase):
    def test_baseline_and_future_exclusion(self):
        now=datetime(2026,11,26,tzinfo=timezone.utc)
        games=[(now-timedelta(days=i+1),"A","B",8,False) for i in range(20)]
        p=DEFAULTS["NBA"]
        first=forecasts("NBA",games,p)
        second=forecasts("NBA",games+[(now,"A","B",-99,False)],p)
        self.assertTrue(first)
        self.assertEqual(first,{k:second[k] for k in first})
        self.assertEqual(len(candidates("NBA")),11)
        self.assertEqual(len(candidates("NHL")),9)
    def test_small_sample(self):
        self.assertEqual(audit("NFL",[])["status"],"Insufficient common games")
