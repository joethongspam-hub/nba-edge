import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
from nba_team_model import annotate, fit

class TestTeamModel(unittest.TestCase):
    def test_direction_and_push(self):
        now=datetime(2026,11,26,tzinfo=timezone.utc)
        games=[(now-timedelta(days=i+1),"A","B",15,False) for i in range(12)]
        rows=[dict(home="A",away="B",team=t,market="h2h",line=None) for t in ("A","B")]
        annotate(rows,games,now)
        self.assertGreater(rows[0]["model_probability"],.5)
        self.assertAlmostEqual(sum(r["model_probability"] for r in rows),1,places=5)
        row=dict(home="A",away="B",team="A",market="spreads",line=-5)
        annotate([row],games,now)
        self.assertGreater(row["push_probability"],0)
        self.assertLess(row["model_probability"]+row["push_probability"],1)
        self.assertEqual(fit(games+[(now,"A","B",-100,False)],now),fit(games,now))
    def test_missing(self):
        row=dict(home="A",away="B",team="A",market="h2h",line=None)
        annotate([row],[],datetime.now(timezone.utc))
        self.assertNotIn("model_probability",row)
