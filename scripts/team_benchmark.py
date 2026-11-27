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

def segments(rows):
    groups=defaultdict(list)
    for r in rows:
        market=r["market"]
        p=r.get("model_probability")
        odds=r.get("odds")
        mp=r.get("market_probability")
        if r.get("team") and r.get("home") and r.get("away"):
            venue="Home" if r["team"]==r["home"] else "Away" if r["team"]==r["away"] else "Unknown"
            groups[("Venue",venue)].append(r)
        if market=="h2h" and mp is not None:
            groups[("Market side","Favorite" if mp>.5 else "Underdog" if mp<.5 else "Even")].append(r)
        elif market=="spreads" and r.get("line") is not None:
            line=r["line"]
            groups[("Market side","Giving points" if line<0 else "Receiving points" if line>0 else "Pick'em")].append(r)
        if p is not None:
            for low,high,label in [(0,.55,"Below 55%"),(.55,.60,"55–59%"),(.60,.70,"60–69%"),(.70,.80,"70–79%"),(.80,1.01,"80%+")]:
                if low<=p<high:
                    groups[("Model probability",label)].append(r)
                    break
            if mp is not None:
                gap=p-mp
                label="Below market" if gap<0 else "0–<5 pp" if gap<.05 else "5–<10 pp" if gap<.10 else "10+ pp"
                groups[("Model minus no-vig market",label)].append(r)
            if odds and abs(odds)>=100:
                breakeven=100/(100+odds) if odds>0 else -odds/(100-odds)
                push=r.get("push_probability",0) or 0
                gap=p-(1-push)*breakeven
                groups[("Model vs break-even","Above" if gap>1e-9 else "Below" if gap< -1e-9 else "Equal")].append(r)
        agreement=r.get("archived_agreement")
        if agreement:
            groups[("Challenger direction",agreement)].append(r)
        else:
            groups[("Challenger direction","Not recorded")].append(r)
    return [dict(dimension=d,label=l,forecasts=len(rs),**record(rs)) for (d,l),rs in sorted(groups.items())]

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
                        matched_model=record(matched),market_reference=record(favorites),confidence=bins,segments=segments(rows)))
    return out
