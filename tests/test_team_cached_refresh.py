import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import team_markets

class CachedRefreshTest(unittest.TestCase):
    def test_cache_filters_started_games_and_preserves_odds_timestamp(self):
        now = datetime(2026, 11, 27, 18, tzinfo=timezone.utc)
        original = {"updated": "2026-11-27T12:00:00+00:00", "method": "test",
                    "sports": {"NHL": [
                        {"start": "2026-11-27T17:00:00Z", "odds": -110},
                        {"start": "2026-11-27T20:00:00Z", "odds": -120,
                         "model_probability": .7}]}}
        with patch.object(Path, "read_text", return_value=json.dumps(original)):
            with patch.object(team_markets, "fetch", side_effect=AssertionError("API call")):
                result = team_markets.cached_snapshot(now)
        self.assertEqual(result["odds_mode"], "cached")
        self.assertEqual(result["odds_updated"], original["updated"])
        self.assertEqual(len(result["sports"]["NHL"]), 1)
        self.assertEqual(result["sports"]["NHL"][0]["odds"], -120)
        self.assertNotIn("model_probability", result["sports"]["NHL"][0])
