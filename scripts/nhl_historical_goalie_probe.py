"""Bounded source audit; never infers a starter from minutes or uses paid odds."""
import csv
import io
import json
from pathlib import Path
from datetime import datetime, timezone
from urllib.request import Request,urlopen
from urllib.error import HTTPError

def fetch(url, limit=4000000):
    with urlopen(Request(url,headers={"User-Agent":"SPORTS-EDGE research"}),timeout=25) as r:
        return r.read(limit)

def probe():
    report={"updated":datetime.now(timezone.utc).isoformat(),"sources":[],"research_only":True}
    urls=[
        "https://moneypuck.com/moneypuck/playerData/careers/gameByGame/regular/goalies/8480045.csv",
        "https://moneypuck.com/moneypuck/playerData/careers/gameByGame/regular/goalies/8475683.csv",
        "https://moneypuck.com/moneypuck/playerData/careers/gameByGame/regular/goalies/8474593.csv",
    ]
    for url in urls:
        entry={"url":url}
        try:
            reader=csv.DictReader(io.StringIO(fetch(url).decode("utf-8-sig")))
            entry["fields"]=reader.fieldnames
            rows=list(reader)
            row=next((r for r in rows if r.get("situation")=="all"),None)
            entry["all_situation_rows"]=sum(r.get("situation")=="all" for r in rows)
            entry["dates"]=sorted({r.get("gameDate") for r in rows if r.get("gameDate")})[::100]
            entry["season_counts"]={str(y):sum(r.get("situation")=="all" and str(r.get("season"))==str(y) for r in rows) for y in (2023,2024,2025,2026)}
            entry["sample"]={k:row.get(k) for k in ("gameId","gameDate","playerId","name","playerTeam","team","situation","icetime","xGoals","goals") if k in row} if row else None
            entry["game_level"]=bool({"gameId","gameDate","icetime","xGoals","goals"}.issubset(reader.fieldnames or []))
        except HTTPError as e:entry["error"]="HTTP_"+str(e.code)
        except Exception as e:entry["error"]=type(e).__name__
        report["sources"].append(entry)
    for game in ("2024020001","2025020001"):
        for endpoint in ("boxscore","play-by-play"):
            url=f"https://api-web.nhle.com/v1/gamecenter/{game}/{endpoint}"
            entry={"url":url}
            try:
                data=json.loads(fetch(url))
                entry["fields"]=list(data)
                entry["game_state"]=data.get("gameState")
                if endpoint=="boxscore":
                    entry["goalies"]={side:[{k:v for k,v in g.items() if k in ("playerId","name","starter","toi","decision")} for g in data.get("playerByGameStats",{}).get(side+"Team",{}).get("goalies",[])] for side in ("home","away")}
                else:
                    entry["early_events"]=[{k:p.get(k) for k in ("typeDescKey","timeInPeriod","periodDescriptor","details")} for p in data.get("plays",[])[:12]]
            except HTTPError as e:entry["error"]="HTTP_"+str(e.code)
            except Exception as e:entry["error"]=type(e).__name__
            report["sources"].append(entry)
    Path("docs/nhl_historical_goalie_probe.json").write_text(json.dumps(report,indent=2)+"\n")
if __name__=="__main__":probe()
