import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from team_markets import implied, normalize

class TeamMarketsTest(unittest.TestCase):
    def test_implied(self):
        self.assertAlmostEqual(implied(-110), 110/210)
        self.assertAlmostEqual(implied(150), .4)

    def test_normalize(self):
        event = dict(id="1", home_team="A", away_team="B", commence_time="2027-01-01T00:00:00Z", bookmakers=[
            dict(key="fanduel", markets=[
                dict(key="spreads", outcomes=[dict(name="A",price=-110,point=-2.5),dict(name="B",price=-110,point=2.5)]),
                dict(key="h2h", outcomes=[dict(name="A",price=-150),dict(name="B",price=130)])])])
        rows = normalize([event])
        self.assertEqual(len(rows),4)
        self.assertEqual(rows[0]["market_probability"], .5)
        self.assertEqual(rows[0]["line"], -2.5)
        self.assertAlmostEqual(sum(r["market_probability"] for r in rows[2:]),1)
        event["bookmakers"][0]["markets"][0]["outcomes"][1]["point"]=3
        self.assertEqual(len(normalize([event])),2)
