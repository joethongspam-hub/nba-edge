"""Experimental NBA margin model using only completed pre-snapshot ESPN games."""
from datetime import datetime, timedelta, timezone
from math import erf, sqrt, exp
from collections import defaultdict
from urllib.request import urlopen
import json

BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"

def parse_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))

def history(now):
    from team_history import history as fetch_history
    return fetch_history(BASE, now, "NBA", 84)

def fit(games, now):
    # Weighted ridge-like iterative opponent adjustment; 2.5-point home prior.
    obs = defaultdict(list)
    for time, home, away, margin, neutral in games:
        if time >= now:
            continue
        w = exp(-(now-time).total_seconds()/86400/35)
        adjusted = margin - (0 if neutral else 2.5)
        obs[home].append((away, adjusted, w))
        obs[away].append((home, -adjusted, w))
    ratings = dict.fromkeys(obs, 0.0)
    for _ in range(40):
        ratings = {team: sum(w*(margin+ratings[opp]) for opp,margin,w in rows)/(4+sum(w for _,_,w in rows)) for team,rows in obs.items()}
    return ratings, {team: len(rows) for team, rows in obs.items()}

def cdf(x):
    return (1+erf(x/sqrt(2)))/2

def annotate(rows, games, now):
    ratings, counts = fit(games, now)
    for row in rows:
        home, away = row["home"], row["away"]
        if min(counts.get(home,0), counts.get(away,0)) < 8:
            row["model_status"] = "Insufficient team history"
            continue
        margin = ratings[home]-ratings[away]+2.5
        if row["team"] == away:
            margin = -margin
        line = row["line"] if row["market"] == "spreads" else 0
        # Integer margin approximation with continuity correction.
        threshold = -line
        import math
        win = 1-cdf((math.floor(threshold)+.5-margin)/12)
        push = 0.0
        if threshold == int(threshold) and row["market"] == "spreads":
            push = cdf((threshold+.5-margin)/12)-cdf((threshold-.5-margin)/12)
        if row["market"] == "h2h":
            win = cdf(margin/12)  # NBA final scores cannot tie.
        row.update(projected_margin=round(margin,2), model_probability=round(win,6),
                   push_probability=round(push,6), model_status="Experimental; uncalibrated",
                   history_games=min(counts[home],counts[away]))
    return rows
