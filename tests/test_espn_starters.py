import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import espn_starters as p

NOW = datetime(2026,11,27,17,tzinfo=timezone.utc)
START = "2026-11-27T18:00Z"

def fixture():
    row = {"home":"Boston Bruins","away":"Toronto Maple Leafs","start":START}
    teams = []
    for side,name,tid,goalie,status in [
        ("home","Boston Bruins","1","Jeremy Swayman","confirmed"),
        ("away","Toronto Maple Leafs","21","Anthony Stolarz","expected")]:
        teams.append({"homeAway":side,"team":{"displayName":name,"id":tid},
                      "probables":[{"name":"probableStartingGoalie",
                        "athlete":{"id":"123","fullName":goalie,"position":"G","team":{"id":tid}},
                        "status":{"type":status}}]})
    event = {"id":"1","date":START,"status":{"type":{"state":"pre"}},
             "competitions":[{"competitors":teams}]}
    return row,event

class ESPNTest(unittest.TestCase):
    def test_confirmed_and_projected(self):
        row,event = fixture()
        self.assertEqual(p.apply([row],[event],NOW),1)
        self.assertEqual(row["goalie_home"]["status"],"confirmed")
        self.assertEqual(row["goalie_away"]["status"],"projected")
        self.assertIsNone(row["goalie_home"]["reported_at"])
    def test_wrong_team(self):
        row,event = fixture()
        event["competitions"][0]["competitors"][0]["probables"][0]["athlete"]["team"]["id"]="9"
        p.apply([row],[event],NOW)
        self.assertEqual(row["goalie_home"]["status"],"unknown")
    def test_no_fallback_when_complete(self):
        row,event = fixture()
        with patch.object(p,"board",return_value=[event]), patch.object(p.propline_starters,"annotate",side_effect=AssertionError("fallback")):
            health=p.annotate([row,dict(row)],NOW)
        self.assertEqual(health["confirmed_goalies"],1)
        self.assertEqual(health["projected_goalies"],1)
    def test_in_progress_rejected(self):
        row,event = fixture()
        event["status"]["type"]["state"]="in"
        self.assertEqual(p.apply([row],[event],NOW),0)
