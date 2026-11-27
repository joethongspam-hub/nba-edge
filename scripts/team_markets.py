"""Shared team-market odds snapshot. No independent predictions yet."""
import json
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
                "method": "Sportsbook no-vig baseline; not a predictive model", "sports": {n: [] for n in SPORTS}}
    for index, (name, key) in enumerate(active):
        check_budget(remaining, len(active)-index, worst_cost=2)
        events, headers = fetch(key, "odds", regions="us", markets="h2h,spreads",
                                bookmakers="fanduel,draftkings", oddsFormat="american")
        remaining = remaining_from_headers(headers)
        snapshot["sports"][name] = normalize(events)
    target = Path("docs/team_markets.json")
    temp = target.with_suffix(".tmp")
    temp.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    temp.replace(target)

if __name__ == "__main__":
    main()
