"""No-network regression tests for verified NBA prop settlement."""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import update
from settlement import unique_verified_log


class VerifiedSettlementTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 21, tzinfo=timezone.utc)
        self.pick = {"player": "Sample Player", "market": "player_points",
                     "side": "Over", "line": 19.5, "odds": -110,
                     "startsAt": "2026-11-20T01:00:00Z",
                     "event": "LA Clippers @ San Antonio Spurs",
                     "result": "pending"}
        self.log = {"player": "Sample Player", "player_points": 22,
                    "gameId": "espn-123", "playerId": "456",
                    "event": "Los Angeles Clippers @ San Antonio Spurs",
                    "startsAt": "2026-11-20T01:10:00Z",
                    "date": "2026-11-19"}

    def test_verified_match_settles_and_saves_identity(self):
        picks = [dict(self.pick)]
        update.settle_picks(picks, [self.log], self.now)
        self.assertEqual(picks[0]["result"], "win")
        self.assertEqual(picks[0]["verifiedGameId"], "espn-123")
        self.assertEqual(picks[0]["verifiedPlayerId"], "456")
        self.assertEqual(picks[0]["settlementStatus"], "verified_matchup_and_start")

    def test_different_matchup_never_settles(self):
        wrong = {**self.log, "event": "LA Clippers @ Denver Nuggets"}
        picks = [dict(self.pick)]
        update.settle_picks(picks, [wrong], self.now)
        self.assertEqual(picks[0]["result"], "pending")

    def test_missing_event_identity_never_settles(self):
        old = {k: v for k, v in self.log.items() if k not in ("event", "startsAt")}
        picks = [dict(self.pick)]
        update.settle_picks(picks, [old], self.now)
        self.assertEqual(picks[0]["result"], "pending")

    def test_start_time_mismatch_never_settles(self):
        wrong = {**self.log, "startsAt": "2026-11-21T01:10:00Z"}
        self.assertIsNone(unique_verified_log(self.pick, [wrong]))

    def test_duplicate_matching_rows_never_settle(self):
        picks = [dict(self.pick)]
        update.settle_picks(picks, [self.log, {**self.log, "gameId": "espn-999"}], self.now)
        self.assertEqual(picks[0]["result"], "pending")

    def test_existing_settlement_remains_frozen(self):
        settled = {**self.pick, "result": "loss", "actual": 12, "units": -1}
        update.settle_picks([settled], [self.log], self.now)
        self.assertEqual(settled["result"], "loss")
        self.assertNotIn("verifiedGameId", settled)


if __name__ == "__main__":
    unittest.main()
