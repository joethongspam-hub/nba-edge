"""Walk-forward evidence redesign: chronological leakage, parity, and no-odds regressions."""
import sys
import unittest
from datetime import date,timedelta,datetime,timezone
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from evidence_walkforward import history_stats,score,report
from evidence_research import analyze
from update import ranking_probability,rank
from analysis_export import build

def games(player,n=45,start=date(2026,8,1),outlier=False):
    rows=[]
    for i in range(n):
        r={"player":player,"gameId":f"{player}-{i}",
           "date":(start+timedelta(days=i)).isoformat(),"minutes":30+i%3,
           "player_points":20+i%5,"player_rebounds":5+i%3,
           "player_assists":4+i%2,"player_threes":2+i%2}
        if outlier and i==n-1:r["player_points"]=300
        rows.append(r)
    return rows

def prop(player):
    return {"player":player,"market":"player_points","side":"Over",
            "line":14.5,"odds":-110,"book":"FanDuel",
            "startsAt":"2026-12-03T00:00:00Z","event":"Home @ Away"}

class WalkForwardEvidenceTests(unittest.TestCase):
    def test_strictly_earlier_day_prevents_peeking_and_same_day_leakage(self):
        a=games("A",23)
        previous=a[:-1]
        s=history_stats(previous,"player_points",date.fromisoformat(a[-1]["date"]))
        self.assertIsNotNone(s)
        self.assertAlmostEqual(s["projection"],ranking_probability(prop("A"),list(reversed(previous)))["projection"])
        b=[*previous,{**a[-1],"player_points":999,"date":a[-1]["date"]}]
        # Different current-game outcome should not change the score of that game.
        first=report(a)
        altered=report(b)
        for method in ("current","candidate"):
            self.assertEqual(first["methods"][method]["lastQuarter"]["meanScore"],
                             altered["methods"][method]["lastQuarter"]["meanScore"])
            self.assertNotEqual(first["methods"][method]["lastQuarter"]["mae"],
                                altered["methods"][method]["lastQuarter"]["mae"])

    def test_date_relative_age_not_today_relative_age(self):
        a=games("A",20,start=date(2024,1,1))
        s=history_stats(a,"player_points",date(2024,2,1))
        self.assertEqual(s["oldGames"],0)
        later=history_stats(a,"player_points",date(2025,1,1))
        self.assertEqual(later["oldGames"],20)

    def test_redesign_changes_score_not_projection(self):
        stats={"sample":20,"recentMinutes":31,"minutesCv":.10,
               "volatility":3,"projection":20,"oldGames":7}
        old=score(stats,"current")
        new=score(stats,"candidate")
        self.assertGreater(new,old)
        self.assertEqual(stats["projection"],20)

    def test_holdout_pairs_same_game_markets(self):
        data=games("A",45)+games("B",45)
        r=report(data)
        self.assertEqual(r["methods"]["current"]["lastQuarter"]["n"],
                         r["methods"]["candidate"]["lastQuarter"]["n"])
        self.assertEqual(r["methods"]["current"]["lastQuarter"]["mae"],
                         r["methods"]["candidate"]["lastQuarter"]["mae"])
        self.assertEqual(r["markets"].__len__(),8)
        self.assertFalse(r["productionChanges"])
        self.assertEqual(r["extraOddsApiCalls"],0)
        self.assertLess(r["holdoutDistinctDates"],r["distinctDates"])
        self.assertFalse(r["sufficientForReview"])

    def test_same_day_games_are_not_training_for_each_other(self):
        data=games("A",20)
        date20=data[-1]["date"]
        data.append({**data[-1],"gameId":"second","player_points":500})
        r=report(data)
        self.assertEqual(r["methods"]["current"]["allHistorical"]["n"],2*8)

    def test_same_slate_redesign_only_changes_shadow_counts(self):
        data=games("A",40,start=date.today()-timedelta(days=40))
        p=prop("A")
        p["startsAt"]=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
        result=analyze([p],data,ranking_probability)
        self.assertIn("redesigned_60",result["scenarios"])
        self.assertTrue(result["scenarios"]["redesigned_60"]["researchOnly"])
        production=rank([p],data)
        self.assertEqual(result["scenarios"]["current"]["top10Count"],len(production))

    def test_no_remote_calls_in_walk_forward_or_export(self):
        data=games("A",45)
        with patch("urllib.request.urlopen",side_effect=AssertionError("network")):
            research=report(data)
            exported=build({"ranked":[]},{"picks":[]},datetime.now(timezone.utc).isoformat(),logs=data)
        self.assertEqual(exported["evidenceScoreWalkForward"]["methods"]["candidate"]["lastQuarter"]["n"],
                         research["methods"]["candidate"]["lastQuarter"]["n"])

if __name__=="__main__":
    unittest.main()
