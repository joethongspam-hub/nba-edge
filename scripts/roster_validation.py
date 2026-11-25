"""Current roster verification using public ESPN team feeds; no paid odds calls."""
from collections import defaultdict, Counter
from datetime import timedelta
from settlement import team_name, matchup_from_string, parse_time

def norm(value):
    return ''.join(c for c in str(value or '').casefold() if c.isalnum())

def history_index(logs):
    by_id=defaultdict(list)
    by_name=defaultdict(list)
    for row in logs:
        if row.get('playerId'): by_id[str(row['playerId'])].append(row)
        by_name[norm(row.get('player'))].append(row)
    return by_id,by_name

def player_history(prop,index):
    by_id,by_name=index
    rows=by_id.get(str(prop['playerId']),[]) if prop.get('playerId') else by_name.get(norm(prop.get('player')),[])
    start=parse_time(prop.get('startsAt'))
    # Explicitly dated logs must precede the advertised game.
    rows=[r for r in rows if not start or not parse_time(r.get('startsAt')) or parse_time(r['startsAt'])<start]
    return sorted(rows,key=lambda r:(r.get('date',''),r.get('startsAt','')),reverse=True)

def role_context(prop,games):
    team=team_name(prop.get('rosterTeam',''))
    known=[r for r in games[:40] if r.get('team')]
    other=sum(team_name(r['team'])!=team for r in known)
    return {'currentTeamHistoryGames':len(known)-other,'otherTeamHistoryGames':other,
            'roleReviewRequired':bool(other),
            'roleReviewNote':'Prior-team history present; projection not adjusted for changed role.' if other else None}

def team_directory(body):
    teams={}
    for sport in body.get('sports',[]):
        for league in sport.get('leagues',[]):
            for item in league.get('teams',[]):
                t=item.get('team',{})
                if t.get('id') and t.get('displayName'):
                    teams[team_name(t['displayName'])]=(str(t['id']),t['displayName'])
    return teams

def roster_index(body):
    players=defaultdict(set)
    def walk(node):
        if isinstance(node,list):
            for item in node:walk(item)
        elif isinstance(node,dict):
            if node.get('id') and (node.get('fullName') or node.get('displayName')):
                for field in ('fullName','displayName'):
                    if node.get(field):players[norm(node[field])].add(str(node['id']))
            for field in ('items','athletes'):
                if field in node:walk(node[field])
    walk(body.get('athletes',[]))
    return players

def validate_props(props,request,base,now):
    counts=Counter()
    examples={}
    teams_needed=set()
    for p in props:
        matchup=matchup_from_string(p.get('event'))
        if matchup:teams_needed.update(matchup.split(' @ '))
    directory={}
    if teams_needed:
        try:directory=team_directory(request(base+'/teams?limit=50'))
        except Exception:pass
    rosters={}
    for team in sorted(teams_needed):
        if team not in directory:continue
        tid,_=directory[team]
        try:
            body=request(base+'/teams/'+tid+'/roster')
            actual=body.get('team') or {}
            if actual.get('id') and str(actual['id'])!=tid:continue
            roster=roster_index(body)
            if roster:rosters[team]=roster
        except Exception:continue
    out=[]
    for p in props:
        matchup=matchup_from_string(p.get('event'))
        start=parse_time(p.get('startsAt'))
        if not start or start<=now:reason='not_pregame'
        elif not matchup:reason='invalid_matchup'
        else:
            teams=matchup.split(' @ ')
            if any(t not in rosters for t in teams):reason='roster_unavailable'
            else:
                hits={(t,i) for t in teams for i in rosters[t].get(norm(p.get('player')),set())}
                if len(hits)==1:
                    team,pid=next(iter(hits))
                    out.append({**p,'playerId':pid,'rosterTeam':directory[team][1],'rosterStatus':'verified'})
                    counts['verified']+=1
                    continue
                reason='ambiguous_player' if hits else 'player_not_on_matchup_rosters'
        counts[reason]+=1
        examples.setdefault(reason,set()).add(str(p.get('player'))+' | '+str(p.get('event')))
    return out,{'status':'complete' if teams_needed<=rosters.keys() else 'partial',
                'checkedAt':now.isoformat(),'totalProps':len(props),'verifiedProps':len(out),
                'excludedProps':len(props)-len(out),'counts':dict(counts),
                'unavailableTeams':sorted(teams_needed-rosters.keys()),
                'examples':{k:sorted(v)[:20] for k,v in examples.items()},
                'extraOddsApiCalls':0,'note':'Both matchup rosters must be available; exact normalized names resolve unique ESPN IDs. Membership is not active status. Prior-team history is flagged, not automatically adjusted.'}
