"""Experimental NFL opponent-adjusted scoring margin model."""
from collections import defaultdict
from datetime import timedelta
from math import erf, exp, floor, sqrt
from urllib.request import urlopen
import json
from nba_team_model import parse_time

BASE = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"

def history(now):
    from team_history import history as fetch_history
    return fetch_history(BASE, now, "NFL", 126)

def fit(games, now):
    obs = defaultdict(list)
    for time, home, away, margin, neutral in games:
        if time >= now:
            continue
        w = exp(-(now-time).total_seconds()/86400/56)
        adjusted = margin - (0 if neutral else 1.5)
        obs[home].append((away, adjusted, w))
        obs[away].append((home, -adjusted, w))
    ratings = dict.fromkeys(obs, 0.0)
    for _ in range(40):
        ratings = {team: sum(w*(margin+ratings[opp]) for opp,margin,w in rows)/(3+sum(w for _,_,w in rows)) for team,rows in obs.items()}
    return ratings, {team: len(rows) for team,rows in obs.items()}

def cdf(x):
    return (1+erf(x/sqrt(2)))/2

def outcome(margin, line):
    threshold = -line
    win = 1-cdf((floor(threshold)+.5-margin)/13.5)
    push = 0.0
    if threshold == int(threshold):
        push = cdf((threshold+.5-margin)/13.5)-cdf((threshold-.5-margin)/13.5)
    return win, push

def annotate(rows, games, now):
    ratings, counts = fit(games, now)
    for row in rows:
        home, away = row["home"], row["away"]
        if min(counts.get(home,0), counts.get(away,0)) < 5:
            row["model_status"] = "Insufficient team history"
            continue
        margin = ratings[home]-ratings[away]+1.5
        if row["team"] == away:
            margin = -margin
        line = row["line"] if row["market"] == "spreads" else 0
        win, push = outcome(margin, line)
        row.update(projected_margin=round(margin,2), model_probability=round(win,6),
                   push_probability=round(push,6), model_status="Experimental; uncalibrated",
                   history_games=min(counts[home],counts[away]))
    return rows
