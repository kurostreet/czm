"""Voice relay security / authorization tests. No microphone or network required."""
import os
import tempfile
import time
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from czm import accounts,api,db,lobbies,service,voice_lobby
from czm.config import get_settings


class LobbyVoiceTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        env=patch.dict(os.environ,{"CZM_DATA_DIR":folder.name,
                                  "CZM_PLAY_SERVICE_ACCOUNT_FILE":"/nonexistent"})
        env.start();self.addCleanup(env.stop)
        get_settings.cache_clear();self.addCleanup(get_settings.cache_clear)
        # Each TestClient shares testclient IP; keep scenarios isolated.
        api._lobby_limit.calls.clear()
        db.init()
        app=FastAPI();app.include_router(api.router)
        self.client=TestClient(app);self.addCleanup(self.client.close)
        self.keys=[];self.players=[]
        with db.db() as conn:
            for i in range(3):
                original="voice-test-legacy-%d"%i
                service.hello(conn,original,"voice-device-%d"%i,"Guest","","ru","test")
                actor=accounts.register(conn,original,"VoiceUser%d"%i,
                                      "Password123","Password123","ip%d"%i)
                self.keys.append(actor["token"])
                self.players.append(actor["profile"]["id"])
        res=self.client.post("/api/v1/lobbies",headers={"X-CZM-Key":self.keys[0]},
                             json={"title":"Voice Room","description":"","visibility":"private",
                                   "capacity":3,"server":"203.0.113.5:27015",
                                   "proto":"gs","nonce":"voice-create-nonce-001"})
        self.assertEqual(res.status_code,200,res.text)
        self.room=res.json()["lobby"]["id"]
        # Admin adds a member directly here. Other tests cover private invitations.
        with db.db() as c:
            c.execute("INSERT INTO lobby_members(player,lobby,joined) VALUES(?,?,?)",
                      (self.players[1],self.room,lobbies.now()))

    def conn(self,idx):
        return self.client.websocket_connect("/api/v1/lobbies/"+self.room+"/voice",
                                            headers={"X-CZM-Key":self.keys[idx]})

    def mute(self,actor,target,muted):
        return self.client.post("/api/v1/lobbies/"+self.room+"/voice/mute",
            headers={"X-CZM-Key":self.keys[actor]},
            json={"target":target,"muted":muted})

    def test_host_mute_individual_and_all(self):
        self.assertEqual(self.mute(1,self.players[0],True).status_code,403)
        self.assertEqual(self.mute(0,self.players[2],True).status_code,403)
        self.assertEqual(self.mute(0,self.players[0],True).status_code,400)
        p=self.mute(0,self.players[1],True)
        self.assertEqual(p.status_code,200,p.text)
        with db.db() as c:
            self.assertEqual(voice_lobby.can_transmit(c,self.keys[1],self.room),
                             (self.players[1],True))
        self.assertEqual(self.mute(0,None,True).status_code,200)
        with db.db() as c:
            self.assertFalse(voice_lobby.can_transmit(c,self.keys[0],self.room)[1])
        self.assertEqual(self.mute(0,self.players[1],False).status_code,200)
        with db.db() as c:
            self.assertTrue(voice_lobby.can_transmit(c,self.keys[1],self.room)[1])
        self.assertEqual(self.mute(0,None,False).status_code,200)
        with db.db() as c:
            self.assertFalse(voice_lobby.can_transmit(c,self.keys[1],self.room)[1])

    def test_expired_and_closed_room_cannot_rejoin_voice(self):
        with db.db() as c:
            c.execute("UPDATE lobbies SET last_seen=? WHERE id=?",
                      (lobbies.now()-lobbies.HOST_TTL-10,self.room))
            with self.assertRaises(accounts.AuthError):
                voice_lobby.can_transmit(c,self.keys[0],self.room)
        with self.assertRaises(WebSocketDisconnect) as ex:
            with self.conn(0) as ws:
                ws.receive_json()
        self.assertEqual(ex.exception.code,4403)

    def test_absent_or_outsider_cannot_join_socket(self):
        for header in [{},{"X-CZM-Key":self.keys[2]}]:
            with self.assertRaises(WebSocketDisconnect) as err:
                with self.client.websocket_connect(
                    "/api/v1/lobbies/"+self.room+"/voice",headers=header) as ws:
                    ws.receive_json()
            self.assertIn(err.exception.code,(4401,4403))

    def test_relay_frames_are_tagged_and_do_not_echo_to_origin(self):
        with self.conn(0) as host:
            with self.conn(1) as member:
                self.assertEqual(host.receive_json()["type"],"joined")
                self.assertEqual(member.receive_json()["type"],"joined")
                host.send_bytes(b"U"+bytes([0xAA])*320)
                status=member.receive_json()
                self.assertEqual(status,{"type":"talk","player":self.players[0],"active":True})
                payload=member.receive_bytes()
                self.assertEqual(payload[:1],b"U")
                self.assertEqual(int.from_bytes(payload[1:5],"big"),self.players[0])
                self.assertEqual(payload[5:],bytes([0xAA])*320)
                # Other clients cannot send text with forged speaker status.
                member.send_text('{"type":"talk","player":999,"active":true}')
                with self.assertRaises(WebSocketDisconnect) as err:
                    member.receive_json()
                self.assertEqual(err.exception.code,4400)

    def test_voice_controls_visible_in_lobby_state(self):
        from czm import lobbies
        self.assertEqual(self.mute(0,self.players[1],True).status_code,200)
        self.assertEqual(self.mute(0,None,True).status_code,200)
        with db.db() as c:
            detail=lobbies.detail(c,self.keys[1],self.room)["lobby"]
            self.assertEqual(detail["voice_mute_all"],True)
            self.assertEqual(detail["voice_muted"],[self.players[1]])
        self.assertEqual(self.mute(0,self.players[1],False).status_code,200)
        with db.db() as c:
            detail=lobbies.detail(c,self.keys[1],self.room)["lobby"]
            self.assertEqual(detail["voice_muted"],[])

    def test_duplicate_socket_for_same_account_rejected(self):
        # A stale or cloned client must not impersonate a second talker.
        with self.conn(0) as first:
            with self.assertRaises(WebSocketDisconnect) as error:
                with self.conn(0) as second:
                    second.receive_json()
            self.assertEqual(error.exception.code,4409)

    def test_invalid_audio_frames_do_not_reach_participants(self):
        with self.conn(0) as host:
            with self.conn(1) as participant:
                host.receive_json()
                participant.receive_json()
                host.send_bytes(b"X"+bytes([88])*320)
                host.send_bytes(b"U"+bytes([88])*321)
                host.send_bytes(b"U"+bytes([27])*320)
                event=participant.receive_json()
                self.assertEqual(event,{"type":"talk","player":self.players[0],
                                        "active":True})
                packet=participant.receive_bytes()
                self.assertEqual(packet[:1],b"U")
                self.assertEqual(packet[5:],bytes([27])*320)

    def test_voice_data_removed_with_room(self):
        self.assertEqual(self.mute(0,self.players[1],True).status_code,200)
        r=self.client.post(f"/api/v1/lobbies/{self.room}/leave",
                           headers={"X-CZM-Key":self.keys[0]})
        self.assertEqual(r.status_code,200,r.text)
        with db.db() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM lobby_voice_mutes").fetchone()[0],0)
            with self.assertRaises(accounts.AuthError):
                voice_lobby.can_transmit(c,self.keys[1],self.room)
