"""SUPPORT role and in-game moderation: who may act, on whom, and what each action changes."""
import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from czm import accounts, api, db, lobbies, moderation, service, voice_lobby
from czm.config import get_settings


def clear_limits():
    for value in vars(api).values():
        if isinstance(value, api._Limiter):
            value.calls.clear()


class ModerationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        env = patch.dict(os.environ, {"CZM_DATA_DIR": temp.name, "CZM_PLAY_SERVICE_ACCOUNT_FILE": "/nonexistent"})
        env.start(); self.addCleanup(env.stop)
        get_settings.cache_clear(); self.addCleanup(get_settings.cache_clear)
        clear_limits(); self.addCleanup(clear_limits)
        db.init()
        app = FastAPI(); app.include_router(api.router)
        self.client = TestClient(app); self.addCleanup(self.client.close)
        self.keys, self.ids = [], []
        with db.db() as c:
            for i in range(4):
                legacy = "moderation-legacy-key-%d" % i
                service.hello(c, legacy, "moderation-device-%d" % i, "Player %d" % i, "", "ru", "test")
                user = accounts.register(c, legacy, "ModPlayer%d" % i, "Password123", "Password123", "ip%d" % i)
                self.keys.append(user["token"]); self.ids.append(user["profile"]["id"])
            self.guest = "moderation-guest-key-0001"
            self.guest_id = service.hello(c, self.guest, "guest-device", "Guest", "", "ru", "test")["id"]
            self.assertEqual(moderation.grant(c, self.ids[0])["role"], "support")
            with self.assertRaises(accounts.AuthError):
                moderation.grant(c, self.guest_id)    # the role needs a registered account

    def request(self, method, path, actor=0, **kwargs):
        return self.client.request(method, "/api/v1/" + path, headers={"X-CZM-Key": self.keys[actor]}, **kwargs)

    def act(self, action, target=1, actor=0, nonce=None, **fields):
        self._n = getattr(self, "_n", 0) + 1
        body = {"target": self.ids[target] if isinstance(target, int) and target < 10 else target,
                "action": action, "nonce": nonce or "moderation-nonce-%04d" % self._n, **fields}
        return self.request("POST", "moderation/act", actor, json=body)

    def chat(self, actor, text):
        return self.request("POST", "chat/global", actor, json={"text": text})

    def test_only_the_support_account_reaches_the_panel(self):
        for actor in (1, 2):
            for verb, path in [("GET", "moderation/summary"), ("GET", "moderation/reports"), ("GET", "moderation/sanctions"),
                               ("GET", "moderation/history"), ("GET", "moderation/player/%d" % self.ids[2])]:
                self.assertEqual(self.request(verb, path, actor).status_code, 403, path)
            self.assertEqual(self.act("ban", 2, actor, minutes=0, reason="x").status_code, 403)
        guest = self.client.get("/api/v1/moderation/summary", headers={"X-CZM-Key": self.guest})
        self.assertEqual(guest.status_code, 403)
        ok = self.request("GET", "moderation/summary")
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertEqual(ok.json(), {"reports_open": 0, "sanctions_active": 0})

    def test_the_role_is_shown_everywhere_and_only_for_support(self):
        hello = self.client.post("/api/v1/hello", json={"key": self.keys[0]}).json()
        self.assertEqual(hello["role"], "support")
        self.assertEqual(self.client.post("/api/v1/hello", json={"key": self.keys[1]}).json()["role"], "")
        self.assertEqual(self.chat(0, "official notice").status_code, 200)
        self.assertEqual(self.chat(1, "hello").status_code, 200)
        messages = self.request("GET", "chat/global", 2).json()["messages"]
        self.assertEqual([m.get("r") for m in messages], ["support", None])
        self.assertEqual(self.request("GET", "social/profile/%d" % self.ids[0], 2).json()["profile"]["role"], "support")
        self.assertNotIn("role", self.request("GET", "social/profile/%d" % self.ids[1], 2).json()["profile"])
        room = self.request("POST", "lobbies", 1, json={"title": "Room", "description": "", "visibility": "public",
                                                      "capacity": 4, "server": "203.0.113.5:27015", "proto": "gs",
                                                      "nonce": "moderation-room-0001"}).json()["lobby"]["id"]
        self.assertEqual(self.request("POST", "lobbies/%s/join" % room, 0).status_code, 200)
        members = self.request("GET", "lobbies/%s" % room, 1).json()["lobby"]["members"]
        self.assertEqual({m["id"]: m.get("role") for m in members}, {self.ids[1]: None, self.ids[0]: "support"})

    def test_text_mute_closes_writing_until_lifted(self):
        r = self.act("mute_text", minutes=10, reason="Оскорбления")
        self.assertEqual(r.status_code, 200, r.text)
        refused = self.chat(1, "still here")
        self.assertEqual(refused.status_code, 403)
        self.assertEqual(refused.json()["error"], "muted")
        self.assertEqual(refused.json()["mute"]["reason"], "Оскорбления")
        self.assertEqual(self.request("POST", "social/status", 1, json={"text": "x"}).json(), {"error": "muted"})
        state = self.client.post("/api/v1/hello", json={"key": self.keys[1]}).json()["moderation"]
        self.assertGreater(state["text"]["until"], 0)
        self.assertIsNone(state["voice"])
        # private messages between friends, lobby rooms
        for a, b in ((1, 2), (2, 1)):
            self.request("POST", "social/action", a, json={"target": self.ids[b], "action": "follow"})
        dm = self.request("POST", "social/dialog/%d" % self.ids[2], 1, json={"text": "hi", "nonce": "moderation-dm-000001"})
        self.assertEqual(dm.json(), {"error": "muted"})
        lobby = self.request("POST", "lobbies", 1, json={"title": "Room", "description": "", "visibility": "public",
                                                       "capacity": 4, "server": "203.0.113.5:27015", "proto": "gs",
                                                       "nonce": "moderation-room-0002"})
        self.assertEqual(lobby.json(), {"error": "muted"})
        # reading stays open; other players are not touched
        self.assertEqual(self.request("GET", "chat/global", 1).status_code, 200)
        self.assertEqual(self.chat(2, "free").status_code, 200)
        sanction = self.request("GET", "moderation/sanctions").json()["sanctions"][0]
        self.assertEqual((sanction["kind"], sanction["target"]["id"]), ("text", self.ids[1]))
        lifted = self.request("POST", "moderation/sanctions/%d/lift" % sanction["id"], json={"nonce": "moderation-lift-0001"})
        self.assertEqual(lifted.status_code, 200, lifted.text)
        self.assertEqual(self.chat(1, "back again").status_code, 200)
        actions = [h["action"] for h in self.request("GET", "moderation/history").json()["history"]]
        self.assertEqual(actions, ["lift", "mute_text"])

    def test_voice_and_photo_restrictions_are_separate(self):
        self.assertEqual(self.act("mute_voice", minutes=60, reason="Спам").status_code, 200)
        room = self.request("POST", "lobbies", 0, json={"title": "Voice", "description": "", "visibility": "public",
                                                      "capacity": 4, "server": "203.0.113.5:27015", "proto": "gs",
                                                      "nonce": "moderation-room-0003"}).json()["lobby"]["id"]
        self.assertEqual(self.request("POST", "lobbies/%s/join" % room, 1).status_code, 200)
        with db.db() as c:
            self.assertTrue(voice_lobby.can_transmit(c, self.keys[1], room)[1])
            self.assertFalse(voice_lobby.can_transmit(c, self.keys[0], room)[1])
        self.assertEqual(self.chat(1, "text still works").status_code, 200)
        with db.db() as c:
            c.execute("UPDATE players SET avatar='photo' WHERE id=?", (self.ids[2],))
        self.assertEqual(self.act("restrict_photo", 2, minutes=0, reason="Сексуальный контент").status_code, 200)
        upload = self.request("POST", "avatar", 2, content=b"x")
        self.assertEqual((upload.status_code, upload.json()["error"]), (403, "photo_restricted"))
        with db.db() as c:
            self.assertEqual(c.execute("SELECT avatar FROM players WHERE id=?", (self.ids[2],)).fetchone()[0], "")

    def test_warning_reaches_the_player_once(self):
        self.assertEqual(self.act("warn", reason="Без оскорблений").status_code, 200)
        warning = self.client.post("/api/v1/hello", json={"key": self.keys[1]}).json()["moderation"]["warning"]
        self.assertEqual(warning["reason"], "Без оскорблений")
        seen = self.request("POST", "moderation/warning/seen", 1, json={"id": warning["id"]})
        self.assertIsNone(seen.json()["moderation"]["warning"])
        # a player cannot mark another player's warning
        self.act("warn", 2, reason="Спам")
        other = self.client.post("/api/v1/hello", json={"key": self.keys[2]}).json()["moderation"]["warning"]
        self.request("POST", "moderation/warning/seen", 1, json={"id": other["id"]})
        self.assertIsNotNone(self.client.post("/api/v1/hello", json={"key": self.keys[2]}).json()["moderation"]["warning"])

    def test_a_report_is_acted_on_the_right_player(self):
        self.chat(1, "rude words")
        with db.db() as c:
            message = c.execute("SELECT id FROM messages WHERE player=?", (self.ids[1],)).fetchone()[0]
        self.assertEqual(self.request("POST", "report", 2, json={"message": message}).status_code, 200)
        reports = self.request("GET", "moderation/reports").json()["reports"]
        self.assertEqual((len(reports), reports[0]["evidence"], reports[0]["target"]["id"]), (1, "rude words", self.ids[1]))
        report = reports[0]["id"]
        wrong = self.act("delete_message", 2, report=report)
        self.assertEqual(wrong.status_code, 409)          # the complaint is not about player 2
        done = self.act("delete_message", report=report)
        self.assertEqual(done.status_code, 200, done.text)
        self.assertEqual(self.request("GET", "chat/global", 2).json()["messages"], [])
        self.assertEqual(self.request("GET", "moderation/summary").json()["reports_open"], 0)
        # a message id must belong to the target too
        self.chat(2, "mine")
        with db.db() as c:
            other = c.execute("SELECT id FROM messages WHERE player=?", (self.ids[2],)).fetchone()[0]
        self.assertEqual(self.act("delete_message", 1, message=other).status_code, 409)

    def test_ban_closes_the_open_complaints_and_limits_are_checked(self):
        self.chat(1, "spam")
        with db.db() as c:
            message = c.execute("SELECT id FROM messages WHERE player=?", (self.ids[1],)).fetchone()[0]
        self.request("POST", "report", 2, json={"message": message})
        self.request("POST", "report", 3, json={"player": self.ids[1]})
        self.assertEqual(self.act("mute_text", minutes=0, reason="x").status_code, 400)      # a mute is never forever
        self.assertEqual(self.act("ban", minutes=60).status_code, 400)                       # a reason is required
        self.assertEqual(self.act("ban", 0, minutes=60, reason="x").status_code, 400)        # not oneself
        with db.db() as c:
            moderation.grant(c, self.ids[3])
        self.assertEqual(self.act("ban", 3, minutes=60, reason="x").status_code, 403)        # not another SUPPORT
        r = self.act("ban", minutes=0, reason="Угрозы")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["forever"])
        with db.db() as c:
            self.assertTrue(service.active_ban(c, service.player_by_key(c, self.keys[1]))["forever"])
            self.assertEqual(c.execute("SELECT COUNT(*) FROM reports WHERE status='open'").fetchone()[0], 0)

    def test_a_repeated_tap_does_not_punish_twice(self):
        first = self.act("mute_text", minutes=10, reason="Спам", nonce="moderation-same-0001")
        again = self.act("mute_text", minutes=10, reason="Спам", nonce="moderation-same-0001")
        self.assertEqual(again.json()["repeated"], True)
        self.assertEqual(again.json()["log"], first.json()["log"])
        self.assertEqual(len(self.request("GET", "moderation/sanctions").json()["sanctions"]), 1)
        other = self.act("mute_text", 2, minutes=10, reason="Спам", nonce="moderation-same-0001")
        self.assertEqual(other.status_code, 409)

    def test_lobby_room_and_message_actions(self):
        room = self.request("POST", "lobbies", 1, json={"title": "Bad name", "description": "", "visibility": "public",
                                                      "capacity": 4, "server": "203.0.113.5:27015", "proto": "gs",
                                                      "nonce": "moderation-room-0004"}).json()["lobby"]["id"]
        self.request("POST", "lobbies/%s/join" % room, 2)
        sent = self.request("POST", "lobbies/%s/messages" % room, 1, json={"text": "hello all", "nonce": "moderation-lm-0001"})
        lobby_message = sent.json()["message"]["id"]
        self.assertEqual(self.act("delete_message", lobby_message=lobby_message).status_code, 200)
        self.assertEqual(self.request("GET", "lobbies/%s/messages" % room, 2).json()["messages"], [])
        self.request("POST", "report", 2, json={"lobby": room})
        report = self.request("GET", "moderation/reports").json()["reports"][0]
        self.assertEqual(report["kind"], "lobby")
        self.assertEqual(self.act("close_lobby", report=report["id"]).status_code, 200)
        self.assertEqual(self.request("GET", "lobbies/%s" % room, 2).status_code, 404)


if __name__ == "__main__":
    unittest.main()
