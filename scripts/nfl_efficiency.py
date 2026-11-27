"""nflverse team weekly stats (https://github.com/nflverse/nflverse-data).
Historical opponent EPA is inferred from paired team rows, not current rankings.
"""
import csv
import io
from collections import defaultdict
from datetime import timedelta
from math import exp,isfinite
from urllib.request import Request,urlopen
from nfl_team_model import outcome
from nba_team_model import parse_time

BASE="https://github.com/nflverse/nflverse-data/releases/download/stats_team/stats_team_week_"
NAMES=dict(zip("ARI ATL BAL BUF CAR CHI CIN CLE DAL DEN DET GB HOU IND JAX KC LV LAC LA MIA MIN NE NO NYG NYJ PHI PIT SEA SF TB TEN WAS".split(),
    "Arizona Cardinals|Atlanta Falcons|Baltimore Ravens|Buffalo Bills|Carolina Panthers|Chicago Bears|Cincinnati Bengals|Cleveland Browns|Dallas Cowboys|Denver Broncos|Detroit Lions|Green Bay Packers|Houston Texans|Indianapolis Colts|Jacksonville Jaguars|Kansas City Chiefs|Las Vegas Raiders|Los Angeles Chargers|Los Angeles Rams|Miami Dolphins|Minnesota Vikings|New England Patriots|New Orleans Saints|New York Giants|New York Jets|Philadelphia Eagles|Pittsburgh Steelers|Seattle Seahawks|San Francisco 49ers|Tampa Bay Buccaneers|Tennessee Titans|Washington Commanders".split("|")))
NAMES.update(LAR=NAMES["LA"],JAC=NAMES["JAX"],WSH=NAMES["WAS"])

def parse(rows,history):
    grouped=defaultdict(list)
    for row in rows:
        if row.get("season_type") not in ("REG","POST"):continue
        try:
            team=NAMES[row["team"]]
            passing,rushing=float(row["passing_epa"]),float(row["rushing_epa"])
            if not all(map(isfinite,(passing,rushing))):continue
            grouped[row["game_id"]].append((team,passing,rushing))
        except (KeyError,ValueError,TypeError):continue
    matchups=defaultdict(list)
    for g in history:
        matchups[frozenset(g[1:3])].append(g)
    result=[]
    # Game IDs identify opponents and week, but not date. Pair chronological
    # occurrences only when every occurrence in the season is accounted for.
    pairs=defaultdict(list)
    for key,values in grouped.items():
        if len(values)==2 and values[0][0]!=values[1][0]:
            pairs[frozenset(x[0] for x in values)].append((key,values))
    for teams,items in pairs.items():
        games=sorted(matchups.get(teams,[]))
        if len(games)!=len(items):continue
        for g,(_,values) in zip(games,sorted(items)):
            t,h,a,m,neutral=g
            by={x[0]:x[1:] for x in values}
            result.append((t,h,a,m,neutral,*by[h],*by[a]))
    return sorted(result)

def load(now,history):
    season=now.year if now.month>=7 else now.year-1
    with urlopen(Request(BASE+str(season)+".csv",headers={"User-Agent":"SPORTS-EDGE research"}),timeout=25) as response:
        rows=list(csv.DictReader(io.StringIO(response.read().decode("utf-8-sig"))))
    return parse(rows,history)

def ratings(games,cutoff):
    obs=defaultdict(list)
    for t,h,a,m,n,hp,hr,ap,ar in games:
        # Allow a full day for nflverse's nightly publishing schedule.
        if not cutoff-timedelta(days=126)<=t<cutoff-timedelta(hours=24):continue
        w=exp(-(cutoff-t).total_seconds()/86400/56)
        obs[h].append((hp,hr,ap+ar,w))
        obs[a].append((ap,ar,hp+hr,w))
    return {team:(sum(p*w for p,r,d,w in rows)/(3+sum(x[3] for x in rows)),
                  sum(r*w for p,r,d,w in rows)/(3+sum(x[3] for x in rows)),
                  sum(d*w for p,r,d,w in rows)/(3+sum(x[3] for x in rows)),len(rows))
            for team,rows in obs.items()}

def margin(home,away,stats,neutral=False):
    h,a=stats.get(home),stats.get(away)
    if not h or not a or min(h[3],a[3])<5:return None
    return .5*((h[0]+h[1]-h[2])-(a[0]+a[1]-a[2]))+(0 if neutral else 1.5)

def annotate(rows,games,now):
    stats=ratings(games,now)
    for r in rows:
        m=margin(r["home"],r["away"],stats)
        if m is None:continue
        if r["team"]==r["away"]:m=-m
        p,q=outcome(m,r.get("line") or 0)
        passing,rushing,allowed,_=stats[r["team"]]
        r.update(epa_margin=round(m,2),epa_probability=round(p,6),epa_push=round(q,6),
                 epa_passing=round(passing,2),epa_rushing=round(rushing,2),epa_allowed=round(allowed,2))

def audit(games,baseline):
    lookup={(r["time"],r["home"],r["away"]):r for r in baseline["results"]}
    pairs=[]
    for t,h,a,m,n,*_ in games:
        b=lookup.get((t.isoformat(),h,a))
        if not b:continue
        cutoff=t.replace(hour=0,minute=0,second=0,microsecond=0)
        pred=margin(h,a,ratings(games,cutoff),n)
        if pred is None:continue
        p,q=outcome(pred,0)
        actual="win" if m>0 else "loss" if m<0 else "push"
        score=sum((v-(actual==label))**2 for v,label in [(p,"win"),(q,"push"),(1-p-q,"loss")])
        pairs.append((b["brier"],score,b["margin_error"],abs(pred-m),b["correct"],(p>=1-p-q)==(m>0),m!=0))
    count=len(pairs)
    decisive=[p for p in pairs if p[6]]
    return dict(games=count,baseline_brier=sum(p[0] for p in pairs)/count if count else None,
                epa_brier=sum(p[1] for p in pairs)/count if count else None,
                baseline_mae=sum(p[2] for p in pairs)/count if count else None,
                epa_mae=sum(p[3] for p in pairs)/count if count else None,
                baseline_accuracy=sum(p[4] for p in decisive)/len(decisive) if decisive else None,
                epa_accuracy=sum(p[5] for p in decisive)/len(decisive) if decisive else None)
