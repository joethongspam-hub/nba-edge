"""No-network tests for fail-closed quota checks and shadow injury flags."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from credit_budget import check_budget, remaining_from_headers, OddsBudgetError
from injury_review import extract_injuries, review


class BudgetGuardTests(unittest.TestCase):
    def test_free_endpoint_header_is_required(self):
        with self.assertRaises(OddsBudgetError):
            remaining_from_headers({})
        self.assertEqual(remaining_from_headers({"x-requests-remaining": "19020"}), 19020)

    def test_preserve_full_slate_and_reserve(self):
        self.assertTrue(check_budget(2080, 10))
        with self.assertRaises(OddsBudgetError):
            check_budget(2079, 10)

    def test_zero_games_spends_nothing(self):
        self.assertTrue(check_budget(2000, 0))

    def test_never_continue_after_limit(self):
        for remaining in (0, 1999, 2030):
            with self.assertRaises(OddsBudgetError):
                check_budget(remaining, 9)

    def test_reject_bad_quota_header(self):
        for value in ("", "unknown", "-1"):
            with self.assertRaises(OddsBudgetError):
                remaining_from_headers({"x-requests-remaining": value})


class InjuryReviewTests(unittest.TestCase):
    def test_grouped_feed(self):
        payload = {"injuries": [{"team": {"displayName": "Example Team"},
                                 "injuries": [{"athlete": {"displayName": "Test Player"},
                                               "status": "Questionable"}]}]}
        items, ok = extract_injuries(payload)
        self.assertTrue(ok)
        self.assertEqual(items[0]["player"], "Test Player")
        self.assertEqual(items[0]["status"], "Questionable")

    def test_not_listed_not_assumed_healthy(self):
        result = review([{"player": "Unknown Player", "market": "player_points"}],
                        [], True, "2026-11-20T00:00:00Z")
        self.assertEqual(result["picks"][0]["reviewStatus"], "not_listed_unconfirmed")
        self.assertTrue(result["picks"][0]["manualAvailabilityCheckRequired"])
        self.assertFalse(result["productionChanges"])

    def test_unavailable_feed_is_explicit(self):
        result = review([{"player": "Test Player"}], [], False, "2026-11-20T00:00:00Z")
        self.assertEqual(result["picks"][0]["reviewStatus"], "feed_unavailable")

    def test_name_matching(self):
        result = review([{"player": "R.J. Barrett"}],
                        [{"player": "RJ Barrett", "status": "Out", "team": "Toronto"}],
                        True, "2026-11-20T00:00:00Z")
        self.assertEqual(result["picks"][0]["reviewStatus"], "reported")
        self.assertEqual(result["picks"][0]["reportedInjury"]["status"], "Out")


if __name__ == "__main__":
    unittest.main()
