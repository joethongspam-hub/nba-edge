"""Combo props: real game totals, missing components, settlement and budget."""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import update
from prop_markets import MARKETS, COMBO_COMPONENTS, stat_value
from shadow_projections import project
from credit_budget import check_budget, OddsBudgetError


class ComboPropsTests(unittest.TestCase):
    def setUp(self):
        self.game = {"player_points": 21, "player_rebounds": 8,
                     "player_assists": 7, "minutes": 33}

    def test_all_eight_markets_included(self):
        self.assertEqual(len(MARKETS), 8)
        self.assertEqual(len(COMBO_COMPONENTS), 4)

    def test_game_by_game_combo_totals(self):
        expected = {"player_points_rebounds": 29,
                    "player_points_assists": 28,
                    "player_rebounds_assists": 15,
                    "player_points_rebounds_assists": 36}
        for market, total in expected.items():
            with self.subTest(market=market):
                self.assertEqual(stat_value(self.game, market), total)

    def test_missing_component_is_not_zero(self):
        incomplete = dict(self.game)
        del incomplete["player_assists"]
        self.assertIsNone(stat_value(incomplete, "player_points_assists"))
        self.assertIsNone(stat_value(incomplete, "player_rebounds_assists"))
        self.assertIsNone(stat_value(incomplete, "player_points_rebounds_assists"))
        self.assertEqual(stat_value(incomplete, "player_points_rebounds"), 29)

    def test_combo_projection_and_probability(self):
        games = [{**self.game, "player_points": 18 + i % 7,
                  "player_rebounds": 5 + i % 4, "player_assists": 4 + i % 3,
                  "date": f"2026-10-{i+1:02d}", "gameId": str(i)}
                 for i in range(25)]
        prop = {"market": "player_points_rebounds_assists", "line": 25.5, "side": "Over"}
        result = update.ranking_probability(prop, games)
        self.assertIsNotNone(result)
        self.assertGreater(result["projection"], 25)
        shadow = project(games, "player_points_rebounds_assists")
        self.assertIsNotNone(shadow)
        self.assertGreater(shadow["projectedStat"], 25)

    def test_combo_settlement_requires_verified_components(self):
        now = datetime(2026, 11, 21, tzinfo=timezone.utc)
        base = {"player": "Sample Player", "market": "player_points_rebounds_assists",
                "startsAt": "2026-11-20T01:00:00Z", "event": "LA Clippers @ San Antonio Spurs",
                "odds": -110, "result": "pending"}
        log = {**self.game, "player": "Sample Player", "gameId": "abc",
               "playerId": "123", "event": "Los Angeles Clippers @ San Antonio Spurs",
               "startsAt": "2026-11-20T01:10:00Z"}
        picks = [{**base, "line": 35.5, "side": "Over"},
                 {**base, "line": 36, "side": "Under"},
                 {**base, "line": 36.5, "side": "Over"}]
        update.settle_picks(picks, [log], now)
        self.assertEqual([p["result"] for p in picks], ["win", "push", "loss"])
        incomplete = dict(log)
        del incomplete["player_assists"]
        waiting = {**base, "line": 35.5, "side": "Over"}
        update.settle_picks([waiting], [incomplete], now)
        self.assertEqual(waiting["result"], "pending")

    def test_full_slate_guard_with_eight_markets(self):
        self.assertTrue(check_budget(2120, 10))
        with self.assertRaises(OddsBudgetError):
            check_budget(2119, 10)


if __name__ == "__main__":
    unittest.main()
