"""Forward-only paper parlay archive, using existing team tracker final margins."""
import json
import math
from datetime import datetime
from pathlib import Path

def time(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))

def identity(row):
    return (row["book"], tuple(sorted((x["sport"], x["event_id"], x["market"], x["team"], str(x["line"])) for x in row["legs"])))

def update(previous, export, team):
    rows = previous.get("forecasts", [])
    seen = {identity(r) for r in rows}
    captured = time(export["updated"])
    for candidates in export["candidates"].values():
        for candidate in candidates:
            key = identity(candidate)
            if key in seen or any(time(l["start"]) <= captured for l in candidate["legs"]):
                continue
            rows.append(dict(candidate, captured=export["updated"], result="pending"))
            seen.add(key)
    margins = {}
    for r in team["forecasts"]:
        if r.get("result") not in ("win","loss","push") or not isinstance(r.get("actual_margin"), (int,float)):
            continue
        if r["team"] not in (r["home"],r["away"]):
            continue
        key = (r["sport"],r["event_id"],r["start"])
        for side, sign in ((r["team"],1),(r["away"] if r["team"]==r["home"] else r["home"],-1)):
            margins.setdefault((key,side),set()).add(sign*r["actual_margin"])
    for row in rows:
        if row["result"] != "pending":
            continue
        outcomes = []
        for leg in row["legs"]:
            values = margins.get(((leg["sport"],leg["event_id"],leg["start"]),leg["team"]),set())
            if len(values)!=1:
                outcomes.append("pending")
                continue
            adjusted = next(iter(values))+(leg["line"] or 0)
            outcomes.append("win" if adjusted>0 else "loss" if adjusted<0 else "push")
        row["leg_results"] = outcomes
        if "pending" in outcomes:
            continue
        payout = 0 if "loss" in outcomes else math.prod(l["decimal"] for l,o in zip(row["legs"],outcomes) if o=="win")
        row["units"] = payout-1
        row["result"] = "loss" if "loss" in outcomes else "reduced" if "push" in outcomes else "win"
    summary = {}
    for n in (2,3):
        group = [r for r in rows if len(r["legs"])==n]
        settled = [r for r in group if r["result"]!="pending"]
        binary = [r for r in settled if r["result"] in ("win","loss")]
        wins = sum(r["result"]=="win" for r in binary)
        summary[str(n)] = dict(archived=len(group), pending=len(group)-len(settled), settled=len(settled),
            wins=wins, losses=len(binary)-wins, reduced=len(settled)-len(binary),
            win_rate=wins/len(binary) if binary else None,
            average_probability=sum(r["probability"] for r in binary)/len(binary) if binary else None,
            brier=sum((r["probability"]-(r["result"]=="win"))**2 for r in binary)/len(binary) if binary else None,
            paper_roi=sum(r["units"] for r in settled)/len(settled) if settled else None)
    return dict(updated=export["updated"], forecasts=rows, summary=summary,
        limitations=["First observed quote per book and exact combination; overlapping combinations are not independent.",
        "Estimated payouts, not verified sportsbook parlay prices. Reduced parlays assume pushed legs are removed.",
        "Unmatched or conflicting final margins remain pending. Forward-only, not a historical backtest."])

if __name__ == "__main__":
    path=Path("docs/paper_parlay_tracker.json")
    previous=json.loads(path.read_text()) if path.exists() else {}
    export=json.loads(Path("docs/paper_parlay_analysis.json").read_text())
    team=json.loads(Path("docs/team_tracker.json").read_text())
    result=update(previous,export,team)
    temp=path.with_suffix(".tmp")
    temp.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    temp.replace(path)
