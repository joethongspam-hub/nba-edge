"""Experimental NFL rest and margin-distribution challenger."""
from datetime import timedelta
from math import exp
from nfl_team_model import fit, outcome
from nba_team_model import parse_time

def annotate(rows,games,now):
    for row in rows:
        tip=parse_time(row["start"])
        cutoff=min(now,tip)
        train=[g for g in games if cutoff-timedelta(days=126)<=g[0]<cutoff]
        ratings,counts=fit(train,cutoff)
        h,a=row["home"],row["away"]
        if min(counts.get(h,0),counts.get(a,0))<5:
            continue
        last={}
        for t,home,away,margin,neutral in sorted(train):
            last[home]=last[away]=t
        def rest(t):
            days=(tip-last[t]).total_seconds()/86400
            return -.75 if days<5 else .5 if 10<=days<=17 else 0
        adjustment=rest(h)-rest(a)
        margin=ratings[h]-ratings[a]+1.5+adjustment
        sign=1 if row["team"]==h else -1
        margin*=sign
        win,push=outcome(margin,row.get("line") or 0)
        row.update(shadow_margin=round(margin,2),shadow_probability=round(win,6),
                   shadow_push_probability=round(push,6),shadow_rest_adjustment=round(sign*adjustment,2))
    return rows

def audit(games):
    from team_backtest import evaluate
    base=evaluate("NFL",games)
    by_key={(r["time"],r["home"],r["away"]):r for r in base["results"]}
    pairs=[]
    for t,h,a,m,_ in sorted(games):
        key=(t.isoformat(),h,a)
        if key not in by_key:
            continue
        cutoff=t.replace(hour=0,minute=0,second=0,microsecond=0)
        row=dict(start=t.isoformat(),home=h,away=a,team=h,market="h2h",line=None)
        annotate([row],games,cutoff)
        if "shadow_probability" not in row:
            continue
        b=by_key[key]; p=row["shadow_probability"]; q=row["shadow_push_probability"]
        actual="win" if m>0 else "loss" if m<0 else "push"
        loss=max(0,1-p-q)
        brier=sum((prob-(label==actual))**2 for label,prob in (("win",p),("loss",loss),("push",q)))
        pairs.append((b["brier"],brier,b["margin_error"],abs(row["shadow_margin"]-m),b["correct"],("win" if p>=loss else "loss")==actual,actual!="push"))
    n=len(pairs)
    decisive=[p for p in pairs if p[6]]
    keys=["baseline_brier","shadow_brier","baseline_mae","shadow_mae"]
    result=dict(games=n,**{k:sum(p[i] for p in pairs)/n if n else None for i,k in enumerate(keys)})
    result.update(baseline_accuracy=sum(p[4] for p in decisive)/len(decisive) if decisive else None,
                  shadow_accuracy=sum(p[5] for p in decisive)/len(decisive) if decisive else None)
    return result
