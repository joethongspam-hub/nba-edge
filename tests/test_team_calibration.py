import sys
import unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from team_calibration import evaluate,probabilities,metrics
from team_history import canonical

class CalibrationTest(unittest.TestCase):
    def test_holdout_does_not_fit_future_results(self):
        start=datetime(2026,8,1,tzinfo=timezone.utc)
        rows=[dict(time=(start+timedelta(days=i)).isoformat(),home_probability=.8,tie_probability=0,actual="win" if i%2 else "loss") for i in range(100)]
        first=evaluate(rows)
        changed=[dict(r,actual="win") if i>=60 else r for i,r in enumerate(rows)]
        second=evaluate(changed)
        self.assertEqual(first["scale"],second["scale"])
        self.assertEqual(first["training_games"],60)
        self.assertEqual(first["baseline"]["games"],40)
        self.assertEqual(first["scale"],0)
    def test_ties_and_alias(self):
        p=probabilities(dict(home_probability=.7,tie_probability=.04),.5)
        self.assertAlmostEqual(sum(p),1)
        self.assertAlmostEqual(p[2],.04)
        self.assertEqual(canonical("St Louis Blues"),canonical("St. Louis Blues"))
    def test_small_sample(self):
        self.assertEqual(evaluate([])["status"],"Insufficient sample")
