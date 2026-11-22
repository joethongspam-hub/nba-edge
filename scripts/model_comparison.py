"""Offline, paired NBA EDGE vs Claude-inspired core projection benchmark.

This reproduces the historical-rate + recent-minutes *core* idea from NBA-Picks,
NOT its full injury, position-defense, sportsbook or market-price model.
Both models see identical, strictly prior-date player logs. No odds calls.
"""
from collections import defaultdict
from datetime import date
import math

from prop_markets import MARKETS, stat_value
from shadow_projections import name_key

MIN_HISTORY = 15
MIN_HOLDOUT_SAMPLES = 200
MIN_HOLDOUT_DATES = 20


def season_key(day):
    """NBA season ending year; July-December belongs to the next season."""
    parsed = date.fromisoformat(day)
    return parsed.year + (parsed.month >= 7)


def _mean(values):
    return sum(values) / len(values) if values else None


def paired_predictions(prior, market):
    """Production baseline vs a Claude-style season/L10 minutes x rate challenger."""
    rows = [g for g in prior if g.get("minutes") is not None
            and float(g["minutes"]) >= 12 and stat_value(g, market) is not None]
    rows = sorted(rows, key=lambda g: (g["date"], str(g.get("gameId", ""))), reverse=True)[:40]
    if len(rows) < MIN_HISTORY:
        return None
    stats = [stat_value(g, market) for g in rows]
    minutes = [float(g["minutes"]) for g in rows]
    weights = [0.97 ** i for i in range(len(rows))]
    edge_mean = sum(v*w for v,w in zip(stats, weights))/sum(weights)

    # Claude-style profile: L10 rate plus current/previous-season production
    # rates, plus recent-five and current-season expected playing time.
    current_season = season_key(rows[0]["date"])
    current = [g for g in rows if season_key(g["date"]) == current_season]
    previous = [g for g in rows if season_key(g["date"]) == current_season - 1]
    current_rate = (sum(stat_value(g,market) for g in current) /
                    sum(float(g["minutes"]) for g in current)) if current else None
    prior_rate = (sum(stat_value(g,market) for g in previous) /
                  sum(float(g["minutes"]) for g in previous)) if previous else None
    recent = rows[:10]
    recent_rate = (sum(stat_value(g,market) for g in recent) /
                   sum(float(g["minutes"]) for g in recent))
    if current_rate is not None and prior_rate is not None:
        season_weight = len(current)/(len(current)+10)
        rate = (season_weight*(.65*current_rate+.35*recent_rate) +
                (1-season_weight)*(.60*prior_rate+.40*recent_rate))
    elif current_rate is not None:
        rate = .65*current_rate + .35*recent_rate
    elif prior_rate is not None:
        rate = .60*prior_rate + .40*recent_rate
    else:
        rate = recent_rate
    last5_min = _mean(minutes[:5])
    season_min = _mean([float(g["minutes"]) for g in current]) if current else _mean(minutes)
    proj_min = min(42., max(8., .5*last5_min+.5*season_min))
    challenger = max(0., proj_min*rate)
    return edge_mean, challenger, proj_min


def _accumulate(records):
    n = len(records)
    if not n:
        return {"n":0,"edgeMAE":None,"claudeCoreMAE":None,
                "edgeRMSE":None,"claudeCoreRMSE":None,
                "deltaMAE":None,"claudeCoreImprovementPct":None,
                "winner":"insufficient_data"}
    eb = sum(abs(r["baseline"]-r["actual"]) for r in records)/n
    cc = sum(abs(r["challenger"]-r["actual"]) for r in records)/n
    e2 = math.sqrt(sum((r["baseline"]-r["actual"])**2 for r in records)/n)
    c2 = math.sqrt(sum((r["challenger"]-r["actual"])**2 for r in records)/n)
    return {"n":n,"edgeMAE":round(eb,3),"claudeCoreMAE":round(cc,3),
            "edgeRMSE":round(e2,3),"claudeCoreRMSE":round(c2,3),
            "deltaMAE":round(eb-cc,3),
            "claudeCoreImprovementPct":round((eb-cc)/eb*100,2) if eb else None,
            "winner":"claude_core" if cc<eb else "nba_edge" if eb<cc else "tie"}


def compare(logs):
    grouped = defaultdict(list)
    for row in logs:
        if row.get("date") and row.get("player"):
            try:
                date.fromisoformat(row["date"])
                minutes = float(row.get("minutes"))
                if not math.isfinite(minutes) or minutes < 0:
                    continue
            except (ValueError, TypeError, OverflowError):
                continue
            grouped[name_key(row["player"])].append(row)

    records = []
    for games in grouped.values():
        # Group by day. Crucial: no game from the same calendar date may be
        # used to forecast any other game that date.
        by_date=defaultdict(list)
        for row in games:
            by_date[row["date"]].append(row)
        history=[]
        for day in sorted(by_date):
            todays = by_date[day]
            for g in todays:
                if float(g["minutes"]) < 8:
                    continue
                for market in MARKETS:
                    actual=stat_value(g,market)
                    if actual is None:
                        continue
                    prediction=paired_predictions(history,market)
                    if prediction is None:
                        continue
                    baseline,challenger,projected_min=prediction
                    records.append({"date":day,"market":market,"actual":actual,
                                    "baseline":baseline,"challenger":challenger,
                                    "actualMinutes":float(g["minutes"]),
                                    "projectedMinutes":projected_min})
            history.extend(todays)

    # A fixed, chronological last-quarter evaluation window is used only
    # for reporting. It does NOT select weights or tune parameters.
    dates=sorted({r["date"] for r in records})
    cutoff=dates[int(.75*len(dates))] if dates else None
    late=[r for r in records if r["date"]>=cutoff] if cutoff else []
    by_market=defaultdict(list)
    late_market=defaultdict(list)
    for r in records:
        by_market[r["market"]].append(r)
    for r in late:
        late_market[r["market"]].append(r)
    ready=len(late)>=MIN_HOLDOUT_SAMPLES and len({r["date"] for r in late})>=MIN_HOLDOUT_DATES
    return {
        "status":"historical_walk_forward_research_only",
        "modelA":"nba_edge_production_weighted_stat_mean_v3_4",
        "modelB":"claude_inspired_minutes_rate_core_v1",
        "modelsEvaluatedOnIdenticalGames":True,
        "productionChanges":False,
        "usesSportsbookPrices":False,
        "usesOpponentOrInjuryContext":False,
        "allWalkForward":_accumulate(records),
        "byMarket":{m:_accumulate(by_market[m]) for m in MARKETS},
        "lastQuarterHoldout":{
            **_accumulate(late),"startDate":cutoff,
            "distinctDates":len({r["date"] for r in late}),
            "minimumPairedSamples":MIN_HOLDOUT_SAMPLES,
            "minimumDistinctDates":MIN_HOLDOUT_DATES,
            "sufficientForReview":ready,
            "byMarket":{m:_accumulate(late_market[m]) for m in MARKETS},
        },
        "methodology":"For each player/date/stat, compare the existing NBA EDGE 40-game 0.97-weighted projection with a Claude-inspired last-10 and season blended per-minute rate times projected minutes. Train on strictly earlier dates; evaluate both on the same completed player games. Last quarter is a fixed chronological reporting holdout, not a fitted hyperparameter search.",
        "limitations":"Not the full Claude NBA-Picks model (injury, defense, odds, rest and market blending unavailable). Stats MAE does not establish prop win rate, ROI or profitable EV. Do not auto-promote based on one retrospective comparison.",
    }
