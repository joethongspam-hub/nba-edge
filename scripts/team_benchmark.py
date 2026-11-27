"""Paper performance at archived prices, never current or reconstructed odds."""
from collections import defaultdict

def profit(result,odds):
    if result=="push":
        return 0.0
    if result=="loss":
        return -1.0
    if result=="win":
        if not odds:
            raise ValueError("Invalid American odds")
        return odds/100 if odds>0 else 100/abs(odds)
    raise ValueError("Unsettled forecast")

def record(rows):
    settled=[r for r in rows if r["result"] in ("win","loss","push") and r.get("odds")]
    n=len(settled)
    w=sum(r["result"]=="win" for r in settled)
    l=sum(r["result"]=="loss" for r in settled)
    units=sum(profit(r["result"],r["odds"]) for r in settled)
    return dict(settled=n,wins=w,losses=l,pushes=n-w-l,accuracy=w/(w+l) if w+l else None,
                units=units,roi=units/n if n else None)

def benchmark(tracker):
    groups=defaultdict(list)
    for r in tracker:
        groups[(r["sport"],r["market"],r["book"])].append(r)
    out=[]
    for (sport,market,book),rows in sorted(groups.items()):
        matched=[]; favorites=[]
        for r in rows:
            f=r.get("market_reference")
            if not f or r["result"] not in ("win","loss","push") or not f.get("odds") or not r.get("odds"):
                continue
            if f["team"]==r["team"]:
                result=r["result"]
            else:
                # Use actual selected-team margin and the archived opposite line.
                margin=-r["actual_margin"]+(f.get("line") or 0)
                result="win" if margin>0 else "loss" if margin<0 else "push"
            matched.append(r)
            favorites.append(dict(f,result=result))
        bins=[]
        for low,high in [(0,.55),(.55,.60),(.60,.70),(.70,.80),(.80,1.01)]:
            subset=[r for r in rows if low<=r["model_probability"]<high]
            if subset:
                bins.append(dict(low=low,high=min(high,1),**record(subset)))
        out.append(dict(sport=sport,market=market,book=book,model=record(rows),
                        matched_model=record(matched),market_reference=record(favorites),confidence=bins))
    return out
