import sys
import unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from nfl_context_shadow import annotate,audit

class NFLContextTest(unittest.TestCase):
    def test_rest_and_future_exclusion(self):
        now=datetime(2026,11,26,tzinfo=timezone.utc)
        games=[(now-timedelta(days=7*i+7),"A","B",7,False) for i in range(8)]
        games.append((now-timedelta(days=1),"B","C",3,False))
        row=dict(start=(now+timedelta(days=1)).isoformat(),home="A",away="B",team="A",market="h2h",line=None)
        a=annotate([dict(row)],games,now)[0]
        b=annotate([dict(row)],games+[(now,"A","B",-99,False)],now)[0]
        self.assertEqual(a,b)
        self.assertGreater(a["shadow_rest_adjustment"],0)
        self.assertGreater(a["shadow_probability"],.5)
    def test_audit_and_missing(self):
        now=datetime(2026,11,26,tzinfo=timezone.utc)
        games=[(now-timedelta(days=7*i+7),"A","B",7,False) for i in range(8)]
        self.assertEqual(audit(games)["games"],3)
        row=dict(start=now.isoformat(),home="A",away="B",team="A",market="h2h",line=None)
        annotate([row],[],now)
        self.assertNotIn("shadow_probability",row)
