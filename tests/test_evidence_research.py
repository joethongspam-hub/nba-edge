"""Offline checks for evidence scoring sensitivity, no sportsbook requests."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import update
from evidence_research import analyze, components
from analysis_export import build


def logs(name,values,minutes=34,days_ago=1):
    now=datetime.now(timezone.utc)
    return [{"player":name,"date":(now-timedelta(days=days_ago+i)).date().isoformat(),
             "minutes":minutes if isinstance(minutes,(float,int)) else minutes[i],
             "player_points":v} for i,v in enumerate(values)]


def prop(name,side="Over",line=20.5):
    return {"player":name,"market":"player_points","side":side,"line":line,
            "odds":-110,"book":"FanDuel","event":"Away Team @ Home Team",
            "startsAt":(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()}


class EvidenceSensitivityTests(unittest.TestCase):
    def setUp(self):
        self.player_logs=(
            logs("Solid",[28+(i%3) for i in range(40)])+
            logs("Inconsistent",[27+i%3 for i in range(40)],
                 minutes=[34 if i%2 else 18 for i in range(40)])+
            logs("Short",[27+i%3 for i in range(17)])+
            logs("Missing",[25]*10)+
            logs("Stale",[26+i%3 for i in range(40)],days_ago=160)
        )
        self.props=[
            prop("Solid"),prop("Solid",side="Under"),
            prop("Inconsistent"),prop("Short"),prop("Missing"),prop("Stale")
        ]

    def test_current_what_if_matches_unmodified_live_screen(self):
        diagnostic={}
        live=update.rank(self.props,self.player_logs,diagnostics=diagnostic)
        result=analyze(self.props,self.player_logs,update.ranking_probability)
        current=result["scenarios"]["current"]
        self.assertEqual(current["eligibleProps"],diagnostic["stages"]["qualified"])
        self.assertEqual(current["top10Count"],len(live))
        self.assertEqual(current["uniquePlayerDates"],diagnostic["distinctEligiblePlayers"])
        self.assertFalse(result["productionChanges"])
        self.assertEqual(result["extraOddsApiCalls"],0)

    def test_scenarios_are_monotone_in_lower_cutoff(self):
        result=analyze(self.props,self.player_logs,update.ranking_probability)
        x=result["scenarios"]
        values=[x[k]["eligibleProps"] for k in
                ("current","evidence_55","evidence_50","evidence_45")]
        self.assertEqual(values,sorted(values))
        self.assertGreaterEqual(x["minutes_cv_050"]["eligibleProps"],x["current"]["eligibleProps"])
        self.assertGreaterEqual(x["games_15_evidence_55"]["eligibleProps"],x["evidence_55"]["eligibleProps"])

    def test_component_formula_reproduces_production_pure_evidence(self):
        scored=update.ranking_probability(prop("Solid"),self.player_logs[:40])
        c=components(scored)
        sample=min(35,scored["sample"]/40*35)
        minutes=min(20,scored["recentMinutes"]/32*20)
        stability=max(0,20*(1-min(1,scored["minutesCv"]/.35)))
        variation=max(0,15*(1-min(1,scored["volatility"]/
                                    max(2,abs(scored["projection"])))))
        age=min(25,scored["oldGames"]*1.5)
        expected=max(0,min(100,round(sample+minutes+stability+variation-age)))
        self.assertEqual(c["evidence"],expected)

    def test_score_distribution_and_components_consistent(self):
        r=analyze(self.props,self.player_logs,update.ranking_probability)
        self.assertEqual(sum(b["count"] for b in r["evidenceDistribution"]),
                         r["with20GamesAndFreshness"])
        self.assertEqual(sum(b["strongGapCount"] for b in r["evidenceDistribution"]),
                         r["strongGapRegardlessOfEvidence"])
        self.assertLessEqual(r["strongGapRegardlessOfEvidence"],
                             r["with20GamesAndFreshness"])
        self.assertIn("minutesStability",r["scoreComponents"])

    def test_research_uses_only_injected_scorer_not_remote_requests(self):
        with patch.object(update,"request",side_effect=AssertionError("Unexpected request")):
            with patch.object(update,"odds",side_effect=AssertionError("Unexpected odds API")):
                report=analyze(self.props,self.player_logs,update.ranking_probability)
        self.assertEqual(report["totalProps"],len(self.props))

    def test_snapshot_and_analysis_export_have_study(self):
        now=datetime.now(timezone.utc)
        research=analyze(self.props,self.player_logs,update.ranking_probability)
        cache={"eventsChecked":0,"props":self.props,"fetchedAt":now.isoformat(),
               "oddsCreditsUsed":0,"oddsCreditsRemaining":"3000"}
        snap=update.build_snapshot(now,now.date().isoformat(),cache,[],[],{},
                                   "recomputed_from_cache",{},research)
        self.assertEqual(snap["evidenceResearch"],research)
        self.assertEqual(snap["oddsCreditsUsed"],0)
        exported=build(snap,{"picks":[]},now.isoformat(),logs=[])
        self.assertEqual(exported["evidenceResearch"],research)


if __name__=="__main__":
    unittest.main()
