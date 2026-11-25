"""Verified matching of sportsbook picks against ESPN boxscore records.

Only settle when the matchup, game start, and unique player row agree.
Never guess from a name + adjacent calendar date alone.
"""
from datetime import datetime, timedelta, timezone
from prop_markets import stat_value

ALIASES = {
    "la clippers": "los angeles clippers",
    "ny knicks": "new york knicks",
}


def team_name(value):
    simplified = " ".join("".join(c.lower() if c.isalnum() else " " for c in str(value)).split())
    return ALIASES.get(simplified, simplified)


def matchup_name(away, home):
    if not away or not home:
        return None
    return team_name(away) + " @ " + team_name(home)


def matchup_from_string(value):
    if not isinstance(value, str) or " @ " not in value:
        return None
    away, home = value.split(" @ ", 1)
    return matchup_name(away, home)


def parse_time(value):
    if not isinstance(value, str):
        return None
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return timestamp.astimezone(timezone.utc) if timestamp.tzinfo else None


def matching_logs(pick, logs, max_start_difference=timedelta(hours=18)):
    pick_matchup = matchup_from_string(pick.get("event"))
    pick_start = parse_time(pick.get("startsAt"))
    if pick_matchup is None or pick_start is None:
        return []
    matches = []
    for row in logs:
        if pick.get('playerId') and str(row.get('playerId',''))!=str(pick['playerId']):
            continue
        if matchup_from_string(row.get("event")) != pick_matchup:
            continue
        row_start = parse_time(row.get("startsAt"))
        if row_start is None or abs(row_start - pick_start) > max_start_difference:
            continue
        if stat_value(row, pick.get("market")) is None or not row.get("gameId"):
            continue
        matches.append(row)
    return matches


def unique_verified_log(pick, player_logs):
    matches = matching_logs(pick, player_logs)
    # A single matched, fully identified boxscore row is required.
    return matches[0] if len(matches) == 1 else None
