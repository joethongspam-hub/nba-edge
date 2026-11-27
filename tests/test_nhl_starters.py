import sys
import unittest
from pathlib import Path
from datetime import datetime, timezone
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from nhl_starters import parse

NOW = datetime(2026, 11, 27, 17, tzinfo=timezone.utc)
HTML = """<div>Toronto Maple Leafs at Boston Bruins</div>
<div>2026-11-27T18:00:00Z</div>
<div>Anthony Stolarz</div><div>Confirmed</div><div>2026-11-27T16:00:00Z</div>
<div>Jeremy Swayman</div><div>Unconfirmed</div>"""

class StarterTests(unittest.TestCase):
    def test_pair(self):
        result = next(iter(parse(HTML, "source", NOW).values()))
        self.assertEqual(result["away"]["name"], "Anthony Stolarz")
        self.assertEqual(result["away"]["status"], "confirmed")
        self.assertEqual(result["home"]["status"], "projected")
    def test_future_confirmation(self):
        result = next(iter(parse(HTML.replace("T16:00:00Z", "T17:30:00Z"), "source", NOW).values()))
        self.assertEqual(result["away"]["status"], "unknown")
    def test_ambiguous(self):
        self.assertEqual(parse(HTML + "<div>Another Goalie</div><div>Projected</div>", "source", NOW), {})
    def test_started(self):
        self.assertEqual(parse(HTML.replace("T18:00:00Z", "T15:00:00Z"), "source", NOW), {})

    def test_split_heading_and_diagnostics(self):
        html = HTML.replace("Toronto Maple Leafs at Boston Bruins",
            "<span>Toronto Maple Leafs</span><span>at</span><span>Boston Bruins</span>")
        detail = {}
        results = parse(html, "source", NOW, detail)
        self.assertEqual(len(results), 1)
        self.assertEqual(detail["headings"], 1)
        self.assertEqual(detail["status_nodes"], 2)
