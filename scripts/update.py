#!/usr/bin/env python3
"""NBA EDGE research screener. Published snapshots contain no API credentials."""
import json, os, urllib.request, urllib.parse, sys, math
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from pathlib import Path

BASE='https://site.api.espn.com/apis/site/v2/sports/basketball/nba'
ODDS='https://api.the-odds-api.com/v4/sports/basketball_nba'
ROOT=Path(__file__).resolve().parents[1]/'docs'
MARKETS=('player_points','player_rebounds','player_assists','player_threes')
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
    for team in body.get('boxscore',{}).get('players',[]):
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
    cutoff=(now-timedelta(days=65)).strftime('%Y-%m-%d')
    rows=[x for x in old.get('logs',[]) if x.get('date','')>=cutoff]
    games={k:v for k,v in old.get('games',{}).items() if v>=cutoff.replace('-','')}
    for days in range(38,0,-1):
        date=(now-timedelta(days=days)).strftime('%Y%m%d')
        try:board=request(BASE+'/scoreboard?'+urllib.parse.urlencode({'dates':date,'limit':50}))
        except Exception as e:
            print('Scoreboard warning',date,e,file=sys.stderr);continue
        for event in board.get('events',[]):
            eid=str(event.get('id',''))
            if not eid or eid in games or not (event.get('status',{}).get('type',{}).get('completed')):continue
            try:
                found=boxscore(eid,date[:4]+'-'+date[4:6]+'-'+date[6:])
                if found:rows.extend(found);games[eid]=date
            except Exception as e:print('Boxscore warning',eid,e,file=sys.stderr)
    rows=list({(r['gameId'],r['playerId']):r for r in rows if r.get('playerId')}.values())
    rows.sort(key=lambda r:r['date'])
    file.write_text(json.dumps({'games':games,'logs':rows},separators=(',',':'))+'\n')
    return rows

def odds(key,now):
    if not key:raise RuntimeError('Set ODDS_API_KEY in GitHub Actions secrets')
    events=request(ODDS+'/events',key)
    future=[e for e in events if e.get('commence_time','')>now.isoformat().replace('+00:00','Z')][:12]
    props=[];warnings=[]
    for event in future:
        args=urllib.parse.urlencode({'regions':'us','bookmakers':'draftkings,fanduel','markets':','.join(MARKETS),'oddsFormat':'american'})
        try:detail=request(ODDS+'/events/'+urllib.parse.quote(event['id'])+'/odds?'+args,key)
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
                    props.append({'player':outcome['description'],'market':market['key'],'side':outcome['name'],'line':line,'odds':int(price),'book':BOOKS[book['key']],'event':event.get('away_team','')+' @ '+event.get('home_team',''),'startsAt':event.get('commence_time','')})
    return props,warnings

def implied(price):
    return 100/(100+price) if price>0 else -price/(100-price)

def ranking_probability(prop, games):
    """Blend recent hit rate and a simple distribution estimate; both remain uncalibrated."""
    eligible=[g for g in games if g.get('minutes',0)>=12 and g.get(prop['market']) is not None][:20]
    if len(eligible)<15:return None
    values=[float(g[prop['market']]) for g in eligible]
    weights=[0.94**i for i in range(len(values))]
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
    return {'probability':max(0.05,min(0.95,probability)),'projection':mean,
            'sample':len(values),'last5Hits':sum(v>prop['line'] if prop['side']=='Over' else v<prop['line'] for v in values[:5]),
            'volatility':std,'recentMinutes':sum(g['minutes'] for g in eligible[:5])/min(5,len(eligible))}

def rank(props,logs):
    histories=defaultdict(list)
    for row in logs:
        histories[''.join(c for c in row['player'].casefold() if c.isalnum())].append(row)
    candidates=[]
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
        # Conservative research screen, not proof of a profitable bet.
        if ev<=0.045 or edge<=0.035:continue
        confidence='B' if stats['sample']>=18 and stats['recentMinutes']>=24 and stats['volatility']<max(3,stats['projection']*.55) else 'C'
        candidates.append({**prop,'probability':round(probability,4),'implied':round(implied(price),4),
          'edge':round(edge,4),'ev':round(ev,4),'projection':round(stats['projection'],1),
          'sample':stats['sample'],'last5Hits':stats['last5Hits'],'recentMinutes':round(stats['recentMinutes'],1),
          'volatility':round(stats['volatility'],1),'grade':confidence,'model':'Blended historical model (uncalibrated), no injury adjustment'})
    # Keep highest expected value, but avoid overloading the same player's correlated outcomes.
    candidates.sort(key=lambda p:p['ev'],reverse=True)
    top=[];used=set()
    for p in candidates:
        key=(p['player'].casefold(),p['startsAt'][:10])
        if key in used:continue
        used.add(key);top.append(p)
        if len(top)==10:break
    return top

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
        games=by_name[key]
        # Date +/- one day covers UTC times near midnight; only accept a game
        # whose date is the scheduled UTC day or immediate neighboring date.
        found=[g for g in games if abs((datetime.strptime(g['date'],'%Y-%m-%d').date()-game_time.date()).days)<=1
               and g.get(p['market']) is not None]
        if not found:continue
        # Avoid ambiguous games rather than settling the wrong event.
        if len(found)!=1:continue
        actual=float(found[0][p['market']])
        p['actual']=actual
        p['result']='push' if actual==p['line'] else ('win' if ((actual>p['line'])==(p['side']=='Over')) else 'loss')
        p['settledAt']=now.isoformat()
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
            ledger[-1].update({'id':id,'slate':slate,'recordedAt':now.isoformat(),'result':'pending'})
    # Bound size, but keep records from recent seasons.
    ledger=[p for p in ledger if p.get('slate','')>=(now-timedelta(days=365)).strftime('%Y-%m-%d')]
    file.write_text(json.dumps({'picks':ledger},separators=(',',':'))+'\\n')
    finished=[p for p in ledger if p.get('result') in ('win','loss','push')]
    wins=sum(p['result']=='win' for p in finished)
    losses=sum(p['result']=='loss' for p in finished)
    units=round(sum(p.get('units',0) for p in finished),3)
    graded=wins+losses
    return {'wins':wins,'losses':losses,'pushes':len(finished)-graded,'pending':sum(p.get('result')=='pending' for p in ledger),
            'units':units,'roi':round(units/graded,4) if graded else None,'winRate':round(wins/graded,4) if graded else None,
            'settled':len(finished),'recorded':len(ledger)}

def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    now=datetime.now(timezone.utc)
    key=os.environ.get('ODDS_API_KEY')
    if not key:raise RuntimeError('ODDS_API_KEY missing; snapshots unchanged')
    # Retrieve odds first: do not spend 38 days of backfill requests if the key is missing/broken.
    props,warnings=odds(key,now)
    if not props:raise RuntimeError('No valid odds returned; do not publish an empty refresh')
    logs=history(now)
    picks=rank(props,logs)
    performance=track(picks,logs,now)
    snapshot={'updatedAt':now.isoformat(),'ranked':picks,'propsScanned':len(props),'playersInHistory':len({r['playerId'] for r in logs}),'warnings':warnings,'modelVersion':'3.0-experimental','performance':performance}
    (ROOT/'data.json').write_text(json.dumps(snapshot,separators=(',',':'))+'\n')
    print('Props:',len(props),'Ranked:',len(picks),'History rows:',len(logs))

if __name__=='__main__':main()
