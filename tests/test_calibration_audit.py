"""No-network chronological calibration audit tests."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
from calibration_audit import audit, examine, valid_record


def pick(day, outcome, probability=0.7, market="player_points", verified=True):
    date = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=day)
    return {
        "slate": date.date().isoformat(),
        "recordedAt": (date + timedelta(hours=12)).isoformat(),
        "startsAt": (date + timedelta(hours=20)).isoformat(),
        "probability": probability,
        "result": "win" if outcome else "loss",
        "market": market,
        "settlementStatus": "verified_matchup_and_start" if verified else "awaiting_verified_game",
    }


class CalibrationAuditTests(unittest.TestCase):
    def test_unverified_never_enters_training(self):
        picks = [pick(i, i % 2, verified=False) for i in range(250)]
        result = examine(picks)
        self.assertEqual(result["verifiedEligible"], 0)
        self.assertEqual(result["status"], "insufficient_verified_history")
        self.assertIsNone(result["experimentalBrier"])
        self.assertFalse(result["autoApply"])

    def test_incomplete_history_blocks_calibration(self):
        result = examine([pick(i, i % 2) for i in range(19)])
        self.assertEqual(result["verifiedEligible"], 19)
        self.assertEqual(result["evaluatedPicks"], 0)
        self.assertIsNone(result["brierImprovement"])

    def test_walk_forward_uses_only_prior_slates(self):
        # First date contains exactly the required 100 train records;
        # second date provides 30 evaluation records.
        picks = [pick(0, 0) for _ in range(100)] + [pick(1, 1) for _ in range(30)]
        result = examine(picks)
        self.assertEqual(result["evaluatedPicks"], 30)
        self.assertEqual(result["evaluationSlates"], 1)
        self.assertEqual(result["status"], "evaluated")
        self.assertGreater(result["experimentalBrier"], 0)
        self.assertFalse(result["autoApply"])

    def test_same_day_never_leaks_into_training(self):
        picks = [pick(0, 0) for _ in range(130)]
        self.assertEqual(examine(picks)["evaluatedPicks"], 0)

    def test_post_tipoff_and_invalid_predictions_rejected(self):
        record = pick(0, 1)
        record["recordedAt"] = record["startsAt"]
        self.assertIsNone(valid_record(record))
        record = pick(0, 1)
        record["probability"] = float("nan")
        self.assertIsNone(valid_record(record))

    def test_market_reports_are_independent(self):
        picks = [pick(0, 0, market="player_points"), pick(1, 1, market="player_assists")]
        result = audit(picks)
        self.assertEqual(result["overall"]["verifiedEligible"], 2)
        self.assertEqual(result["byMarket"]["player_assists"]["verifiedEligible"], 1)
        self.assertFalse(result["productionCalibrationEnabled"])


if __name__ == "__main__":
    unittest.main()
