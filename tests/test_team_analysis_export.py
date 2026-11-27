import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from team_analysis_export import build, write

class TeamAnalysisExportTest(unittest.TestCase):
    def test_export(self):
        base=dict(event_id="1",home="A",away="B",start="2026-11-27T00:00:00Z",book="fanduel",market="h2h",line=None)
        a=dict(base,team="A",odds=150,model_probability=.6,market_probability=.4,shadow_probability=.45)
        b=dict(base,team="B",odds=-150,model_probability=.4,market_probability=.6,shadow_probability=.55)
        past=dict(a,event_id="2",start="2026-11-25T00:00:00Z")
        snapshot=dict(updated="2026-11-26T00:00:00Z",sports={"NBA":[a,b,past],"NHL":[],"NFL":[]})
        tracker=dict(updated=snapshot["updated"],forecasts=[dict(past,sport="NBA",result="win")])
        export=build(snapshot,tracker)
        nba=export["sports"]["NBA"]
        self.assertEqual(len(nba["games"]),1)
        game=nba["games"][0]
        self.assertEqual(game["quotes"][0]["model_minus_market_pp"],20)
        self.assertIsNone(game["quotes"][0]["efficiency_probability"])
        self.assertEqual(game["model_directions"][0]["directions"],{"model_probability":"A","shadow_probability":"B"})
        self.assertEqual(nba["recent_seven_day_paper"][0]["roi"],1.5)
        self.assertEqual(export["sports"]["NHL"]["games"],[])
        with TemporaryDirectory() as folder:
            path=Path(folder)/"export.json"
            self.assertEqual(write(snapshot,tracker,path),export)
            self.assertTrue(path.read_text().endswith("\n"))
