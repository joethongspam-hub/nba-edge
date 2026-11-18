"""Unit tests for NBA EDGE research metrics; no external API or private key required."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import update

class ModelTests(unittest.TestCase):
    def test_probability_is_bounded(self):
        games = [
            {"minutes": 30, "player_points": 20 + (i % 5)}
            for i in range(20)
        ]
        prop = {"market": "player_points", "line": 19.5, "side": "Over"}
        result = update.ranking_probability(prop, games)
        self.assertIsNotNone(result)
        self.assertGreater(result["probability"], 0)
        self.assertLess(result["probability"], 1)

    def test_insufficient_history_returns_none(self):
        games = [{"minutes": 30, "player_points": 21}] * 10
        prop = {"market": "player_points", "line": 18.5, "side": "Over"}
        self.assertIsNone(update.ranking_probability(prop, games))

    def test_no_history_means_no_picks(self):
        prop = {"player": "Sample Player", "market": "player_points", "line": 20.5,
                "side": "Over", "odds": -110, "book": "FanDuel", "startsAt": "2026-11-19T00:00:00Z"}
        self.assertEqual(update.rank([prop], []), [])

    def test_settlement_win_loss_push(self):
        from datetime import datetime, timezone
        now = datetime(2026, 11, 20, tzinfo=timezone.utc)
        base = {"player": "Example Player", "market": "player_points",
                "line": 20.5, "startsAt": "2026-11-19T01:00:00Z",
                "odds": -110, "result": "pending"}
        entries = [{**base, "side": "Over"}, {**base, "side": "Under"}]
        logs = [{"player": "Example Player", "date": "2026-11-19", "player_points": 22}]
        update.settle_picks(entries, logs, now)
        self.assertEqual(entries[0]["result"], "win")
        self.assertEqual(entries[1]["result"], "loss")
        self.assertAlmostEqual(entries[0]["units"], 100/110, places=4)
        self.assertEqual(entries[1]["units"], -1)

if __name__ == "__main__":
    unittest.main()
