"""Experimental NHL challenger with known pregame rest and fatigue context."""
from datetime import timedelta
from nhl_team_model import fit, distribution
from nba_team_model import parse_time

def annotate(rows,games,now):
    cache={}
    for row in rows:
        tip=parse_time(row["start"])
        cutoff=min(now,tip)
        home,away=row["home"],row["away"]
        key=(tip,home,away)
        if key not in cache:
            train=[g for g in games if cutoff-timedelta(days=84)<=g[0]<cutoff]
            attack,defense,counts=fit(train,cutoff)
            if min(counts.get(home,0),counts.get(away,0))<8:
                cache[key]=None
                continue
            last={}
            for t,h,a,*_ in sorted(train):
                last[h]=last[a]=t
            def fatigue(team):
                hours=(tip-last[team]).total_seconds()/3600
                return .12 if hours<30 else 0
            hf,af=fatigue(home),fatigue(away)
            h=max(.5,min(7,3+attack[home]-defense[away]+.15-hf+af))
            a=max(.5,min(7,3+attack[away]-defense[home]-.15-af+hf))
            cache[key]=(distribution(h,a),hf,af)
        if cache[key] is None:
            continue
        dist,hf,af=cache[key]
        sign=1 if row["team"]==home else -1
        line=row.get("line") or 0
        win=sum(p for m,p in dist.items() if sign*m+line>0)
        push=sum(p for m,p in dist.items() if sign*m+line==0)
        margin=sum(sign*m*p for m,p in dist.items())
        row.update(shadow_margin=round(margin,2),shadow_probability=round(win,6),
                   shadow_push_probability=round(push,6),shadow_rest_adjustment=round(sign*2*(af-hf),2))
    return rows

def audit(games):
    from team_backtest import evaluate
    base=evaluate("NHL",games)
    by_key={(r["time"],r["home"],r["away"]):r for r in base["results"]}
    pairs=[]
    for t,h,a,hg,ag,_ in sorted(games):
        key=(t.isoformat(),h,a)
        if key not in by_key:
            continue
        cutoff=t.replace(hour=0,minute=0,second=0,microsecond=0)
        row=dict(start=t.isoformat(),home=h,away=a,team=h,market="h2h",line=None)
        annotate([row],games,cutoff)
        if "shadow_probability" not in row:
            continue
        b=by_key[key]; p=row["shadow_probability"]; actual=hg>ag
        pairs.append((b["brier"],2*(p-actual)**2,b["margin_error"],abs(row["shadow_margin"]-(hg-ag)),b["correct"],(p>=.5)==actual))
    n=len(pairs)
    keys=["baseline_brier","shadow_brier","baseline_mae","shadow_mae","baseline_accuracy","shadow_accuracy"]
    return dict(games=n,**{k:sum(p[i] for p in pairs)/n if n else None for i,k in enumerate(keys)})
