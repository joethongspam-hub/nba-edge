"""Research-only goalie adjustment to the existing NHL score model.
Coefficients are provisional, not calibrated. Never feeds production rankings.
"""
from math import isfinite
from datetime import timedelta
from nhl_team_model import fit, distribution
from team_history import parse_time

COEFFICIENT = .5
MAX_ADJUSTMENT = .5
STATUS_WEIGHT = {"confirmed": 1., "projected": .5}

def adjustment(goalie):
    rating = goalie.get("rating") or {}
    value = rating.get("relative_gsax60")
    status = goalie.get("status")
    if (status not in STATUS_WEIGHT or not rating.get("rating_eligible")
            or not isinstance(value, (int,float)) or not isfinite(value)):
        return None
    return max(-MAX_ADJUSTMENT,min(MAX_ADJUSTMENT,
               COEFFICIENT*STATUS_WEIGHT[status]*value))

def clamp(rate):
    return max(.5,min(7,rate))

def probabilities(dist,sign,line):
    return (sum(p for m,p in dist.items() if sign*m+line>0),
            sum(p for m,p in dist.items() if sign*m+line==0),
            sum(sign*m*p for m,p in dist.items()))

def annotate(rows,games,now):
    # Match existing baseline fit and distribution exactly.
    attack,defense,counts = fit(games,now)
    eligible,modeled,confirmed = set(),set(),set()
    cache = {}
    for row in rows:
        start = parse_time(row["start"])
        if not now < start <= now+timedelta(hours=36):
            continue
        h,a = row["home"],row["away"]
        key = (h,a,start)
        eligible.add(key)
        if min(counts.get(h,0),counts.get(a,0))<8:
            continue
        gh,ga = row.get("goalie_home",{}),row.get("goalie_away",{})
        dh,da = adjustment(gh),adjustment(ga)
        # Require both starters to have eligible ratings; do not silently
        # assign league-average ability to a missing or untrusted goalie.
        if dh is None or da is None:
            continue
        hr = clamp(3+attack[h]-defense[a]+.15)
        ar = clamp(3+attack[a]-defense[h]-.15)
        # A stronger home goalie lowers the away scoring rate, and vice versa.
        adj_h,adj_a = clamp(hr-da),clamp(ar-dh)
        dk = (hr,ar,adj_h,adj_a)
        if dk not in cache:
            cache[dk] = (distribution(hr,ar),distribution(adj_h,adj_a))
        baseline,adjusted = cache[dk]
        sign = 1 if row["team"]==h else -1
        line = row["line"] if row["market"]=="spreads" else 0
        base,_,_ = probabilities(baseline,sign,line)
        win,push,margin = probabilities(adjusted,sign,line)
        row.update(goalie_probability=round(win,6),goalie_push=round(push,6),
                   goalie_margin=round(margin,3),goalie_baseline_probability=round(base,6),
                   goalie_probability_delta=round(win-base,6),
                   goalie_home_rate=round(adj_h,3),goalie_away_rate=round(adj_a,3),
                   goalie_home_adjustment=round(dh,3),goalie_away_adjustment=round(da,3),
                   goalie_model_status="experimental_confirmed" if
                   gh["status"]==ga["status"]=="confirmed" else "experimental_projected")
        modeled.add(key)
        if gh["status"]==ga["status"]=="confirmed":
            confirmed.add(key)
    return {"eligible_games":len(eligible),"modeled_games":len(modeled),
            "both_confirmed_games":len(confirmed),"coefficient":COEFFICIENT,
            "projected_weight":STATUS_WEIGHT["projected"],"max_adjustment":MAX_ADJUSTMENT,
            "research_only":True,"checked_at":now.isoformat()}
