import sys
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone, timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from nhl_goalie_validation import update

NOW=datetime(2026,11,27,17,tzinfo=timezone.utc)
def goalie(name,value):
    return {"name":name,"status":"confirmed","rating":{"rating_eligible":True,"relative_gsax60":value}}

class ValidationTests(unittest.TestCase):
    def test_record_and_settle(self):
        start=NOW+timedelta(hours=1)
        games=[(NOW-timedelta(days=i+1),"Home","Away",4,2,False) for i in range(10)]
        row={"home":"Home","away":"Away","team":"Home","market":"h2h",
             "start":start.isoformat(),"goalie_home":goalie("A",.4),
             "goalie_away":goalie("B",-.4)}
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"audit.json"
            first=update([row,row],games,NOW,path)
            self.assertEqual(first["recorded"],1)
            self.assertEqual(first["settled"],0)
            second=update([],games+[(start,"Home","Away",4,2,False)],
                          start+timedelta(hours=4),path)
            self.assertEqual(second["settled"],1)
            self.assertEqual(second["all"]["0.0"]["games"],1)
            self.assertLess(second["all"]["1.0"]["brier"],second["all"]["0.0"]["brier"])
