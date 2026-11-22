#!/usr/bin/env python3
"""Free ESPN-based gate for NBA EDGE scheduled runs. No Odds API requests."""
import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1] / "docs"
CENTRAL = ZoneInfo("America/Chicago")
SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"


def today_games(board, now):
    day = now.astimezone(CENTRAL).date()
    times = []
    for game in board.get("events", []):
        try:
            start = datetime.fromisoformat(game["date"].replace("Z", "+00:00"))
            if start.astimezone(CENTRAL).date() == day and start > now:
                times.append(start)
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(times)


def cache_state(now, cache):
    today = now.astimezone(CENTRAL).date().isoformat()
    if cache.get("slateDate") != today or cache.get("cacheVersion") != 2:
        return 0, None
    try:
        fetched = datetime.fromisoformat(cache["fetchedAt"].replace("Z", "+00:00"))
        if fetched.tzinfo is None:
            return 1, None
    except (KeyError, TypeError, ValueError):
        return 1, None
    return max(1, int(cache.get("refreshCount", 1))), fetched


def decide(now, games, cache, manual=False, manual_refresh=False):
    count, fetched = cache_state(now, cache)
    if manual:
        return True, bool(manual_refresh and count == 1 and games), "manual"
    if not games:
        return False, False, "no_future_games"
    local = now.astimezone(CENTRAL)
    # First run on the first hourly gate within two hours of the next tipoff.
    # The 5:13 PM CT gate also serves as a fallback for later games.
    if count == 0:
        due = games[0] <= now + timedelta(hours=2) or (local.hour == 17 and local.minute >= 13)
        return due, False, "first_pregame" if due else "not_due"
    # One optional late refresh of remaining, not-yet-started games.
    # Never fetch the same late slate repeatedly or silently spend credits.
    if count == 1 and fetched is not None and (local.hour == 17 and local.minute >= 13):
        if now - fetched >= timedelta(hours=3):
            return True, True, "late_slate_refresh"
    return False, False, "already_cached"


def main():
    now = datetime.now(timezone.utc)
    manual = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
    try:
        cache = json.loads((ROOT / "odds_cache.json").read_text())
    except (OSError, ValueError):
        cache = {}
    # A manual cached analysis rerun requires no ESPN call or paid quota.
    if manual and os.environ.get("MANUAL_ODDS_REFRESH", "false").lower() != "true":
        run, refresh, reason = True, False, "manual_cached"
    else:
        try:
            url = SCOREBOARD + "?dates=" + now.astimezone(CENTRAL).strftime("%Y%m%d")
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "NBA-EDGE/3.5"}), timeout=15) as response:
                board = json.load(response)
            games = today_games(board, now)
            run, refresh, reason = decide(now, games, cache, manual,
                                          os.environ.get("MANUAL_ODDS_REFRESH", "false").lower() == "true")
        except Exception as exc:
            # Fail closed on schedule: no unplanned quota usage from a broken
            # discovery feed. Manual analysis can still reuse the local cache.
            run, refresh, reason = (manual, False, "scoreboard_unavailable")
            print("Free schedule lookup unavailable:", type(exc).__name__)
    print("Adaptive gate:", reason, "run=", run, "paid_refresh=", refresh)
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as file:
            file.write(f"should_run={str(run).lower()}\nrefresh_odds={str(refresh).lower()}\n")


if __name__ == "__main__":
    main()
