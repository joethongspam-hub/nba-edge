"""Regression tests: selection funnel never changes picks or makes odds calls."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from update import rank, build_snapshot


def records(name,values,days_ago=1,minutes=34):
    now=datetime.now(timezone.utc)
    return [{"player":name,"date":(now-timedelta(days=days_ago+i)).date().isoformat(),
             "minutes":minutes,"player_points":v} for i,v in enumerate(values)]


def prop(name,side="Over",line=20.5):
    return {"player":name,"side":side,"line":line,"market":"player_points",
            "odds":-110,"book":"FanDuel","event":"Away @ Home",
            "startsAt":(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()}


class ProjectionFunnelTests(unittest.TestCase):
    def test_diagnostics_leave_selection_untouched(self):
        logs=records("Strong",[28+(i%3) for i in range(40)])
        props=[prop("Strong",line=20.5),prop("Strong",side="Under",line=20.5)]
        without=rank(props,logs)
        diag={}
        with_diagnostics=rank(props,logs,diagnostics=diag)
        self.assertEqual(with_diagnostics,without)
        self.assertEqual(diag["totalProps"],2)
        self.assertEqual(diag["stages"]["qualified"],1)
        self.assertEqual(diag["stages"]["wrong_direction"],1)
        self.assertEqual(diag["selectedTop10"],1)
        self.assertEqual(sum(diag["stages"].values()),2)

    def test_first_failure_priority(self):
        games=(records("Missing",[25]*10)+
               records("Few",[26]*17)+
               records("Stale",[28]*40,days_ago=160)+
               records("Good",[28+i%3 for i in range(40)]))
        props=[prop(name,line=20.5) for name in ("Missing","Few","Stale","Good")]
        diag={}
        picks,candidates=rank(props,games,return_candidates=True,diagnostics=diag)
        self.assertEqual(diag["stages"]["insufficient_history"],1)
        self.assertEqual(diag["stages"]["under_20_games"],1)
        self.assertEqual(diag["stages"]["stale_history"],1)
        self.assertEqual(diag["stages"]["qualified"],1)
        self.assertEqual(diag["selectedTop10"],len(picks))
        self.assertEqual(diag["eligibleBeforePlayerDedup"],1)
        self.assertEqual(sum(diag["stages"].values()),len(props))
        self.assertEqual(len(candidates),3)

    def test_low_evidence_and_gap_filters(self):
        games=records("LowEvidence",[20+(i%10)*4 for i in range(20)],minutes=12)
        games+=records("Wrong",[29+i%3 for i in range(40)])
        games+=records("Small",[21+i%3 for i in range(40)])
        props=[prop("LowEvidence",line=10.5),
               prop("Wrong",side="Under",line=20.5),
               prop("Small",line=21.7)]
        diag={}
        rank(props,games,diagnostics=diag)
        self.assertEqual(diag["stages"]["low_evidence"],1)
        self.assertEqual(diag["stages"]["wrong_direction"],1)
        self.assertEqual(diag["stages"]["small_raw_gap"],1)

    def test_snapshot_and_market_counts(self):
        diag={}
        rank([prop("NoPlayer")],[],diagnostics=diag)
        self.assertEqual(diag["byMarket"]["player_points"]["totalProps"],1)
        self.assertEqual(sum(v for k,v in diag["byMarket"]["player_points"].items()
                             if k!="totalProps"),1)
        now=datetime.now(timezone.utc)
        cache={"eventsChecked":0,"props":[prop("NoPlayer")],
               "fetchedAt":now.isoformat(),"oddsCreditsUsed":0,
               "oddsCreditsRemaining":"2500"}
        snapshot=build_snapshot(now,now.date().isoformat(),cache,[],[],{},
                                "recomputed_from_cache",diag)
        self.assertEqual(snapshot["selectionDiagnostics"],diag)
        self.assertEqual(snapshot["oddsCreditsUsed"],0)


if __name__=="__main__":
    unittest.main()
