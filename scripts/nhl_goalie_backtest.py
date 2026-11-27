"""Research-only historical test with realized starters, not archived pregame announcements."""
import csv
import io
import json
import math
import time
from urllib.error import HTTPError, URLError
from email.utils import parsedate_to_datetime
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
CACHE=Path(".research-cache/nhl-goalies-v1")
MIN_COVERAGE=.90
MIN_EVALUATED=2000

def fetch(url):
    with urlopen(Request(url,headers={"User-Agent":"SPORTS-EDGE research"}),timeout=30) as r:
        return r.read()

def csv_rows(url):
    return list(csv.DictReader(io.StringIO(fetch(url).decode("utf-8-sig"))))

def error_label(exc):
    return "HTTP_"+str(exc.code) if isinstance(exc,HTTPError) else type(exc).__name__

def retry_delay(exc, attempt):
    delay=5*2**attempt
    if isinstance(exc,HTTPError):
        if exc.code not in (429,500,502,503,504):
            return None
        value=exc.headers.get("Retry-After") if exc.headers else None
        if value:
            try:delay=max(delay,float(value))
            except ValueError:
                try:delay=max(delay,(parsedate_to_datetime(value)-datetime.now(timezone.utc)).total_seconds())
                except (ValueError,TypeError):pass
    elif not isinstance(exc,(URLError,TimeoutError)):
        return None
    return delay

def paced_rows(url):
    for attempt in range(3):
        time.sleep(3)
        try:return csv_rows(url)
        except Exception as exc:
            delay=retry_delay(exc,attempt)
            if delay is None or delay>120 or attempt==2:raise
            time.sleep(delay)

def write_cache(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data,separators=(",",":")))
    tmp.replace(path)

def career_downloads(ids):
    results,errors=[],[]
    cached_count=0
    pending=[]
    # Today's files include the active season; old cache entries must be refreshed.
    today=datetime.now(ET).date().isoformat()
    for ident in ids:
        path=CACHE/"careers"/(ident+".json")
        try:
            cached=json.loads(path.read_text())
            if cached["date"]!=today or not cached["rows"]:raise ValueError("stale")
            rows=[(datetime.fromisoformat(r[0]).date(),*r[1:]) for r in cached["rows"]]
            results.append((ident,rows));cached_count+=1
        except (OSError,ValueError,KeyError,TypeError):
            pending.append((ident,path))
    stopped=False
    for ident,path in pending:
        if stopped:
            errors.append({"item":ident,"error":"deferred_source_limit"})
            continue
        try:
            rows=parse_goalie(ident,paced_rows(f"{ROOT}/careers/gameByGame/regular/goalies/{ident}.csv"))
            if not rows:raise ValueError("empty career")
            write_cache(path,{"date":today,"rows":[[r[0].isoformat(),*r[1:]] for r in rows]})
            results.append((ident,rows))
        except Exception as exc:
            errors.append({"item":ident,"error":error_label(exc)})
            if isinstance(exc,HTTPError) and exc.code in (403,429):
                stopped=True
    return results,errors,cached_count

def cached_box(game_id):
    path=CACHE/"boxes"/(game_id+".json")
    try:
        b=json.loads(path.read_text())
        return (datetime.fromisoformat(b[0]).date(),datetime.fromisoformat(b[1]),*b[2:])
    except (OSError,ValueError,TypeError,IndexError):pass
    b=box(game_id)
    if b is not None:write_cache(path,[b[0].isoformat(),b[1].isoformat(),*b[2:]])
    return b

def team(code):
    return NAMES.get(code,{"ARI":"Arizona Coyotes"}.get(code))

def parallel(items,fn,workers=4):
    results,errors=[],[]
    def safe(item):
        try:return item,fn(item),None
        except Exception as e:return item,None,error_label(e)
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
    summaries,errors=parallel(YEARS,lambda y:paced_rows(f"{ROOT}/seasonSummary/{y}/regular/goalies.csv"),workers=1)
    ids=sorted({str(r["playerId"]) for _,rows in summaries for r in rows if r.get("playerId") and r.get("situation")=="all"})
    career,errs,cache_hits=career_downloads(ids)
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
    boxes,errs=parallel(gids,cached_box,workers=4);errors+=errs
    valid=[b for _,b in boxes if b is not None]
    results,coverage,selected=evaluate(valid,observations)
    source_coverage=len(career)/len(ids) if ids else 0
    box_coverage=len(valid)/len(gids) if gids else 0
    paired_games=sum(coverage.get(y,{}).get("evaluated",0) for y in (2024,2025))
    usable=(len(summaries)==len(YEARS) and source_coverage>=MIN_COVERAGE and box_coverage>=MIN_COVERAGE and paired_games>=MIN_EVALUATED and all(coverage.get(y,{}).get("evaluated",0)>=800 for y in (2024,2025)))
    report={"updated":datetime.now(timezone.utc).isoformat(),"research_only":True,
            "method":"historical realized starters, prior-day-only season-weighted ratings; no announcement timestamps",
            "attribution":"MoneyPuck.com / NHL API","goalie_ids":len(ids),"career_files":len(career),
            "observations":len(observations),"scheduled_final_games":len(gids),"verified_boxscores":len(valid),
            "errors":errors,"coverage":coverage,"results":results,"selected_on_2024":selected if usable else None,
            "exploratory_selection":selected,"actionable":usable,"career_cache_hits":cache_hits,
            "source_coverage":source_coverage,"box_coverage":box_coverage,"paired_games":paired_games,
            "minimum_source_coverage":MIN_COVERAGE,"minimum_paired_games":MIN_EVALUATED,
            "evaluation_season":2025,"additional_validation_season":2026,
            "limitations":["Realized starters are not evidence of pregame confirmation; optimistic information availability.",
                           "Missing historical files or boxscores may bias coverage; no production changes.",
                           "No historical odds or betting ROI tested."]}
    OUT.write_text(json.dumps(report,indent=2)+"\n")
    print("Historical goalie audit:",len(valid),"verified games;",len(errors),"source errors;",coverage)
if __name__=="__main__":main()
