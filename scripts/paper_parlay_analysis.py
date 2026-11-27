"""Experimental paper-only parlay screening from existing team export."""
import argparse
import itertools
import json
import math
from datetime import datetime
from pathlib import Path

def decimal(odds):
    if not isinstance(odds, (int, float)) or not math.isfinite(odds) or abs(odds) < 100:
        raise ValueError("Invalid American odds")
    return 1 + (odds / 100 if odds > 0 else 100 / -odds)

def analyze(snapshot):
    books = {}
    asof = datetime.fromisoformat(snapshot["updated"].replace("Z", "+00:00"))
    for sport, data in snapshot["sports"].items():
        for game in data.get("games", []):
            if datetime.fromisoformat(game["start"].replace("Z", "+00:00")) <= asof:
                continue
            for q in game.get("quotes", []):
                p = q.get("model_probability")
                if not isinstance(p, (int, float)) or not .70 <= p <= 1:
                    continue
                if q.get("push_probability") != 0 or q.get("market") not in ("h2h", "spreads"):
                    continue
                if q.get("market") == "spreads" and (not isinstance(q.get("line"), (int,float)) or abs(q["line"]) % 1 != .5):
                    continue
                try:
                    d = decimal(q.get("odds"))
                except ValueError:
                    continue
                if p*d <= 1 or not game.get("event_id") or not q.get("book"):
                    continue
                leg = dict(sport=sport, event_id=game["event_id"], start=game["start"],
                           team=q["team"], market=q["market"], line=q.get("line"),
                           odds=q["odds"], probability=p, decimal=d)
                books.setdefault(q["book"], []).append(leg)
    groups = {"2": [], "3": []}
    for book, legs in books.items():
        for n in (2, 3):
            for combo in itertools.combinations(legs, n):
                if len({x["event_id"] for x in combo}) != n:
                    continue
                if len({x["start"][:10] for x in combo}) != 1:
                    continue
                p = math.prod(x["probability"] for x in combo)
                d = math.prod(x["decimal"] for x in combo)
                if p < .50 or not 1+100/150 <= d <= 2.5 or p*d <= 1:
                    continue
                groups[str(n)].append(dict(book=book, legs=list(combo), probability=p,
                    estimated_decimal_odds=d, estimated_ev=p*d-1))
    for rows in groups.values():
        rows.sort(key=lambda x: (-x["probability"], -x["estimated_ev"]))
        del rows[10:]
    return dict(updated=snapshot["updated"], status="Experimental paper analysis; uncalibrated",
                limitations=["Assumes independent outcomes; distinct games do not guarantee independence.",
                "Multiplied odds are estimates, not verified sportsbook parlay quotes.",
                "Not a historical backtest or settled results tracker.",
                "Only zero-push quotes included; integer spreads excluded."], candidates=groups)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = analyze(json.loads(args.source.read_text()))
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
