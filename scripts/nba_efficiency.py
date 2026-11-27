"""Possession estimates from completed team boxscores; independent shadow forecast."""
import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlencode
from math import exp,floor
from nba_team_model import cdf,parse_time
from team_history import canonical,week

BASE="https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
CACHE=Path("docs/nba_efficiency_cache.json")

def extract(body,event):
    teams={}
    for item in body.get("boxscore",{}).get("teams",[]):
        name=canonical(item["team"]["displayName"])
        stats={s["name"]:str(s["displayValue"]) for s in item["statistics"]}
        def attempts(key):
            return float(stats[key].split("-")[-1])
        poss=attempts("fieldGoalsMade-fieldGoalsAttempted")+.44*attempts("freeThrowsMade-freeThrowsAttempted")-float(stats["offensiveRebounds"])+float(stats["totalTurnovers"])
        if not 60<poss<170:
            raise ValueError("Invalid estimated possessions")
        teams[name]=poss
    comp=event["competitions"][0]
    sides={c["homeAway"]:c for c in comp["competitors"]}
    h,a=sides["home"],sides["away"]
    home,away=canonical(h["team"]["displayName"]),canonical(a["team"]["displayName"])
    possessions=(teams[home]+teams[away])/2
    # Normalize pace to 48 minutes using final period (NBA overtime is 5 minutes).
    period=int(event.get("status",{}).get("period",4))
    minutes=48+5*max(0,period-4)
    return dict(time=event["date"],home=home,away=away,hs=int(h["score"]),as_=int(a["score"]),poss=possessions,pace=possessions*48/minutes,neutral=bool(comp.get("neutralSite")))

def load(now,path=CACHE):
    try: cache=json.loads(path.read_text())
    except (OSError,ValueError): cache={}
    cutoff=now-timedelta(days=84)
    cache={k:v for k,v in cache.items() if cutoff<=parse_time(v["time"])<now}
    events={}
    for offset in range(0,84,7):
        for e in week(BASE+"/scoreboard",now.date()-timedelta(days=offset)):
            if e.get("status",{}).get("type",{}).get("completed") and int(e.get("season",{}).get("type",0)) in (2,3) and cutoff<=parse_time(e["date"])<now:
                events[str(e["id"])]=e
    # Bounded incremental backfill; newest completed games first.
    missing=sorted((e for k,e in events.items() if k not in cache),key=lambda e:e["date"],reverse=True)[:60]
    def get(e):
        try:
            url=BASE+"/summary?"+urlencode({"event":e["id"]})
            with urlopen(Request(url,headers={"User-Agent":"NBA-EDGE/2.0 research dashboard"}),timeout=12) as response:
                return str(e["id"]),extract(json.load(response),e)
        except Exception as exc:
            print("NBA efficiency boxscore",e["id"],type(exc).__name__)
            return str(e["id"]),None
    with ThreadPoolExecutor(max_workers=4) as pool:
        for key,value in pool.map(get,missing):
            if value is not None: cache[key]=value
    temp=path.with_suffix(".tmp")
    temp.write_text(json.dumps(cache,separators=(",",":"))+"\n")
    temp.replace(path)
    return list(cache.values()),dict(cached=len(cache),eligible=len(events),attempted=len(missing))

def ratings(games,cutoff):
    obs=defaultdict(list)
    for g in games:
        t=parse_time(g["time"])
        if not cutoff-timedelta(days=84)<=t<cutoff: continue
        w=exp(-(cutoff-t).total_seconds()/86400/35)
        h,a=g["home"],g["away"]
        hr,ar=100*g["hs"]/g["poss"],100*g["as_"]/g["poss"]
        obs[h].append((hr,ar,g["pace"],w))
        obs[a].append((ar,hr,g["pace"],w))
    total=sum(w for rows in obs.values() for _,_,_,w in rows)
    if not total:return {}
    league=sum(o*w for rows in obs.values() for o,_,_,w in rows)/total
    pace=sum(p*w for rows in obs.values() for _,_,p,w in rows)/total
    out={}
    for team,rows in obs.items():
        weight=sum(r[3] for r in rows)
        out[team]=dict(off=(4*league+sum(o*w for o,d,p,w in rows))/(4+weight),
                       defense=(4*league+sum(d*w for o,d,p,w in rows))/(4+weight),
                       pace=(4*pace+sum(p*w for o,d,p,w in rows))/(4+weight),
                       games=len(rows))
    return out

def forecast(home,away,stats,neutral=False):
    h,a=stats.get(home),stats.get(away)
    if not h or not a or min(h["games"],a["games"])<8:return None
    pace=(h["pace"]+a["pace"])/2
    margin=((h["off"]-h["defense"])-(a["off"]-a["defense"]))*pace/100+(0 if neutral else 2.5)
    return margin,pace

def annotate(rows,games,now):
    stats=ratings(games,now)
    for r in rows:
        f=forecast(r["home"],r["away"],stats)
        if f is None:continue
        margin,pace=f
        if r["team"]==r["away"]:margin=-margin
        threshold=-(r.get("line") or 0)
        win=cdf(margin/12) if r["market"]=="h2h" else 1-cdf((floor(threshold)+.5-margin)/12)
        push=0
        if r["market"]=="spreads" and threshold==int(threshold):
            push=cdf((threshold+.5-margin)/12)-cdf((threshold-.5-margin)/12)
        team=stats[r["team"]]
        r.update(efficiency_margin=round(margin,2),efficiency_probability=round(win,6),efficiency_push=round(push,6),
                 efficiency_off=round(team["off"],2),efficiency_def=round(team["defense"],2),efficiency_pace=round(pace,2))

def audit(games,baseline):
    by_key={(r["time"],r["home"],r["away"]):r for r in baseline["results"]}
    pairs=[]
    for g in games:
        t=parse_time(g["time"])
        b=by_key.get((t.isoformat(),g["home"],g["away"]))
        if not b:continue
        cutoff=t.replace(hour=0,minute=0,second=0,microsecond=0)
        f=forecast(g["home"],g["away"],ratings(games,cutoff),g["neutral"])
        if f is None:continue
        m=f[0]; actual=g["hs"]-g["as_"]; p=cdf(m/12)
        pairs.append((b["brier"],2*(p-(actual>0))**2,b["margin_error"],abs(m-actual),b["correct"],(p>=.5)==(actual>0)))
    n=len(pairs)
    keys=("baseline_brier","efficiency_brier","baseline_mae","efficiency_mae","baseline_accuracy","efficiency_accuracy")
    return dict(games=n,**{k:sum(p[i] for p in pairs)/n if n else None for i,k in enumerate(keys)})
