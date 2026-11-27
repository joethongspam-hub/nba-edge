"""Explore one-factor changes to baseline ratings, without promoting live settings."""
from collections import defaultdict
from datetime import timedelta
from math import exp,floor
from nba_team_model import cdf
from nhl_team_model import distribution

DEFAULTS={"NBA":(84,35,4,2.5,12),"NFL":(126,56,3,1.5,13.5),"NHL":(84,35,5,.15,None)}

def candidates(sport):
    base=DEFAULTS[sport]
    out=[base]
    for i,values in enumerate(([42,63] if sport!="NFL" else [70,98],
                                [base[1]*.5,base[1]*1.5],
                                [base[2]*.5,base[2]*2],
                                [0,base[3]*1.5],
                                [] if sport=="NHL" else [base[4]*.8,base[4]*1.2])):
        for value in values:
            p=list(base);p[i]=value;out.append(tuple(p))
    return out

def fit(sport,games,cutoff,params):
    lookback,decay,prior,home,_=params
    obs=defaultdict(list)
    for g in games:
        t,h,a=g[:3]
        if not cutoff-timedelta(days=lookback)<=t<cutoff:continue
        w=exp(-(cutoff-t).total_seconds()/86400/decay)
        adj=0 if g[-1] else home
        if sport=="NHL":
            hg,ag=g[3:5]
            obs[h].append((a,hg-adj,ag+adj,w))
            obs[a].append((h,ag+adj,hg-adj,w))
        else:
            m=g[3]-adj
            obs[h].append((a,m,w))
            obs[a].append((h,-m,w))
    counts={t:len(rows) for t,rows in obs.items()}
    weight={t:prior+sum(r[-1] for r in rows) for t,rows in obs.items()}
    strength=dict.fromkeys(obs,0.0)
    defense=dict.fromkeys(obs,0.0)
    for _ in range(40):
        if sport=="NHL":
            new_s={t:sum(w*(gf-3+defense[o]) for o,gf,ga,w in rows)/weight[t] for t,rows in obs.items()}
            new_d={t:sum(w*(3+strength[o]-ga) for o,gf,ga,w in rows)/weight[t] for t,rows in obs.items()}
            strength,defense=new_s,new_d
        else:
            strength={t:sum(w*(m+strength[o]) for o,m,w in rows)/weight[t] for t,rows in obs.items()}
    return strength,defense,counts

def predict(sport,state,game,params):
    s,d,counts=state
    h,a=game[1:3]
    if min(counts.get(h,0),counts.get(a,0))<(5 if sport=="NFL" else 8):return None
    # Match existing primary forecast convention (designated home advantage).
    adj=params[3]
    if sport=="NHL":
        dist=distribution(max(.5,min(7,3+s[h]-d[a]+adj)),max(.5,min(7,3+s[a]-d[h]-adj)))
        return sum(p for m,p in dist.items() if m>0),0,sum(m*p for m,p in dist.items())
    m=s[h]-s[a]+adj
    sd=params[4]
    if sport=="NBA":return cdf(m/sd),0,m
    return 1-cdf((.5-m)/sd),cdf((.5-m)/sd)-cdf((-.5-m)/sd),m

def forecasts(sport,games,params):
    out={}
    cache={}
    for g in sorted(games):
        t,h,a=g[:3]
        cutoff=t.replace(hour=0,minute=0,second=0,microsecond=0)
        if cutoff not in cache:cache[cutoff]=fit(sport,games,cutoff,params)
        pred=predict(sport,cache[cutoff],g,params)
        if pred is None:continue
        p,q,m=pred
        actual=g[3]-g[4] if sport=="NHL" else g[3]
        label=0 if actual>0 else 1 if actual<0 else 2
        out[(t,h,a)]=(sum((v-(i==label))**2 for i,v in enumerate((p,1-p-q,q))),abs(m-actual),int((0 if p>=1-p-q else 1)==label),label!=2)
    return out

def metrics(rows):
    n=len(rows);decisive=[r for r in rows if r[3]]
    return dict(games=n,brier=sum(r[0] for r in rows)/n if n else None,
                mae=sum(r[1] for r in rows)/n if n else None,
                accuracy=sum(r[2] for r in decisive)/len(decisive) if decisive else None)

def audit(sport,games):
    params=candidates(sport)
    runs=[forecasts(sport,games,p) for p in params]
    # Identical game set for all configurations; no coverage advantage.
    common=sorted(set(runs[0]).intersection(*(set(r) for r in runs[1:])))
    if len(common)<60:return dict(status="Insufficient common games",games=len(common))
    split=common[int(.6*len(common))][0].date()
    train=[k for k in common if k[0].date()<split]
    test=[k for k in common if k[0].date()>=split]
    if len(train)<30 or len(test)<20:return dict(status="Insufficient chronological sample",games=len(common))
    scores=[metrics([r[k] for k in train]) for r in runs]
    winner=min(range(len(runs)),key=lambda i:scores[i]["brier"])
    fields=("lookback","decay","prior","home_advantage","margin_sd")
    return dict(status="Experimental holdout",games=len(common),training_games=len(train),split=split.isoformat(),
                tested=len(runs),baseline_params=dict(zip(fields,params[0])),selected_params=dict(zip(fields,params[winner])),
                baseline=metrics([runs[0][k] for k in test]),challenger=metrics([runs[winner][k] for k in test]),
                training=[dict(params=dict(zip(fields,p)),**score) for p,score in zip(params,scores)])
