"""Prospective ranking experiment tests (entirely offline, no real wagers)."""
import copy
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from ranking_experiment import select, freeze, settle, report, update_file, risk_score
from analysis_export import build


NOW=datetime(2026,11,22,18,0,tzinfo=timezone.utc)
START="2026-11-23T00:00:00Z"


def candidate(player,ev,evidence,market="player_points",line=20.5):
    return {"player":player,"market":market,"side":"Over","line":line,
            "book":"FanDuel","odds":-110,"event":"Away Team @ Home Team",
            "startsAt":START,"probability":.61,"ev":ev,"edge":.08,
            "grade":"B" if evidence>=75 else "D","evidenceScore":evidence}


class RankingExperimentTests(unittest.TestCase):
    def test_risk_model_can_select_different_top_pick(self):
        rows=[candidate("Risky",.25,48),candidate("Stable",.15,90)]
        self.assertEqual(select(rows,NOW,"ev")[0]["player"],"Risky")
        self.assertEqual(select(rows,NOW,"risk")[0]["player"],"Stable")
        self.assertGreater(risk_score(rows[1]),risk_score(rows[0]))

    def test_one_player_per_game_for_both_methods(self):
        rows=[candidate("Same",.4,80),candidate("Same",.3,90,market="player_assists")]
        self.assertEqual(len(select(rows,NOW,"ev")),1)
        self.assertEqual(len(select(rows,NOW,"risk")),1)

    def test_all_started_games_are_excluded(self):
        old={**candidate("Old",.5,90),"startsAt":"2026-11-21T00:00:00Z"}
        self.assertEqual(select([old],NOW,"ev"),[])
        self.assertFalse(freeze({},[old],NOW,"2026-11-22"))

    def test_freeze_is_idempotent_after_odds_move(self):
        state={}
        rows=[candidate("Risky",.25,48),candidate("Stable",.15,90)]
        self.assertTrue(freeze(state,rows,NOW,"2026-11-22"))
        original=copy.deepcopy(state)
        new=[{**p,"odds":-300,"ev":.01} for p in rows]
        self.assertFalse(freeze(state,new,NOW+timedelta(minutes=30),"2026-11-22"))
        self.assertEqual(state,original)
        self.assertEqual(state["slates"]["2026-11-22"]["ev"][0].split("|")[0],"Risky")

    def test_no_leaked_outcomes_until_unique_matched_game(self):
        state={}
        freeze(state,[candidate("Stable",.15,90)],NOW,"2026-11-22")
        after=NOW+timedelta(days=1)
        self.assertEqual(settle(state,[{"player":"Stable","player_points":30,
                                         "gameId":"abc","event":"Other @ Teams",
                                         "startsAt":START}],after),0)
        key=state["slates"]["2026-11-22"]["ev"][0]
        self.assertEqual(state["slates"]["2026-11-22"]["picks"][key]["result"],"pending")
        good={"player":"Stable","player_points":30,"gameId":"espn-id",
              "playerId":"456","event":"Away Team @ Home Team",
              "startsAt":"2026-11-23T00:05:00Z"}
        self.assertEqual(settle(state,[good],after),1)
        self.assertEqual(settle(state,[good],after),0)
        self.assertEqual(state["slates"]["2026-11-22"]["picks"][key]["result"],"win")

    def test_overlap_not_double_counted_within_strategy(self):
        state={}
        freeze(state,[candidate("Solo",.1,75)],NOW,"2026-11-22")
        out=report(state)
        self.assertEqual(out["slatesCompared"],1)
        self.assertEqual(out["overlappingSelections"],1)
        self.assertEqual(out["results"]["ev"]["selections"],1)
        self.assertEqual(out["results"]["risk"]["selections"],1)
        self.assertFalse(out["sufficientForReview"])

    def test_file_update_uses_no_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/"experiment.json"
            update_file(file,[candidate("One",.22,75)],[],NOW,"2026-11-22")
            baseline=file.read_text()
            update_file(file,[candidate("One",.99,30)],[],NOW,"2026-11-22")
            # Updates do not change frozen odds or rankings.
            self.assertEqual(baseline,file.read_text())

    def test_analysis_report_contains_distinct_paper_cohorts(self):
        state={}
        freeze(state,[candidate("One",.22,75)],NOW,"2026-11-22")
        analysis=build({"ranked":[]},{"picks":[]},NOW.isoformat(),logs=[],
                       ranking_state=state)
        self.assertFalse(analysis["rankingExperiment"]["productionChanges"])
        self.assertEqual(analysis["rankingExperiment"]["results"]["ev"]["selections"],1)


if __name__=="__main__":
    unittest.main()
