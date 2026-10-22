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

    def link_friends(self,a=0,b=1):
        for src,dst in ((a,b),(b,a)):
            response=self.client.post("/api/v1/social/action",
                headers={"X-CZM-Key":self.keys[src]},
                json={"target":self.ids[dst],"action":"follow"})
            self.assertEqual(response.status_code,200,response.text)

    def invite(self,room,actor=0,target=1,nonce="invite-test-nonce-001"):
        return self.req("POST",f"/{room}/invite/{self.ids[target]}",actor,json={"nonce":nonce})

    def test_private_invites_are_recipient_bound_and_idempotent(self):
        room=self.create(visibility="private").json()["lobby"]["id"]
        self.assertEqual(self.invite(room).status_code,403)
        self.link_friends()
        invited=self.invite(room)
        self.assertEqual(invited.status_code,200,invited.text)
        self.assertEqual(self.invite(room).json(),invited.json())
        invitation=invited.json()["invite"]["id"]
        self.assertEqual(self.req("GET","/invitations",2).json()["invites"],[])
        self.assertEqual(len(self.req("GET","/invitations",1).json()["invites"]),1)
        self.assertEqual(self.req("POST",f"/invitations/{invitation}/answer",2,
                                  json={"accept":True}).status_code,404)
        accepted=self.req("POST",f"/invitations/{invitation}/answer",1,json={"accept":True})
        self.assertEqual(accepted.status_code,200,accepted.text)
        self.assertEqual(accepted.json(),self.req("POST",f"/invitations/{invitation}/answer",1,
                                                 json={"accept":True}).json())
        self.assertEqual(len(accepted.json()["lobby"]["members"]),2)

    def test_invites_expire_and_close_with_room(self):
        self.link_friends()
        room=self.create(visibility="private").json()["lobby"]["id"]
        invitation=self.invite(room).json()["invite"]["id"]
        with patch("czm.lobbies.now",return_value=lobbies.now()+lobbies.INVITE_SECONDS+1):
            self.assertEqual(self.req("GET","/invitations",1).json()["invites"],[])
            expired=self.req("POST",f"/invitations/{invitation}/answer",1,json={"accept":True})
            self.assertEqual(expired.status_code,410,expired.text)
        self.assertEqual(self.req("POST",f"/{room}/leave").status_code,200)
        self.assertEqual(self.req("POST",f"/invitations/{invitation}/answer",1,
                                  json={"accept":True}).status_code,404)

    def test_invite_block_and_decline_reinvite(self):
        self.link_friends()
        room=self.create().json()["lobby"]["id"]
        self.req("POST",f"/{room}/join",2)
        self.assertEqual(self.invite(room,actor=2).status_code,403)
        a=self.invite(room).json()["invite"]["id"]
        self.assertEqual(self.req("POST",f"/invitations/{a}/answer",1,
                                  json={"accept":False}).status_code,200)
        b=self.invite(room,nonce="invite-test-nonce-002").json()["invite"]["id"]
        self.assertNotEqual(a,b)
        self.client.post("/api/v1/social/action",
            headers={"X-CZM-Key":self.keys[1]},
            json={"target":self.ids[0],"action":"block"})
        self.assertEqual(self.req("POST",f"/invitations/{b}/answer",1,
                                  json={"accept":True}).status_code,403)

    def test_edit_capacity_visibility_permissions(self):
        room=self.create(capacity=3).json()["lobby"]["id"]
        self.req("POST",f"/{room}/join",1)
        self.assertEqual(self.req("POST",f"/{room}/edit",1,
            json={"title":"New", "description":"", "visibility":"private","capacity":2}).status_code,403)
        no=self.req("POST",f"/{room}/edit",json={"title":"New","description":"",
                                                "visibility":"private","capacity":1})
        self.assertIn(no.status_code,(400,422))
        changed=self.req("POST",f"/{room}/edit",json={"title":"New Room","description":"Run",
                                                   "visibility":"private","capacity":2})
        self.assertEqual(changed.status_code,200,changed.text)
        self.assertEqual(self.req("GET","",2).json()["lobbies"],[])
        self.assertEqual(self.req("POST",f"/{room}/join",2).status_code,403)

    def test_invite_not_exposed_after_block_and_transfer(self):
        self.link_friends()
        self.link_friends(0,2)
        room=self.create().json()["lobby"]["id"]
        invited=self.invite(room).json()["invite"]["id"]
        self.client.post("/api/v1/social/action",
            headers={"X-CZM-Key":self.keys[1]},
            json={"target":self.ids[0],"action":"block"})
        self.assertEqual(self.req("GET","/invitations",1).json()["invites"],[])
        self.assertEqual(self.req("POST",f"/invitations/{invited}/answer",1,
                                  json={"accept":True}).status_code,403)
        self.req("POST",f"/{room}/join",2)
        self.assertEqual(self.invite(room,actor=2,nonce="bad-invite-nonce-03").status_code,403)
        self.client.post("/api/v1/social/action",
            headers={"X-CZM-Key":self.keys[1]},
            json={"target":self.ids[0],"action":"unblock"})
        self.link_friends()
        self.assertEqual(self.req("POST",f"/{room}/transfer",
                                  json={"target":self.ids[2]}).status_code,200)
        self.assertEqual(self.req("GET","/invitations",1).json()["invites"],[])
        self.assertEqual(self.req("POST",f"/invitations/{invited}/answer",1,
                                  json={"accept":True}).status_code,409)

    def test_internal_launch_atomic_close_ready_and_idempotency(self):
        self.create()
        room=self.req("GET","/mine").json()["lobby"]["id"]
        self.req("POST",f"/{room}/join",1)
        with db.db() as conn:
            with self.assertRaises(accounts.AuthError) as issue:
                lobbies.launch_internal(conn,self.keys[0],room,"launch-request-0001",1)
            self.assertEqual(issue.exception.code,"members_not_ready")
        self.assertEqual(len(self.req("GET","").json()["lobbies"]),1)
        self.req("POST",f"/{room}/ready",1,json={"revision":1,"ready":True})
        with db.db() as conn:
            with self.assertRaises(accounts.AuthError) as issue:
                lobbies.launch_internal(conn,self.keys[1],room,"launch-request-0001",1)
            self.assertEqual(issue.exception.code,"not_owner")
            first=lobbies.launch_internal(conn,self.keys[0],room,"launch-request-0001",1)
            again=lobbies.launch_internal(conn,self.keys[0],room,"launch-request-0001",1)
            self.assertEqual(first,again)
            self.assertEqual(first["launch"]["size"],2)
            self.assertEqual(set(first["launch"]["members"]),set(self.ids[:2]))
            self.assertEqual(lobbies.pending_launch(conn,self.keys[1])["launches"][0]["id"],
                             first["launch"]["id"])
            self.assertEqual(lobbies.pending_launch(conn,self.keys[2])["launches"],[])
            with self.assertRaises(accounts.AuthError) as different:
                lobbies.launch_internal(conn,self.keys[0],room,"launch-request-0002",1)
            self.assertEqual(different.exception.code,"launch_already_started")
        self.assertEqual(self.req("GET","").json()["lobbies"],[])
        self.assertEqual(self.req("GET",f"/{room}/messages",1).status_code,404)

    def test_internal_launch_stale_revision_preserves_room(self):
        self.create()
        room=self.req("GET","/mine").json()["lobby"]["id"]
        self.req("POST",f"/{room}/join",1)
        self.req("POST",f"/{room}/ready",1,json={"revision":1,"ready":True})
        self.req("POST",f"/{room}/server",json={"server":"203.0.113.6:27015","proto":"49"})
        with db.db() as conn:
            with self.assertRaises(accounts.AuthError) as issue:
                lobbies.launch_internal(conn,self.keys[0],room,"launch-request-0003",1)
            self.assertEqual(issue.exception.code,"stale_revision")
        self.assertEqual(len(self.req("GET","").json()["lobbies"]),1)

    def test_expired_launch_records_are_physically_cleaned(self):
        self.create()
        room=self.req("GET","/mine").json()["lobby"]["id"]
        self.req("POST",f"/{room}/join",1)
        self.req("POST",f"/{room}/ready",1,json={"revision":1,"ready":True})
        with db.db() as c:
            item=lobbies.launch_internal(c,self.keys[0],room,"launch-cleanup-nonce-01",1)
            c.execute("UPDATE lobby_launches SET delivery_expires=?,episode_expires=? "
                      "WHERE id=?", (db.now()-100, db.now()-10,item["launch"]["id"]))
            self.assertEqual(lobbies.pending_launch(c,self.keys[0])["launches"],[])
            db.cleanup(c,30,100,[])
            self.assertEqual(c.execute("SELECT COUNT(*) FROM lobby_launches").fetchone()[0],0)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM launch_members").fetchone()[0],0)

    def test_together_status_counts_only_original_connected_members(self):
        self.link_friends()
        self.create()
        room=self.req("GET","/mine").json()["lobby"]["id"]
        self.req("POST",f"/{room}/join",1)
        self.req("POST",f"/{room}/ready",1,json={"revision":1,"ready":True})
        with db.db() as c:
            launch=lobbies.launch_internal(c,self.keys[0],room,"launch-cohort-nonce-01",1)
            from czm import social
            server=launch["launch"]["server"]
            social.heartbeat(c,self.keys[0],server,"ze_first")
            social.heartbeat(c,self.keys[1],server,"ze_first")
            friend=social.profile(c,social.actor(c,self.keys[0]),self.ids[1])
            self.assertEqual(friend["together"],{"count":2,"size":2})
            social.heartbeat(c,self.keys[2],server,"ze_first")
            friend=social.profile(c,social.actor(c,self.keys[0]),self.ids[1])
            self.assertEqual(friend["together"],{"count":2,"size":2})
            social.heartbeat(c,self.keys[1],server,"ze_second")
            friend=social.profile(c,social.actor(c,self.keys[0]),self.ids[1])
            self.assertEqual(friend["together"],{"count":2,"size":2})
            social.heartbeat(c,self.keys[1],"","")
            friend=social.profile(c,social.actor(c,self.keys[0]),self.ids[1])
            self.assertNotIn("together",friend)
            social.heartbeat(c,self.keys[1],server,"ze_second")
            self.assertEqual(social.profile(c,social.actor(c,self.keys[0]),self.ids[1])
                             ["together"],{"count":2,"size":2})
            # The old party is not resurrected after a long absence.
            with patch("czm.lobbies.now",return_value=db.now()+lobbies.LAUNCH_RECONNECT_GRACE+5):
                lobbies.record_launch_presence(c,self.ids[1],server)
            self.assertNotIn("together",social.profile(c,social.actor(c,self.keys[0]),self.ids[1]))

    def test_together_marker_hidden_after_block(self):
        self.link_friends()
        self.create()
        room=self.req("GET","/mine").json()["lobby"]["id"]
        self.req("POST",f"/{room}/join",1)
        self.req("POST",f"/{room}/ready",1,json={"revision":1,"ready":True})
        from czm import social
        with db.db() as c:
            lobbies.launch_internal(c,self.keys[0],room,"launch-cohort-nonce-02",1)
            social.heartbeat(c,self.keys[0],"203.0.113.5:27015","zm_one")
            social.heartbeat(c,self.keys[1],"203.0.113.5:27015","zm_one")
            self.assertIn("together",social.profile(c,social.actor(c,self.keys[0]),self.ids[1]))
        self.client.post("/api/v1/social/action",headers={"X-CZM-Key":self.keys[0]},
                         json={"target":self.ids[1],"action":"block"})
        with db.db() as c:
            profile=social.profile(c,social.actor(c,self.keys[0]),self.ids[1])
            self.assertNotIn("together",profile)
            self.assertFalse(profile["online"])

    def test_invalid_capacity_and_nonce(self):
        for n in [1,7,8]:
            r=self.create(capacity=n,nonce=f"invalid-capacity-{n}-nonce")
            self.assertIn(r.status_code,(400,422),r.text)
        self.assertEqual(self.create().status_code,200)
        self.assertEqual(self.create(capacity=2).status_code,409)

if __name__=="__main__":
    unittest.main()
