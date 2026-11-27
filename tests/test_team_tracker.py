import sys
import unittest
from pathlib import Path
from datetime import datetime, timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from team_tracker import archive, settle, summarize

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
