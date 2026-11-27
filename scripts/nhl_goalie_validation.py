"""Prospective, paired NHL moneyline validation; not a historical backtest."""
import json
from pathlib import Path
from datetime import timedelta
from nhl_goalie_model import clamp, probabilities, adjustment
from nhl_team_model import fit, distribution
from team_history import parse_time

PATH = Path("docs/nhl_goalie_validation.json")
COEFFICIENTS = (0., .25, .5, .75, 1.)
VERSION = 1

def update(rows, games, now, path=PATH):
    if path.exists():
        archive = json.loads(path.read_text(encoding="utf-8"))
        if archive["version"] != VERSION:
            raise ValueError("Unsupported validation version")
    else:
        archive = {"version":VERSION,"predictions":{}}
    entries = archive["predictions"]
    attack, defense, counts = fit(games, now)
    for r in rows:
        if r.get("market") != "h2h" or r["team"] != r["home"]:
            continue
        start = parse_time(r["start"])
        # One immutable prediction per game, first observed within six hours.
        if not now < start <= now+timedelta(hours=6):
            continue
        h,a = r["home"],r["away"]
        key = "|".join((h,a,start.isoformat()))
        if min(counts.get(h,0),counts.get(a,0))<8:
            continue
        gh,ga = r.get("goalie_home",{}),r.get("goalie_away",{})
        if adjustment(gh) is None or adjustment(ga) is None:
            continue
        both_confirmed = gh["status"]==ga["status"]=="confirmed"
        existing = entries.get(key)
        if existing is not None and (not both_confirmed or existing["both_confirmed"]
                                     or "confirmed_snapshot" in existing or "result" in existing):
            continue
        hr,ar = clamp(3+attack[h]-defense[a]+.15),clamp(3+attack[a]-defense[h]-.15)
        def delta(g,c):
            weight = 1 if g["status"]=="confirmed" else .5
            return max(-.5,min(.5,c*weight*g["rating"]["relative_gsax60"]))
        forecasts={}
        for c in COEFFICIENTS:
            d=distribution(clamp(hr-delta(ga,c)),clamp(ar-delta(gh,c)))
            win,_,margin=probabilities(d,1,0)
            forecasts[str(c)]={"probability":win,"margin":margin}
        snapshot={"home":h,"away":a,"start":start.isoformat(),
                      "observed_at":now.isoformat(),"home_goalie":gh["name"],
                      "away_goalie":ga["name"],"both_confirmed":gh["status"]==ga["status"]=="confirmed",
                      "forecasts":forecasts}
        if existing is None:
            entries[key]=snapshot
        else:
            # Preserve the first forecast; separately capture first confirmed pair.
            existing["confirmed_snapshot"]=snapshot
    for entry in entries.values():
        if "result" in entry:
            continue
        start=parse_time(entry["start"])
        matches=[g for g in games if g[1:3]==(entry["home"],entry["away"])
                 and abs((g[0]-start).total_seconds())<=900 and g[0]<now]
        if len(matches)==1:
            g=matches[0]
            entry["result"]={"home_goals":g[3],"away_goals":g[4]}
    settled=[e for e in entries.values() if "result" in e]
    confirmed_sample=[]
    for e in settled:
        if e["both_confirmed"]:
            confirmed_sample.append(e)
        elif "confirmed_snapshot" in e:
            confirmed_sample.append({**e["confirmed_snapshot"],"result":e["result"]})
    def score(sample):
        result={}
        for c in COEFFICIENTS:
            brier,correct,mae=0.,0,0.
            for e in sample:
                margin=e["result"]["home_goals"]-e["result"]["away_goals"]
                f=e["forecasts"][str(c)]
                p=f["probability"]
                brier+=(p-int(margin>0))**2
                correct+=int((p>=.5)==(margin>0))
                mae+=abs(f["margin"]-margin)
            n=len(sample)
            result[str(c)]={"games":n,"brier":brier/n if n else None,
                            "accuracy":correct/n if n else None,"margin_mae":mae/n if n else None}
        return result
    archive.update(updated=now.isoformat(),summary={"recorded":len(entries),
        "settled":len(settled),"all":score(settled),
        "both_confirmed":score(confirmed_sample),
        "projected":score([e for e in settled if not e["both_confirmed"]])})
    tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(archive,indent=2)+"\n",encoding="utf-8")
    tmp.replace(path)
    return archive["summary"]
