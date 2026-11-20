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

    def test_long_history_enables_stronger_evidence_grade(self):
        from datetime import datetime, timedelta, timezone
        today=datetime.now(timezone.utc)
        logs=[]
        for i in range(40):
            logs.append({"player":"Sample Player","date":(today-timedelta(days=i+1)).strftime('%Y-%m-%d'),
                         "minutes":32+(i%3),"player_points":25+(i%3)})
        prop={"player":"Sample Player","market":"player_points","line":20.5,
              "side":"Over","odds":-110,"book":"FanDuel",
              "startsAt":(today+timedelta(days=1)).isoformat()}
        ranked=update.rank([prop],logs)
        self.assertEqual(len(ranked),1)
        self.assertEqual(ranked[0]["sample"],40)
        self.assertEqual(ranked[0]["grade"],"B")
        self.assertLessEqual(ranked[0]["evidenceScore"],100)

    def test_no_a_grade_without_prospective_calibration(self):
        from datetime import datetime, timedelta, timezone
        today=datetime.now(timezone.utc)
        logs=[{"player":"Sample Player","date":(today-timedelta(days=i+1)).strftime('%Y-%m-%d'),
               "minutes":33,"player_points":28} for i in range(40)]
        prop={"player":"Sample Player","market":"player_points","line":20.5,
              "side":"Over","odds":-110,"book":"FanDuel",
              "startsAt":(today+timedelta(days=1)).isoformat()}
        self.assertTrue(all(p["grade"]!="A" for p in update.rank([prop],logs)))

    def test_cached_props_reuse_without_odds_api(self):
        from datetime import datetime, timezone
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        now=datetime(2026,11,18,23,13,tzinfo=timezone.utc)
        props=[{"player":"Sample","market":"player_points","side":"Over",
                "line":22.5,"odds":-110,"book":"FanDuel",
                "event":"Away @ Home","startsAt":"2026-11-19T01:00:00Z"}]
        with TemporaryDirectory() as temp:
            with patch.object(update,'ROOT',Path(temp)):
                update.write_odds_cache("2026-11-18",now,props,8,32,"1500")
                with patch.object(update,'request',side_effect=AssertionError("Unexpected API request")):
                    result=update.cached_props("2026-11-18")
                self.assertEqual(result['props'],props)
                self.assertEqual(result['eventsChecked'],8)
                self.assertIsNone(update.cached_props("2026-11-19"))
                self.assertEqual(result['oddsCreditsUsed'],32)

    def test_recomputed_snapshot_uses_zero_new_paid_credits(self):
        from datetime import datetime, timezone
        now=datetime(2026,11,18,23,13,tzinfo=timezone.utc)
        cache={'props':[{"player":"One"}],'eventsChecked':3,
               'oddsCreditsUsed':12,'oddsCreditsRemaining':'800',
               'fetchedAt':now.isoformat()}
        result=update.build_snapshot(now,'2026-11-18',cache,[],[],{},
                                     'recomputed_from_cache')
        self.assertEqual(result['oddsCreditsUsed'],0)
        self.assertEqual(result['propsScanned'],1)
        self.assertEqual(result['oddsSnapshotAt'],now.isoformat())
        self.assertEqual(result['modelVersion'],'3.3-experimental')

    def test_settlement_win_loss_push(self):
        from datetime import datetime, timezone
        now = datetime(2026, 11, 20, tzinfo=timezone.utc)
        base = {"player": "Example Player", "market": "player_points",
                "line": 20.5, "startsAt": "2026-11-19T01:00:00Z",
                "odds": -110, "result": "pending", "event": "Away Team @ Home Team"}
        entries = [{**base, "side": "Over"}, {**base, "side": "Under"}]
        logs = [{"player": "Example Player", "date": "2026-11-19", "player_points": 22, "gameId": "401", "playerId": "12", "event": "Away Team @ Home Team", "startsAt": "2026-11-19T01:10:00Z"}]
        update.settle_picks(entries, logs, now)
        self.assertEqual(entries[0]["result"], "win")
        self.assertEqual(entries[1]["result"], "loss")
        self.assertAlmostEqual(entries[0]["units"], 100/110, places=4)
        self.assertEqual(entries[1]["units"], -1)
        self.assertEqual(entries[0]["verifiedGameId"], "401")

if __name__ == "__main__":
    unittest.main()
