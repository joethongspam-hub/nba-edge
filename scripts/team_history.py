"""Public scoreboard history with bounded requests and explicit coverage errors."""
from datetime import datetime, timedelta
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from concurrent.futures import ThreadPoolExecutor
import json

def parse_time(value):
    return datetime.fromisoformat(value.replace("Z","+00:00"))

def canonical(name):
    return {"LA Clippers":"Los Angeles Clippers", "LA Rams":"Los Angeles Rams",
            "LA Chargers":"Los Angeles Chargers", "NY Giants":"New York Giants",
            "NY Jets":"New York Jets", "Utah Hockey Club":"Utah Mammoth", "St Louis Blues":"St. Louis Blues"}.get(name,name)

def board(base, dates):
    url=base+"?"+urlencode({"dates":dates,"limit":100})
    req=Request(url,headers={"User-Agent":"NBA-EDGE/2.0 research dashboard","Accept":"application/json"})
    with urlopen(req,timeout=12) as response:
        data=json.load(response)
    if not isinstance(data,dict) or not isinstance(data.get("events"),list):
        raise ValueError("Scoreboard response missing events")
    return data["events"]

def week(base,end):
    start=end-timedelta(days=6)
    try:
        events=board(base,start.strftime("%Y%m%d")+"-"+end.strftime("%Y%m%d"))
        if len(events)>=100:
            raise ValueError("Scoreboard range may be truncated")
        if any(not start<=parse_time(e["date"]).date()<=end+timedelta(days=1) for e in events):
            raise ValueError("Scoreboard returned wrong date range")
        return events
    except Exception as exc:
        print("Scoreboard range fallback:",type(exc).__name__,start,end)
        events=[]
        for offset in range(7):
            events.extend(board(base,(start+timedelta(days=offset)).strftime("%Y%m%d")))
        return events

def parse_events(events,now,sport):
    games={}
    malformed=0
    for event in events:
        if not event.get("status",{}).get("type",{}).get("completed"):
            continue
        try:
            if int(event.get("season",{}).get("type",0)) not in (2,3):
                continue
            t=parse_time(event["date"])
            if t>=now:
                continue
            comp=event["competitions"][0]
            teams={c["homeAway"]:c for c in comp["competitors"]}
            h,a=teams["home"],teams["away"]
            home,away=canonical(h["team"]["displayName"]),canonical(a["team"]["displayName"])
            hs,as_=int(h["score"]),int(a["score"])
            neutral=bool(comp.get("neutralSite"))
            if home==away or min(hs,as_)<0 or (sport!="NFL" and hs==as_):
                raise ValueError("Invalid final score")
            games[event["id"]]=(t,home,away,hs,as_,neutral) if sport=="NHL" else (t,home,away,hs-as_,neutral)
        except (ValueError,TypeError,KeyError,IndexError,AttributeError):
            malformed+=1
    if malformed:
        print(sport,"Malformed final events skipped:",malformed)
    return sorted(games.values())

def history(base,now,sport,days):
    ends=[now.date()-timedelta(days=i) for i in range(0,days,7)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        batches=list(pool.map(lambda end:week(base,end),ends))
    games=parse_events([e for batch in batches for e in batch],now,sport)
    print(sport,"completed games:",len(games))
    return games
