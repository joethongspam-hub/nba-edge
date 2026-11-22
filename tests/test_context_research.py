"""Offline validation: no invented context, paired context studies, no ranking edits."""
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from context_research import compare_context, _clean_opponent
from analysis_export import build


def records(n=40,player="Example Player",context=True,position="PG"):
    start=date(2026,10,1)
    rows=[]
    for i in range(n):
        row={"player":player,"playerId":player,"gameId":f"{player}-{i}",
             "date":(start+timedelta(days=i)).isoformat(),
             "minutes":32,"player_points":20+i%5,
             "player_rebounds":4+i%3,"player_assists":6+i%3,"player_threes":2}
        if context:
            row.update({"team":"Home Team","opponent":"Away Team",
                        "event":"Away Team @ Home Team","position":position})
        rows.append(row)
    return rows


class ContextResearchTests(unittest.TestCase):
    def test_missing_context_does_not_infer_team(self):
        self.assertIsNone(_clean_opponent(records(1,context=False)[0]))
        result=compare_context(records(context=False))
        self.assertEqual(result["allHistorical"]["n"],0)
        self.assertGreater(result["contextCoverage"]["missingOpponentOrPosition"],0)

    def test_matchup_mismatch_rejected(self):
        row=records(1)[0]
        row["opponent"]="Random Team"
        self.assertIsNone(_clean_opponent(row))

    def test_opponent_position_requires_prior_history(self):
        rows=records(50)
        result=compare_context(rows)
        self.assertGreater(result["allHistorical"]["n"],0)
        self.assertEqual(result["oddsApiCalls"],0)
        self.assertFalse(result["productionChanges"])
        self.assertFalse(result["lastQuarterHoldout"]["sufficientForReview"])
        self.assertEqual(len(result["lastQuarterHoldout"]["byMarket"]),8)

    def test_unrelated_position_does_not_train_same_position(self):
        # Different position has its own prior opponent records.
        rows=records(40,player="Guard",position="PG") + records(40,player="Center",position="C")
        result=compare_context(rows)
        self.assertGreater(result["allHistorical"]["n"],0)

    def test_report_integrates_context_without_production_change(self):
        report=build({"ranked":[]},{"picks":[]},"2026-11-21T00:00:00Z",logs=records())
        self.assertIn("contextResearch",report)
        self.assertFalse(report["contextResearch"]["productionChanges"])


if __name__=="__main__":
    unittest.main()
