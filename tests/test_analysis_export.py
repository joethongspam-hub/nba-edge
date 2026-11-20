"""No-network tests for the daily analysis export."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from analysis_export import summarize, build


class AnalysisExportTests(unittest.TestCase):
    def test_empty_history_is_not_calibrated(self):
        result = build({"ranked": [], "slateDate": "2026-11-20"},
                       {"picks": []}, "2026-11-20T00:00:00+00:00")
        self.assertIsNone(result["calibration"]["overall"]["brierScore"])
        self.assertFalse(result["calibration"]["sufficientForCalibration"])
        self.assertEqual(result["today"]["ranked"], [])

    def test_brier_push_and_roi(self):
        picks = [
            {"result": "win", "probability": .8, "odds": -110, "market": "player_points"},
            {"result": "loss", "probability": .3, "odds": 120, "market": "player_assists"},
            {"result": "push", "probability": .7, "odds": -110},
            {"result": "pending", "probability": .6, "odds": -110},
        ]
        result = summarize(picks)
        self.assertEqual(result["graded"], 2)
        self.assertEqual(result["pushes"], 1)
        self.assertEqual(result["pending"], 1)
        self.assertEqual(result["brierScore"], .065)
        self.assertEqual(result["units"], -.0909)
        self.assertEqual(result["roi"], -.0455)

    def test_reject_invalid_probabilities_without_discarding_results(self):
        result = summarize([{"result": "win", "probability": None, "odds": 105},
                            {"result": "loss", "probability": "nan", "odds": -110}])
        self.assertEqual(result["graded"], 2)
        self.assertEqual(result["probabilitySamples"], 0)
        self.assertIsNone(result["logLoss"])

    def test_market_slices_do_not_modify_picks(self):
        picks = [{"result": "win", "probability": .7, "odds": 100, "market": "player_threes"}]
        report = build({"ranked": [{"player": "Example", "grade": "C"}]},
                       {"picks": picks}, "2026-11-20T00:00:00+00:00")
        self.assertEqual(report["calibration"]["byMarket"]["player_threes"]["wins"], 1)
        self.assertEqual(report["today"]["ranked"][0]["player"], "Example")
        self.assertEqual(picks[0]["result"], "win")


if __name__ == "__main__":
    unittest.main()
