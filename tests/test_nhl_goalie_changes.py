import sys
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone, timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from nhl_goalie_changes import update

class ChangesTests(unittest.TestCase):
    def test_replacement_and_confirmation(self):
        now=datetime(2026,11,27,17,tzinfo=timezone.utc)
        row={"home":"H","away":"A","team":"H","market":"h2h",
             "start":(now+timedelta(hours=2)).isoformat(),
             "goalie_home":{"name":"One","status":"projected"},
             "goalie_away":{"name":"Two","status":"confirmed"},
             "goalie_probability_delta":.01}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"changes.json"
            self.assertEqual(update([row,row],now,path)["changes"],0)
            new=dict(row,goalie_home={"name":"Three","status":"projected"},
                     goalie_probability_delta=.04)
            self.assertEqual(update([new],now+timedelta(minutes=5),path)["alerts"],1)
            self.assertEqual(update([new],now+timedelta(minutes=6),path)["changes"],0)
            confirmed=dict(new,goalie_home={"name":"Three","status":"confirmed"})
            self.assertEqual(update([confirmed],now+timedelta(minutes=7),path)["changes"],1)
            self.assertEqual(update([dict(confirmed,goalie_home={})],now+timedelta(minutes=8),path)["changes"],0)
