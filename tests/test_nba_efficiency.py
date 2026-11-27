import sys
import unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from nba_efficiency import extract,ratings,forecast,annotate

class EfficiencyTest(unittest.TestCase):
    def test_boxscore(self):
        def team(name):
            stats={"fieldGoalsMade-fieldGoalsAttempted":"40-90","freeThrowsMade-freeThrowsAttempted":"20-25","offensiveRebounds":"10","totalTurnovers":"12"}
            return {"team":{"displayName":name},"statistics":[{"name":k,"displayValue":v} for k,v in stats.items()]}
        body={"boxscore":{"teams":[team("A"),team("B")]}}
        event={"date":"2026-11-25T00:00:00Z","status":{"period":5},"competitions":[{"competitors":[{"homeAway":"home","team":{"displayName":"A"},"score":"110"},{"homeAway":"away","team":{"displayName":"B"},"score":"100"}]}]}
        game=extract(body,event)
        self.assertAlmostEqual(game["poss"],103)
        self.assertAlmostEqual(game["pace"],103*48/53)
    def test_cutoff_and_forecast(self):
        now=datetime(2026,11,26,tzinfo=timezone.utc)
        games=[dict(time=(now-timedelta(days=i+1)).isoformat(),home="A",away="B",hs=115,as_=105,poss=100,pace=100,neutral=False) for i in range(10)]
        stats=ratings(games,now)
        self.assertGreater(stats["A"]["off"],stats["B"]["off"])
        self.assertEqual(stats,ratings(games+[dict(games[0],time=now.isoformat(),hs=1)],now))
        self.assertGreater(forecast("A","B",stats)[0],0)
        row=dict(home="A",away="B",team="A",market="h2h",line=None)
        annotate([row],games,now)
        self.assertGreater(row["efficiency_probability"],.5)
        self.assertIsNone(forecast("A","C",stats))
