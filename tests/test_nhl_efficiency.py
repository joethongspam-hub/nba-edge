import sys
import unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from nhl_efficiency import parse,ratings,forecast,annotate

class XGTest(unittest.TestCase):
    def test_match(self):
        t=datetime(2026,11,26,1,tzinfo=timezone.utc)
        g=(t,"Boston Bruins","Buffalo Sabres",4,2,False)
        r=dict(situation="all",home_or_away="HOME",team="BOS",opposingTeam="BUF",gameDate="20261125",xGoalsFor="3.5",xGoalsAgainst="2.2",goalsFor="4",goalsAgainst="2")
        self.assertEqual(parse([r],[g])[0][6:],(3.5,2.2,4,2))
        self.assertEqual(parse([r],[g,g]),[])
    def test_ratings(self):
        now=datetime(2026,11,26,tzinfo=timezone.utc)
        games=[(now-timedelta(days=i+2),"A","B",4,2,False,4,2,4,2) for i in range(10)]
        stats=ratings(games,now)
        self.assertEqual(stats,ratings(games+[(now,"A","B",1,8,False,1,8,1,8)],now))
        self.assertIsNone(forecast("A","C",stats))
        row=dict(home="A",away="B",team="A",line=None)
        annotate([row],games,now)
        self.assertGreater(row["xg_probability"],.5)
        self.assertEqual(row["xg_push"],0)
