#!/usr/bin/env python3
"""Best-effort ntfy status message. Never print secrets or topic URLs."""
import json
import os
import re
import urllib.request
from pathlib import Path

def main():
    topic=os.environ.get('NTFY_TOPIC','').strip()
    if not topic:
        print('NTFY_TOPIC not configured; skipping optional notification')
        return
    if not re.fullmatch(r'[A-Za-z0-9_-]{8,128}',topic):
        raise ValueError('NTFY_TOPIC must be 8-128 letters, digits, underscores or dashes')
    status=os.environ.get('WORKFLOW_STATUS','unknown')
    try:
        snapshot=json.loads((Path(__file__).resolve().parents[1]/'docs'/'data.json').read_text())
    except (OSError,ValueError):snapshot={}
    success=status=='success'
    title='NBA EDGE refresh succeeded' if success else 'NBA EDGE refresh failed'
    message=(
        ('NBA EDGE 3.1: '+str(snapshot.get('refreshStatus','complete'))+'\n'
         +'Games checked: '+str(snapshot.get('eventsChecked','?'))+'\n'
         +'Props scanned: '+str(snapshot.get('propsScanned','?'))+'\n'
         +'Top picks: '+str(len(snapshot.get('ranked',[])))+'\n'
         +'Odds credits this run: '+str(snapshot.get('oddsCreditsUsed','?'))+'\n'
         +'Credits spent today: '+str(snapshot.get('oddsCreditsToday','?'))+'\n'
         +'Paid refreshes today: '+str(snapshot.get('oddsRefreshCount','?'))+'/2\n'
         +'Credits remaining: '+str(snapshot.get('oddsCreditsRemaining') or 'unknown')+' (2,000 reserve)')
        if success else 'The refresh did not complete successfully. See the workflow logs.'
    )
    team_mode=os.environ.get('TEAM_MARKETS_NOTIFY')=='true'
    if team_mode:
        title='SPORTS EDGE refresh succeeded' if success else 'SPORTS EDGE refresh failed'
        if success:
            try:
                team_data=json.loads((Path(__file__).resolve().parents[1]/'docs'/('team_context_refresh.json' if os.environ.get('TEAM_REFRESH_MODE')=='cached' else 'team_markets.json')).read_text())
                counts={sport:len({row['event_id'] for row in rows}) for sport,rows in team_data.get('sports',{}).items()}
                message='Team-market snapshot updated.\\n'+'\\n'.join(f'{sport}: {count} games' for sport,count in counts.items())+'\\nCredits remaining: '+str(team_data.get('odds_credits_remaining','unknown'))
                if os.environ.get('TEAM_REFRESH_MODE')=='cached':
                    message='Cached context refreshed (0 Odds API credits).\n'+ '\n'.join(f'{sport}: {count} games' for sport,count in counts.items())
                try:
                    changes=json.loads((Path(__file__).resolve().parents[1]/'docs'/'nhl_goalie_changes.json').read_text())
                    alerts=[c for c in changes.get('changes',[]) if c.get('alert')] if team_data.get('nhl_goalie_changes',{}).get('alerts',0)>0 else []
                    if alerts:
                        title='SPORTS EDGE goalie update'
                        message+='\nResearch-only goalie changes:\n'+'\n'.join(f"{c['team']}: {c['before']['name']} → {c['after']['name']} ({c['type']}); home win effect {100*c['home_probability_effect_change']:+.1f} pp" for c in alerts[:5])
                except (OSError,ValueError,KeyError,TypeError):
                    pass
            except (OSError,ValueError,KeyError):
                message='Refresh completed; snapshot summary unavailable.'
        else:
            message='Team-market refresh failed. See workflow logs.'
    run_url=os.environ.get('RUN_URL','')
    if run_url.startswith('https://github.com/'):
        message+='\nRun details: '+run_url
    headers={'Title':title,'Priority':'default' if success else 'high',
             'Tags':'basketball,white_check_mark' if success else 'warning',
             'Click':'https://joethongspam-hub.github.io/nba-edge/team-markets.html' if team_mode else 'https://joethongspam-hub.github.io/nba-edge/'}
    token=os.environ.get('NTFY_TOKEN','').strip()
    if token:headers['Authorization']='Bearer '+token
    url='https://ntfy.sh/'+topic
    request=urllib.request.Request(url,data=message.encode('utf-8'),headers=headers,method='POST')
    with urllib.request.urlopen(request,timeout=15) as response:
        print('ntfy status HTTP',response.status)

if __name__=='__main__':main()
