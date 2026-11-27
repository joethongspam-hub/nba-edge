"""Research-only historical test with realized starters, not archived pregame announcements."""
import csv
import io
import json
import math
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
from nhl_team_model import fit, distribution
from nhl_goalie_model import clamp, probabilities
from nhl_efficiency import NAMES

ET=ZoneInfo("America/New_York")
YEARS=(2023,2024,2025,2026)
COEFFICIENTS=(0.,.25,.5,.75,1.)
ROOT="https://moneypuck.com/moneypuck/playerData"
OUT=Path("docs/nhl_goalie_backtest.json")

def fetch(url):
    with urlopen(Request(url,headers={"User-Agent":"SPORTS-EDGE research"}),timeout=30) as r:
        return r.read()

def csv_rows(url):
    return list(csv.DictReader(io.StringIO(fetch(url).decode("utf-8-sig"))))

def team(code):
    return NAMES.get(code,{"ARI":"Arizona Coyotes"}.get(code))

def parallel(items,fn,workers=4):
    results,errors=[],[]
    def safe(item):
        try:return item,fn(item),None
        except Exception as e:return item,None,type(e).__name__
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for item,value,error in pool.map(safe,items):
            if error:errors.append({"item":str(item),"error":error})
            else:results.append((item,value))
    return results,errors

def parse_goalie(ident,rows):
    out={}
    for r in rows:
        if r.get("situation")!="all":continue
        try:
            y=int(r["season"]); day=datetime.strptime(r["gameDate"],"%Y%m%d").date()
            gid=str(r["gameId"]); t=team(r["playerTeam"])
            h=float(r["icetime"])/3600; x=float(r["xGoals"]); g=float(r["goals"])
            if y not in YEARS or str(r["playerId"])!=ident or not t or not all(map(math.isfinite,(h,x,g))) or not 0<h<=1.1 or min(x,g)<0:continue
            out[gid]=(day,y,ident,t,h,x-g)
        except (KeyError,ValueError,TypeError):continue
    return list(out.values())

def box(game_id):
    d=json.loads(fetch("https://api-web.nhle.com/v1/gamecenter/"+game_id+"/boxscore"))
    if str(d.get("id"))!=game_id or d.get("gameState") not in ("FINAL","OFF") or d.get("gameType")!=2:return None
    h,a=d["homeTeam"],d["awayTeam"]
    hn,an=team(h["abbrev"]),team(a["abbrev"])
    if not hn or not an:return None
    ids=[]
    for side in ("home","away"):
        goalies=d["playerByGameStats"][side+"Team"]["goalies"]
        starters=[str(g["playerId"]) for g in goalies if g.get("starter") is True]
        if len(starters)!=1:return None
        ids.append(starters[0])
    t=datetime.fromisoformat(d["startTimeUTC"].replace("Z","+00:00"))
    day=datetime.strptime(d["gameDate"],"%Y-%m-%d").date()
    return (day,t,hn,an,int(h["score"]),int(a["score"]),ids[0],ids[1],int(game_id[:4]),bool(d.get("neutralSite",False)))

def relative(person,team_totals,year,ident,t):
    h,g=person.get((year,ident),(0.,0.))
    ph,pg=person.get((year-1,ident),(0.,0.))
    th,tg=team_totals.get((year,t),(0.,0.))
    effective=h+.5*ph
    if h<=0 or effective<5 or th<=0:return None
    return g/(effective+15)+.5*pg/(effective+15)-tg/(th+15)

def evaluate(boxes,observations):
    person=defaultdict(lambda:[0.,0.]); teams=defaultdict(lambda:[0.,0.])
    obs=sorted(observations); i=0; history=[]; stats=defaultdict(lambda:defaultdict(list))
    coverage=defaultdict(lambda:{"completed":0,"evaluated":0})
    for day,t,h,a,hg,ag,hi,ai,year,neutral in sorted(boxes):
        while i<len(obs) and obs[i][0]<day:
            _,y,p,tm,hours,saved=obs[i]; i+=1
            for dest,key in ((person,(y,p)),(teams,(y,tm))):
                dest[key][0]+=hours;dest[key][1]+=saved
        coverage[year]["completed"]+=1
        cutoff=datetime.combine(day,datetime.min.time(),ET).astimezone(timezone.utc)
        # Match live model's 84-day lookback, excluding all same-day games.
        prior=[g for g in history if cutoff-timedelta(days=84)<=g[0]<cutoff and g[0].astimezone(ET).date()<day]
        history.append((t,h,a,hg,ag,neutral))
        if year==2023 or hg==ag:continue
        dh,da=relative(person,teams,year,hi,h),relative(person,teams,year,ai,a)
        if dh is None or da is None:continue
        attack,defense,counts=fit(prior,cutoff)
        if min(counts.get(h,0),counts.get(a,0))<8:continue
        hr=clamp(3+attack[h]-defense[a]+.15); ar=clamp(3+attack[a]-defense[h]-.15)
        coverage[year]["evaluated"]+=1
        for c in COEFFICIENTS:
            adjust=lambda v:max(-.5,min(.5,c*v))
            p,_,margin=probabilities(distribution(clamp(hr-adjust(da)),clamp(ar-adjust(dh))),1,0)
            stats[year][c].append(((p-int(hg>ag))**2,int((p>=.5)==(hg>ag)),abs(margin-hg+ag)))
    result={}
    for year,cohorts in stats.items():
        result[str(year)]={str(c):{"games":len(v),"brier":sum(x[0] for x in v)/len(v),
            "accuracy":sum(x[1] for x in v)/len(v),"margin_mae":sum(x[2] for x in v)/len(v)} for c,v in cohorts.items()}
    tuning=result.get("2024",{})
    selected=min(tuning,key=lambda c:(tuning[c]["brier"],float(c))) if tuning else None
    return result,dict(coverage),selected

def main():
    summaries,errors=parallel(YEARS,lambda y:csv_rows(f"{ROOT}/seasonSummary/{y}/regular/goalies.csv"))
    ids=sorted({str(r["playerId"]) for _,rows in summaries for r in rows if r.get("playerId") and r.get("situation")=="all"})
    career,errs=parallel(ids,lambda p:parse_goalie(p,csv_rows(f"{ROOT}/careers/gameByGame/regular/goalies/{p}.csv")))
    errors+=errs
    observations=[o for _,rows in career for o in rows]
    # Discover games independently from the official schedule, not goalie performance.
    weeks=[]
    for y in YEARS:
        start=datetime(y,9,25,tzinfo=timezone.utc)
        end=min(datetime(y+1,5,1,tzinfo=timezone.utc),datetime.now(timezone.utc))
        while start<end:
            weeks.append(start.date().isoformat());start+=timedelta(days=7)
    schedules,errs=parallel(weeks,lambda day:json.loads(fetch("https://api-web.nhle.com/v1/schedule/"+day)))
    errors+=errs
    gids=sorted({str(g["id"]) for _,d in schedules for week in d.get("gameWeek",[]) for g in week.get("games",[])
                 if g.get("gameType")==2 and g.get("gameState") in ("FINAL","OFF") and int(str(g["id"])[:4]) in YEARS})
    boxes,errs=parallel(gids,box,workers=4);errors+=errs
    valid=[b for _,b in boxes if b is not None]
    results,coverage,selected=evaluate(valid,observations)
    report={"updated":datetime.now(timezone.utc).isoformat(),"research_only":True,
            "method":"historical realized starters, prior-day-only season-weighted ratings; no announcement timestamps",
            "attribution":"MoneyPuck.com / NHL API","goalie_ids":len(ids),"career_files":len(career),
            "observations":len(observations),"scheduled_final_games":len(gids),"verified_boxscores":len(valid),
            "errors":errors,"coverage":coverage,"results":results,"selected_on_2024":selected,
            "evaluation_season":2025,"additional_validation_season":2026,
            "limitations":["Realized starters are not evidence of pregame confirmation; optimistic information availability.",
                           "Missing historical files or boxscores may bias coverage; no production changes.",
                           "No historical odds or betting ROI tested."]}
    OUT.write_text(json.dumps(report,indent=2)+"\n")
    print("Historical goalie audit:",len(valid),"verified games;",len(errors),"source errors;",coverage)
if __name__=="__main__":main()
