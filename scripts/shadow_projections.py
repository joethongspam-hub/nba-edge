"""Shadow-only NBA prop projections from existing ESPN game logs.

These projections are explicitly experimental. No injuries, pace or matchup
adjustments are claimed; no odds API calls and no changes to betting picks.
"""
from collections import defaultdict
from datetime import datetime, timezone
import math
from prop_markets import MARKETS, stat_value



def name_key(name):
    return "".join(c for c in str(name).casefold() if c.isalnum())


def eligible_games(games, market, before_date=None):
    eligible = []
    for g in games:
        if stat_value(g, market) is None or not g.get("date") or g.get("minutes") is None:
            continue
        if before_date is not None and g["date"] >= before_date:
            continue
        try:
            minutes, actual = float(g["minutes"]), stat_value(g, market)
        except (TypeError, ValueError):
            continue
        if not all(math.isfinite(x) for x in (minutes, actual)):
            continue
        if minutes < 8 or actual < 0:
            continue
        eligible.append(g)
    return sorted(eligible, key=lambda g:(g["date"],str(g.get("gameId",""))), reverse=True)


def weighted_mean(values, decay=0.88):
    weights = [decay ** i for i in range(len(values))]
    return sum(w*v for w,v in zip(weights,values))/sum(weights)


def project(games, market, before_date=None):
    if market not in MARKETS:
        return None
    rows = eligible_games(games, market, before_date)[:30]
    if len(rows) < 12:
        return None
    # Minutes capture role changes; rate estimate is winsorized to stop
    # low-minute outliers from dominating per-minute expectations.
    minutes = [float(g["minutes"]) for g in rows]
    stats = [stat_value(g, market) for g in rows]
    recent_minutes = weighted_mean(minutes[:8], 0.83)
    baseline_minutes = weighted_mean(minutes, 0.96)
    projected_minutes = min(42.0, max(8.0, 0.75*recent_minutes+0.25*baseline_minutes))
    rates = [s/m for s,m in zip(stats,minutes)]
    rates_sorted = sorted(rates)
    low, high = rates_sorted[max(0,int(len(rates_sorted)*0.1))], rates_sorted[min(len(rates_sorted)-1,int(len(rates_sorted)*0.9))]
    rates = [min(high,max(low,r)) for r in rates]
    recent_rate = weighted_mean(rates[:10],0.86)
    longer_rate = weighted_mean(rates,0.96)
    expected_rate = 0.65*recent_rate+0.35*longer_rate
    projection = min(1.4*max(1.0,weighted_mean(stats,0.96)),
                     projected_minutes*expected_rate)
    minutes_cv = math.sqrt(sum((m-recent_minutes)**2 for m in minutes[:8])/8)/max(1,recent_minutes)
    role_change = (recent_minutes-baseline_minutes)/max(1,baseline_minutes)
    flags = []
    if abs(role_change)>=0.15:
        flags.append("recent_minutes_shift")
    if minutes_cv>=0.25:
        flags.append("unstable_minutes")
    if len(rows)<20:
        flags.append("limited_sample")
    flags.append("injury_and_matchup_not_adjusted")
    return {"projectedStat":round(max(0,projection),2),
            "projectedMinutes":round(projected_minutes,1),
            "recentMinutes":round(recent_minutes,1),
            "baselineMinutes":round(baseline_minutes,1),
            "roleChangePct":round(role_change*100,1),
            "sample":len(rows),
            "flags":flags,
            "model":"shadow_role_rate_v1"}


def compare_history(logs, min_previous=12):
    """Expanding chronological replay. Each game uses strictly prior dates."""
    by_player=defaultdict(list)
    for g in logs:
        by_player[name_key(g.get("player"))].append(g)
    sums={m:{"n":0,"shadowAbs":0.0,"baselineAbs":0.0,
             "shadowSq":0.0,"baselineSq":0.0} for m in MARKETS}
    for games in by_player.values():
        games=sorted(games,key=lambda g:(g.get("date",""),str(g.get("gameId",""))))
        for g in games:
            if not g.get("date"):
                continue
            previous=[v for v in games if v.get("date","")<g["date"]]
            if len(previous)<min_previous:
                continue
            for market in MARKETS:
                prediction=project(previous,market,before_date=g["date"])
                if prediction is None or stat_value(g,market) is None:
                    continue
                try:
                    actual=stat_value(g,market)
                except (TypeError,ValueError):
                    continue
                if not math.isfinite(actual):
                    continue
                baseline_values=[stat_value(v,market) for v in eligible_games(previous,market,g["date"])[:30]]
                if not baseline_values:
                    continue
                baseline=weighted_mean(baseline_values,0.96)
                shadow=prediction["projectedStat"]
                d=sums[market]
                d["n"]+=1
                d["shadowAbs"]+=abs(shadow-actual)
                d["baselineAbs"]+=abs(baseline-actual)
                d["shadowSq"]+=(shadow-actual)**2
                d["baselineSq"]+=(baseline-actual)**2
    return {market: {"n":d["n"],
                     "shadowMAE":round(d["shadowAbs"]/d["n"],3) if d["n"] else None,
                     "baselineMAE":round(d["baselineAbs"]/d["n"],3) if d["n"] else None,
                     "shadowRMSE":round(math.sqrt(d["shadowSq"]/d["n"]),3) if d["n"] else None,
                     "baselineRMSE":round(math.sqrt(d["baselineSq"]/d["n"]),3) if d["n"] else None}
            for market,d in sums.items()}


def report(snapshot, logs):
    by_player=defaultdict(list)
    for g in logs:
        by_player[name_key(g.get("player"))].append(g)
    picks=[]
    for p in snapshot.get("ranked",[]):
        market=p.get("market")
        projected=project(by_player[name_key(p.get("player"))],market,
                          before_date=snapshot.get("slateDate"))
        picks.append({"player":p.get("player"),"market":market,"side":p.get("side"),
                      "line":p.get("line"),"book":p.get("book"),
                      "shadowProjection":projected})
    return {"status":"research_only_not_ranked",
            "productionChanges":False,
            "injuryFeedConnected":False,
            "opponentAdjustmentConnected":False,
            "candidateProjections":picks,
            "historicalStatError":compare_history(logs),
            "note":"Stat-prediction MAE is not evidence of profitable prop odds; projections exclude injuries, pace, opponents and live rotations."}
