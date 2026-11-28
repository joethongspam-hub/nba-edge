"""Settle existing team forecasts only, using ESPN final scores and no odds requests."""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import team_history
import team_tracker
from team_benchmark import benchmark

BASES = {
    "NBA": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
    "NFL": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
    "NHL": "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard",
}

def refresh(data, now, fetch=team_history.board):
    rows = data["forecasts"]
    histories = {}
    for sport, base in BASES.items():
        dates = set()
        for row in rows:
            start = team_history.parse_time(row["start"])
            if row["sport"] == sport and row["result"] == "pending" and start < now:
                dates.update((start + timedelta(days=i)).date() for i in (-1, 0, 1))
        events = []
        for day in sorted(dates):
            events.extend(fetch(base, day.strftime("%Y%m%d")))
        histories[sport] = team_history.parse_events(events, now, sport)
    team_tracker.settle(rows, histories)
    for row in rows:
        row["settlement_status"] = ("upcoming" if team_history.parse_time(row["start"]) >= now else "awaiting_verification") if row["result"] == "pending" else "settled"
    return dict(data, settlement_updated=now.isoformat(), forecasts=rows,
                summary=team_tracker.summarize(rows), benchmark=benchmark(rows),
                line_movement=team_tracker.line_movement(rows))

if __name__ == "__main__":
    path = Path("docs/team_tracker.json")
    data = refresh(json.loads(path.read_text()), datetime.now(timezone.utc))
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    temp.replace(path)
