import sys
import unittest
from pathlib import Path
from datetime import datetime, timezone
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from nhl_goalie_ratings import ratings, name_key

class GoalieRatingTests(unittest.TestCase):
    def test_shrinkage_and_exclusions(self):
        now = datetime(2026,11,27,17,tzinfo=timezone.utc)
        row = {"situation":"all","gameDate":"20261126","icetime":"3600",
               "xGoals":"4","goals":"2","playerTeam":"BOS","playerId":"1",
               "gameId":"1","name":"Jeremy Swayman"}
        players, teams, health = ratings([row,row,dict(row,gameId="2",gameDate="20261127"),
                                          dict(row,gameId="3",situation="5on5")],now)
        r=players[name_key("Jeremy Swayman")]
        self.assertEqual(health["games"],1)
        self.assertEqual(r["season_gsax"],2)
        self.assertEqual(r["season_gsax60"],2)
        self.assertGreater(r["gsax60"],0)
        self.assertLess(r["gsax60"],2)
        self.assertFalse(r["rating_eligible"])
        self.assertIn("Boston Bruins",teams)
    def test_name_normalization(self):
        self.assertEqual(name_key("Jakub Dobeš"),name_key("Jakub Dobes"))
