"""No-network tests for projection-versus-line Top 10 and legacy paper pool."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from update import rank


def logs_for(player, value, market="player_points", variability=1.0, minutes=34, n=40):
    now=datetime.now(timezone.utc)
    rows=[]
    for i in range(n):
        rows.append({"player":player,"gameId":player+str(i),
                     "date":(now-timedelta(days=i+1)).strftime("%Y-%m-%d"),
                     "minutes":minutes,
                     market: value+variability*((i%3)-1)})
    return rows


def prop(player,side="Over",line=20.5,market="player_points",odds=-110,book="FanDuel"):
    return {"player":player,"market":market,"side":side,"line":line,
            "odds":odds,"book":book,"startsAt":(datetime.now(timezone.utc)+
                                               timedelta(hours=8)).isoformat(),
            "event":"Away Team @ Home Team"}


class ProjectionConfidenceTests(unittest.TestCase):
    def test_rejects_opposite_side_and_includes_correct_side(self):
        games=logs_for("A",27)
        picks=rank([prop("A","Over",21.5),prop("A","Under",21.5)],games)
        self.assertEqual(len(picks),1)
        self.assertEqual(picks[0]["side"],"Over")
        self.assertGreater(picks[0]["projection"],picks[0]["line"])
        self.assertGreater(picks[0]["projectionGap"],0)

    def test_negative_ev_does_not_disqualify_strong_projected_gap(self):
        games=logs_for("A",27)
        picks,ev_candidates=rank([prop("A",line=21.5,odds=-2000)],
                                  games,return_candidates=True)
        self.assertEqual(len(picks),1)
        self.assertLess(picks[0]["ev"],0)
        self.assertEqual(ev_candidates,[])
        self.assertEqual(picks[0]["rankingMethod"],"projection_gap_evidence_v1")

    def test_weak_projection_gap_does_not_qualify(self):
        games=logs_for("A",23,variability=4)
        picks=rank([prop("A",line=22.5)],games)
        self.assertEqual(picks,[])

    def test_insufficient_reliable_history_does_not_qualify(self):
        games=logs_for("A",30,n=17)
        self.assertEqual(rank([prop("A",line=20.5)],games),[])

    def test_last_five_minutes_and_old_games_penalties(self):
        now=datetime.now(timezone.utc)
        games=logs_for("Old",30)
        for row in games:
            row["date"]=(now-timedelta(days=120)).strftime("%Y-%m-%d")
        picks=rank([prop("Old",line=20.5)],games)
        self.assertEqual(picks,[])

    def test_volatility_normalizes_market_gaps(self):
        # A larger absolute points gap can be less decisive if points vary
        # widely compared with a stable rebound discrepancy.
        point_games=logs_for("Points",35,variability=9)
        rebound_games=logs_for("Boards",8,market="player_rebounds",variability=1)
        picks=rank([prop("Points",line=28.5),
                    prop("Boards",line=5.5,market="player_rebounds")],
                   point_games+rebound_games)
        self.assertEqual(len(picks),2)
        self.assertEqual(picks[0]["player"],"Boards")
        self.assertGreater(picks[0]["normalizedGap"],picks[1]["normalizedGap"])

    def test_at_most_one_per_player_even_across_bookmakers(self):
        games=logs_for("A",27)
        props=[prop("A",line=21.5),prop("A",line=22.5,book="DraftKings")]
        self.assertEqual(len(rank(props,games)),1)

    def test_all_supported_markets_allowed(self):
        markets=("player_points","player_rebounds","player_assists",
                 "player_threes","player_points_rebounds",
                 "player_points_assists","player_rebounds_assists",
                 "player_points_rebounds_assists")
        # Complete component stats allow all combinations to be evaluated.
        games=logs_for("A",30)
        for g in games:
            g.update({"player_rebounds":9,"player_assists":8,"player_threes":4})
        props=[prop("A",line=1.5,market=m) for m in markets]
        _,candidates=rank(props,games,return_candidates=True)
        self.assertEqual(len({x["market"] for x in candidates}),8)

    def test_a_grades_still_disabled(self):
        picks=rank([prop("A",line=20.5)],logs_for("A",30))
        self.assertEqual(picks[0]["grade"],"B")
        self.assertNotIn("A",{p["grade"] for p in picks})


if __name__=="__main__":
    unittest.main()
