"""Zero-odds-call opponent-defense / rotation shadow study.

Historical opponent-defense signals are keyed by ESPN opponent and position and
learned only from earlier game DATES. Missing identity is explicitly excluded.
No production prop scores or probabilities are modified.
"""
from collections import defaultdict
from datetime import date
import math

from model_comparison import paired_predictions
from prop_markets import MARKETS, stat_value
from shadow_projections import name_key

PRIOR_STRENGTH = 60
MIN_DEFENSE_MATCHUPS = 15
MIN_HOLDOUT_DATES = 20
MIN_HOLDOUT_OBSERVATIONS = 200
POSITIONS = {"PG", "SG", "SF", "PF", "C"}


def _position(g):
    pos = str(g.get("position", "")).upper()
    if pos in POSITIONS:
        return pos
    return None


def _clean_opponent(g):
    opponent = g.get("opponent")
    team = g.get("team")
    event = g.get("event")
    if not isinstance(opponent, str) or not opponent.strip():
        return None
    if not isinstance(team, str) or not team.strip():
        return None
    # Enforce actual scoreboard matchup consistency; no guessing team from name.
    if not isinstance(event, str) or " @ " not in event:
        return None
    away, home = event.split(" @ ", 1)
    if team not in (away, home):
        return None
    expected = home if team == away else away
    return opponent if opponent == expected else None


def _metrics(rows):
    n = len(rows)
    if not n:
        return {"n":0,"baseMAE":None,"rotationMAE":None,"defenseMAE":None,
                "defenseAndRotationMAE":None,"winner":"insufficient_data"}
    keys = ("base", "rotation", "defense", "defenseAndRotation")
    values = {k:sum(abs(r[k]-r["actual"]) for r in rows)/n for k in keys}
    return {"n":n,**{k+"MAE":round(v,3) for k,v in values.items()},
            "winner":min(keys,key=lambda k:values[k])}


def compare_context(logs):
    """All models evaluate the same contexts; learn defense from earlier dates.

    The fixed constants are not fit or chosen based on holdout outcomes.
    Matches without reliable positions/opponents are excluded; no adjustment
    for absent opponent context is silently treated as tested performance.
    """
    games_by_day=defaultdict(list)
    for row in logs:
        try:
            day=str(row["date"])
            date.fromisoformat(day)
            minutes=float(row.get("minutes"))
            if not math.isfinite(minutes) or minutes < 0 or not row.get("player"):
                continue
            games_by_day[day].append(row)
        except (KeyError,ValueError,TypeError,OverflowError):
            continue

    histories=defaultdict(list)
    # Context signal consists of cumulative capped actual/baseline ratios
    # for each (defense team, *specific* position, market).
    defense=defaultdict(lambda:[0.,0])
    evaluated=[]
    skipped={"missingOpponentOrPosition":0,"insufficientPlayerHistory":0,
             "insufficientPriorOpponentHistory":0}
    for day in sorted(games_by_day):
        todays=games_by_day[day]
        deferred=[]
        for g in todays:
            player=name_key(g["player"])
            prior=histories[player]
            opponent=_clean_opponent(g)
            position=_position(g)
            if not opponent or not position:
                skipped["missingOpponentOrPosition"]+=1
                continue
            if float(g["minutes"]) < 8:
                continue
            for market in MARKETS:
                actual=stat_value(g,market)
                if actual is None:
                    continue
                predicted=paired_predictions(prior,market)
                if predicted is None:
                    skipped["insufficientPlayerHistory"]+=1
                    continue
                baseline,rotation,_=predicted
                # Defensive ratios are learned from *other earlier games*
                # with valid identity, not the current or later game.
                key=(opponent,position,market)
                residual_total,n=defense[key]
                if n < MIN_DEFENSE_MATCHUPS:
                    skipped["insufficientPriorOpponentHistory"]+=1
                    deferred.append((key,baseline,actual))
                    continue
                factor = max(.85,min(1.15,(residual_total+PRIOR_STRENGTH) /
                                                   (n+PRIOR_STRENGTH)))
                evaluated.append({"date":day,"market":market,"actual":actual,
                                  "base":baseline,"rotation":rotation,
                                  "defense":baseline*factor,
                                  "defenseAndRotation":rotation*factor})
                deferred.append((key,baseline,actual))
        # All training updates happen AFTER every game on this date has
        # been evaluated, preventing same-day info leakage.
        # Historical opponent signals only update when the player had
        # enough earlier games to estimate an individual baseline.
        for key,baseline,actual in deferred:
            if baseline > .5:
                ratio=max(.5,min(1.5,actual/baseline))
                defense[key][0]+=ratio
                defense[key][1]+=1
        for g in todays:
            histories[name_key(g["player"])].append(g)

    dates=sorted({r["date"] for r in evaluated})
    cutoff=dates[int(.75*len(dates))] if dates else None
    tail=[r for r in evaluated if r["date"]>=cutoff] if cutoff else []
    by_market=defaultdict(list)
    for r in tail:
        by_market[r["market"]].append(r)
    holdout_ready=(len(tail)>=MIN_HOLDOUT_OBSERVATIONS and
                   len({r["date"] for r in tail})>=MIN_HOLDOUT_DATES)
    return {"status":"shadow_context_research_only",
            "productionChanges":False,"oddsApiCalls":0,
            "contextCoverage":skipped,
            "priorDefenseMatchupsRequired":MIN_DEFENSE_MATCHUPS,
            "allHistorical":_metrics(evaluated),
            "lastQuarterHoldout":{
                **_metrics(tail),"startDate":cutoff,
                "distinctDates":len({r["date"] for r in tail}),
                "sufficientForReview":holdout_ready,
                "minObservations":MIN_HOLDOUT_OBSERVATIONS,
                "minDates":MIN_HOLDOUT_DATES,
                "byMarket":{m:_metrics(by_market[m]) for m in MARKETS},
            },
            "limitations":"Only games with explicit scoreboard-consistent team, opponent and listed position are compared. Old incomplete history is excluded. Defense uses shrunk per-position residuals from prior eligible player-games; rotation uses a Claude-inspired minutes-rate core. Missing injury/lineup data means effects of injured teammates are NOT modeled. Statistical error is not betting ROI.",
            "modelNames":{"base":"NBA EDGE weighted mean",
                          "rotation":"Minutes-rate challenger",
                          "defense":"Prior opponent-position residual adjustment",
                          "defenseAndRotation":"Combined minutes and defense research"}}
