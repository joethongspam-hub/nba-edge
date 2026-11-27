import sys
import unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from nfl_efficiency import parse,ratings,margin,annotate

class EPATest(unittest.TestCase):
    def test_pairing(self):
        now=datetime(2026,11,26,tzinfo=timezone.utc)
        history=[(now,"Buffalo Bills","Miami Dolphins",7,False)]
        rows=[dict(season_type="REG",team=t,passing_epa=p,rushing_epa=2,game_id="2026_12_MIA_BUF") for t,p in [("BUF","10"),("MIA","-2")]]
        games=parse(rows,history)
        self.assertEqual(len(games),1)
        self.assertEqual(games[0][5:],(10,2,-2,2))
        self.assertEqual(parse(rows,history*2),[])
    def test_cutoff(self):
        now=datetime(2026,11,26,tzinfo=timezone.utc)
        games=[(now-timedelta(days=7*i+7),"A","B",7,False,10,2,-2,0) for i in range(8)]
        stats=ratings(games,now)
        self.assertEqual(stats,ratings(games+[(now,"A","B",-99,False,-99,0,99,0)],now))
        self.assertGreater(margin("A","B",stats),0)
        row=dict(home="A",away="B",team="A",line=None)
        annotate([row],games,now)
        self.assertGreater(row["epa_probability"],.5)
        self.assertIsNone(margin("A","C",stats))
