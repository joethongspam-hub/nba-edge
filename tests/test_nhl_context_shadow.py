import sys
import unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from nhl_context_shadow import annotate,audit

class NHLContextTest(unittest.TestCase):
    def test_rest_and_future_exclusion(self):
        now=datetime(2026,11,26,tzinfo=timezone.utc)
        games=[(now-timedelta(days=i+2),"A","B",4,2,False) for i in range(12)]
        games.append((now-timedelta(hours=12),"B","C",3,2,False))
        row=dict(start=(now+timedelta(hours=6)).isoformat(),home="A",away="B",team="A",market="h2h",line=None)
        a=annotate([dict(row)],games,now)[0]
        b=annotate([dict(row)],games+[(now,"A","B",0,20,False)],now)[0]
        self.assertEqual(a,b)
        self.assertGreater(a["shadow_rest_adjustment"],0)
        self.assertEqual(a["shadow_push_probability"],0)
        spread=annotate([dict(row,market="spreads",line=-1.5)],games,now)[0]
        self.assertLess(spread["shadow_probability"],a["shadow_probability"])
    def test_audit_and_missing(self):
        now=datetime(2026,11,26,tzinfo=timezone.utc)
        games=[(now-timedelta(days=i+1),"A","B",4,2,False) for i in range(12)]
        self.assertEqual(audit(games)["games"],4)
        row=dict(start=now.isoformat(),home="A",away="C",team="A",market="h2h",line=None)
        annotate([row],games,now)
        self.assertNotIn("shadow_probability",row)
