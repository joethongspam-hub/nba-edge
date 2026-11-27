"""PropLine lineup context, independent of Odds API."""
import json
import os
from datetime import timedelta
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from zoneinfo import ZoneInfo
from nba_team_model import parse_time
from team_history import canonical

URL = "https://api.prop-line.com/v1/sports/hockey_nhl/lineups"
ET = ZoneInfo("America/New_York")

def unknown(now):
    return {"name": None, "status": "unknown", "source": URL,
            "reported_at": None, "checked_at": now.isoformat()}

def starter(team, now):
    candidates = []
    for p in team.get("players", []):
        if str(p.get("role", "")).lower() != "starter":
            continue
        if str(p.get("position", "")).lower() not in ("g", "goalie", "goaltender"):
            continue
        if p.get("status") != "confirmed" or team.get("status") != "confirmed":
            continue
        try:
            since = parse_time(p["since"])
            updated = parse_time(team["updated_at"])
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
        if since > now or updated > now or not p.get("player_name"):
            continue
        candidates.append({"name": p["player_name"], "status": "confirmed",
                           "source": URL, "reported_at": since.isoformat(),
                           "checked_at": now.isoformat()})
    return candidates[0] if len(candidates) == 1 else unknown(now)

def apply(rows, payload, now):
    index = {}
    for g in payload["games"]:
        teams = g.get("teams", [])
        home = [t for t in teams if t.get("home") is True]
        away = [t for t in teams if t.get("home") is False]
        if len(home) != 1 or len(away) != 1:
            continue
        if not home[0].get("team") or not away[0].get("team"):
            continue
        key = (g.get("game_date"), canonical(home[0]["team"]), canonical(away[0]["team"]))
        index.setdefault(key, []).append((home[0], away[0]))
    eligible, matched, confirmed = set(), set(), set()
    for row in rows:
        start = parse_time(row["start"])
        key = (start.astimezone(ET).date().isoformat(), row["home"], row["away"])
        row["goalie_home"] = unknown(now)
        row["goalie_away"] = unknown(now)
        if not now < start <= now + timedelta(hours=36):
            continue
        eligible.add(key)
        games = index.get(key, [])
        if len(games) != 1:
            continue
        matched.add(key)
        for side, team in zip(("home", "away"), games[0]):
            row["goalie_"+side] = starter(team, now)
            if row["goalie_"+side]["status"] == "confirmed":
                confirmed.add((key, side))
    return {"source": URL, "checked_at": now.isoformat(), "eligible_games": len(eligible),
            "matched_games": len(matched), "confirmed_goalies": len(confirmed),
            "source_games": len(payload["games"]), "research_only": True}

def annotate(rows, now):
    if not rows:
        return apply(rows, {"games": []}, now)
    key = os.environ.get("PROPLINE_API_KEY")
    error = None
    if not key:
        error = "missing_secret"
    else:
        try:
            with urlopen(Request(URL, headers={"X-API-Key": key, "Accept": "application/json"}), timeout=20) as response:
                payload = json.load(response)
            return apply(rows, payload, now)
        except HTTPError as exc:
            error = "HTTP_" + str(exc.code)
        except Exception as exc:
            error = type(exc).__name__
    result = apply(rows, {"games": []}, now)
    result["error"] = error
    return result
