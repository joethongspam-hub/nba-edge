"""No-network tests for resumable ESPN game-context backfill."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from context_backfill import backfill, candidate_game_ids, matched_side
from context_research import _clean_opponent, _position


def historical_record(gid="espn-1", pid="100", date="2026-10-01"):
    return {
        "player": "Sample Player", "playerId": pid,
        "gameId": gid, "date": date, "minutes": 36.0,
        "player_points": 20.0, "player_rebounds": 7.0,
        "player_assists": 6.0, "event": "LA Clippers @ San Antonio Spurs",
        "startsAt": "2026-10-02T00:00:00Z",
    }


def refreshed_record(gid="espn-1", pid="100"):
    return {
        "playerId": pid, "gameId": gid,
        "team": "Los Angeles Clippers", "teamId": "12",
        "position": "PG",
        "event": "Los Angeles Clippers @ San Antonio Spurs",
        "startsAt": "2026-10-02T00:00:00Z",
    }


class ContextBackfillTests(unittest.TestCase):
    def test_verified_alias_matches_saved_scoreboard(self):
        self.assertEqual(
            matched_side("LA Clippers @ San Antonio Spurs", "Los Angeles Clippers"),
            ("LA Clippers", "San Antonio Spurs"))
        self.assertIsNone(matched_side(
            "LA Clippers @ San Antonio Spurs", "Portland Trail Blazers"))

    def test_merge_preserves_stats_and_verified_settlements(self):
        original=historical_record()
        data={"logs":[copy.deepcopy(original)],"games":{"espn-1":"20261001"},
              "scannedDates":["20261001"]}
        results=backfill(data,fetcher=lambda gid,date:[refreshed_record()],limit=1)
        self.assertEqual(results["successfulGames"],1)
        self.assertEqual(results["updatedRows"],1)
        row=data["logs"][0]
        self.assertEqual(row["minutes"],original["minutes"])
        self.assertEqual(row["player_points"],original["player_points"])
        self.assertEqual(row["event"],original["event"])
        self.assertEqual(row["opponent"],"San Antonio Spurs")
        self.assertEqual(row["team"],"LA Clippers")
        self.assertEqual(row["position"],"PG")
        self.assertEqual(_clean_opponent(row),"San Antonio Spurs")
        self.assertEqual(_position(row),"PG")
        self.assertEqual(data["games"],{"espn-1":"20261001"})
        self.assertEqual(data["scannedDates"],["20261001"])

        # A successful attempt is cached and does not call ESPN again.
        def forbidden(*args):
            raise AssertionError("Already cached game was refetched")
        again=backfill(data,fetcher=forbidden,limit=1)
        self.assertEqual(again["selectedGames"],0)

    def test_summary_can_recover_missing_scoreboard_label(self):
        row=historical_record()
        del row["event"]
        data={"logs":[row]}
        result=backfill(data,lambda gid,d:[refreshed_record()],limit=1)
        self.assertEqual(result["contextQualifiedRows"],1)
        self.assertEqual(row["event"],"Los Angeles Clippers @ San Antonio Spurs")

    def test_matchup_conflict_never_overwrites_identity(self):
        row=historical_record()
        data={"logs":[row]}
        conflicting={**refreshed_record(),"event":"Portland Trail Blazers @ Utah Jazz"}
        backfill(data,lambda gid,d:[conflicting],limit=1)
        self.assertNotIn("team",row)
        self.assertNotIn("position",row)
        self.assertNotIn("opponent",row)
        self.assertEqual(row["player_points"],20)

    def test_player_id_must_match(self):
        row=historical_record()
        data={"logs":[row]}
        backfill(data,lambda gid,d:[refreshed_record(pid="other")],limit=1)
        self.assertNotIn("team",row)

    def test_resume_and_failure_limit(self):
        data={"logs":[historical_record()]}
        def unavailable(*args):
            raise RuntimeError("temporary ESPN failure")
        for i in range(3):
            r=backfill(data,fetcher=unavailable,limit=1)
            self.assertEqual(r["selectedGames"],1)
        self.assertEqual(data["contextBackfill"]["failedGames"]["espn-1"],3)
        self.assertEqual(candidate_game_ids(data,limit=1)[0],[])
        self.assertEqual(backfill(data,fetcher=unavailable,limit=1)["selectedGames"],0)

    def test_game_selection_is_chronological_and_bounded(self):
        data={"logs":[historical_record("new",date="2026-11-01"),
                      historical_record("old",date="2026-10-01")]}
        selected,remaining=candidate_game_ids(data,limit=1)
        self.assertEqual(selected,["old"])
        self.assertEqual(remaining,2)

    def test_invalid_batch_size_rejected(self):
        with self.assertRaises(ValueError):
            backfill({"logs":[]},limit=121)


if __name__=="__main__":
    unittest.main()
