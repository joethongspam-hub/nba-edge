"""Fixed-weight current-team / role challenger; research only, no odds calls."""
from collections import defaultdict
import math
from prop_markets import MARKETS, stat_value
from settlement import team_name
from roster_validation import history_index, player_history

def weighted(values,weights):
    return sum(v*w for v,w in zip(values,weights))/sum(weights)

def project(prior,market,team):
    rows=sorted((g for g in prior if g.get('minutes',0)>=12 and stat_value(g,market) is not None),
                key=lambda g:(g.get('date',''),g.get('startsAt','')),reverse=True)[:40]
    if len(rows)<15 or not team:return None
    stats=[stat_value(g,market) for g in rows]
    mins=[float(g['minutes']) for g in rows]
    baseline=weighted(stats,[.97**i for i in range(len(rows))])
    current=[i for i,g in enumerate(rows) if g.get('team') and team_name(g['team'])==team_name(team)]
    other=[i for i,g in enumerate(rows) if g.get('team') and team_name(g['team'])!=team_name(team)]
    # Unknown teams receive conservative weight, never assumed current.
    weights=[.97**i*(1 if i in current else .35 if i in other else .60) for i in range(len(rows))]
    # Recent minutes estimate is shrunk toward the broader team-weighted role.
    recent=weighted(mins[:5],[.85**i for i in range(5)])
    expected_minutes=min(42,max(8,.65*recent+.35*weighted(mins,weights)))
    rates=[v/m for v,m in zip(stats,mins)]
    long_rate=weighted(rates,weights)
    recent_rate=weighted(rates[:10],weights[:10])
    role_rate=.65*long_rate+.35*recent_rate
    # Conservative shrinkage when current-team history is thin.
    blend=len(current)/(len(current)+8)
    prediction=max(0,(1-blend)*baseline+blend*expected_minutes*role_rate)
    return {'baseline':baseline,'roleProjection':prediction,'projectedMinutes':expected_minutes,
            'currentTeamGames':len(current),'previousTeamGames':len(other),
            'minutesShift':recent-weighted(mins,weights)}

def summarize(rows):
    n=len(rows)
    return {'n':n,'baselineMAE':round(sum(abs(x['baseline']-x['actual']) for x in rows)/n,3) if n else None,
            'roleMAE':round(sum(abs(x['roleProjection']-x['actual']) for x in rows)/n,3) if n else None,
            'baselineRMSE':round(math.sqrt(sum((x['baseline']-x['actual'])**2 for x in rows)/n),3) if n else None,
            'roleRMSE':round(math.sqrt(sum((x['roleProjection']-x['actual'])**2 for x in rows)/n),3) if n else None}

def report(snapshot,logs):
    index=history_index(logs)
    today=[]
    for p in snapshot.get('ranked',[])+snapshot.get('watchlist',[]):
        if p.get('market') not in MARKETS or not p.get('rosterTeam') or not snapshot.get('slateDate'):
            continue
        prior=[g for g in player_history(p,index) if g.get('date','')<snapshot['slateDate']]
        result=project(prior,p['market'],p.get('rosterTeam'))
        if result:today.append({'player':p['player'],'market':p['market'],**{k:round(v,3) for k,v in result.items()}})
    observations=[]
    for games in index[0].values():
        dates=defaultdict(list)
        for g in games:
            if g.get('date'):dates[g['date']].append(g)
        prior=[]
        for day in sorted(dates):
            for g in dates[day]:
                if not g.get('team') or g.get('minutes',0)<8:continue
                for market in MARKETS:
                    actual=stat_value(g,market)
                    if actual is None:continue
                    result=project(prior,market,g['team'])
                    if result:observations.append({**result,'date':day,'market':market,'actual':actual})
            prior.extend(dates[day])
    days=sorted({x['date'] for x in observations})
    cutoff=days[int(.75*len(days))] if days else None
    late=[x for x in observations if cutoff and x['date']>=cutoff]
    return {'status':'shadow_only','productionChanges':False,'extraOddsApiCalls':0,'today':today,
            'all':summarize(observations),'holdout':{**summarize(late),'startDate':cutoff,
            'distinctDates':len({x['date'] for x in late}),
            'byMarket':{m:summarize([x for x in late if x['market']==m]) for m in MARKETS},
            'transferred':summarize([x for x in late if x['previousTeamGames']>0])},
            'note':'Fixed weights; chronological replay on identical observations, target team known at game time assumed. Recent minutes and per-minute production proxy role, not measured usage. No injury adjustments. Retrospective errors are not betting profitability or independent samples; future validation required.'}
