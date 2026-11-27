import sys
import unittest
from pathlib import Path
from datetime import datetime,timezone,date
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from team_history import parse_events,week

class TeamHistoryTest(unittest.TestCase):
    def test_parse(self):
        now=datetime(2026,11,27,tzinfo=timezone.utc)
        event=dict(id="1",date="2026-11-25T00:00:00Z",season={"type":"2"},status={"type":{"completed":True}},competitions=[{"competitors":[{"homeAway":"home","team":{"displayName":"LA Clippers"},"score":"110"},{"homeAway":"away","team":{"displayName":"Boston Celtics"},"score":"100"}]}])
        self.assertEqual(parse_events([event,event],now,"NBA")[0][1:4],("Los Angeles Clippers","Boston Celtics",10))
        self.assertEqual(len(parse_events([event,event],now,"NBA")),1)
        self.assertEqual(parse_events([dict(event,date="2026-11-28T00:00:00Z")],now,"NBA"),[])
        self.assertEqual(parse_events([dict(event,competitions=[])],now,"NBA"),[])
    def test_range_fallback(self):
        with patch("team_history.board",side_effect=[ValueError("range")]+[[]]*7) as mock:
            self.assertEqual(week("https://example.com",date(2026,11,26)),[])
            self.assertEqual(mock.call_count,8)
