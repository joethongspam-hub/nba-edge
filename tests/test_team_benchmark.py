import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from team_benchmark import profit,record,benchmark
from team_tracker import archive

class BenchmarkTest(unittest.TestCase):
    def test_returns(self):
        self.assertAlmostEqual(profit("win",-110),100/110)
        self.assertEqual(profit("win",150),1.5)
        self.assertEqual(profit("push",-110),0)
        self.assertEqual(profit("loss",150),-1)
        self.assertIsNone(record([dict(result="pending",odds=100)])["roi"])
        self.assertAlmostEqual(record([dict(result="win",odds=150),dict(result="loss",odds=-110)])["roi"],.25)
    def test_reference_frozen_and_matched(self):
        base=dict(event_id="1",home="A",away="B",start="2026-11-27T00:00:00Z",book="fanduel",market="h2h",line=None)
        rows=[dict(base,team="A",odds=150,model_probability=.6,market_probability=.4),dict(base,team="B",odds=-150,model_probability=.4,market_probability=.6)]
        snapshot=dict(updated="2026-11-26T00:00:00Z",sports={"NBA":rows})
        tracker=archive([],snapshot)
        self.assertEqual(tracker[0]["market_reference"]["team"],"B")
        rows[1]["odds"]=-200
        archive(tracker,snapshot)
        self.assertEqual(tracker[0]["market_reference"]["odds"],-150)
        tracker[0].update(result="win",actual_margin=5)
        result=benchmark(tracker)[0]
        self.assertEqual(result["matched_model"]["units"],1.5)
        self.assertEqual(result["market_reference"]["units"],-1)
        legacy=dict(tracker[0])
        legacy.pop("market_reference")
        result=benchmark([legacy])[0]
        self.assertEqual(result["model"]["settled"],1)
        self.assertEqual(result["matched_model"]["settled"],0)
    def test_spread_push(self):
        row=dict(sport="NFL",market="spreads",book="draftkings",team="A",line=-3,odds=-110,result="push",actual_margin=3,model_probability=.55,market_reference=dict(team="B",line=3,odds=-110))
        result=benchmark([row])[0]
        self.assertEqual(result["market_reference"]["pushes"],1)
        self.assertEqual(result["market_reference"]["roi"],0)
