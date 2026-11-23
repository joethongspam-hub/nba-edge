"""Static safety tests for the compact NBA EDGE dashboard.

No web/network access; verify critical live data bindings survive rearrangement.
"""
import unittest
from html.parser import HTMLParser
from pathlib import Path

PAGE=Path(__file__).resolve().parents[1]/"docs"/"index.html"

class DashboardParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids=[]
        self.details=0
        self.summaries=0
        self.panels=0
    def handle_starttag(self,tag,attrs):
        data=dict(attrs)
        if "id" in data:self.ids.append(data["id"])
        if tag=="details":self.details+=1
        if tag=="summary":self.summaries+=1
        if tag=="section" and "panel" in data.get("class","").split():self.panels+=1

class DashboardLayoutTests(unittest.TestCase):
    def test_all_original_sections_and_data_targets_remain(self):
        html=PAGE.read_text(encoding="utf-8")
        parser=DashboardParser()
        parser.feed(html)
        self.assertEqual(parser.panels,12)
        self.assertEqual(parser.details,4)
        self.assertEqual(parser.summaries,4)
        self.assertEqual(len(parser.ids),len(set(parser.ids)),"Duplicate element IDs")
        for target in ("rows","status","gapCountsRows","gapTestRows","record",
                       "units","roi","pending","shadowRows","filterRows",
                       "evidenceRows","walkForwardRows","auditRows","compareRows",
                       "contextRows","rankingRows","oddsBudget","search","market",
                       "side","book","refresh"):
            with self.subTest(target=target):
                self.assertIn(target,parser.ids)
        self.assertLess(html.index('id="daily-picks"'),
                        html.index('id="threshold-results"'))
        self.assertLess(html.index('id="threshold-results"'),
                        html.index('id="performance"'))
        self.assertLess(html.index('id="performance"'),
                        html.index('id="research"'))

if __name__=="__main__":
    unittest.main()
