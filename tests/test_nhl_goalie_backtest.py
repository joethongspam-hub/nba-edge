import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from nhl_goalie_backtest import relative,evaluate

class HistoricalGoalieTests(unittest.TestCase):
    def test_rating(self):
        self.assertAlmostEqual(relative({(2024,"1"):(10,10),(2023,"1"):(20,10)},
                                       {(2024,"H"):(20,5)},2024,"1","H"),15/35-5/35)
        self.assertIsNone(relative({}, {},2024,"1","H"))
    def test_no_same_day_leak(self):
        t=datetime(2024,11,20,20,tzinfo=timezone.utc)
        games=[]
        for i in range(10,0,-1):
            s=t-timedelta(days=i)
            games.append((s.date(),s,"H","A",4,2,"1","2",2024,False))
        games.append((t.date(),t,"H","A",4,2,"1","2",2024,False))
        observations=[(t.date(),2024,"1","H",10,10),(t.date(),2024,"2","A",10,-10)]
        results,coverage,selected=evaluate(games,observations)
        self.assertEqual(coverage[2024]["evaluated"],0)
        self.assertIsNone(selected)
