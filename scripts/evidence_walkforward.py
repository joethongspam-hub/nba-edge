"""Offline walk-forward evidence reliability benchmark (zero external calls).

Each historical player-game-market prediction uses STRICTLY earlier game dates.
Score redesign is evaluated on the same projections, never fit on target results.
This is not a line-based betting backtest: historical sportsbook lines absent.
"""
from collections import defaultdict
from datetime import date, timedelta, datetime, timezone
from math import sqrt
from prop_markets import MARKETS, stat_value

MIN_HISTORY=15
MAX_HISTORY=40
MIN_HOLDOUT_DATES=20
MIN_HOLDOUT_OBSERVATIONS=200

def key(name):
    return "".join(c for c in str(name).casefold() if c.isalnum())

def history_stats(prior,market,as_of):
    """Recompute only production *pre-game* historical projection diagnostics."""
    eligible=[g for g in reversed(prior) if (g.get("minutes") or 0)>=12
              and stat_value(g,market) is not None][:MAX_HISTORY]
    if len(eligible)<MIN_HISTORY:
        return None
    values=[stat_value(g,market) for g in eligible]
    weights=[0.97**i for i in range(len(values))]
    total=sum(weights)
    projected=sum(w*v for w,v in zip(weights,values))/total
    variance=sum(w*(v-projected)**2 for w,v in zip(weights,values))/total
    std=max(sqrt(variance),1.1 if market=="player_points" else 0.75)
    minutes=[float(g["minutes"]) for g in eligible[:10]]
    mean_minutes=sum(minutes)/len(minutes)
    cv=(sqrt(sum((v-mean_minutes)**2 for v in minutes)/len(minutes))
        /max(1,mean_minutes))
    old_cutoff=as_of-timedelta(days=90)
    older=sum(date.fromisoformat(g["date"])<old_cutoff for g in eligible)
    return {"projection":projected,"sample":len(values),
            "recentMinutes":sum(float(g["minutes"]) for g in eligible[:5])/min(5,len(eligible)),
            "minutesCv":cv,"volatility":std,"oldGames":older}

def score(stats,method):
    """Predeclared two score definitions, both avoid outcome-target leakage."""
    n=stats["sample"]
    if method=="current":
        sample=min(35,n/40*35)
        age=min(25,stats["oldGames"]*1.5)
        cv_limit=.35
    elif method=="candidate":
        # Diminishing-returns sample credit: 20 games ~ 29/35 points.
        # Penalize old-game FRACTION rather than absolute old-game count.
        sample=35*n/(n+4)
        age=15*stats["oldGames"]/max(n,1)
        cv_limit=.45
    else:
        raise ValueError("Unknown score definition")
    minutes=min(20,stats["recentMinutes"]/32*20)
    stability=max(0,20*(1-min(1,stats["minutesCv"]/cv_limit)))
    variation=max(0,15*(1-min(1,stats["volatility"]/
                              max(2,abs(stats["projection"])))))
    return max(0,min(100,round(sample+minutes+stability+variation-age)))

def _summary(rows):
    n=len(rows)
    if not n:return {"n":0,"mae":None,"normalizedMAE":None,"meanScore":None,
                    "distinctDates":0}
    return {"n":n,
            "mae":round(sum(x["error"] for x in rows)/n,4),
            "normalizedMAE":round(sum(x["normError"] for x in rows)/n,4),
            "meanScore":round(sum(x["score"] for x in rows)/n,2),
            "distinctDates":len({x["date"] for x in rows})}

def report(logs):
    """Walk forward all eight markets on distinct (player, date, game) observations.

    No sportsbook odds, no randomized train/test leakage. Date-ordered holdout
    is the final quarter of distinct dates; 20 distinct dates AND 200 outcomes
    required to even mark diagnostics as reviewable.
    """
    grouped=defaultdict(list)
    for g in logs:
        if not g.get("player") or not g.get("date"):continue
        try:date.fromisoformat(g["date"])
        except (ValueError,TypeError):continue
        grouped[key(g["player"])].append(g)
    observations=[]
    duplicate_games=0
    for player,rows in grouped.items():
        ordered=sorted(rows,key=lambda r:(r["date"],str(r.get("gameId",""))))
        by_day=defaultdict(list)
        for r in ordered:by_day[r["date"]].append(r)
        prior=[]
        for day in sorted(by_day):
            current=by_day[day]
            as_of=date.fromisoformat(day)
            # Same-day games are never visible to one another.
            for g in current:
                if (g.get("minutes") or 0)<12:continue
                for market in MARKETS:
                    actual=stat_value(g,market)
                    if actual is None:continue
                    stats=history_stats(prior,market,as_of)
                    if stats is None:continue
                    err=abs(stats["projection"]-actual)
                    for method in ("current","candidate"):
                        observations.append({
                            "method":method,"date":day,"market":market,
                            "player":player,"score":score(stats,method),
                            "error":err,
                            "normError":err/max(stats["volatility"],1e-9),
                            "sample":stats["sample"],"oldGames":stats["oldGames"],
                            "eligible20":stats["sample"]>=20 and stats["oldGames"]<=20,
                        })
            prior.extend(current)
    days=sorted({x["date"] for x in observations})
    hold_days=set(days[-max(1,len(days)//4):]) if days else set()
    hold=[x for x in observations if x["date"] in hold_days]
    methods={}
    for method in ("current","candidate"):
        all_rows=[x for x in observations if x["method"]==method]
        hold_rows=[x for x in hold if x["method"]==method]
        qualified=[x for x in hold_rows if x["eligible20"] and x["score"]>=60]
        # Fair comparison: both methods use EXACTLY identical target outcomes
        # and projection/variance, only confidence/coverage differs.
        buckets=[]
        for low,high in ((0,40),(40,50),(50,60),(60,70),(70,80),(80,101)):
            subset=[x for x in hold_rows if low<=x["score"]<high and x["eligible20"]]
            buckets.append({"range":f"{low}-{high-1}",**_summary(subset)})
        methods[method]={
            "allHistorical":_summary(all_rows),
            "lastQuarter":_summary(hold_rows),
            "holdoutEligibleScore60":_summary(qualified),
            "holdoutEvidenceBands":buckets,
            "holdoutEligibleCount":sum(x["eligible20"] for x in hold_rows),
        }
    ncurrent=methods["current"]["lastQuarter"]["n"]
    ncandidate=methods["candidate"]["lastQuarter"]["n"]
    enough=len(hold_days)>=MIN_HOLDOUT_DATES and min(ncurrent,ncandidate)>=MIN_HOLDOUT_OBSERVATIONS
    # No "winner" from in-sample evidence thresholds. Promotion requires
    # future frozen-selection results + error discrimination across bands.
    return {
        "version":1,"status":"offline_walk_forward_shadow_only",
        "generatedAt":datetime.now(timezone.utc).isoformat(),
        "productionChanges":False,"extraOddsApiCalls":0,
        "markets":list(MARKETS),"distinctDates":len(days),
        "holdoutDistinctDates":len(hold_days),
        "holdoutStart":min(hold_days) if hold_days else None,
        "minHoldoutDistinctDates":MIN_HOLDOUT_DATES,
        "minHoldoutObservations":MIN_HOLDOUT_OBSERVATIONS,
        "sufficientForReview":enough,
        "methods":methods,
        "methodDefinitions":{
            "current":"Current 35*n/40 sample credit, old-games * 1.5 penalty, .35 minutes CV",
            "candidate":"35*n/(n+4) sample credit, 15*(old/n) age penalty, .45 minutes CV"},
        "interpretation":"Same observed games and same frozen historical-stat projections for both methods; only scores differ. Lower MAE within high-score groups may reflect sample selection rather than improved projections. Score bands depend on stat market; normalized MAE is descriptive, not calibrated confidence. No historical sportsbook lines, no profitability inference, no parameter tuning based on holdout.",
    }
