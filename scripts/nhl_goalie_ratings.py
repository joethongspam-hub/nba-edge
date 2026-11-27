"""Research-only goalie ratings. No changes to production probabilities."""
import csv
import io
import math
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
from nhl_efficiency import NAMES

SOURCE = "https://moneypuck.com/moneypuck/playerData/careers/gameByGame/all_goalies.csv"
ET = ZoneInfo("America/New_York")

def name_key(name):
    return "".join(c for c in unicodedata.normalize("NFKD", name.casefold())
                   if c.isalnum() and not unicodedata.combining(c))

def ratings(rows, now):
    today = now.astimezone(ET).date()
    people, teams, identities = defaultdict(list), defaultdict(list), defaultdict(set)
    seen = set()
    latest = None
    for r in rows:
        if r.get("situation") != "all":
            continue
        try:
            date = datetime.strptime(r["gameDate"], "%Y%m%d").date()
            age = (today-date).days
            if not 1 <= age <= 730:
                continue
            seconds, xg, goals = float(r["icetime"]), float(r["xGoals"]), float(r["goals"])
            if not all(math.isfinite(v) for v in (seconds,xg,goals)):
                continue
            if not 0 < seconds <= 3900 or min(xg,goals)<0:
                continue
            team = NAMES[r["playerTeam"]]
            ident = r["playerId"]
            key = (ident,r["gameId"])
            if not ident or key in seen or not r["name"]:
                continue
            seen.add(key)
            latest = max(latest,date) if latest else date
            name = name_key(r["name"])
            identities[name].add(ident)
            observation = (age,seconds/3600,xg-goals,team)
            people[ident].append(observation)
            teams[team].append(observation)
        except (KeyError,ValueError,TypeError,AttributeError):
            continue
    def summarize(obs, half_life, prior_hours):
        hours = sum(h*2**(-age/half_life) for age,h,g,t in obs)
        saved = sum(g*2**(-age/half_life) for age,h,g,t in obs)
        return saved/(hours+prior_hours),hours
    out = {}
    for name, ids in identities.items():
        if len(ids)!=1:
            continue
        ident = next(iter(ids))
        obs = people[ident]
        long, effective = summarize(obs,180,15)
        recent, recent_hours = summarize([o for o in obs if o[0]<=60],30,10)
        current = [o for o in obs if o[0] <= 365 and
                   (today-timedelta(days=o[0])).year -
                   int((today-timedelta(days=o[0])).month < 7) ==
                   today.year-int(today.month<7)]
        season_hours = sum(o[1] for o in current)
        season_saved = sum(o[2] for o in current)
        out[name] = {"moneypuck_id":ident,"gsax60":round(long,3),
                     "recent_gsax60":round(recent,3),"effective_hours":round(effective,2),
                     "recent_effective_hours":round(recent_hours,2),
                     "season_gsax":round(season_saved,2),
                     "season_gsax60":round(season_saved/season_hours,3) if season_hours else None,
                     "season_hours":round(season_hours,2),"appearances":len(obs),
                     "teams":sorted({o[3] for o in obs if o[0]<=365}),
                     "rating_eligible":effective>=5}
    team_ratings = {t:round(summarize(obs,35,10)[0],3)
                    for t,obs in teams.items()}
    return out,team_ratings,{"goalies":len(out),"games":len(seen),
                             "latest_game_date":latest.isoformat() if latest else None}

def annotate(rows, now):
    if not any(r.get("goalie_"+s,{}).get("name") for r in rows for s in ("home","away")):
        return {"source":SOURCE,"status":"no starters","research_only":True}
    with urlopen(Request(SOURCE,headers={"User-Agent":"SPORTS-EDGE research"}),timeout=60) as response:
        with io.TextIOWrapper(response,encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            required = {"situation","gameDate","icetime","xGoals","goals","playerTeam","playerId","gameId","name"}
            if not required.issubset(reader.fieldnames or []):
                return {"source":SOURCE,"status":"schema mismatch",
                        "fields":reader.fieldnames,"research_only":True}
            players,teams,health = ratings(reader,now)
    identified,rated = set(),set()
    for row in rows:
        for side in ("home","away"):
            goalie = row.get("goalie_"+side,{})
            name = goalie.get("name")
            if not name:
                continue
            slot = (row["home"],row["away"],row["start"],side)
            identified.add(slot)
            stats = players.get(name_key(name))
            if not stats or row[side] not in stats["teams"]:
                continue
            data = dict(stats)
            team = teams.get(row[side])
            data["team_gsax60"] = team
            data["relative_gsax60"] = round(data["gsax60"]-team,3) if team is not None else None
            goalie["rating"] = data
            rated.add(slot)
    return dict(health,source=SOURCE,identified_slots=len(identified),rated_slots=len(rated),
                research_only=True,checked_at=now.isoformat())
