"""Offline tests for early-tipoff schedule and controlled paid refresh."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from adaptive_schedule import today_games, cache_state, decide

CT = ZoneInfo("America/Chicago")


def local(hour, minute=13):
    return datetime(2026, 11, 22, hour, minute, tzinfo=CT).astimezone(timezone.utc)


def cache(now, count=1, hours=4):
    return {"slateDate": now.astimezone(CT).date().isoformat(),
            "cacheVersion": 2, "refreshCount": count,
            "fetchedAt": (now - timedelta(hours=hours)).isoformat()}


class AdaptiveScheduleTests(unittest.TestCase):
    def test_first_early_game_triggers(self):
        now = local(9)
        self.assertEqual(decide(now, [local(11, 0)], {})[:2], (True, False))

    def test_too_early_does_not_spend(self):
        self.assertEqual(decide(local(9), [local(14, 0)], {})[:2], (False, False))

    def test_late_fallback(self):
        self.assertEqual(decide(local(17), [local(20, 0)], {})[:2], (True, False))

    def test_one_late_refresh_only(self):
        now = local(17)
        self.assertEqual(decide(now, [local(19)], cache(now))[:2], (True, True))
        self.assertEqual(decide(now, [local(19)], cache(now, count=2))[:2], (False, False))

    def test_no_refresh_soon_after_first(self):
        now = local(17)
        self.assertEqual(decide(now, [local(19)], cache(now, hours=1))[:2], (False, False))

    def test_no_future_games(self):
        self.assertEqual(decide(local(17), [], {})[:2], (False, False))

    def test_manual_defaults_cached(self):
        now = local(11)
        self.assertEqual(decide(now, [local(19)], cache(now), manual=True)[:2], (True, False))
        self.assertEqual(decide(now, [local(19)], cache(now), manual=True, manual_refresh=True)[:2], (True, True))
        self.assertEqual(decide(now, [local(19)], cache(now, count=2), manual=True, manual_refresh=True)[:2], (True, False))

    def test_timezone_and_date_filter(self):
        board = {"events": [{"date": local(12).isoformat()}, {"date": (local(12) + timedelta(days=1)).isoformat()}]}
        self.assertEqual(today_games(board, local(9)), [local(12)])

    def test_missing_timestamp_blocks_second(self):
        now = local(17)
        c = cache(now)
        del c["fetchedAt"]
        self.assertEqual(decide(now, [local(19)], c)[:2], (False, False))


if __name__ == "__main__":
    unittest.main()
