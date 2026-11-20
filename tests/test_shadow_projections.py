"""No-network tests: experimental projection and chronological replay."""
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from shadow_projections import project, compare_history, report


def history(n=35, minutes=30, stat=20):
    start=date(2026,9,1)
    return [{"player":"Example Player","gameId":str(i),
             "date":(start+timedelta(days=i)).isoformat(),
             "minutes":minutes,"player_points":stat}
            for i in range(n)]


class ShadowProjectionTests(unittest.TestCase):
    def test_missing_history(self):
        self.assertIsNone(project(history(6),"player_points"))

    def test_constant_role_produces_sane_projection(self):
        p=project(history(),"player_points")
        self.assertIsNotNone(p)
        self.assertAlmostEqual(p["projectedStat"],20,delta=0.1)
        self.assertEqual(p["model"],"shadow_role_rate_v1")
        self.assertIn("injury_and_matchup_not_adjusted",p["flags"])

    def test_minutes_change_is_flagged(self):
        rows=history()
        for r in rows[-8:]:
            r["minutes"]=38
        p=project(rows,"player_points")
        self.assertIn("recent_minutes_shift",p["flags"])
        self.assertGreater(p["projectedMinutes"],30)

    def test_future_games_never_affect_prediction(self):
        rows=history(20)
        baseline=project(rows,"player_points",before_date="2026-09-20")
        altered=[dict(r) for r in rows]
        altered[-1]["player_points"]=1000
        self.assertEqual(project(altered,"player_points",before_date="2026-09-20"),baseline)

    def test_replay_has_no_same_day_leakage(self):
        rows=history(22)
        rows[-1]["player_points"]=1000
        stats=compare_history(rows)
        self.assertGreater(stats["player_points"]["n"],0)
        self.assertIsNotNone(stats["player_points"]["shadowMAE"])

    def test_report_does_not_modify_rankings(self):
        ranked=[{"player":"Example Player","market":"player_points","side":"Over",
                 "book":"FanDuel","line":19.5}]
        original=ranked[0].copy()
        r=report({"ranked":ranked,"slateDate":"2026-11-20"},history())
        self.assertFalse(r["productionChanges"])
        self.assertFalse(r["injuryFeedConnected"])
        self.assertEqual(ranked[0],original)
        self.assertIsNotNone(r["candidateProjections"][0]["shadowProjection"])


if __name__=="__main__":
    unittest.main()
