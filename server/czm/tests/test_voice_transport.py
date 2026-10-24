"""Regression: TestClient alone misses a missing production WebSocket engine."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from unittest.mock import patch
from websockets.sync.client import connect
from websockets.exceptions import InvalidStatus
from czm import accounts,db,lobbies,service
from czm.config import get_settings

class VoiceTransportTests(unittest.TestCase):
    def test_real_uvicorn_authentication_and_audio_relay(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ,{'CZM_DATA_DIR':folder,'CZM_PLAY_SERVICE_ACCOUNT_FILE':'/nonexistent'}):
                get_settings.cache_clear()
                self.addCleanup(get_settings.cache_clear)
                db.init();keys=[];players=[]
                with db.db() as c:
                    for i in range(2):
                        legacy='transport-legacy-%d'%i
                        service.hello(c,legacy,'transport-device-%d'%i,'Guest','','ru','test')
                        actor=accounts.register(c,legacy,'TransportUser%d'%i,'Password123','Password123','transport-ip-%d'%i)
                        keys.append(actor['token']);players.append(actor['profile']['id'])
                    room=lobbies.create(c,keys[0],'Voice Transport','','public',2,'203.0.113.5:27015','gs','transport-create-0001')['lobby']['id']
                    lobbies.join(c,keys[1],room)
                listener=socket.socket();listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
                app=Path(folder)/'transport_app.py'
                app.write_text('from fastapi import FastAPI\nfrom czm import api\napp=FastAPI()\napp.include_router(api.router)\n@app.get("/health")\ndef health():return {"ok":True}\n')
                code='import sys,socket,uvicorn;from transport_app import app;uvicorn.Server(uvicorn.Config(app,log_level="error",access_log=False,lifespan="off")).run(sockets=[socket.socket(fileno=int(sys.argv[1]))])'
                env=dict(os.environ);env['PYTHONPATH']=folder+os.pathsep+str(Path(__file__).resolve().parents[1])+os.pathsep+env.get('PYTHONPATH','')
                with (Path(folder)/'uvicorn.log').open('w+') as log:
                    process=subprocess.Popen([sys.executable,'-c',code,str(listener.fileno())],env=env,pass_fds=(listener.fileno(),),stdout=log,stderr=log)
                    listener.close()
                    try:
                        for attempt in range(150):
                            try:
                                urllib.request.urlopen('http://127.0.0.1:%d/health'%port,timeout=.2).close();break
                            except OSError:
                                if process.poll() is not None:self.fail('Uvicorn exited before becoming ready')
                                time.sleep(.02)
                        else:self.fail('Uvicorn did not become ready')
                        url='ws://127.0.0.1:%d/api/v1/lobbies/%s/voice'%(port,room)
                        with self.assertRaises(InvalidStatus) as denied:connect(url,open_timeout=3)
                        self.assertEqual(denied.exception.response.status_code,403)
                        with self.assertRaises(InvalidStatus):connect(url,additional_headers={'X-CZM-Key':'transport-legacy-0'},open_timeout=3)
                        with connect(url,additional_headers={'X-CZM-Key':keys[0]},open_timeout=3) as host:
                            with connect(url,additional_headers={'X-CZM-Key':keys[1]},open_timeout=3) as peer:
                                self.assertEqual(json.loads(host.recv(timeout=3))['type'],'joined')
                                self.assertEqual(json.loads(peer.recv(timeout=3))['type'],'joined')
                                host.send(b'U'+bytes([0xAA])*320)
                                self.assertEqual(json.loads(peer.recv(timeout=3))['type'],'talk')
                                packet=peer.recv(timeout=3)
                                self.assertEqual(packet,b'U'+players[0].to_bytes(4,'big')+bytes([0xAA])*320)
                    finally:
                        process.terminate()
                        try:process.wait(timeout=5)
                        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)

if __name__=='__main__':unittest.main()
