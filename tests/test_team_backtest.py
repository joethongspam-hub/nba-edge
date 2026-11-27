import sys
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from team_backtest import evaluate

class WalkForwardTest(unittest.TestCase):
    def test_future_results_do_not_change_earlier_predictions(self):
        start=datetime(2026,10,1,tzinfo=timezone.utc)
        games=[(start+timedelta(days=i),"A","B",10,False) for i in range(15)]
        first=evaluate("NBA",games)
        self.assertEqual(first["games"],7)
        second=evaluate("NBA",games+[(start+timedelta(days=15),"A","B",-100,False)])
        self.assertEqual(first["results"],second["results"][:len(first["results"])])
    def test_empty_history(self):
        result=evaluate("NHL",[])
        self.assertEqual(result["games"],0)
        self.assertIsNone(result["accuracy"])
    def test_same_day_excluded(self):
        start=datetime(2026,10,1,tzinfo=timezone.utc)
        games=[(start+timedelta(days=i),"A","B",10,False) for i in range(8)]
        time=start+timedelta(days=8)
        a=evaluate("NBA",games+[(time+timedelta(hours=2),"A","B",10,False)])
        b=evaluate("NBA",games+[(time,"A","B",-100,False),(time+timedelta(hours=2),"A","B",10,False)])
        self.assertEqual(a["results"][-1],b["results"][-1])
