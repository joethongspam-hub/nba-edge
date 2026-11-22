#!/usr/bin/env python3
"""NBA EDGE research screener. Published snapshots contain no API credentials."""
import json, os, urllib.request, urllib.parse, sys, math
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from collections import defaultdict
from pathlib import Path
from settlement import unique_verified_log
from prop_markets import MARKETS, stat_value
from credit_budget import check_budget, remaining_from_headers, MAX_EVENT_COST, OddsBudgetError
from ranking_experiment import update_file as update_ranking_experiment

BASE='https://site.api.espn.com/apis/site/v2/sports/basketball/nba'
ODDS='https://api.the-odds-api.com/v4/sports/basketball_nba'
ROOT=Path(__file__).resolve().parents[1]/'docs'
BOOKS={'draftkings':'DraftKings','fanduel':'FanDuel'}

def request(url,key=None):
    headers={'User-Agent':'NBA-EDGE/2.0 research dashboard'}
    if key: headers['x-api-key']=key
    with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=18) as res:
        return json.load(res)

def num(v):
    try:return float(v)
    except (TypeError, ValueError):return None

def boxscore(event,date):
    body=request(BASE+'/summary?'+urllib.parse.urlencode({'event':event}))
    rows=[]
    # The event-specific ESPN summary can supply a verified matchup for
    # older rows where the saved scoreboard event label is incomplete.
    competitions=(body.get('header') or {}).get('competitions') or []
    competition=competitions[0] if competitions else {}
    sides=competition.get('competitors') or []
    def side_name(home_away):
        match=next((x for x in sides if x.get('homeAway')==home_away),None)
        info=(match or {}).get('team') or {}
        return info.get('displayName') or info.get('name')
    away_name,home_name=side_name('away'),side_name('home')
    verified_event=(away_name+' @ '+home_name) if away_name and home_name else None
    verified_start=competition.get('date')
    for team in body.get('boxscore',{}).get('players',[]):
        team_info=team.get('team') or {}
        own_team=str(team_info.get('displayName') or team_info.get('name') or '')
        own_team_id=str(team_info.get('id') or '')
        for group in team.get('statistics',[]):
            labels=[str(x).lower() for x in group.get('labels',[])]
            def column(*names):
                return next((labels.index(n) for n in names if n in labels),-1)
            cols={'minutes':column('min'),'player_points':column('pts'),'player_rebounds':column('reb'),'player_assists':column('ast'),'player_threes':column('3pt','3pm')}
            for entry in group.get('athletes',[]):
                if entry.get('didNotPlay'):continue
                stats=entry.get('stats') or []
                def value(name):
                    i=cols[name]
                    return stats[i] if i>=0 and i<len(stats) else None
                player=entry.get('athlete') or {}
                name=player.get('displayName') or player.get('fullName')
                minutes=num(str(value('minutes')).split(':')[0])
                pts=num(value('player_points'));reb=num(value('player_rebounds'));ast=num(value('player_assists'))
                if not name or minutes is None or pts is None or reb is None or ast is None:continue
                record={'player':name,'playerId':str(player.get('id','')),'gameId':event,'date':date,'minutes':minutes,'player_points':pts,'player_rebounds':reb,'player_assists':ast}
                if verified_event:record['event']=verified_event
                if verified_start:record['startsAt']=verified_start
                if own_team:record['team']=own_team
                if own_team_id:record['teamId']=own_team_id
                pos=entry.get('position') or player.get('position') or {}
                if isinstance(pos,dict):pos=pos.get('abbreviation') or ''
                if isinstance(pos,str) and pos.upper() in ('PG','SG','SF','PF','C'):
                    record['position']=pos.upper()
                threes=value('player_threes')
                if threes is not None:
                    parsed=num(str(threes).split('-')[0])
                    if parsed is not None:record['player_threes']=parsed
                rows.append(record)
    return rows

def history(now):
    file=ROOT/'game_logs.json'
    try:old=json.loads(file.read_text())
    except (OSError,ValueError):old={'games':{},'logs':[]}
    cutoff=(now-timedelta(days=220)).strftime('%Y-%m-%d')
    rows=[x for x in old.get('logs',[]) if x.get('date','')>=cutoff]
    games={k:v for k,v in old.get('games',{}).items() if v>=cutoff.replace('-','')}
    # Progressively backfill old NBA dates in manageable batches. No Odds API cost.
    # Persist successful scans, including dates without a completed game.
    scanned={d for d in old.get('scannedDates',[]) if d>=cutoff.replace('-','')}
    recent=[(now-timedelta(days=day)).strftime('%Y%m%d') for day in range(4,-1,-1)]
    older=[(now-timedelta(days=day)).strftime('%Y%m%d') for day in range(5,221)]
    dates=recent+[date for date in older if date not in scanned][:12]
    for date in dates:
        try:board=request(BASE+'/scoreboard?'+urllib.parse.urlencode({'dates':date,'limit':50}))
        except Exception as e:
            print('Scoreboard warning',date,e,file=sys.stderr);continue
        ok=True
        for event in board.get('events',[]):
            eid=str(event.get('id',''))
            if not eid or not (event.get('status',{}).get('type',{}).get('completed')):continue
            competitors=(event.get('competitions') or [{}])[0].get('competitors',[])
            home=next((c.get('team',{}).get('displayName') for c in competitors if c.get('homeAway')=='home'),None)
            away=next((c.get('team',{}).get('displayName') for c in competitors if c.get('homeAway')=='away'),None)
            matchup=(away+' @ '+home) if away and home else None
            scheduled=event.get('date')
            # Enrich even older saved boxscores with scoreboard event identity.
            # Only infer opponent for logs with an explicit team identity.
            def attach_context(row):
                if matchup: row['event']=matchup
                if scheduled: row['startsAt']=scheduled
                named=row.get('team')
                if named and named==home:row['opponent']=away
                elif named and named==away:row['opponent']=home
            if matchup and scheduled:
                for row in rows:
                    if row.get('gameId')==eid:
                        attach_context(row)
            if eid in games:continue
            try:
                found=boxscore(eid,date[:4]+'-'+date[4:6]+'-'+date[6:])
                if found:
                    if matchup and scheduled:
                        for row in found:
                            attach_context(row)
                    rows.extend(found);games[eid]=date
                else:ok=False
            except Exception as e:
                print('Boxscore warning',eid,e,file=sys.stderr)
                ok=False
        if ok:scanned.add(date)
    rows=list({(r['gameId'],r['playerId']):r for r in rows if r.get('playerId')}.values())
    rows.sort(key=lambda r:r['date'])
    # Preserve separately collected free-ESPN context progress across normal
    # refreshes. The scheduled picks workflow must not reset the backfill.
    payload={'games':games,'logs':rows,'scannedDates':sorted(scanned)}
    if isinstance(old.get('contextBackfill'),dict):
        payload['contextBackfill']=old['contextBackfill']
    file.write_text(json.dumps(payload,separators=(',',':'))+'\n')
    return rows

def odds(key,now):
    if not key:raise RuntimeError('Set ODDS_API_KEY in GitHub Actions secrets')
    # The free event listing provides a live quota header. If unavailable,
    # fail closed rather than guess and risk a paid credit overrun.
    req=urllib.request.Request(ODDS+'/events',
        headers={'User-Agent':'NBA-EDGE/3.4','x-api-key':key})
    with urllib.request.urlopen(req,timeout=18) as response:
        events=json.load(response)
        remaining=remaining_from_headers(response.headers)
    local_day=now.astimezone(ZoneInfo('America/Chicago')).date()
    future=[]
    for event in events:
        try:
            start=datetime.fromisoformat(event['commence_time'].replace('Z','+00:00'))
            if start>now and start.astimezone(ZoneInfo('America/Chicago')).date()==local_day:
                future.append(event)
        except (KeyError,ValueError):continue
    # All games or none. Never silently omit a game because of the quota.
    check_budget(remaining,len(future))
    props=[];warnings=[]
    credits_used=0;credits_remaining=str(remaining)
    for index,event in enumerate(future):
        # Recheck after every paid request in case the live balance changed.
        check_budget(remaining,len(future)-index)
        args=urllib.parse.urlencode({'regions':'us','bookmakers':'draftkings,fanduel','markets':','.join(MARKETS),'oddsFormat':'american'})
        try:
            url=ODDS+'/events/'+urllib.parse.quote(event['id'])+'/odds?'+args
            headers={'User-Agent':'NBA-EDGE/3.1','x-api-key':key}
            with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=18) as response:
                detail=json.load(response)
                cost_header=response.headers.get('x-requests-last')
                if cost_header is None:
                    raise OddsBudgetError('Missing per-request quota cost; stopping paid calls')
                cost=int(cost_header)
                credits_used+=cost
                remaining=remaining_from_headers(response.headers)
                credits_remaining=str(remaining)
                if cost>MAX_EVENT_COST:
                    raise OddsBudgetError('Unexpected Odds API event cost; stopping paid calls')
        except OddsBudgetError:
            raise  # Do not swallow budget violations and continue scanning.
        except Exception as e:
            warnings.append('Some events had unavailable odds');print('Odds warning',e,file=sys.stderr);continue
        for book in detail.get('bookmakers',[]):
            if book.get('key') not in BOOKS:continue
            for market in book.get('markets',[]):
                if market.get('key') not in MARKETS:continue
                for outcome in market.get('outcomes',[]):
                    if outcome.get('name') not in ('Over','Under') or not outcome.get('description'):continue
                    line=num(outcome.get('point'));price=num(outcome.get('price'))
                    if line is None or price is None or price==0:continue
                    props.append({'player':outcome['description'],'market':market['key'],'side':outcome['name'],'line':line,'odds':int(price),'book':BOOKS[book['key']],'event':event.get('away_team','')+' @ '+event.get('home_team',''),'startsAt':event.get('commence_time',''),'oddsEventId':event.get('id','')})
    if warnings:raise RuntimeError('One or more scheduled games failed to load; refresh aborted to avoid an incomplete slate.')
    return props,warnings,len(future),credits_used,credits_remaining

def implied(price):
    return 100/(100+price) if price>0 else -price/(100-price)

def ranking_probability(prop, games):
    """Blend recent hit rate and a simple distribution estimate; both remain uncalibrated."""
    eligible=[g for g in games if g.get('minutes',0)>=12 and stat_value(g, prop['market']) is not None][:40]
    if len(eligible)<15:return None
    values=[stat_value(g, prop['market']) for g in eligible]
    weights=[0.97**i for i in range(len(values))]
    total=sum(weights)
    mean=sum(w*v for v,w in zip(values,weights))/total
    variance=sum(w*(v-mean)**2 for v,w in zip(values,weights))/total
    std=max(math.sqrt(variance),1.1 if prop['market']=='player_points' else 0.75)
    # Continuity correction approximates discrete counting props.
    boundary=prop['line']+0.5 if prop['side']=='Over' else prop['line']-0.5
    z=(boundary-mean)/std
    distribution=0.5*math.erfc(z/math.sqrt(2))
    if prop['side']=='Under':distribution=1-distribution
    hit_weights=sum(w for v,w in zip(values,weights) if (v>prop['line'] if prop['side']=='Over' else v<prop['line']))
    empirical=(hit_weights+4)/(total+8)
    probability=0.55*empirical+0.45*distribution
    # Shrink toward neutral probability, guarding against overconfident small samples.
    probability=0.5+0.8*(probability-0.5)
    minutes=[g['minutes'] for g in eligible[:10]]
    minutes_mean=sum(minutes)/len(minutes)
    minutes_std=math.sqrt(sum((m-minutes_mean)**2 for m in minutes)/len(minutes))
    return {'probability':max(0.05,min(0.95,probability)),'projection':mean,
            'sample':len(values),'last5Hits':sum(v>prop['line'] if prop['side']=='Over' else v<prop['line'] for v in values[:5]),
            'volatility':std,'recentMinutes':sum(g['minutes'] for g in eligible[:5])/min(5,len(eligible)),
            'minutesCv':minutes_std/max(1,minutes_mean),
            'oldGames':sum(g.get('date','9999-12-31')<(datetime.now(timezone.utc)-timedelta(days=90)).strftime('%Y-%m-%d') for g in eligible)}

def rank(props,logs,return_candidates=False):
    histories=defaultdict(list)
    for row in logs:
        histories[''.join(c for c in row['player'].casefold() if c.isalnum())].append(row)
    candidates=[]  # Keep original EV-qualified pool for the frozen paper experiment.
    projection_candidates=[]
    for prop in props:
        name=''.join(c for c in prop['player'].casefold() if c.isalnum())
        games=sorted(histories[name],key=lambda g:g['date'],reverse=True)
        stats=ranking_probability(prop,games)
        if not stats:continue
        price=prop['odds']
        probability=stats['probability']
        profit=price/100 if price>0 else 100/-price
        ev=probability*profit-(1-probability)
        edge=probability-implied(price)
        # EV is retained only for the legacy paper comparison; it is NOT
        # a requirement or sorting input for the new production Top 10.
        # Evidence quality is separate from projected value and is NOT an outcome guarantee.
        # Old/offseason samples receive a large penalty, avoiding false confidence from
        # reaching 40 games by mixing prior-season rotations with the current season.
        sample_score=min(35,stats['sample']/40*35)
        minutes_score=min(20,stats['recentMinutes']/32*20)
        stability_score=max(0,20*(1-min(1,stats['minutesCv']/.35)))
        relative_volatility=stats['volatility']/max(2,abs(stats['projection']))
        variation_score=max(0,15*(1-min(1,relative_volatility)))
        value_score=min(10,max(0,edge)*75)
        age_penalty=min(25,stats['oldGames']*1.5)
        evidence_score=max(0,min(100,round(sample_score+minutes_score+stability_score+variation_score+value_score-age_penalty)))
        # A is withheld pending out-of-sample calibration with enough settled props.
        confidence=('B' if evidence_score>=75 else
                    'C' if evidence_score>=60 else
                    'D' if evidence_score>=45 else 'F')
        candidate={**prop,'probability':round(probability,4),'implied':round(implied(price),4),
          'edge':round(edge,4),'ev':round(ev,4),'projection':round(stats['projection'],1),
          'sample':stats['sample'],'last5Hits':stats['last5Hits'],'recentMinutes':round(stats['recentMinutes'],1),
          'volatility':round(stats['volatility'],1),'grade':confidence,'evidenceScore':evidence_score,
          'historyOlderThan90Days':stats['oldGames'],'model':'Historical weighted projection (uncalibrated; no injury adjustment)'}
        if ev>0.045 and edge>0.035:
            # Preserve legacy paper-experiment inputs and their original
            # evidence scoring for an apples-to-apples prospective replay.
            candidates.append(candidate.copy())
        # Separate *purely historical* evidence from the 10-point bookmaker
        # edge term; no EV, odds payout or hit-probability ranking inputs.
        pure_evidence=max(0,min(100,round(sample_score+minutes_score+
            stability_score+variation_score-age_penalty)))
        signed_gap=(stats['projection']-prop['line']) * (1 if prop['side']=='Over' else -1)
        normalized_gap=signed_gap/max(stats['volatility'],1e-9)
        # Require 20+ usable games, at least Grade C evidence, a meaningful
        # correctly-directed gap of 0.75 observed stat deviations, and a
        # minimum 0.5 physical stat gap. Under and Over are treated equally.
        if stats['sample']<20 or pure_evidence<60 or signed_gap<0.5 or normalized_gap<0.75:
            continue
        score=normalized_gap*(pure_evidence/100)**2
        model_grade=('B' if pure_evidence>=75 else 'C')
        projection_candidates.append({
            **candidate,'evidenceScore':pure_evidence,'grade':model_grade,
            'projectionGap':round(signed_gap,2),
            'normalizedGap':round(normalized_gap,3),
            'rankingScore':round(score,4),
            'rankingMethod':'projection_gap_evidence_v1',
        })
    # Compare across markets by gap / historical stat volatility; raw points
    # alone would otherwise swamp rebounds, assists and three-point props.
    projection_candidates.sort(key=lambda p:(-p['rankingScore'],
        -p['evidenceScore'],-p['normalizedGap'],p['player'].casefold(),
        p['market'],p['book']))
    top=[];used=set()
    for p in projection_candidates:
        key=(p['player'].casefold(),p['startsAt'][:10])
        if key in used:continue
        used.add(key);top.append(p)
        if len(top)==10:break
    return (top,candidates) if return_candidates else top

def settle_picks(ledger,logs,now):
    by_name=defaultdict(list)
    for row in logs:
        by_name[''.join(c for c in row['player'].casefold() if c.isalnum())].append(row)
    for p in ledger:
        if p.get('result')!='pending':continue
        try:game_time=datetime.fromisoformat(p['startsAt'].replace('Z','+00:00'))
        except (ValueError,KeyError):continue
        if now<game_time+timedelta(hours=4):continue
        key=''.join(c for c in p['player'].casefold() if c.isalnum())
        verified=unique_verified_log(p,by_name[key])
        if verified is None:
            p['settlementStatus']='awaiting_verified_game'
            continue
        actual=stat_value(verified,p['market'])
        if actual is None:
            p['settlementStatus']='awaiting_verified_stat'
            continue
        p['actual']=actual
        p['result']='push' if actual==p['line'] else ('win' if ((actual>p['line'])==(p['side']=='Over')) else 'loss')
        p['settledAt']=now.isoformat()
        p['settlementStatus']='verified_matchup_and_start'
        p['verifiedGameId']=verified['gameId']
        p['verifiedPlayerId']=verified.get('playerId')
        p['verifiedGameStart']=verified['startsAt']
        p['units']=round((p['odds']/100 if p['odds']>0 else 100/-p['odds']) if p['result']=='win' else (0 if p['result']=='push' else -1),4)

def track(top,logs,now):
    file=ROOT/'tracker.json'
    try:ledger=json.loads(file.read_text()).get('picks',[])
    except (OSError,ValueError):ledger=[]
    settle_picks(ledger,logs,now)
    # Freeze picks at their first published snapshot for each UTC slate date.
    # Later refreshes must not rewrite or replace these picks after odds move.
    slate=now.strftime('%Y-%m-%d')
    existing={p.get('id') for p in ledger}
    if not any(p.get('slate')==slate for p in ledger):
        for p in top:
            id='|'.join([slate,p['player'],p['market'],p['side'],str(p['line']),p['book']])
            if id in existing:continue
            ledger.append({k:p[k] for k in ('player','market','side','line','book','odds','event','startsAt','probability','edge','ev','grade')})
            # Freeze model diagnostics with the original line for true forward evaluation.
            # Previously recorded picks remain unchanged; no retroactive reconstruction.
            for field in ('projection','sample','evidenceScore','recentMinutes','volatility','implied',
                          'projectionGap','normalizedGap','rankingScore','rankingMethod'):
                if p.get(field) is not None:ledger[-1][field]=p[field]
            if p.get('oddsEventId'):ledger[-1]['oddsEventId']=p['oddsEventId']
            ledger[-1].update({'id':id,'slate':slate,'recordedAt':now.isoformat(),'result':'pending'})
    # Bound size, but keep records from recent seasons.
    ledger=[p for p in ledger if p.get('slate','')>=(now-timedelta(days=365)).strftime('%Y-%m-%d')]
    file.write_text(json.dumps({'picks':ledger},separators=(',',':'))+'\n')
    finished=[p for p in ledger if p.get('result') in ('win','loss','push')]
    wins=sum(p['result']=='win' for p in finished)
    losses=sum(p['result']=='loss' for p in finished)
    units=round(sum(p.get('units',0) for p in finished),3)
    graded=wins+losses
    return {'wins':wins,'losses':losses,'pushes':len(finished)-graded,'pending':sum(p.get('result')=='pending' for p in ledger),
            'units':units,'roi':round(units/graded,4) if graded else None,'winRate':round(wins/graded,4) if graded else None,
            'settled':len(finished),'recorded':len(ledger)}

def cached_props(slate):
    """Return previously captured full-slate props; no Odds API traffic."""
    try:
        cache=json.loads((ROOT/'odds_cache.json').read_text())
    except (OSError,ValueError):
        return None
    if cache.get('slateDate')!=slate or cache.get('cacheVersion')!=2:
        return None
    if not isinstance(cache.get('props'),list) or not isinstance(cache.get('eventsChecked'),int):
        return None
    return cache


def write_odds_cache(slate,now,props,events_checked,credits_used,credits_remaining):
    # This file contains only public sportsbook lines, never the API key.
    cache={'cacheVersion':2,'slateDate':slate,'fetchedAt':now.isoformat(),
           'props':props,'eventsChecked':events_checked,
           'oddsCreditsUsed':credits_used,'oddsCreditsRemaining':credits_remaining}
    (ROOT/'odds_cache.json').write_text(json.dumps(cache,separators=(',',':'))+'\n')
    return cache


def build_snapshot(now,slate,cache,logs,picks,performance,status):
    return {'updatedAt':now.isoformat(),'slateDate':slate,
            'oddsFetched':cache['eventsChecked']>0,'refreshStatus':status,
            'ranked':picks,'propsScanned':len(cache['props']),
            'eventsChecked':cache['eventsChecked'],
            'oddsCreditsUsed':0 if status=='recomputed_from_cache' else cache['oddsCreditsUsed'],
            'oddsCreditsRemaining':cache['oddsCreditsRemaining'],
            'oddsSnapshotAt':cache['fetchedAt'],
            'playersInHistory':len({r['playerId'] for r in logs}),
            'warnings':[],'modelVersion':'3.5-projection-confidence','performance':performance}


def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    now=datetime.now(timezone.utc)
    slate=now.astimezone(ZoneInfo('America/Chicago')).date().isoformat()
    cache=cached_props(slate)
    if cache is None:
        # Legacy snapshots lack raw props. Do not burn paid credits just to
        # migrate the same-day cache; collect odds normally next local day.
        try:previous=json.loads((ROOT/'data.json').read_text())
        except (OSError,ValueError):previous={}
        if previous.get('slateDate')==slate and previous.get('oddsFetched'):
            logs=history(now)
            previous['performance']=track([],logs,now)
            update_ranking_experiment(ROOT/'ranking_experiment.json',[],logs,now,slate)
            previous['updatedAt']=now.isoformat()
            previous['refreshStatus']='legacy_cached'
            (ROOT/'data.json').write_text(json.dumps(previous,separators=(',',':'))+'\n')
            print('Legacy daily cache has no raw props; 0 paid odds credits spent')
            return
        key=os.environ.get('ODDS_API_KEY')
        if not key:raise RuntimeError('ODDS_API_KEY missing; snapshots unchanged')
        props,warnings,events_checked,credits_used,credits_remaining=odds(key,now)
        cache=write_odds_cache(slate,now,props,events_checked,credits_used,credits_remaining)
        status='success' if events_checked else 'no_games'
    else:
        props=cache['props']
        status='recomputed_from_cache'
    logs=history(now)
    picks,candidates=rank(props,logs,return_candidates=True)
    update_ranking_experiment(ROOT/'ranking_experiment.json',candidates,logs,now,slate)
    performance=track(picks,logs,now)
    snapshot=build_snapshot(now,slate,cache,logs,picks,performance,status)
    (ROOT/'data.json').write_text(json.dumps(snapshot,separators=(',',':'))+'\n')
    print('Source:',status,'Games:',cache['eventsChecked'],'Props:',len(props),
          'Ranked:',len(picks),'Paid credits this run:',0 if status=='recomputed_from_cache' else cache['oddsCreditsUsed'])

if __name__=='__main__':main()
