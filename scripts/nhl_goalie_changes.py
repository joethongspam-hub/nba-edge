"""Compare observed starters without treating missing data as a replacement."""
import json
from pathlib import Path
from datetime import timedelta
from team_history import parse_time
from nhl_goalie_ratings import name_key

PATH=Path("docs/nhl_goalie_changes.json")
THRESHOLD=.02

def update(rows,now,path=PATH):
    previous=json.loads(path.read_text())["games"] if path.exists() else {}
    games={k:v for k,v in previous.items() if parse_time(v["start"])>now}
    changes=[]
    seen=set()
    for r in rows:
        if r.get("market")!="h2h" or r["team"]!=r["home"]:
            continue
        start=parse_time(r["start"])
        if not now<start<=now+timedelta(hours=36):
            continue
        key="|".join((r["home"],r["away"],start.isoformat()))
        if key in seen:continue
        seen.add(key)
        old=games.get(key,{})
        current={"start":start.isoformat(),"home":r["home"],"away":r["away"],
                 "probability":r.get("goalie_probability"),"checked_at":now.isoformat()}
        for side in ("home","away"):
            g=r.get("goalie_"+side,{})
            prior=old.get(side,{})
            if not g.get("name") or g.get("status") not in ("confirmed","projected"):
                current[side]=prior
                continue
            current[side]={"name":g["name"],"status":g["status"]}
            if not prior.get("name"):continue
            replacement=name_key(prior["name"])!=name_key(g["name"])
            confirmation=not replacement and prior.get("status")=="projected" and g["status"]=="confirmed"
            if not (replacement or confirmation):continue
            # Compare incremental goalie effect rather than unrelated team-model movement.
            before=old.get("effect")
            after=r.get("goalie_probability_delta")
            delta=after-before if before is not None and after is not None else None
            changes.append({"team":r[side],"home":r["home"],"away":r["away"],
                            "start":start.isoformat(),"before":prior,"after":current[side],
                            "type":"replacement" if replacement else "confirmation",
                            "home_probability_effect_change":delta,
                            "alert":delta is not None and abs(delta)>=THRESHOLD and start<=now+timedelta(hours=6)})
        current["effect"]=r.get("goalie_probability_delta")
        games[key]=current
    result={"updated":now.isoformat(),"games":games,"changes":changes,
            "alerts":sum(c["alert"] for c in changes),"research_only":True}
    tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(result,indent=2)+"\n")
    tmp.replace(path)
    return {"changes":len(changes),"alerts":result["alerts"],"threshold":THRESHOLD}
