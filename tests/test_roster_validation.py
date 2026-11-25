import sys,unittest
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from roster_validation import validate_props,history_index,player_history,role_context

class RosterTests(unittest.TestCase):
    def test_rosters(self):
        now=datetime(2026,11,25,tzinfo=timezone.utc)
        def request(url):
            if 'limit' in url:return {'sports':[{'leagues':[{'teams':[{'team':{'id':'1','displayName':'LA Clippers'}},{'team':{'id':'2','displayName':'Memphis Grizzlies'}}]}]}]}
            return {'athletes':[{'items':[{'id':'11' if '/1/' in url else '22','fullName':'A. Player' if '/1/' in url else 'B Player'}]}]}
        def p(name):return {'player':name,'event':'Los Angeles Clippers @ Memphis Grizzlies','startsAt':'2026-11-26T01:00:00Z'}
        rows,report=validate_props([p('A Player'),p('B Player'),p('Unknown')],request,'base',now)
        self.assertEqual([x['playerId'] for x in rows],['11','22'])
        self.assertEqual(report['excludedProps'],1)
        rows,report=validate_props([p('A Player')],lambda u:{},'base',now)
        self.assertEqual(rows,[])
        self.assertEqual(report['counts']['roster_unavailable'],1)
    def test_id_and_prior_team(self):
        p={'player':'Same','playerId':'1','rosterTeam':'New'}
        logs=[{'player':'Same','playerId':'2','team':'New'},{'player':'Renamed','playerId':'1','team':'Old'}]
        rows=player_history(p,history_index(logs))
        self.assertEqual(len(rows),1)
        self.assertTrue(role_context(p,rows)['roleReviewRequired'])
