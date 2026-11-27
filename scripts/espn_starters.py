"""Pregame goalie context from ESPN, with PropLine fallback."""
from datetime import timedelta
from zoneinfo import ZoneInfo
from team_history import board, canonical, parse_time
from nhl_team_model import BASE
import propline_starters

ET = ZoneInfo("America/New_York")

def unknown(now):
    return {"name": None, "status": "unknown", "source": BASE,
            "reported_at": None, "checked_at": now.isoformat()}

def starter(competitor, now):
    team_id = str(competitor.get("team", {}).get("id") or "")
    candidates = []
    for p in competitor.get("probables", []):
        if p.get("name") != "probableStartingGoalie":
            continue
        a = p.get("athlete", {})
        status = {"confirmed":"confirmed", "expected":"projected"}.get(
            p.get("status", {}).get("type"))
        if (not status or not a.get("fullName") or a.get("position") != "G"
                or not team_id or str(a.get("team", {}).get("id")) != team_id):
            continue
        candidates.append({"name":a["fullName"], "player_id":str(a.get("id") or ""),
                           "status":status, "source":BASE,
                           "reported_at":None, "checked_at":now.isoformat()})
    return candidates[0] if len(candidates) == 1 else unknown(now)

def eligible(row, now):
    return now < parse_time(row["start"]) <= now + timedelta(hours=36)

def apply(rows, events, now):
    index = {}
    seen = set()
    for event in events:
        try:
            start = parse_time(event["date"])
            if start <= now or event.get("status",{}).get("type",{}).get("state") != "pre":
                continue
            comp = event["competitions"][0]
            teams = {c["homeAway"]:c for c in comp["competitors"]}
            h,a = teams["home"],teams["away"]
            key = (canonical(h["team"]["displayName"]), canonical(a["team"]["displayName"]))
            ident = event["id"]
            if ident in seen:
                continue
            seen.add(ident)
            index.setdefault(key, []).append((start,h,a))
        except (KeyError, ValueError, TypeError, IndexError, AttributeError):
            continue
    matched = set()
    for row in rows:
        for side in ("home","away"):
            row["goalie_"+side] = unknown(now)
        if not eligible(row,now):
            continue
        key = (row["home"],row["away"])
        start = parse_time(row["start"])
        games = [g for g in index.get(key,[]) if abs((g[0]-start).total_seconds()) <= 900]
        if len(games) != 1:
            continue
        matched.add((*key,start))
        for side,c in zip(("home","away"),games[0][1:]):
            row["goalie_"+side] = starter(c,now)
    return len(matched)

def annotate(rows, now):
    dates = {parse_time(r["start"]).astimezone(ET).date() for r in rows if eligible(r,now)}
    events, errors = [], []
    for day in sorted(dates):
        try:
            events.extend(board(BASE,day.strftime("%Y%m%d")))
        except Exception as exc:
            errors.append(str(day)+": "+type(exc).__name__)
    matched = apply(rows,events,now)
    missing = [r for r in rows if eligible(r,now) and
               any(r["goalie_"+side]["status"]=="unknown" for side in ("home","away"))]
    fallback_health = None
    if missing:
        copies = [dict(r) for r in missing]
        fallback_health = propline_starters.annotate(copies,now)
        for row, alt in zip(missing,copies):
            for side in ("home","away"):
                k = "goalie_"+side
                if row[k]["status"]=="unknown" and alt[k]["status"]=="confirmed":
                    row[k] = alt[k]
    slots = {}
    for r in rows:
        if eligible(r,now):
            for side in ("home","away"):
                slots[(r["home"],r["away"],r["start"],side)] = r["goalie_"+side]["status"]
    return {"source":BASE,"checked_at":now.isoformat(),"eligible_games":len(slots)//2,
            "matched_games":matched,"confirmed_goalies":sum(v=="confirmed" for v in slots.values()),
            "projected_goalies":sum(v=="projected" for v in slots.values()),
            "unknown_goalies":sum(v=="unknown" for v in slots.values()),
            "errors":errors,"fallback":fallback_health,"research_only":True}
