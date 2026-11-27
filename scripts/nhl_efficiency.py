"""Research-only MoneyPuck xG challenger; team-level goals saved proxy, not starter ratings."""
import csv
from collections import defaultdict
from datetime import timedelta
from math import exp,isfinite
from urllib.request import Request,urlopen
from nhl_team_model import distribution

SOURCE="https://moneypuck.com/moneypuck/playerData/careers/gameByGame/all_teams.csv"
NAMES=dict(zip("ANA BOS BUF CAR CBJ CGY CHI COL DAL DET EDM FLA LAK MIN MTL NJD NSH NYI NYR OTT PHI PIT SEA SJS STL TBL TOR UTA VAN VGK WPG WSH".split(),
"Anaheim Ducks|Boston Bruins|Buffalo Sabres|Carolina Hurricanes|Columbus Blue Jackets|Calgary Flames|Chicago Blackhawks|Colorado Avalanche|Dallas Stars|Detroit Red Wings|Edmonton Oilers|Florida Panthers|Los Angeles Kings|Minnesota Wild|Montreal Canadiens|New Jersey Devils|Nashville Predators|New York Islanders|New York Rangers|Ottawa Senators|Philadelphia Flyers|Pittsburgh Penguins|Seattle Kraken|San Jose Sharks|St. Louis Blues|Tampa Bay Lightning|Toronto Maple Leafs|Utah Mammoth|Vancouver Canucks|Vegas Golden Knights|Winnipeg Jets|Washington Capitals".split("|")))

def parse(rows,history):
    lookup=defaultdict(list)
    for g in history:
        lookup[(g[1],g[2])].append(g)
    out={}
    for r in rows:
        if r.get("situation")!="all" or r.get("home_or_away")!="HOME":continue
        try:
            h,a=NAMES[r["team"]],NAMES[r["opposingTeam"]]
            date=r["gameDate"]
            date=f"{date[:4]}-{date[4:6]}-{date[6:8]}"
            matches=[g for g in lookup[(h,a)] if g[0].date().isoformat()==date or (g[0]-timedelta(days=1)).date().isoformat()==date]
            if len(matches)!=1:continue
            g=matches[0]
            xh,xa=float(r["xGoalsFor"]),float(r["xGoalsAgainst"])
            gh,ga=float(r["goalsFor"]),float(r["goalsAgainst"])
            if not all(isfinite(v) and v>=0 for v in (xh,xa,gh,ga)):continue
            out[g[:3]]=(*g,xh,xa,gh,ga)
        except (KeyError,ValueError,TypeError):continue
    return sorted(out.values())

def load(history):
    # Public downloadable file listed by MoneyPuck for non-commercial research.
    import io
    with urlopen(Request(SOURCE,headers={"User-Agent":"SPORTS-EDGE research"}),timeout=60) as response:
        with io.TextIOWrapper(response,encoding="utf-8-sig") as stream:
            return parse(csv.DictReader(stream),history)

def ratings(games,now):
    obs=defaultdict(list)
    for t,h,a,hg,ag,n,xh,xa,gh,ga in games:
        if not now-timedelta(days=84)<=t<now-timedelta(hours=24):continue
        w=exp(-(now-t).total_seconds()/86400/35)
        obs[h].append((xh,xa,xa-ga,w))
        obs[a].append((xa,xh,xh-gh,w))
    return {team:((15+sum(x*w for x,y,z,w in rows))/(5+sum(r[3] for r in rows)),
                  (15+sum(y*w for x,y,z,w in rows))/(5+sum(r[3] for r in rows)),
                  sum(z*w for x,y,z,w in rows)/(10+sum(r[3] for r in rows)),len(rows))
            for team,rows in obs.items()}

def forecast(h,a,stats,neutral=False):
    h,a=stats.get(h),stats.get(a)
    if not h or not a or min(h[3],a[3])<8:return None
    adj=0 if neutral else .15
    return distribution(max(.5,min(7,(h[0]+a[1])/2-.5*a[2]+adj)),
                        max(.5,min(7,(a[0]+h[1])/2-.5*h[2]-adj)))

def annotate(rows,games,now):
    stats=ratings(games,now)
    for r in rows:
        d=forecast(r["home"],r["away"],stats)
        if d is None:continue
        sign=1 if r["team"]==r["home"] else -1
        line=r.get("line") or 0
        x,y,z,_=stats[r["team"]]
        r.update(xg_for=round(x,2),xg_against=round(y,2),xg_saved_proxy=round(z,2),
                 xg_margin=round(sum(sign*m*p for m,p in d.items()),2),
                 xg_probability=round(sum(p for m,p in d.items() if sign*m+line>0),6),
                 xg_push=round(sum(p for m,p in d.items() if sign*m+line==0),6))

def audit(games,baseline):
    lookup={(r["time"],r["home"],r["away"]):r for r in baseline["results"]}
    pairs=[]
    for t,h,a,hg,ag,n,*_ in games:
        b=lookup.get((t.isoformat(),h,a))
        if not b:continue
        d=forecast(h,a,ratings(games,t.replace(hour=0,minute=0,second=0,microsecond=0)),n)
        if d is None:continue
        p=sum(v for m,v in d.items() if m>0)
        margin=sum(m*v for m,v in d.items())
        pairs.append((b["brier"],2*(p-(hg>ag))**2,b["margin_error"],abs(margin-hg+ag),b["correct"],(p>=.5)==(hg>ag)))
    count=len(pairs)
    keys=("baseline_brier","xg_brier","baseline_mae","xg_mae","baseline_accuracy","xg_accuracy")
    return dict(games=count,**{k:sum(p[i] for p in pairs)/count if count else None for i,k in enumerate(keys)})
