import sys
import unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from nba_context_shadow import annotate,audit

class ContextShadowTest(unittest.TestCase):
    def test_future_exclusion_and_audit(self):
        now=datetime(2026,11,26,tzinfo=timezone.utc)
        games=[(now-timedelta(days=i+1),"A","B",10,False) for i in range(14)]
        row=dict(start=(now+timedelta(hours=12)).isoformat(),home="A",away="B",team="A",market="h2h",line=None)
        a=annotate([dict(row)],games,now)[0]
        b=annotate([dict(row)],games+[(now,"A","B",-100,False)],now)[0]
        self.assertEqual(a,b)
        self.assertGreater(a["shadow_probability"],.5)
        self.assertEqual(audit(games)["games"],6)
    def test_missing(self):
        row=dict(start="2026-11-27T00:00:00Z",home="A",away="B",team="A",market="h2h",line=None)
        annotate([row],[],datetime(2026,11,26,tzinfo=timezone.utc))
        self.assertNotIn("shadow_probability",row)
