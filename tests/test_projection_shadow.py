"""Prospective projection-gap paper experiment, wholly offline."""
import copy
import sys
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from projection_shadow import select,freeze,settle,report,update_file
from update import rank
from analysis_export import build

NOW=datetime(2026,11,22,18,tzinfo=timezone.utc)
START="2026-11-23T00:00:00Z"

def candidate(player,gap,evidence=50,side="Over",odds=-110,market="player_points"):
    return {"player":player,"market":market,"side":side,"line":20.5,
            "projection":20.5+(gap*3 if side=="Over" else -gap*3),
            "projectionGap":gap*3,"normalizedGap":gap,
            "paperRankingScore":gap*(0.5+evidence/200),
            "evidenceScore":evidence,"sample":20,"volatility":3,
            "paperEvidenceLabel":"moderate","book":"FanDuel","odds":odds,
            "event":"Away Team @ Home Team","startsAt":START}

class ProjectionShadowTests(unittest.TestCase):
    def test_sort_is_not_driven_by_ev_or_book_odds(self):
        a={**candidate("Strong",1.4,50),"ev":-.5}
        b={**candidate("Weak",.85,50),"ev":99}
        self.assertEqual(select([a,b],NOW)[0]["player"],"Strong")
        self.assertEqual(select([{**a,"odds":-2000},{**b,"odds":+800}],NOW)[0]["player"],"Strong")

    def test_one_prop_per_player_and_at_most_ten(self):
        pool=[candidate("Same",1.2),candidate("Same",1.1,market="player_assists")]
        pool += [candidate(f"Other{i}",1+i/100) for i in range(20)]
        self.assertEqual(len(select(pool,NOW)),10)
        self.assertEqual(len([p for p in select(pool,NOW) if p["player"]=="Same"]),1)

    def test_no_post_start_freeze_no_hindsight(self):
        state={}
        old={**candidate("Past",3),"startsAt":"2026-11-22T01:00:00Z"}
        self.assertFalse(freeze(state,[old],NOW,"2026-11-22"))
        self.assertEqual(state["slates"],{})

    def test_pregame_snapshot_immutable_even_if_prices_change(self):
        state={}
        original=candidate("A",1.3,55)
        self.assertTrue(freeze(state,[original],NOW,"2026-11-22"))
        frozen=copy.deepcopy(state)
        self.assertFalse(freeze(state,[{**original,"odds":-500,"projection":100}],NOW,"2026-11-22"))
        self.assertEqual(state,frozen)

    def test_verified_match_is_required_to_grade(self):
        state={}
        freeze(state,[candidate("A",1.3)],NOW,"2026-11-22")
        later=NOW+timedelta(days=1)
        mismatched={"player":"A","player_points":35,"gameId":"wrong",
                    "startsAt":START,"event":"Other @ Teams"}
        self.assertEqual(settle(state,[mismatched],later),0)
        valid={**mismatched,"gameId":"verified","event":"Away Team @ Home Team"}
        self.assertEqual(settle(state,[valid],later),1)
        self.assertEqual(settle(state,[valid],later),0)
        self.assertEqual(report(state)["results"]["wins"],1)

    def test_tracker_and_analysis_integration_without_network(self):
        state={}
        freeze(state,[candidate("A",1.0)],NOW,"2026-11-22")
        exported=build({"ranked":[]},{"picks":[]},NOW.isoformat(),logs=[],projection_shadow_state=state)
        self.assertFalse(exported["projectionShadow"]["productionChanges"])
        self.assertEqual(exported["projectionShadow"]["results"]["pending"],1)

    def test_live_rank_unchanged_when_paper_collector_enabled(self):
        now=datetime.now(timezone.utc)
        logs=[{"player":"Example","date":(now-timedelta(days=i+1)).date().isoformat(),
               "minutes":32,"player_points":25+(i%3)} for i in range(40)]
        p={"player":"Example","market":"player_points","side":"Over","line":20.5,
           "book":"FanDuel","odds":-110,"event":"Away @ Home",
           "startsAt":(now+timedelta(days=1)).isoformat()}
        before=rank([p],logs)
        rows=[]
        after=rank([p],logs,paper_candidates=rows)
        self.assertEqual(before,after)
        self.assertGreaterEqual(len(rows),len(after))

    def test_file_updates_preserve_frozen_paper_record(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"paper.json"
            update_file(path,[candidate("A",1.2)],[],NOW,"2026-11-22")
            first=path.read_text()
            update_file(path,[candidate("B",4.0)],[],NOW,"2026-11-22")
            self.assertEqual(path.read_text(),first)

if __name__=="__main__":
    unittest.main()
