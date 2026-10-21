"""Backend lobby isolation and lifecycle tests. No production database or external services."""
import os
import tempfile
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from czm import accounts, api, db, lobbies, service
from czm.config import get_settings

class LobbyTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        env=patch.dict(os.environ, {"CZM_DATA_DIR":temp.name, "CZM_PLAY_SERVICE_ACCOUNT_FILE":"/nonexistent"})
        env.start(); self.addCleanup(env.stop)
        get_settings.cache_clear(); self.addCleanup(get_settings.cache_clear)
        db.init()
        app=FastAPI(); app.include_router(api.router)
        self.client=TestClient(app); self.addCleanup(self.client.close)
        self.keys=[]; self.ids=[]
        with db.db() as c:
            for i in range(3):
                original="lobby-owner-key-legacy-%d"%i
                service.hello(c,original,"lobby-device-%d"%i,"Guest","","ru","test")
                user=accounts.register(c,original,"LobbyTester%d"%i,"Password123","Password123","ip%d"%i)
                self.keys.append(user["token"]); self.ids.append(user["profile"]["id"])

    def req(self,verb,path,actor=0,**kw):
        return self.client.request(verb,"/api/v1/lobbies"+path,headers={"X-CZM-Key":self.keys[actor]},**kw)

    def create(self,actor=0,nonce="lobby-unique-nonce-01",visibility="public",capacity=3):
        return self.req("POST","",actor,json={"title":"Zombie Team","description":"Play tonight",
           "visibility":visibility,"capacity":capacity,"server":"203.0.113.5:27015","proto":"gs","nonce":nonce})

    def test_create_join_ready_server_and_host_leave(self):
        r=self.create()
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json(),self.create().json())
        room=r.json()["lobby"]["id"]
        self.assertEqual(self.req("GET","").json()["lobbies"][0]["id"],room)
        self.assertEqual(self.req("POST",f"/{room}/join",1).status_code,200)
        self.assertEqual(self.req("POST",f"/{room}/ready",1,json={"revision":1,"ready":True}).status_code,200)
        self.assertTrue(self.req("GET",f"/{room}",1).json()["lobby"]["members"][1]["ready"])
        self.assertEqual(self.req("POST",f"/{room}/server",1,json={"server":"203.0.113.6:27015","proto":"gs"}).status_code,403)
        change=self.req("POST",f"/{room}/server",json={"server":"203.0.113.6:27015","proto":"49"})
        self.assertEqual(change.status_code,200,change.text)
        self.assertEqual(change.json()["lobby"]["revision"],2)
        self.assertFalse(change.json()["lobby"]["members"][1]["ready"])
        self.assertEqual(self.req("POST",f"/{room}/ready",1,json={"revision":1,"ready":True}).status_code,409)
        self.assertEqual(self.req("POST",f"/{room}/leave").json(),{"closed":True})
        self.assertEqual(self.req("GET","").json()["lobbies"],[])
        self.assertEqual(self.req("GET",f"/{room}",1).status_code,404)

    def test_private_and_capacity_and_single_membership(self):
        r=self.create(visibility="private",capacity=2)
        self.assertEqual(r.status_code,200,r.text)
        room=r.json()["lobby"]["id"]
        self.assertEqual(self.req("GET","",1).json()["lobbies"],[])
        self.assertEqual(self.req("POST",f"/{room}/join",1).status_code,403)
        self.assertEqual(self.req("GET",f"/{room}",1).status_code,403)
        pub=self.create(1,nonce="another-lobby-unique-02",capacity=2).json()["lobby"]["id"]
        self.assertEqual(self.req("POST",f"/{pub}/join",2).status_code,200)
        self.assertEqual(self.req("POST",f"/{pub}/join",2).status_code,200)
        self.assertEqual(self.req("POST",f"/{pub}/join").status_code,409)
        self.assertEqual(self.req("POST","",2,json={"title":"Other team","description":"","visibility":"public",
             "capacity":2,"server":"203.0.113.5:27015","proto":"gs","nonce":"other-unique-nonce-03"}).status_code,409)

    def test_permissions_messages_and_transfer(self):
        self.create()
        room=self.req("GET","/mine").json()["lobby"]["id"]
        self.req("POST",f"/{room}/join",1)
        msg={"text":"Hello friends","nonce":"lobby-message-nonce-01"}
        r=self.req("POST",f"/{room}/messages",1,json=msg)
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json(),self.req("POST",f"/{room}/messages",1,json=msg).json())
        self.assertEqual(self.req("GET",f"/{room}/messages",2).status_code,403)
        self.assertEqual(self.req("POST",f"/{room}/transfer",1,json={"target":self.ids[1]}).status_code,403)
        self.assertEqual(self.req("POST",f"/{room}/transfer",json={"target":self.ids[1]}).status_code,200)
        self.assertEqual(self.req("POST",f"/{room}/leave").json(),{"closed":False})
        self.assertEqual(self.req("POST",f"/{room}/leave",1).json(),{"closed":True})
        self.assertEqual(self.req("GET",f"/{room}/messages").status_code,404)

    def test_invalid_capacity_and_nonce(self):
        for n in [1,7,8]:
            r=self.create(capacity=n,nonce=f"invalid-capacity-{n}-nonce")
            self.assertIn(r.status_code,(400,422),r.text)
        self.assertEqual(self.create().status_code,200)
        self.assertEqual(self.create(capacity=2).status_code,409)

if __name__=="__main__":
    unittest.main()
