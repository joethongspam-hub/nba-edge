import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))

from gap_threshold_experiment import select, freeze, report

NOW=datetime(2026,11,23,16,tzinfo=timezone.utc)
def candidate(i,gap,player=None):
    return {"player":player or f"Player {i}","market":"player_points",
            "side":"Over","line":10.5,"book":"FanDuel","odds":-110,
            "event":"Away @ Home","startsAt":(NOW+timedelta(hours=4)).isoformat(),
            "projection":12.0,"volatility":2.0,"normalizedGap":gap,
            "projectionGap":1.5,"sample":25,"evidenceScore":55,
            "paperRankingScore":gap,"paperEvidenceLabel":"moderate"}

class ThresholdExperimentTests(unittest.TestCase):
    def test_boundary_and_identical_rank(self):
        pool=[candidate(i,g) for i,g in enumerate((.59,.60,.64,.65,.69,.70,.74,.75,.90))]
        self.assertEqual([len(select(pool,NOW,t)) for t in (.60,.65,.70,.75)],[8,6,4,2])
        for t in (.60,.65,.70):
            self.assertTrue(set(p["player"] for p in select(pool,NOW,.75))
                            <= set(p["player"] for p in select(pool,NOW,t)))

    def test_single_player_and_started_game(self):
        pool=[candidate(1,.95,player="Same"),candidate(2,.85,player="Same"),
              candidate(3,.80)]
        pool[2]["startsAt"]=(NOW-timedelta(hours=1)).isoformat()
        self.assertEqual(len(select(pool,NOW,.60)),1)

    def test_freeze_no_rewrite_and_group_overlap(self):
        pool=[candidate(1,.62),candidate(2,.68),candidate(3,.72),candidate(4,.80)]
        state={}
        self.assertTrue(freeze(state,pool,NOW,"2026-11-23"))
        original=state["slates"]["2026-11-23"]["picks"].copy()
        self.assertFalse(freeze(state,[candidate(5,.95)],NOW,"2026-11-23"))
        self.assertEqual(original,state["slates"]["2026-11-23"]["picks"])
        r=report(state)
        self.assertEqual([r["results"][t]["selections"] for t in ("0.60","0.65","0.70","0.75")],[4,3,2,1])
        self.assertEqual(r["overlapWithBaseline"]["0.60"],1)
        self.assertFalse(r["sufficientForReview"])
        for p in state["slates"]["2026-11-23"]["picks"].values():
            self.assertEqual(p["selectionRecordedAt"],NOW.isoformat())

    def test_no_past_backfill(self):
        state={}
        self.assertFalse(freeze(state,[candidate(1,.90)],NOW+timedelta(hours=5),"2026-11-23"))
        self.assertFalse(state.get("slates"))

if __name__=="__main__":unittest.main()
