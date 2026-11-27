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

    def test_segments(self):
        base=dict(sport="NBA",market="h2h",book="fanduel",home="A",away="B",team="A",odds=150,model_probability=.62,market_probability=.4,archived_agreement="All agree")
        rows=[dict(base,result="win"),dict(base,result="pending"),dict(base,result="loss",team="B",odds=-150,market_probability=.6)]
        groups={(s["dimension"],s["label"]):s for s in benchmark(rows)[0]["segments"]}
        self.assertEqual(groups["Venue","Home"]["forecasts"],2)
        self.assertEqual(groups["Venue","Home"]["settled"],1)
        self.assertEqual(groups["Market side","Underdog"]["roi"],1.5)
        self.assertEqual(groups["Model minus no-vig market","10+ pp"]["settled"],1)
        self.assertEqual(groups["Challenger direction","All agree"]["settled"],2)

    def test_archive_challenger_direction(self):
        base=dict(event_id="1",home="A",away="B",start="2026-11-27T00:00:00Z",book="fanduel",market="h2h",line=None,odds=-110)
        a=dict(base,team="A",model_probability=.6,shadow_probability=.55,efficiency_probability=.4)
        b=dict(base,team="B",model_probability=.4,shadow_probability=.45,efficiency_probability=.6)
        snapshot=dict(updated="2026-11-26T00:00:00Z",sports={"NBA":[a,b]})
        tracked=archive([],snapshot)
        self.assertEqual(tracked[0]["archived_agreement"],"Mixed or tied")
        self.assertEqual(tracked[0]["archived_challenger_count"],2)
        a["efficiency_probability"]=.9
        archive(tracked,snapshot)
        self.assertEqual(tracked[0]["archived_agreement"],"Mixed or tied")
