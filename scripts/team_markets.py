"""Shared team-market odds snapshot. No independent predictions yet."""
import json
import nba_team_model
import nba_context_shadow
import nfl_team_model
import nhl_team_model
import team_tracker
import team_backtest
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from credit_budget import remaining_from_headers, check_budget

SPORTS = {"NBA": "basketball_nba", "NFL": "americanfootball_nfl", "NHL": "icehockey_nhl"}
BOOKS = {"fanduel", "draftkings"}
BASE = "https://api.the-odds-api.com/v4/sports/"

def fetch(sport, endpoint, **params):
    params["apiKey"] = os.environ["ODDS_API_KEY"]
    with urlopen(BASE + sport + "/" + endpoint + "?" + urlencode(params), timeout=30) as response:
        return json.load(response), response.headers

def implied(price):
    if price == 0:
        raise ValueError("Invalid odds")
    return 100 / (price + 100) if price > 0 else -price / (100 - price)

def normalize(events):
    rows = []
    for event in events:
        for book in event.get("bookmakers", []):
            if book["key"] not in BOOKS:
                continue
            for market in book.get("markets", []):
                if market["key"] not in ("h2h", "spreads"):
                    continue
                outcomes = market["outcomes"]
                if len(outcomes) != 2 or {o["name"] for o in outcomes} != {event["home_team"], event["away_team"]}:
                    continue
                if market["key"] == "spreads" and (any("point" not in o for o in outcomes) or abs(sum(o["point"] for o in outcomes)) > 1e-8):
                    continue
                probs = [implied(o["price"]) for o in outcomes]
                for o, p in zip(outcomes, probs):
                    rows.append({"event_id": event["id"], "home": event["home_team"],
                        "away": event["away_team"], "start": event["commence_time"],
                        "book": book["key"], "market": market["key"], "team": o["name"],
                        "line": o.get("point"), "odds": o["price"],
                        "market_probability": round(p / sum(probs), 6)})
    return rows

def main():
    # Preflight free events requests; reserve 2,000 credits and allow 2 per league.
    active = []
    remaining = None
    for name, key in SPORTS.items():
        events, headers = fetch(key, "events")
        remaining = remaining_from_headers(headers)
        if events:
            active.append((name, key))
    check_budget(remaining, len(active), worst_cost=2)
    snapshot = {"updated": datetime.now(timezone.utc).isoformat(),
                "method": "Sportsbook no-vig baseline; NBA, NFL and NHL experimental independent models where available", "sports": {n: [] for n in SPORTS}}
    for index, (name, key) in enumerate(active):
        check_budget(remaining, len(active)-index, worst_cost=2)
        events, headers = fetch(key, "odds", regions="us", markets="h2h,spreads",
                                bookmakers="fanduel,draftkings", oddsFormat="american")
        remaining = remaining_from_headers(headers)
        snapshot["sports"][name] = normalize(events)
    snapshot["odds_credits_remaining"] = remaining
    histories = {}
    try:
        now = datetime.now(timezone.utc)
        histories["NBA"] = nba_team_model.history(now)
        if snapshot["sports"]["NBA"]:
            nba_team_model.annotate(snapshot["sports"]["NBA"], histories["NBA"], now)
    except Exception:
        for row in snapshot["sports"]["NBA"]:
            row["model_status"] = "NBA history unavailable"
            for key in ("model_probability", "projected_margin", "push_probability", "history_games"):
                row.pop(key, None)
    try:
        now = datetime.now(timezone.utc)
        histories["NFL"] = nfl_team_model.history(now)
        if snapshot["sports"]["NFL"]:
            nfl_team_model.annotate(snapshot["sports"]["NFL"], histories["NFL"], now)
    except Exception:
        for row in snapshot["sports"]["NFL"]:
            row["model_status"] = "NFL history unavailable"
            for key in ("model_probability", "projected_margin", "push_probability", "history_games"):
                row.pop(key, None)
    try:
        now = datetime.now(timezone.utc)
        histories["NHL"] = nhl_team_model.history(now)
        if snapshot["sports"]["NHL"]:
            nhl_team_model.annotate(snapshot["sports"]["NHL"], histories["NHL"], now)
    except Exception:
        for row in snapshot["sports"]["NHL"]:
            row["model_status"] = "NHL history unavailable"
            for key in ("model_probability", "projected_margin", "push_probability", "history_games"):
                row.pop(key, None)
    if "NBA" in histories:
        try:
            nba_context_shadow.annotate(snapshot["sports"]["NBA"], histories["NBA"], datetime.now(timezone.utc))
            snapshot["nba_shadow_audit"] = nba_context_shadow.audit(histories["NBA"])
        except Exception:
            snapshot["nba_shadow_audit"] = {"status": "Unavailable"}
            for row in snapshot["sports"]["NBA"]:
                for key in tuple(row):
                    if key.startswith("shadow_"):
                        row.pop(key)
    snapshot["updated"] = datetime.now(timezone.utc).isoformat()
    team_tracker.update(snapshot, histories)
    audit_path = Path('docs/team_backtest.json')
    audit_temp = audit_path.with_suffix('.tmp')
    audit_temp.write_text(json.dumps({'updated': snapshot['updated'], 'sports': team_backtest.audit(histories)}, indent=2) + '\n', encoding='utf-8')
    audit_temp.replace(audit_path)
    target = Path("docs/team_markets.json")
    temp = target.with_suffix(".tmp")
    temp.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    temp.replace(target)

if __name__ == "__main__":
    main()
