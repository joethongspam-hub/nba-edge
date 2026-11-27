import sys
import unittest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import propline_starters as p

NOW = datetime(2026, 11, 27, 17, tzinfo=timezone.utc)
STAMP = "2026-11-27T16:00:00Z"

def fixture():
    rows = [{"home":"Boston Bruins","away":"Toronto Maple Leafs",
             "start":"2026-11-27T23:00:00Z"}]
    teams = []
    for home, name, goalie in [(True,"Boston Bruins","Jeremy Swayman"),
                               (False,"Toronto Maple Leafs","Anthony Stolarz")]:
        teams.append({"home":home,"team":name,"status":"confirmed","updated_at":STAMP,
                      "players":[{"player_name":goalie,"position":"G","role":"starter",
                                  "status":"confirmed","since":STAMP},
                                 {"player_name":"Backup Goalie","position":"G","role":"active",
                                  "status":"confirmed","since":STAMP}]})
    return rows, {"games":[{"game_date":"2026-11-27","teams":teams}]}

class PropLineTest(unittest.TestCase):
    def test_confirmed(self):
        rows, payload = fixture()
        health = p.apply(rows,payload,NOW)
        self.assertEqual(health["matched_games"],1)
        self.assertEqual(health["confirmed_goalies"],2)
        self.assertEqual(rows[0]["goalie_home"]["name"],"Jeremy Swayman")
    def test_expected_and_duplicate(self):
        rows, payload = fixture()
        payload["games"][0]["teams"][0]["players"][0]["status"]="expected"
        self.assertEqual(p.apply(rows,payload,NOW)["confirmed_goalies"],1)
        payload["games"] *= 2
        self.assertEqual(p.apply(rows,payload,NOW)["matched_games"],0)
        self.assertEqual(rows[0]["goalie_home"]["status"],"unknown")
    def test_missing_secret(self):
        rows, _ = fixture()
        with patch.dict("os.environ",{"PROPLINE_API_KEY":""}):
            with patch.object(p,"urlopen",side_effect=AssertionError("network")):
                self.assertEqual(p.annotate(rows,NOW)["error"],"missing_secret")
