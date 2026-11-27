"""Experimental NHL final-margin distribution using recency-weighted goal ratings."""
from collections import defaultdict
from datetime import timedelta
from math import exp, sqrt
from urllib.request import urlopen
import json
from nba_team_model import parse_time

BASE = "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard"

def history(now):
    games = {}
    for offset in range(0, 84, 7):
        end = now.date() - timedelta(days=offset)
        start = end - timedelta(days=6)
        url = BASE + "?dates=" + start.strftime("%Y%m%d") + "-" + end.strftime("%Y%m%d") + "&limit=500"
        with urlopen(url, timeout=25) as response:
            board = json.load(response)
        for event in board.get("events", []):
            if not event.get("status", {}).get("type", {}).get("completed"):
                continue
            if event.get("season", {}).get("type") not in (2,3):
                continue
            time = parse_time(event["date"])
            if time >= now:
                continue
            comp = event["competitions"][0]
            teams = {c["homeAway"]: c for c in comp["competitors"]}
            if set(teams) != {"home","away"}:
                continue
            h,a = teams["home"],teams["away"]
            games[event["id"]] = (time,h["team"]["displayName"],a["team"]["displayName"],int(h["score"]),int(a["score"]),bool(comp.get("neutralSite")))
    return list(games.values())

def fit(games, now):
    obs = defaultdict(list)
    for time,home,away,hg,ag,neutral in games:
        if time >= now:
            continue
        w = exp(-(now-time).total_seconds()/86400/35)
        adj = 0 if neutral else .15
        obs[home].append((away,hg-adj,ag+adj,w))
        obs[away].append((home,ag+adj,hg-adj,w))
    attack = dict.fromkeys(obs,0.0)
    defense = dict.fromkeys(obs,0.0)
    for _ in range(40):
        new_a = {t:sum(w*(gf-3.0+defense[o]) for o,gf,ga,w in rows)/(5+sum(w for o,gf,ga,w in rows)) for t,rows in obs.items()}
        new_d = {t:sum(w*(3.0+attack[o]-ga) for o,gf,ga,w in rows)/(5+sum(w for o,gf,ga,w in rows)) for t,rows in obs.items()}
        attack,defense = new_a,new_d
    return attack,defense,{t:len(rows) for t,rows in obs.items()}

def poisson(rate):
    p = [exp(-rate)]
    for k in range(1,31):
        p.append(p[-1]*rate/k)
    total=sum(p)
    return [x/total for x in p]

def distribution(home_rate, away_rate):
    # Equal-score mass is split into one-goal final wins, not left as ties.
    # Rates are fitted to final scores; this is a heuristic, not a fitted OT model.
    result=defaultdict(float)
    for h,p in enumerate(poisson(home_rate)):
        for a,q in enumerate(poisson(away_rate)):
            if h==a:
                result[1]+=p*q*.5
                result[-1]+=p*q*.5
            else:
                result[h-a]+=p*q
    return dict(result)

def annotate(rows,games,now):
    attack,defense,counts=fit(games,now)
    for row in rows:
        home,away=row["home"],row["away"]
        if min(counts.get(home,0),counts.get(away,0))<8:
            row["model_status"]="Insufficient team history"
            continue
        h=max(.5,min(7,3+attack[home]-defense[away]+.15))
        a=max(.5,min(7,3+attack[away]-defense[home]-.15))
        dist=distribution(h,a)
        sign=1 if row["team"]==home else -1
        line=row["line"] if row["market"]=="spreads" else 0
        win=sum(p for m,p in dist.items() if sign*m+line>0)
        push=sum(p for m,p in dist.items() if sign*m+line==0)
        margin=sum(sign*m*p for m,p in dist.items())
        row.update(projected_margin=round(margin,2),model_probability=round(win,6),
                   push_probability=round(push,6),history_games=min(counts[home],counts[away]),
                   model_status="Experimental; uncalibrated")
    return rows
