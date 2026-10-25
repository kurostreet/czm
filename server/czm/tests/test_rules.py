"""Community rules acceptance, lobby complaints and blocks inside lobbies."""
import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from czm import accounts, api, bot, db, lobbies, rules, service, social, voice_lobby
from czm.config import get_settings


class RulesTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        env = patch.dict(os.environ, {"CZM_DATA_DIR": temp.name, "CZM_PLAY_SERVICE_ACCOUNT_FILE": "/nonexistent"})
        env.start(); self.addCleanup(env.stop)
        get_settings.cache_clear(); self.addCleanup(get_settings.cache_clear)
        api._lobby_limit.calls.clear()
        db.init()
        app = FastAPI(); app.include_router(api.router)
        self.client = TestClient(app); self.addCleanup(self.client.close)
        self.keys, self.ids = [], []
        with db.db() as c:
            for i in range(3):
                legacy = "rules-player-legacy-key-%d" % i
                service.hello(c, legacy, "rules-device-%d" % i, "Rules player", "", "ru", "test")
                user = accounts.register(c, legacy, "RulesPlayer%d" % i, "Password123", "Password123", "ip%d" % i)
                self.keys.append(user["token"]); self.ids.append(user["profile"]["id"])

    def request(self, method, path, actor=0, **kwargs):
        return self.client.request(method, "/api/v1/" + path, headers={"X-CZM-Key": self.keys[actor]}, **kwargs)

    def hello(self, actor=0, capability=1):
        r = self.client.post("/api/v1/hello", json={"key": self.keys[actor], "nick": "Rules player", "rules": capability})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def accept(self, actor=0, version=rules.VERSION):
        return self.request("POST", "rules/accept", actor, json={"version": version})

    def create_lobby(self, actor=0, nonce="rules-lobby-nonce-001", visibility="public"):
        return self.request("POST", "lobbies", actor, json={
            "title": "Rules Room", "description": "Tonight", "visibility": visibility, "capacity": 4,
            "server": "203.0.113.5:27015", "proto": "gs", "nonce": nonce})

    def room_with_members(self):
        for i in range(3):
            self.hello(i); self.assertEqual(self.accept(i).status_code, 200)
        r = self.create_lobby(); self.assertEqual(r.status_code, 200, r.text)
        room = r.json()["lobby"]["id"]
        for i in (1, 2):
            self.assertEqual(self.request("POST", "lobbies/%s/join" % room, i).status_code, 200)
        return room

    def say(self, room, actor, text, nonce):
        r = self.request("POST", "lobbies/%s/messages" % room, actor, json={"text": text, "nonce": nonce})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["message"]["id"]

    def test_older_games_are_not_asked_for_the_rules(self):
        state = self.hello(capability=0)["rules"]
        self.assertEqual(state, {"version": rules.VERSION, "accepted": False, "url": rules.URL})
        self.assertEqual(self.request("POST", "chat/global", json={"text": "hello all"}).status_code, 200)
        self.assertEqual(self.create_lobby().status_code, 200)

    def test_new_games_post_only_after_accepting_the_rules(self):
        self.assertFalse(self.hello()["rules"]["accepted"])
        refused = self.request("POST", "chat/global", json={"text": "hello all"})
        self.assertEqual(refused.status_code, 403)
        self.assertEqual(refused.json(), {"error": "rules", "version": rules.VERSION})
        self.assertEqual(self.request("POST", "social/status", json={"text": "Ready"}).json(), {"error": "rules"})
        self.assertEqual(self.create_lobby().status_code, 403)
        self.assertEqual(self.request("POST", "avatar", content=b"x").status_code, 403)
        # reading stays open
        self.assertEqual(self.request("GET", "chat/global").status_code, 200)

        self.assertEqual(self.accept(version=rules.VERSION + 1).status_code, 409)
        accepted = self.accept()
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertTrue(accepted.json()["rules"]["accepted"])
        self.assertTrue(self.hello()["rules"]["accepted"])
        self.assertEqual(self.request("POST", "chat/global", json={"text": "hello all"}).status_code, 200)
        self.assertEqual(self.request("POST", "social/status", json={"text": "Ready"}).status_code, 200)
        self.assertEqual(self.create_lobby().status_code, 200)

        # acceptance belongs to the account and survives a new session
        with db.db() as c:
            token = accounts.login(c, "RulesPlayer0", "Password123", "new-ip")["token"]
        r = self.client.post("/api/v1/hello", json={"key": token, "rules": 1})
        self.assertTrue(r.json()["rules"]["accepted"])
        self.assertEqual(self.client.post("/api/v1/rules/accept", json={"version": 1}).status_code, 401)

    def test_lobby_messages_and_voice_need_the_rules(self):
        self.hello(0); self.accept(0)
        room = self.create_lobby().json()["lobby"]["id"]
        self.hello(1)
        self.assertEqual(self.request("POST", "lobbies/%s/join" % room, 1).status_code, 200)
        r = self.request("POST", "lobbies/%s/messages" % room, 1, json={"text": "hi", "nonce": "rules-message-0001"})
        self.assertEqual((r.status_code, r.json()), (403, {"error": "rules"}))
        self.assertEqual(self.request("GET", "lobbies/%s/messages" % room, 1).status_code, 200)
        with db.db() as c:
            self.assertTrue(voice_lobby.can_transmit(c, self.keys[1], room)[1])
            self.assertFalse(voice_lobby.can_transmit(c, self.keys[0], room)[1])
        self.accept(1)
        with db.db() as c:
            self.assertFalse(voice_lobby.can_transmit(c, self.keys[1], room)[1])

    def test_lobby_message_report_keeps_the_text_after_the_room_closes(self):
        room = self.room_with_members()
        message = self.say(room, 1, "rude words here", "rules-message-0002")
        self.request("POST", "lobbies/%s/leave" % room, 2)
        with db.db() as c:
            outsider = social.actor(c, self.keys[2])
            self.assertIsNone(service.report(c, outsider, None, None, None, message))
            sender = social.actor(c, self.keys[1])
            self.assertIsNone(service.report(c, sender, None, None, None, message))
        r = self.request("POST", "report", 0, json={"lobby_message": message})
        self.assertEqual(r.status_code, 200, r.text)
        with db.db() as c:
            report = c.execute("SELECT id FROM reports ORDER BY id DESC").fetchone()["id"]
            # a repeated complaint is ignored
            self.assertIsNone(service.report(c, social.actor(c, self.keys[0]), None, None, None, message))
        self.assertEqual(self.request("POST", "lobbies/%s/leave" % room).json(), {"closed": True})
        with db.db() as c:
            info = service.report_info(c, report)
        self.assertEqual((info["kind"], info["message"], info["context"]), ("lobby_message", "rude words here", "Rules Room"))
        self.assertEqual(info["target"], self.ids[1])
        text = bot.report_text(info)
        self.assertIn("лобби «Rules Room»", text)
        self.assertIn("rude words here", text)
        self.assertEqual(bot.report_keyboard(info).inline_keyboard[1][0].text, "🗑 Удалить сообщение")

    def test_removing_a_reported_lobby_message_hides_it(self):
        room = self.room_with_members()
        message = self.say(room, 1, "spam spam", "rules-message-0003")
        self.say(room, 2, "normal", "rules-message-0004")
        with db.db() as c:
            info = service.report(c, social.actor(c, self.keys[0]), None, None, None, message)
            self.assertEqual(service.remove_report_content(c, info), "сообщение удалено")
        texts = [m["text"] for m in self.request("GET", "lobbies/%s/messages" % room).json()["messages"]]
        self.assertEqual(texts, ["normal"])

    def test_lobby_name_and_member_reports(self):
        room = self.room_with_members()
        with db.db() as c:
            reporter = social.actor(c, self.keys[1])
            member = service.report(c, reporter, None, self.ids[2], None, None, room)
            self.assertEqual((member["kind"], member["message"], member["target"]), ("lobby_member", None, self.ids[2]))
            self.assertIn("голос или поведение", bot.report_text(member))
            self.assertEqual(len(bot.report_keyboard(member).inline_keyboard[1]), 1)
            self.assertEqual(service.remove_report_content(c, member), "")
            name = service.report(c, reporter, None, None, None, None, room)
            self.assertEqual((name["kind"], name["evidence"], name["target"]), ("lobby", "Rules Room\nTonight", self.ids[0]))
            self.assertEqual(bot.report_keyboard(name).inline_keyboard[1][0].text, "🗑 Закрыть лобби")
            self.assertEqual(service.remove_report_content(c, name), "лобби закрыто")
        self.assertEqual(self.request("GET", "lobbies/%s" % room, 1).status_code, 404)

    def test_private_rooms_cannot_be_reported_from_outside(self):
        for i in range(3):
            self.hello(i); self.accept(i)
        room = self.create_lobby(visibility="private").json()["lobby"]["id"]
        with db.db() as c:
            self.assertIsNone(service.report(c, social.actor(c, self.keys[1]), None, None, None, None, room))
            self.assertIsNone(service.report(c, social.actor(c, self.keys[1]), None, self.ids[0], None, None, room))

    def test_profile_report_copies_the_status_and_ban_clears_it(self):
        self.request("POST", "social/status", 1, json={"text": "bad status"})
        with db.db() as c:
            info = service.report(c, social.actor(c, self.keys[0]), None, self.ids[1])
            self.assertEqual((info["kind"], info["evidence"], info["message"]), ("profile", "bad status", None))
            self.assertEqual(service.remove_report_content(c, info), "аватар и статус сброшены")
            self.assertEqual(c.execute("SELECT status FROM social_profiles WHERE player=?", (self.ids[1],)).fetchone()[0], "")

    def test_reports_written_before_kinds_still_read(self):
        self.assertEqual(self.request("POST", "chat/global", 1, json={"text": "old style"}).status_code, 200)
        with db.db() as c:
            mid = c.execute("SELECT id FROM messages ORDER BY id DESC").fetchone()["id"]
            c.execute("INSERT INTO reports(reporter,target,message,created) VALUES(?,?,?,?)",
                      (self.ids[0], self.ids[1], mid, service.now()))
            info = service.report_info(c, c.execute("SELECT max(id) FROM reports").fetchone()[0])
        self.assertEqual((info["kind"], info["message"], info["room"]), ("chat", "old style", "global"))
        self.assertIn("комнате GLOBAL", bot.report_text(info))

    def test_blocked_players_do_not_see_or_hear_each_other_in_a_room(self):
        room = self.room_with_members()
        self.say(room, 0, "from zero", "rules-message-0007")
        self.say(room, 1, "from one", "rules-message-0005")
        self.say(room, 2, "from two", "rules-message-0006")
        self.assertEqual(self.request("POST", "social/action", 0, json={"target": self.ids[1], "action": "block"}).status_code, 200)
        view = lambda i: [m["text"] for m in self.request("GET", "lobbies/%s/messages" % room, i).json()["messages"]]
        self.assertEqual(view(0), ["from zero", "from two"])
        self.assertEqual(view(1), ["from one", "from two"])
        self.assertEqual(view(2), ["from zero", "from one", "from two"])
        # in the public chat only the one who blocked stops seeing the other
        self.assertEqual(self.request("POST", "chat/global", 1, json={"text": "public one"}).status_code, 200)
        public = lambda i: [m["t"] for m in self.request("GET", "chat/global", i).json()["messages"]]
        self.assertEqual(public(0), [])
        self.assertEqual(public(2), ["public one"])
        with db.db() as c:
            self.assertEqual(voice_lobby.blocked_peers(c, self.ids[0]), frozenset({self.ids[1]}))
            self.assertEqual(voice_lobby.blocked_peers(c, self.ids[1]), frozenset({self.ids[0]}))
            self.assertEqual(voice_lobby.blocked_peers(c, self.ids[2]), frozenset())


class VoiceBlockTests(unittest.TestCase):
    """Audio is not forwarded between two players when one blocked the other."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        env = patch.dict(os.environ, {"CZM_DATA_DIR": temp.name, "CZM_PLAY_SERVICE_ACCOUNT_FILE": "/nonexistent"})
        env.start(); self.addCleanup(env.stop)
        get_settings.cache_clear(); self.addCleanup(get_settings.cache_clear)
        api._lobby_limit.calls.clear()
        db.init()
        app = FastAPI(); app.include_router(api.router)
        self.client = TestClient(app); self.addCleanup(self.client.close)
        self.keys, self.ids = [], []
        with db.db() as c:
            for i in range(3):
                legacy = "voice-block-legacy-key-%d" % i
                service.hello(c, legacy, "voice-block-device-%d" % i, "Guest", "", "ru", "test")
                user = accounts.register(c, legacy, "VoiceBlock%d" % i, "Password123", "Password123", "ip%d" % i)
                self.keys.append(user["token"]); self.ids.append(user["profile"]["id"])
        r = self.client.post("/api/v1/lobbies", headers={"X-CZM-Key": self.keys[0]}, json={
            "title": "Voice Room", "description": "", "visibility": "public", "capacity": 3,
            "server": "203.0.113.5:27015", "proto": "gs", "nonce": "voice-block-nonce-001"})
        self.room = r.json()["lobby"]["id"]
        with db.db() as c:
            for i in (1, 2):
                c.execute("INSERT INTO lobby_members(player,lobby,joined) VALUES(?,?,?)", (self.ids[i], self.room, lobbies.now()))
            c.execute("INSERT INTO social_blocks VALUES(?,?)", (self.ids[2], self.ids[0]))

    def socket(self, i):
        return self.client.websocket_connect("/api/v1/lobbies/%s/voice" % self.room, headers={"X-CZM-Key": self.keys[i]})

    def test_audio_skips_blocked_listener(self):
        loud = b"U" + bytes([0xAA]) * 320
        talk = lambda i: {"type": "talk", "player": self.ids[i], "active": True}
        sender = lambda packet: int.from_bytes(packet[1:5], "big")
        with patch.object(voice_lobby, "VOICE_IDLE", 60), \
                self.socket(0) as host, self.socket(1) as friend, self.socket(2) as blocker:
            host.receive_json(); host.receive_json()          # joined: 1, 2
            friend.receive_json(); friend.receive_json()      # joined: 0, 2
            blocker.receive_json(); blocker.receive_json()    # joined: 0, 1
            host.send_bytes(loud)
            self.assertEqual(friend.receive_json(), talk(0))
            self.assertEqual(sender(friend.receive_bytes()), self.ids[0])
            blocker.send_bytes(loud)
            self.assertEqual(friend.receive_json(), talk(2))
            self.assertEqual(sender(friend.receive_bytes()), self.ids[2])
            friend.send_bytes(loud)
            # host and blocker get every talk event, but the first audio each one hears is the friend's
            for peer in (host, blocker):
                self.assertEqual([peer.receive_json() for _ in range(3)], [talk(0), talk(2), talk(1)])
                self.assertEqual(sender(peer.receive_bytes()), self.ids[1])


if __name__ == "__main__":
    unittest.main()
