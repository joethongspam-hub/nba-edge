"""Regression tests for no-odds-call settlement and projection diagnostics."""
import copy
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from performance_diagnostics import (
    inspect_settlements, projection_replay, frozen_projection_accuracy
)
from analysis_export import build


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.pick = {
            "id": "test", "player": "Test Player", "slate": "2026-11-20",
            "market": "player_points_rebounds_assists", "side": "Over",
            "line": 29.5, "result": "win", "actual": 36,
            "startsAt": "2026-11-21T01:00:00Z",
            "event": "LA Clippers @ San Antonio Spurs",
            "probability": .7, "odds": -110, "grade": "C",
        }
        self.game = {
            "player": "Test Player", "gameId": "espn-100", "playerId": "99",
            "event": "Los Angeles Clippers @ San Antonio Spurs",
            "startsAt": "2026-11-21T00:50:00Z",
            "date": "2026-11-20", "minutes": 34,
            "player_points": 21, "player_rebounds": 8, "player_assists": 7,
        }

    def test_legacy_is_corroborated_not_promoted(self):
        original = copy.deepcopy(self.pick)
        audit = inspect_settlements([self.pick], [self.game])
        self.assertEqual(audit["statusCounts"]["legacy_corroborated"], 1)
        self.assertEqual(audit["issuesForManualReview"], 0)
        self.assertEqual(self.pick, original)

    def test_legacy_mismatch_is_reported_without_overwriting(self):
        altered = {**self.pick, "actual": 30}
        audit = inspect_settlements([altered], [self.game])
        self.assertEqual(audit["statusCounts"]["actual_mismatch"], 1)
        self.assertEqual(altered["actual"], 30)

    def test_missing_log_is_not_assumed_verified(self):
        audit = inspect_settlements([self.pick], [])
        self.assertEqual(audit["statusCounts"]["missing_matching_log"], 1)
        self.assertEqual(audit["issuesForManualReview"], 1)

    def test_frozen_projection_excludes_legacy_without_projection(self):
        self.assertEqual(frozen_projection_accuracy([self.pick])["overall"]["n"], 0)
        with_projection = {**self.pick, "projection": 31}
        result = frozen_projection_accuracy([with_projection])
        self.assertEqual(result["overall"]["n"], 1)
        self.assertEqual(result["overall"]["MAE"], 5)
        self.assertEqual(result["overall"]["meanSignedError"], -5)

    def test_projection_replay_uses_prior_games_only(self):
        start = date(2026, 10, 1)
        previous = [
            {"player": "Test Player", "date": (start + timedelta(days=i)).isoformat(),
             "gameId": f"old-{i}", "minutes": 30,
             "player_points": 20, "player_rebounds": 5, "player_assists": 5}
            for i in range(20)
        ]
        early = projection_replay([self.pick], previous)
        changed = projection_replay([self.pick], previous + [
            {**self.game, "date": "2026-11-20"},
            {**self.game, "date": "2026-11-21", "player_points": 500},
        ])
        self.assertEqual(early, changed)
        self.assertEqual(early["sample"], 1)
        self.assertAlmostEqual(early["rows"][0]["shadowProjection"], 30, delta=0.2)

    def test_report_groups_side_market_grade_and_slate(self):
        p2 = {**self.pick, "id": "other", "result": "loss",
              "side": "Under", "market": "player_assists"}
        report = build({"ranked": []}, {"picks": [self.pick, p2]},
                       "2026-11-21T00:00:00Z", logs=[self.game])
        cal = report["calibration"]
        self.assertEqual(cal["bySide"]["Over"]["wins"], 1)
        self.assertEqual(cal["byMarketAndSide"]["player_assists"]["Under"]["losses"], 1)
        self.assertEqual(cal["byGrade"]["C"]["graded"], 2)
        self.assertEqual(cal["bySlate"]["2026-11-20"]["graded"], 2)
        self.assertFalse(report["walkForwardBacktest"]["productionCalibrationEnabled"])
        self.assertEqual(report["schemaVersion"], 3)


if __name__ == "__main__":
    unittest.main()
