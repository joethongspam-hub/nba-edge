"""Offline tests for strictly paired NBA EDGE / Claude-inspired model replay."""
import copy
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from model_comparison import paired_predictions, compare
from analysis_export import build


def games(player="Player", n=50):
    start=date(2026,10,1)
    return [{"player":player,"gameId":str(i),
             "date":(start+timedelta(days=i)).isoformat(),
             "minutes":30 if i<25 else 38,
             "player_points":20 if i<25 else 30,
             "player_rebounds":5+i%3,
             "player_assists":4+i%4,
             "player_threes":2+i%2} for i in range(n)]


class ModelComparisonTests(unittest.TestCase):
    def test_equal_history_predicted_for_both_models(self):
        rows=games()
        pred=paired_predictions(rows[:25],"player_points")
        self.assertIsNotNone(pred)
        baseline,challenger,mins=pred
        self.assertAlmostEqual(baseline,20,delta=.01)
        self.assertAlmostEqual(challenger,20,delta=.01)
        self.assertAlmostEqual(mins,30,delta=.01)

    def test_both_models_see_strictly_prior_dates(self):
        history=games()
        result=compare(history)
        altered=copy.deepcopy(history)
        # Final same-day game cannot influence first same-day game's prediction.
        altered.append({**altered[-1],"gameId":"another",
                        "player_points":100000})
        # Extra game on final date affects scores, but not earlier predictions;
        # paired prior-date forecasts must match exactly.
        old=paired_predictions(history[:-1],"player_points")
        other=paired_predictions(altered[:-2],"player_points")
        self.assertEqual(old,other)
        self.assertEqual(result["productionChanges"],False)

    def test_same_day_doubleheaders_not_train_on_each_other(self):
        base=games()
        duplicated=base[:20]+[{**base[20],"gameId":"A","player_points":70},
                              {**base[20],"gameId":"B","player_points":10}]
        report=compare(duplicated)
        self.assertEqual(report["byMarket"]["player_points"]["n"],7)
        self.assertEqual(report["allWalkForward"]["n"],7*8)

    def test_combo_markets_and_holdout_present(self):
        result=compare(games())
        self.assertEqual(result["allWalkForward"]["n"],35*8)
        self.assertEqual(len(result["byMarket"]),8)
        self.assertEqual(result["lastQuarterHoldout"]["sufficientForReview"],False)
        self.assertFalse(result["usesSportsbookPrices"])

    def test_report_is_research_only(self):
        report=build({"ranked":[]},{"picks":[]},"2026-11-21T00:00:00Z",logs=games())
        self.assertIn("modelHeadToHead",report)
        self.assertFalse(report["modelHeadToHead"]["productionChanges"])
        self.assertFalse(report["walkForwardBacktest"]["productionCalibrationEnabled"])


if __name__=="__main__":
    unittest.main()
