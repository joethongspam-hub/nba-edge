"""Research-only goalie ratings. No changes to production probabilities."""
import csv
import io
import json
from pathlib import Path
from urllib.error import HTTPError
import math
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
from nhl_efficiency import NAMES

SOURCE = "https://moneypuck.com/moneypuck/playerData/seasonSummary/{year}/regular/goalies.csv"
CACHE = Path("docs/nhl_goalie_ratings_cache.json")
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

def season_ratings(batches, year):
    people, teams, identities = defaultdict(list), defaultdict(list), defaultdict(set)
    for season, rows in batches:
        seen = set()
        for r in rows:
            if r.get("situation") != "all":
                continue
            try:
                ident = r["playerId"]
                name = name_key(r["name"])
                team = NAMES[r["team"]]
                hours = float(r["icetime"])/3600
                xg, goals = float(r["xGoals"]), float(r["goals"])
                if not ident or not name or not all(math.isfinite(v) for v in (hours,xg,goals)):
                    continue
                if not 0 < hours <= 100 or min(xg,goals)<0:
                    continue
                key = (ident,team)
                if key in seen:
                    continue
                seen.add(key)
                obs = (season,hours,xg-goals,team)
                people[ident].append(obs)
                teams[team].append(obs)
                identities[name].add(ident)
            except (KeyError,ValueError,TypeError,AttributeError):
                continue
    def summarize(obs):
        hours = sum(h*(1 if y==year else .5) for y,h,g,t in obs)
        saved = sum(g*(1 if y==year else .5) for y,h,g,t in obs)
        return saved/(hours+15),hours
    players = {}
    for name,ids in identities.items():
        if len(ids)!=1:
            continue
        ident = next(iter(ids))
        obs = people[ident]
        gsax60,effective = summarize(obs)
        current = [o for o in obs if o[0]==year]
        hours = sum(o[1] for o in current)
        saved = sum(o[2] for o in current)
        players[name] = {"moneypuck_id":ident,"gsax60":round(gsax60,3),
                         "effective_hours":round(effective,2),
                         "season_hours":round(hours,2),"season_gsax":round(saved,2),
                         "season_gsax60":round(saved/hours,3) if hours else None,
                         "recent_gsax60":None,"rating_eligible":effective>=5,
                         "teams":sorted({o[3] for o in (current or obs)}),
                         "method":"season_weighted_shrinkage"}
    return players,{t:round(summarize([o for o in obs if o[0]==year])[0],3)
                    for t,obs in teams.items() if any(o[0]==year for o in obs)}

def load_seasons(now):
    today = now.astimezone(ET).date()
    year = today.year-int(today.month<7)
    try:
        cached = json.loads(CACHE.read_text(encoding="utf-8"))
        if cached["date"] == today.isoformat() and cached["year"] == year and cached["players"]:
            return cached["players"],cached["teams"],dict(cached["health"],cache_hit=True)
    except (OSError,ValueError,KeyError,TypeError):
        pass
    batches,errors = [],[]
    for season in (year,year-1):
        url = SOURCE.format(year=season)
        try:
            with urlopen(Request(url,headers={"User-Agent":"SPORTS-EDGE research"}),timeout=30) as response:
                with io.TextIOWrapper(response,encoding="utf-8-sig") as stream:
                    reader = csv.DictReader(stream)
                    required = {"situation","team","icetime","xGoals","goals","playerId","name"}
                    if not required.issubset(reader.fieldnames or []):
                        errors.append({"season":season,"schema":reader.fieldnames})
                        continue
                    batches.append((season,list(reader)))
        except HTTPError as exc:
            errors.append({"season":season,"error":"HTTP_"+str(exc.code)})
        except Exception as exc:
            errors.append({"season":season,"error":type(exc).__name__})
    players,teams = season_ratings(batches,year)
    health = {"goalies":len(players),"seasons":[y for y,_ in batches],"errors":errors,
              "method":"season_weighted_shrinkage","cache_hit":False,
              "data_date":today.isoformat(),"attribution":"MoneyPuck.com"}
    if players and not errors and teams:
        temp = CACHE.with_suffix(".tmp")
        temp.write_text(json.dumps({"date":today.isoformat(),"year":year,"players":players,
                                    "teams":teams,"health":health},indent=2)+"\n",encoding="utf-8")
        temp.replace(CACHE)
    return players,teams,health

def annotate(rows, now):
    if not any(r.get("goalie_"+s,{}).get("name") for r in rows for s in ("home","away")):
        return {"source":SOURCE,"status":"no starters","research_only":True}
    players,teams,health = load_seasons(now)
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
            data["rating_eligible"] = data["rating_eligible"] and bool(data["season_hours"]) and team is not None
            goalie["rating"] = data
            rated.add(slot)
    return dict(health,source=SOURCE,identified_slots=len(identified),rated_slots=len(rated),
                research_only=True,checked_at=now.isoformat())
