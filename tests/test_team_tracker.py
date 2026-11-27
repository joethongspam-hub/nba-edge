import sys
import unittest
from pathlib import Path
from datetime import datetime, timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from team_tracker import archive, settle, summarize, capture_pregame, line_movement

class TrackerTest(unittest.TestCase):
    def test_archive_and_settle(self):
        base=dict(event_id="1",home="A",away="B",start="2026-11-27T00:00:00Z",book="fanduel",market="spreads",odds=-110)
        rows=[dict(base,team="A",line=-3,model_probability=.6,push_probability=.05),dict(base,team="B",line=3,model_probability=.35,push_probability=.05)]
        snapshot=dict(updated="2026-11-26T00:00:00Z",sports={"NBA":rows})
        tracker=archive([],snapshot)
        self.assertEqual(len(tracker),1)
        rows[0]["line"]=-4
        archive(tracker,snapshot)
        self.assertEqual(tracker[0]["line"],-3)
        self.assertEqual(len(tracker),1)
        time=datetime(2026,11,27,tzinfo=timezone.utc)
        settle(tracker,{"NBA":[(time,"A","B",3,False)]})
        self.assertEqual(tracker[0]["result"],"push")
        self.assertEqual(summarize(tracker)[0]["pushes"],1)
        self.assertIsNone(summarize(tracker)[0]["accuracy"])
        self.assertEqual(archive([],dict(snapshot,updated="2026-11-28T00:00:00Z")),[])
    def test_ambiguous_and_nhl(self):
        row=dict(sport="NHL",event_id="2",home="A",away="B",team="B",start="2026-11-27T00:00:00Z",line=1.5,result="pending")
        game=(datetime(2026,11,27,tzinfo=timezone.utc),"A","B",4,3,False)
        settle([row],{"NHL":[game,game]})
        self.assertEqual(row["result"],"pending")
        settle([row],{"NHL":[game]})
        self.assertEqual(row["result"],"win")

    def test_pregame_observation(self):
        base=dict(event_id="1",home="A",away="B",start="2026-11-27T00:00:00Z",book="fanduel",market="spreads",odds=-110)
        rows=[dict(base,team="A",line=-3,model_probability=.6),dict(base,team="B",line=3,model_probability=.4)]
        snapshot=dict(updated="2026-11-26T00:00:00Z",sports={"NBA":rows})
        tracker=archive([],snapshot)
        capture_pregame(tracker,snapshot)
        self.assertNotIn("latest_pregame",tracker[0])
        rows[0]["line"]=-5
        snapshot["updated"]="2026-11-26T23:00:00Z"
        capture_pregame(tracker,snapshot)
        self.assertEqual(tracker[0]["line"],-3)
        self.assertEqual(tracker[0]["latest_pregame"]["line"],-5)
        rows[0]["line"]=-8
        snapshot["updated"]="2026-11-27T00:00:00Z"
        capture_pregame(tracker,snapshot)
        self.assertEqual(tracker[0]["latest_pregame"]["line"],-5)
        tracker[0]["result"]="loss"
        m=line_movement(tracker)[0]
        self.assertEqual(m["avg_points"],2)
        self.assertIsNone(m["avg_price_pp"])
        self.assertEqual(m["positive_rate"],1)
        self.assertEqual(m["avg_minutes_before_start"],60)

    def test_moneyline_price_movement(self):
        row=dict(sport="NHL",market="h2h",book="draftkings",odds=120,result="win",
                 start="2026-11-27T00:00:00Z",latest_pregame=dict(captured="2026-11-26T23:00:00Z",odds=100,line=None))
        m=line_movement([row])[0]
        self.assertAlmostEqual(m["avg_price_pp"],100*(.5-100/220))
        self.assertEqual(m["positive_rate"],1)
        self.assertEqual(line_movement([dict(row,result="pending")])[0]["observed"],0)
