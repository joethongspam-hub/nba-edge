import sys
import unittest
from pathlib import Path
from datetime import datetime, timezone
from tempfile import TemporaryDirectory
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from balanced_selection import select, update_file

class BalancedTests(unittest.TestCase):
    def test_filters_and_freeze(self):
        now=datetime(2026,11,25,20,tzinfo=timezone.utc)
        def row(name,e=50,g=.60,start='2026-11-26T01:00:00Z'):
            return dict(player=name,market='player_points',book='FanDuel',side='Over',
                        line=10.5,odds=-110,startsAt=start,evidenceScore=e,
                        exactNormalizedGap=g,rankingScore=g*(e/100)**2)
        rows=[row('A'),row('A',55),row('B',49),row('C',60,.59),row('D',60,.8,'2026-11-25T19:00:00Z'),row('E')]
        self.assertEqual([p['player'] for p in select(rows,now)],['A','E'])
        self.assertEqual([p['player'] for p in select(rows,now,excluded=[row('A')])],['E'])
        with TemporaryDirectory() as d:
            path=Path(d)/'paper.json'
            watch,reports=update_file(path,rows,[],[],now,'2026-11-25')
            self.assertEqual(reports['watchlist']['pending'],2)
            watch,reports=update_file(path,[row('Z')],[],[],now,'2026-11-25')
            self.assertEqual(reports['watchlist']['pending'],2)
            self.assertEqual(watch[0]['player'],'Z')
