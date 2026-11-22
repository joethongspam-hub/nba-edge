"""Zero-odds-request evidence-score sensitivity study for the projection Top 10.

Retrospective same-slate *eligibility yield only*: not a betting backtest and
never changes live grade/thresholds, historical outcomes, or frozen picks.
"""
from collections import defaultdict
from datetime import datetime, timezone
from evidence_walkforward import score as redesigned_score

VERSION = 1
SCENARIOS = (
    ("current", "Current: evidence 60 / 20 games", 60, 20, 0.35),
    ("evidence_55", "Evidence threshold 55 / 20 games", 55, 20, 0.35),
    ("evidence_50", "Evidence threshold 50 / 20 games", 50, 20, 0.35),
    ("evidence_45", "Evidence threshold 45 / 20 games", 45, 20, 0.35),
    ("minutes_cv_050", "Minutes consistency tolerance 0.50 / evidence 60", 60, 20, 0.50),
    ("games_15_evidence_55", "15 games / evidence 55", 55, 15, 0.35),
)
BUCKETS = ((0,30),(30,40),(40,45),(45,50),(50,55),
           (55,60),(60,70),(70,80),(80,101))


def components(stats, minutes_cv_tolerance=0.35):
    """Match Upgrade 22 *pure* evidence inputs exactly at tolerance 0.35."""
    sample=min(35,stats["sample"]/40*35)
    minutes=min(20,stats["recentMinutes"]/32*20)
    stability=max(0,20*(1-min(1,stats["minutesCv"]/minutes_cv_tolerance)))
    variation=max(0,15*(1-min(1,stats["volatility"]/max(2,abs(stats["projection"])))))
    age_penalty=min(25,stats["oldGames"]*1.5)
    pure=max(0,min(100,round(sample+minutes+stability+variation-age_penalty)))
    return {"sample":sample,"minutes":minutes,"minutesStability":stability,
            "statConsistency":variation,"agePenalty":age_penalty,
            "evidence":pure}


def _select(rows, threshold, min_games, cv_tolerance, scoring_method='current'):
    qualifying=[]
    markets=defaultdict(int)
    for p,stats,gap,normalized in rows:
        if stats["sample"]<min_games or stats["oldGames"]>20:
            continue
        evidence=(redesigned_score(stats,'candidate') if scoring_method=='candidate'
                  else components(stats,cv_tolerance)['evidence'])
        if evidence<threshold or gap<0.5 or normalized<0.75:
            continue
        score=normalized*(evidence/100)**2
        qualifying.append((score,evidence,normalized,p))
        markets[p["market"]]+=1
    qualifying.sort(key=lambda x:(-x[0],-x[1],-x[2],
                                 x[3]["player"].casefold(),x[3]["market"],x[3]["book"]))
    unique=set()
    selected=[]
    for score,evidence,normalized,p in qualifying:
        identity=(p["player"].casefold(),p["startsAt"][:10])
        if identity in unique:
            continue
        unique.add(identity)
        if len(selected)<10:
            selected.append((p,score,evidence))
    return {
        "eligibleProps":len(qualifying),
        "uniquePlayerDates":len(unique),
        "top10Count":len(selected),
        "byMarket":dict(sorted(markets.items())),
        "meanEvidenceTop10":round(sum(x[2] for x in selected)/len(selected),1)
                               if selected else None,
    }


def analyze(props,logs,stats_for_prop,generated_at=None):
    """Examine original sportsbook lines and ESPN history without network calls.

    stats_for_prop is the existing ranking_probability function, injected to
    avoid maintaining a second projection model. Calculations use only saved
    current-slate prop odds-cache records and ESPN history.
    """
    histories=defaultdict(list)
    for g in logs:
        name=g.get("player")
        if name:
            key="".join(c for c in name.casefold() if c.isalnum())
            histories[key].append(g)
    for rows in histories.values():
        rows.sort(key=lambda g:g.get("date",""),reverse=True)
    observed=[]
    scored=[]
    gap_pool=[]
    for p in props:
        name="".join(c for c in str(p.get("player","")).casefold() if c.isalnum())
        if not name or p.get("side") not in ("Over","Under"):
            continue
        stats=stats_for_prop(p,histories[name])
        if stats is None:
            continue
        gap=(stats["projection"]-p["line"])*(1 if p["side"]=="Over" else -1)
        normalized=gap/max(stats["volatility"],1e-9)
        observed.append((p,stats,gap,normalized))
        if stats["sample"]>=20 and stats["oldGames"]<=20:
            c=components(stats)
            scored.append(c)
            if gap>=0.5 and normalized>=0.75:
                gap_pool.append(c)

    scenarios={}
    for key,label,threshold,min_games,tolerance in SCENARIOS:
        scenarios[key]={"label":label,
                        "minimumEvidence":threshold,
                        "minimumGames":min_games,
                        "minutesCvTolerance":tolerance,
                        **_select(observed,threshold,min_games,tolerance)}
    scenarios['redesigned_60']={'label':'Redesigned sample/age score >=60, 20 games',
        'minimumEvidence':60,'minimumGames':20,'minutesCvTolerance':0.45,
        'researchOnly':True,
        **_select(observed,60,20,0.45,scoring_method='candidate')}
    mean=lambda arr,key:(round(sum(x[key] for x in arr)/len(arr),2)
                         if arr else None)
    breakdown={}
    for key in ("sample","minutes","minutesStability","statConsistency","agePenalty","evidence"):
        breakdown[key]={"allWith20GamesMean":mean(scored,key),
                        "strongGapPoolMean":mean(gap_pool,key)}
    score_buckets=[
        {"range":f"{low}-{high-1}",
         "count":sum(low<=c["evidence"]<high for c in scored),
         "strongGapCount":sum(low<=c["evidence"]<high for c in gap_pool)}
        for low,high in BUCKETS
    ]
    return {
        "version":VERSION,
        "status":"offline_same_slate_sensitivity_only",
        "generatedAt":generated_at or datetime.now(timezone.utc).isoformat(),
        "source":"current odds cache + ESPN player logs, same projection scorer as live ranker",
        "productionChanges":False,
        "extraOddsApiCalls":0,
        "totalProps":len(props),
        "with15GameProjection":len(observed),
        "with20GamesAndFreshness":len(scored),
        "strongGapRegardlessOfEvidence":len(gap_pool),
        "scoreComponents":breakdown,
        "evidenceDistribution":score_buckets,
        "scenarios":scenarios,
        "limitations":"This is a same-slate what-if eligibility/screening study, not a prospective outcome backtest. Alternative thresholds were examined after seeing the zero-pick slate, and have not demonstrated predictive accuracy or profitability. Do not promote any scenario without future verified results."
    }
