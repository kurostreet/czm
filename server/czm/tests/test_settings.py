import copy
import os
import tempfile
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from czm import accounts,api,db,service,settings
from czm.config import get_settings

class SettingsTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        p=patch.dict(os.environ,{'CZM_DATA_DIR':temp.name});p.start();self.addCleanup(p.stop)
        get_settings.cache_clear();self.addCleanup(get_settings.cache_clear);db.init()
        app=FastAPI();app.include_router(api.router);self.client=TestClient(app);self.addCleanup(self.client.close)
        self.tokens=[]
        for i in range(2):
            with db.db() as c:
                key='legacy-profile-secret-%d-123456'%i;service.hello(c,key,'device','Player','1','ru','test')
                self.tokens.append(accounts.register(c,key,'Player%d'%i,'Password123','Password123','ip%d'%i)['token'])
        self.data={'schema':1,'cvars':{'sensitivity':'2.4','czm_hud_style':'2','cl_crosshair_color':'34 200 135'},'layouts':{'1':[['fire','gfx/czm/touch/fire.png','+attack',.7,.6,.8,.8,255,255,255,200,0]]}}
    def get(self,token):return self.client.get('/api/v1/settings',headers={'X-CZM-Key':token})
    def save(self,token,rev,data):return self.client.post('/api/v1/settings',headers={'X-CZM-Key':token},json={'revision':rev,'payload':data})
    def test_reinstall_second_device_and_account_isolation(self):
        self.assertIsNone(self.get(self.tokens[0]).json()['payload'])
        r=self.save(self.tokens[0],0,self.data);self.assertEqual(r.status_code,200,r.text)
        with db.db() as c:second=accounts.login(c,'Player0','Password123','other-device')['token']
        self.assertEqual(self.get(second).json()['payload'],self.data)
        self.assertIsNone(self.get(self.tokens[1]).json()['payload'])
        self.assertEqual(self.get('forged').status_code,401)
    def test_stale_device_cannot_replace_new_settings(self):
        self.save(self.tokens[0],0,self.data)
        old=copy.deepcopy(self.data);old['cvars']['sensitivity']='1'
        self.assertEqual(self.save(self.tokens[0],0,old).status_code,409)
        self.assertEqual(self.get(self.tokens[0]).json()['payload'],self.data)
    def test_progress_hud_layout_round_trips_between_devices(self):
        self.data['cvars'].update({'czm_hud_progress_x':'0.41','czm_hud_progress_y':'0.75',
            'czm_hud_progress_scale':'1.25','czm_hud_progress_opacity':'0.5','czm_hud_progress_hidden':'1'})
        response=self.save(self.tokens[0],0,self.data)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.get(self.tokens[0]).json()['payload'],self.data)
    def test_import_does_not_execute_commands_or_include_credentials(self):
        for key,value in [('password','secret'),('rcon_password','secret'),('czm_hud_style','nan'),('cl_crosshair_color','256 0 0')]:
            bad=copy.deepcopy(self.data);bad['cvars'][key]=value
            self.assertEqual(self.save(self.tokens[0],0,bad).status_code,400,(key,value))
        for cmd in ['exec evil.cfg','+attack;quit','setinfo _pw secret']:
            bad=copy.deepcopy(self.data);bad['layouts']['1'][0][2]=cmd
            self.assertEqual(self.save(self.tokens[0],0,bad).status_code,400,cmd)
        for n in [float('inf'),-1,2]:
            bad=copy.deepcopy(self.data);bad['layouts']['1'][0][3]=n
            with self.assertRaises(accounts.AuthError):settings.validate(bad)
    def test_revisions_and_three_recovery_versions(self):
        for n in range(5):self.assertEqual(self.save(self.tokens[0],n,self.data).json()['revision'],n+1)
        with db.db() as c:self.assertEqual(c.execute('SELECT revision FROM settings_history ORDER BY revision').fetchall()[0][0],3)
        self.assertEqual(self.get(self.tokens[0]).headers['cache-control'],'no-store')
