"""NBA challenger using known pregame rest and venue context; baseline unchanged."""
from datetime import timedelta
from collections import defaultdict
from math import floor
from nba_team_model import fit, cdf, parse_time

def context(games, cutoff, tip):
    last={}
    venue=defaultdict(list)
    ratings,counts=fit(games,cutoff)
    for t,h,a,m,neutral in sorted(games):
        if t>=cutoff:
            continue
        last[h]=last[a]=t
        if not neutral:
            residual=m-(ratings[h]-ratings[a]+2.5)
            venue[h].append(residual)
            venue[a].append(-residual)
    return ratings,counts,last,venue

def annotate(rows,games,now):
    for row in rows:
        tip=parse_time(row["start"])
        cutoff=min(now,tip)
        train=[g for g in games if g[0]<cutoff and g[0]>=cutoff-timedelta(days=84)]
        ratings,counts,last,venue=context(train,cutoff,tip)
        h,a=row["home"],row["away"]
        if min(counts.get(h,0),counts.get(a,0))<8:
            continue
        # Only use last completed game known at snapshot. Future schedules are not inferred.
        h_rest=(tip-last[h]).total_seconds()/3600
        a_rest=(tip-last[a]).total_seconds()/3600
        rest_adjust=(1 if a_rest<30 else 0)-(1 if h_rest<30 else 0)
        # Shrink observed home/away residuals toward zero.
        hv=venue[h]; av=venue[a]
        venue_adjust=.25*(sum(hv)/(len(hv)+8)-sum(av)/(len(av)+8))
        margin=ratings[h]-ratings[a]+2.5+rest_adjust+venue_adjust
        sign=1 if row["team"]==h else -1
        margin*=sign
        threshold=-(row.get("line") or 0)
        win=cdf(margin/12) if row["market"]=="h2h" else 1-cdf((floor(threshold)+.5-margin)/12)
        row.update(shadow_margin=round(margin,2),shadow_probability=round(win,6),
                   shadow_rest_adjustment=round(sign*rest_adjust,2),shadow_venue_adjustment=round(sign*venue_adjust,2))
    return rows

def audit(games):
    from team_backtest import evaluate
    base=evaluate("NBA",games)
    by_key={(r["time"],r["home"],r["away"]):r for r in base["results"]}
    pairs=[]
    for game in sorted(games):
        t,h,a,m,_=game
        key=(t.isoformat(),h,a)
        if key not in by_key:
            continue
        cutoff=t.replace(hour=0,minute=0,second=0,microsecond=0)
        row=dict(start=t.isoformat(),home=h,away=a,team=h,market="h2h",line=None)
        annotate([row],games,cutoff)
        if "shadow_probability" not in row:
            continue
        b=by_key[key]; p=row["shadow_probability"]; actual=m>0
        pairs.append((b["brier"],2*(p-actual)**2,b["margin_error"],abs(row["shadow_margin"]-m),b["correct"],(p>=.5)==actual))
    n=len(pairs)
    keys=["baseline_brier","shadow_brier","baseline_mae","shadow_mae","baseline_accuracy","shadow_accuracy"]
    return dict(games=n,**{k:sum(p[i] for p in pairs)/n if n else None for i,k in enumerate(keys)})
