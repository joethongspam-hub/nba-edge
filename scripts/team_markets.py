"""Shared team-market odds snapshot. No independent predictions yet."""
import json
import team_history
import nba_team_model
import nba_context_shadow
import nba_efficiency
import nfl_team_model
import nfl_context_shadow
import nfl_efficiency
import nhl_team_model
import nhl_context_shadow
import nhl_efficiency
import espn_starters
import nhl_goalie_ratings
import team_tracker
import team_analysis_export
import team_rankings
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
                    rows.append({"event_id": event["id"], "home": team_history.canonical(event["home_team"]),
                        "away": team_history.canonical(event["away_team"]), "start": event["commence_time"],
                        "book": book["key"], "market": market["key"], "team": team_history.canonical(o["name"]),
                        "line": o.get("point"), "odds": o["price"],
                        "market_probability": round(p / sum(probs), 6)})
    return rows

def cached_snapshot(now):
    old = json.loads(Path("docs/team_markets.json").read_text(encoding="utf-8"))
    from nba_team_model import parse_time
    sports = {}
    for name in SPORTS:
        sports[name] = [
            {k: row[k] for k in ("event_id", "home", "away", "start", "book",
                                  "market", "team", "line", "odds", "market_probability")
             if k in row}
            for row in old["sports"].get(name, [])
            if parse_time(row["start"]) > now
        ]
    return {"updated": now.isoformat(), "method": old["method"],
            "sports": sports, "odds_updated": old.get("odds_updated", old["updated"]),
            "odds_mode": "cached", "odds_credits_remaining": old.get("odds_credits_remaining")}


def main():
    if os.environ.get("TEAM_REFRESH_MODE") == "cached":
        snapshot = cached_snapshot(datetime.now(timezone.utc))
        print("Cached odds mode: zero Odds API requests")
    else:
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
        snapshot["odds_updated"] = snapshot["updated"]
        snapshot["odds_mode"] = "live"
    histories = {}
    snapshot['history_health'] = {}
    try:
        now = datetime.now(timezone.utc)
        histories["NBA"] = nba_team_model.history(now)
        if snapshot["sports"]["NBA"]:
            nba_team_model.annotate(snapshot["sports"]["NBA"], histories["NBA"], now)
    except Exception as exc:
        print("NBA model failure:", type(exc).__name__)
        snapshot["history_health"]["NBA"] = {"error": type(exc).__name__}
        for row in snapshot["sports"]["NBA"]:
            row["model_status"] = "NBA history unavailable"
            for key in ("model_probability", "projected_margin", "push_probability", "history_games"):
                row.pop(key, None)
    try:
        now = datetime.now(timezone.utc)
        histories["NFL"] = nfl_team_model.history(now)
        if snapshot["sports"]["NFL"]:
            nfl_team_model.annotate(snapshot["sports"]["NFL"], histories["NFL"], now)
    except Exception as exc:
        print("NFL model failure:", type(exc).__name__)
        snapshot["history_health"]["NFL"] = {"error": type(exc).__name__}
        for row in snapshot["sports"]["NFL"]:
            row["model_status"] = "NFL history unavailable"
            for key in ("model_probability", "projected_margin", "push_probability", "history_games"):
                row.pop(key, None)
    try:
        now = datetime.now(timezone.utc)
        histories["NHL"] = nhl_team_model.history(now)
        if snapshot["sports"]["NHL"]:
            nhl_team_model.annotate(snapshot["sports"]["NHL"], histories["NHL"], now)
    except Exception as exc:
        print("NHL model failure:", type(exc).__name__)
        snapshot["history_health"]["NHL"] = {"error": type(exc).__name__}
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
    if "NFL" in histories:
        try:
            nfl_context_shadow.annotate(snapshot["sports"]["NFL"], histories["NFL"], datetime.now(timezone.utc))
            snapshot["nfl_shadow_audit"] = nfl_context_shadow.audit(histories["NFL"])
        except Exception:
            snapshot["nfl_shadow_audit"] = {"status": "Unavailable"}
            for row in snapshot["sports"]["NFL"]:
                for key in tuple(row):
                    if key.startswith("shadow_"):
                        row.pop(key)
    if "NHL" in histories:
        try:
            nhl_context_shadow.annotate(snapshot["sports"]["NHL"], histories["NHL"], datetime.now(timezone.utc))
            snapshot["nhl_shadow_audit"] = nhl_context_shadow.audit(histories["NHL"])
        except Exception:
            snapshot["nhl_shadow_audit"] = {"status": "Unavailable"}
            for row in snapshot["sports"]["NHL"]:
                for key in tuple(row):
                    if key.startswith("shadow_"):
                        row.pop(key)
    for sport, games in histories.items():
        snapshot["history_health"].setdefault(sport, {"completed_games": len(games)})
    for sport, rows in snapshot["sports"].items():
        health = snapshot["history_health"].setdefault(sport, {})
        health["quotes"] = len(rows)
        health["modeled"] = sum(r.get("model_probability") is not None for r in rows)
        print(sport, "history health:", health)
    if "NBA" in histories:
        try:
            efficiency_games, health = nba_efficiency.load(datetime.now(timezone.utc))
            snapshot["nba_efficiency_health"] = health
            nba_efficiency.annotate(snapshot["sports"]["NBA"], efficiency_games, datetime.now(timezone.utc))
            snapshot["nba_efficiency_audit"] = nba_efficiency.audit(efficiency_games, team_backtest.evaluate("NBA", histories["NBA"]))
        except Exception as exc:
            print("NBA efficiency unavailable:", type(exc).__name__)
            snapshot["nba_efficiency_health"] = {"error": type(exc).__name__}
            for row in snapshot["sports"]["NBA"]:
                for key in tuple(row):
                    if key.startswith("efficiency_"):
                        row.pop(key)
    if "NFL" in histories:
        try:
            epa_games = nfl_efficiency.load(datetime.now(timezone.utc), histories["NFL"])
            snapshot["nfl_epa_health"] = {"matched": len(epa_games), "eligible": len(histories["NFL"])}
            nfl_efficiency.annotate(snapshot["sports"]["NFL"], epa_games, datetime.now(timezone.utc))
            snapshot["nfl_epa_audit"] = nfl_efficiency.audit(epa_games, team_backtest.evaluate("NFL", histories["NFL"]))
        except Exception as exc:
            print("NFL EPA unavailable:", type(exc).__name__)
            snapshot["nfl_epa_health"] = {"error": type(exc).__name__}
            for row in snapshot["sports"]["NFL"]:
                for key in tuple(row):
                    if key.startswith("epa_"):
                        row.pop(key)
    if "NHL" in histories:
        try:
            xg_games = nhl_efficiency.load(histories["NHL"])
            snapshot["nhl_xg_health"] = {"matched": len(xg_games), "eligible": len(histories["NHL"])}
            nhl_efficiency.annotate(snapshot["sports"]["NHL"], xg_games, datetime.now(timezone.utc))
            snapshot["nhl_xg_audit"] = nhl_efficiency.audit(xg_games, team_backtest.evaluate("NHL", histories["NHL"]))
        except Exception as exc:
            print("NHL xG unavailable:", type(exc).__name__)
            snapshot["nhl_xg_health"] = {"error": type(exc).__name__}
            for row in snapshot["sports"]["NHL"]:
                for key in tuple(row):
                    if key.startswith("xg_"):
                        row.pop(key)
    snapshot["updated"] = datetime.now(timezone.utc).isoformat()
    try:
        snapshot["nhl_goalie_health"] = espn_starters.annotate(
            snapshot["sports"]["NHL"], datetime.now(timezone.utc))
    except Exception as exc:
        snapshot["nhl_goalie_health"] = {"error": type(exc).__name__, "research_only": True}
    snapshot["updated"] = datetime.now(timezone.utc).isoformat()
    try:
        snapshot["nhl_goalie_rating_health"] = nhl_goalie_ratings.annotate(
            snapshot["sports"]["NHL"], datetime.now(timezone.utc))
    except Exception as exc:
        snapshot["nhl_goalie_rating_health"] = {"error": type(exc).__name__, "research_only": True}
    snapshot["updated"] = datetime.now(timezone.utc).isoformat()
    snapshot["rankings"] = team_rankings.rankings(snapshot)
    if snapshot["odds_mode"] == "cached":
        target = Path("docs/team_context_refresh.json")
        temp = target.with_suffix(".tmp")
        temp.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
        temp.replace(target)
        return
    tracker = team_tracker.update(snapshot, histories)
    team_analysis_export.write(snapshot, tracker)
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
