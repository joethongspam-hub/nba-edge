import unittest
from pathlib import Path
from html.parser import HTMLParser

class Parser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])

class TeamDashboardTest(unittest.TestCase):
    def test_targets(self):
        html=(Path(__file__).resolve().parents[1]/"docs/team-markets.html").read_text()
        p=Parser()
        p.feed(html)
        self.assertEqual(len(p.ids),len(set(p.ids)))
        for target in ("sport","market","book","sort","status","rows","matchCards","historyRows","auditRows","shadowAudit","nflShadowAudit","nhlShadowAudit"):
            self.assertIn(target,p.ids)
        for sport in ("NBA","NFL","NHL"):
            self.assertIn('data-sport="'+sport+'"',html)
        self.assertIn("team_tracker.json",html)
        self.assertIn("team_backtest.json",html)
