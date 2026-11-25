import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from team_role_shadow import project,report
from roster_validation import validate_props
from datetime import datetime,timezone

class TeamRoleTests(unittest.TestCase):
    def test_current_team(self):
        rows=[dict(date=f'2026-11-{i+1:02}',player='A',playerId='1',team='New' if i>=10 else 'Old',minutes=30,player_points=24 if i>=10 else 10) for i in range(20)]
        p=project(rows,'player_points','New')
        self.assertEqual(p['currentTeamGames'],10)
        self.assertEqual(p['previousTeamGames'],10)
        self.assertGreater(p['roleProjection'],p['baseline'])
        result=report({},rows)
        self.assertEqual(result['all']['n'],5)
        self.assertFalse(result['productionChanges'])
    def test_incomplete_snapshot(self):
        result=report({'ranked':[{'player':'Example','grade':'C'}]},[])
        self.assertEqual(result['today'],[])
    def test_missing_team(self):
        self.assertIsNone(project([], 'player_points',None))
    def test_suffix(self):
        def request(url):
            if 'limit' in url:return {'sports':[{'leagues':[{'teams':[{'team':{'id':'1','displayName':'A'}},{'team':{'id':'2','displayName':'B'}}]}]}]}
            return {'athletes':[{'id':'11' if '/1/' in url else '22','fullName':'Derrick Jones Jr.' if '/1/' in url else 'Other'}]}
        rows,_=validate_props([{'player':'Derrick Jones','event':'A @ B','startsAt':'2026-11-26T01:00:00Z'}],request,'base',datetime(2026,11,25,tzinfo=timezone.utc))
        self.assertEqual(rows[0]['playerId'],'11')
