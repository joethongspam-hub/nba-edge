"""Read-only source probe; no Odds API requests or prediction changes."""
import json
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from zoneinfo import ZoneInfo
from pathlib import Path

ESPN = "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard"
SCORE = "https://api.thescore.com/nhl/events"

def fetch(url):
    try:
        with urlopen(Request(url, headers={"Accept":"application/json","User-Agent":"Sports Edge research"}), timeout=20) as response:
            return json.load(response), None
    except HTTPError as exc:
        return None, "HTTP_"+str(exc.code)
    except Exception as exc:
        return None, type(exc).__name__

def fields(node, path="", depth=0):
    if depth > 12:
        return []
    result = []
    if isinstance(node, dict):
        for key, value in node.items():
            loc = path+"."+key
            if any(word in key.lower() for word in ("goalie","goaltender","probable","starter","lineup")):
                result.append({"path":loc,"sample":str(value)[:4000]})
            else:
                result.extend(fields(value,loc,depth+1))
    elif isinstance(node,list):
        for i, value in enumerate(node[:40]):
            result.extend(fields(value,path+"["+str(i)+"]",depth+1))
    return result[:100]

def main():
    now = datetime.now(timezone.utc)
    today = now.astimezone(ZoneInfo("America/New_York")).date()
    output = {"checked_at":now.isoformat(),"espn":[],"thescore":[]}
    for day in (today,today+timedelta(days=1)):
        data,error = fetch(ESPN+"?dates="+day.strftime("%Y%m%d"))
        entry = {"date":str(day),"error":error,"games":[]}
        for event in (data or {}).get("events",[]):
            entry["games"].append({"id":event.get("id"),"name":event.get("name"),
                                   "start":event.get("date"),"fields":fields(event)})
        output["espn"].append(entry)
    data,error = fetch(SCORE)
    events = data if isinstance(data,list) else (data or {}).get("events",[])
    output["thescore"] = {"error":error,"event_count":len(events),"events":[]}
    for event in events[:32]:
        if not isinstance(event,dict):
            continue
        entry = {"id":event.get("id"),"start":event.get("game_date"),
                 "keys":list(event),"fields":fields(event)}
        output["thescore"]["events"].append(entry)
    target = Path("docs/nhl_goalie_probe.json")
    target.write_text(json.dumps(output,indent=2)+"\n",encoding="utf-8")
    print("ESPN game count:",sum(len(d["games"]) for d in output["espn"]))
    print("theScore event count:",len(events))

if __name__ == "__main__":
    main()
