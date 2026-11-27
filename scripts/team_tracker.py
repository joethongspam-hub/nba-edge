"""Forward-only team forecast archive; settle against unique ESPN final matchups."""
from datetime import timedelta
from collections import defaultdict
from nba_team_model import parse_time
import json
from team_benchmark import benchmark
from pathlib import Path

def archive(tracker, snapshot):
    seen={(r["sport"],r["event_id"],r["market"],r["book"]) for r in tracker}
    captured=parse_time(snapshot["updated"])
    for sport,rows in snapshot["sports"].items():
        groups=defaultdict(list)
        for row in rows:
            if row.get("model_probability") is not None and parse_time(row["start"])>captured:
                groups[(sport,row["event_id"],row["market"],row["book"])].append(row)
        for key, candidates in groups.items():
            if key in seen or len(candidates)!=2:
                continue
            # One model-direction forecast per book and market, not a bet recommendation.
            chosen=max(candidates,key=lambda r:(r["model_probability"],r["team"]))
            entry=dict(chosen,sport=sport,captured=snapshot["updated"],result="pending")
            if all(c.get("market_probability") is not None for c in candidates):
                reference=max(candidates,key=lambda c:(c["market_probability"],c["team"]))
                entry["market_reference"]={k:reference[k] for k in ("team","line","odds","market_probability")}
            tracker.append(entry)
            seen.add(key)
    return tracker

def settle(tracker, histories):
    for row in tracker:
        if row["result"]!="pending":
            continue
        start=parse_time(row["start"])
        matches=[g for g in histories.get(row["sport"],[]) if g[1]==row["home"] and g[2]==row["away"] and abs(g[0]-start)<timedelta(hours=6)]
        if len(matches)!=1:
            continue
        g=matches[0]
        margin=g[3]-g[4] if row["sport"]=="NHL" else g[3]
        margin*=1 if row["team"]==row["home"] else -1
        adjusted=margin+(row["line"] or 0)
        row["actual_margin"]=margin
        row["result"]="win" if adjusted>0 else "loss" if adjusted<0 else "push"
    return tracker

def summarize(tracker):
    groups=defaultdict(list)
    for row in tracker:
        groups[(row["sport"],row["market"],row["book"])].append(row)
    out=[]
    for (sport,market,book),rows in sorted(groups.items()):
        wins=sum(r["result"]=="win" for r in rows)
        losses=sum(r["result"]=="loss" for r in rows)
        pushes=sum(r["result"]=="push" for r in rows)
        graded=[r for r in rows if r["result"] in ("win","loss","push")]
        # Three-category Brier score, with explicit push class.
        errors=[]
        for r in graded:
            w=r["model_probability"];p=r.get("push_probability",0)
            errors.append(sum((q-(r["result"]==label))**2 for q,label in [(w,"win"),(p,"push"),(1-w-p,"loss")]))
        out.append(dict(sport=sport,market=market,book=book,wins=wins,losses=losses,pushes=pushes,pending=len(rows)-len(graded),accuracy=wins/(wins+losses) if wins+losses else None,brier=sum(errors)/len(errors) if errors else None))
    return out

def update(snapshot,histories,path=Path("docs/team_tracker.json")):
    tracker=json.loads(path.read_text())["forecasts"] if path.exists() else []
    archive(tracker,snapshot)
    settle(tracker,histories)
    data={"updated":snapshot["updated"],"forecasts":tracker,"summary":summarize(tracker),"benchmark":benchmark(tracker)}
    temp=path.with_suffix(".tmp")
    temp.write_text(json.dumps(data,indent=2)+"\n")
    temp.replace(path)
    return data
