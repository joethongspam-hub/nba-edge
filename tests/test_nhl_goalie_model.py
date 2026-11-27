import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from nhl_goalie_model import adjustment, annotate

NOW=datetime(2026,11,27,17,tzinfo=timezone.utc)
def goalie(value,status="confirmed"):
    return {"status":status,"rating":{"rating_eligible":True,"relative_gsax60":value}}

class GoalieModelTests(unittest.TestCase):
    def test_adjustment(self):
        self.assertAlmostEqual(adjustment(goalie(.4)),.2)
        self.assertAlmostEqual(adjustment(goalie(.4,"projected")),.1)
        self.assertEqual(adjustment(goalie(4)),.5)
        self.assertIsNone(adjustment(goalie(.4,"unknown")))
    def test_distribution(self):
        games=[(NOW-timedelta(days=i+1),"Home","Away",3,3,False) for i in range(10)]
        r={"home":"Home","away":"Away","team":"Home","market":"h2h","line":None,
           "start":(NOW+timedelta(hours=1)).isoformat(),"model_probability":.55,
           "goalie_home":goalie(.4),"goalie_away":goalie(-.4)}
        opposite=dict(r,team="Away")
        health=annotate([r,opposite],games,NOW)
        self.assertEqual(health["modeled_games"],1)
        self.assertGreater(r["goalie_probability_delta"],0)
        self.assertAlmostEqual(r["goalie_probability"]+opposite["goalie_probability"],1,places=5)
        self.assertEqual(r["model_probability"],.55)
        missing=dict(r,goalie_home={},start=(NOW+timedelta(hours=2)).isoformat())
        missing.pop("goalie_probability")
        self.assertEqual(annotate([missing],games,NOW)["modeled_games"],0)
        self.assertNotIn("goalie_probability",missing)
