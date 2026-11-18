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
         +'Odds credits used: '+str(snapshot.get('oddsCreditsUsed','?'))+'\n'
         +'Credits remaining: '+str(snapshot.get('oddsCreditsRemaining') or 'unknown'))
        if success else 'The refresh did not complete successfully. See the workflow logs.'
    )
    run_url=os.environ.get('RUN_URL','')
    if run_url.startswith('https://github.com/'):
        message+='\nRun details: '+run_url
    headers={'Title':title,'Priority':'default' if success else 'high',
             'Tags':'basketball,white_check_mark' if success else 'warning'}
    token=os.environ.get('NTFY_TOKEN','').strip()
    if token:headers['Authorization']='Bearer '+token
    url='https://ntfy.sh/'+topic
    request=urllib.request.Request(url,data=message.encode('utf-8'),headers=headers,method='POST')
    with urllib.request.urlopen(request,timeout=15) as response:
        print('ntfy status HTTP',response.status)

if __name__=='__main__':main()
