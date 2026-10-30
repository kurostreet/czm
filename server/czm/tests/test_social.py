import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from czm import accounts, api, db, service, social
from czm.config import get_settings


class SocialTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        env = patch.dict(os.environ, {"CZM_DATA_DIR": temp.name}); env.start(); self.addCleanup(env.stop)
        get_settings.cache_clear(); self.addCleanup(get_settings.cache_clear); db.init()
        app = FastAPI(); app.include_router(api.router)
        self.client = TestClient(app); self.addCleanup(self.client.close)
        self.keys, self.ids = [], []
        with db.db() as c:
            for i in range(3):
                legacy = "social-player-legacy-key-%d" % i
                service.hello(c, legacy, "social-device-%d" % i, "Same nickname", str(i+1), "ru", "test")
                result = accounts.register(c, legacy, "SocialPlayer%d" % i, "Password123", "Password123", "ip%d" % i)
                self.keys.append(result["token"]); self.ids.append(result["profile"]["id"])
            self.guest = "social-guest-legacy-key-123"
            self.guest_id = service.hello(c, self.guest, "guest", "Guest", "", "en", "test")["id"]

    def test_online_friends_lead_all_pages_and_ignore_revoked_sessions(self):
        with db.db() as c:
            for other in (1,2):
                social.action(c,self.keys[0],self.ids[other],"follow")
                social.action(c,self.keys[other],self.ids[0],"follow")
            social.heartbeat(c,self.keys[1],"","")
            result=social.people(c,self.keys[0],"friends")
            self.assertEqual(result["people"][0]["id"],self.ids[1])
            self.assertEqual(result["online"],1)
            c.execute("DELETE FROM account_sessions WHERE player=?",(self.ids[1],))
            result=social.people(c,self.keys[0],"friends")
            self.assertEqual(result["online"],0)
            self.assertTrue(all(not p["online"] for p in result["people"]))

    def test_profile_theme_is_public_persistent_and_only_changes_the_actor(self):
        with db.db() as c:
            social.update_status(c, self.keys[0], "My status")
        before = self.request("GET", "social/profile/%d" % self.ids[0]).json()["profile"]
        self.assertEqual(before["theme"], "ember")
        for theme in ("frost", "city", "ember", "lab"):
            response = self.request("POST", "social/theme", json={"theme": theme, "target": self.ids[1]})
            self.assertEqual(response.status_code, 200)
            profile = self.request("GET", "social/profile/%d" % self.ids[0], 1).json()["profile"]
            self.assertEqual(profile["theme"], theme)
            self.assertEqual(profile["status"], "My status")
            self.assertEqual(profile["nick"], before["nick"])
            self.assertEqual(self.request("GET", "social/profile/%d" % self.ids[1]).json()["profile"]["theme"], "ember")
        with db.db() as c:
            social.update_status(c, self.keys[0], "Updated status")
            self.assertEqual(c.execute("SELECT theme FROM social_profiles WHERE player=?", (self.ids[0],)).fetchone()[0], "lab")
            self.assertEqual(c.execute("SELECT COUNT(*) FROM community_roles").fetchone()[0], 0)

    def test_profile_theme_rejects_unknown_assets_and_requires_an_account(self):
        for value in ("../../../file", "https://example.com/image.png", "support", ""):
            self.assertEqual(self.request("POST", "social/theme", json={"theme": value}).status_code, 422)
        for headers, expected in (({}, 401), ({"X-CZM-Key": self.guest}, 403)):
            response = self.client.post("/api/v1/social/theme", headers=headers, json={"theme": "lab"})
            self.assertEqual(response.status_code, expected)
        self.assertEqual(self.request("GET", "social/profile/%d" % self.ids[0]).json()["profile"]["theme"], "ember")

    def test_profile_theme_migration_preserves_existing_profile(self):
        with db.db() as c:
            social.update_status(c, self.keys[0], "Keep my status")
            c.execute("ALTER TABLE social_profiles RENAME TO old_social_profiles")
            c.execute("CREATE TABLE social_profiles (player INTEGER PRIMARY KEY REFERENCES players(id), status TEXT NOT NULL DEFAULT '', last_seen INTEGER NOT NULL DEFAULT 0)")
            c.execute("INSERT INTO social_profiles SELECT player,status,last_seen FROM old_social_profiles")
            c.execute("DROP TABLE old_social_profiles")
        db.init()
        profile = self.request("GET", "social/profile/%d" % self.ids[0]).json()["profile"]
        self.assertEqual(profile["theme"], "ember")
        self.assertEqual(profile["status"], "Keep my status")
        with db.db() as c:
            self.assertFalse(c.execute("PRAGMA foreign_key_check").fetchall())

    def request(self, method, path, actor=0, **kwargs):
        return self.client.request(method, "/api/v1/"+path, headers={"X-CZM-Key": self.keys[actor]}, **kwargs)

    def follow(self, actor=0, target=1, action="follow"):
        return self.request("POST", "social/action", actor, json={"target": self.ids[target], "action": action})

    def friends(self):
        self.assertEqual(self.follow().status_code, 200)
        self.assertEqual(self.follow(1, 0).status_code, 200)

    def send(self, actor=0, target=1, nonce="message-unique-0001", text="Hello friend"):
        return self.request("POST", "social/dialog/%d" % self.ids[target], actor, json={"text": text, "nonce": nonce})

    def test_directional_links_friend_removal_and_unsubscribe(self):
        self.assertEqual(self.follow().json()["profile"]["relation"], "following")
        c = self.request("GET", "social/summary", 1).json()["counts"]
        self.assertEqual((c["friends"], c["followers"], c["requests"]), (0, 1, 1))
        self.follow(1, 0)
        c = self.request("GET", "social/summary").json()["counts"]
        self.assertEqual((c["friends"], c["followers"], c["following"]), (1, 0, 0))
        self.follow(0, 1, "unfollow")
        self.assertEqual(self.request("GET", "social/people/followers").json()["people"][0]["id"], self.ids[1])
        self.follow(1, 0, "unfollow")
        self.assertEqual(self.request("GET", "social/summary").json()["counts"]["followers"], 0)

    def test_private_messages_require_mutual_friendship_and_are_idempotent(self):
        self.assertEqual(self.send().status_code, 403)
        self.follow()
        self.assertEqual(self.send().status_code, 403)
        self.follow(1, 0)
        sent = self.send(); self.assertEqual(sent.status_code, 200, sent.text)
        self.assertEqual(sent.json(), self.send().json())
        self.assertEqual(self.send(text="different").status_code, 409)
        self.assertEqual(self.request("GET", "social/summary", 1).json()["counts"]["unread"], 1)
        mid = sent.json()["message"]["id"]
        self.request("POST", "social/dialog/%d/read" % self.ids[0], 1, json={"through": mid})
        self.assertEqual(self.request("GET", "social/summary", 1).json()["counts"]["unread"], 0)

    def test_history_survives_unfriending_but_cannot_be_read_by_other_accounts(self):
        self.friends(); self.send()
        self.follow(0, 1, "unfollow")
        history = self.request("GET", "social/dialog/%d" % self.ids[0], 1).json()
        self.assertEqual(history["messages"][0]["t"], "Hello friend")
        self.assertFalse(history["can_send"])
        self.assertEqual(self.send(nonce="message-unique-0002").status_code, 403)
        other = self.request("GET", "social/dialog/%d" % self.ids[0], 2).json()
        self.assertEqual(other["messages"], [])
        self.assertEqual(self.request("GET", "social/dialogs", 2).json()["people"], [])

    def test_block_removes_both_links_and_prevents_messages_and_server_disclosure(self):
        self.friends(); self.send()
        self.request("POST", "social/presence", 1, json={"server": "203.0.113.5:27015", "map": "zm_test"})
        profile = self.request("GET", "social/profile/%d" % self.ids[1]).json()["profile"]
        self.assertEqual(profile["server"], "203.0.113.5:27015")
        self.follow(0, 1, "block")
        self.assertEqual(self.send(nonce="message-unique-0002").status_code, 403)
        self.assertEqual(self.follow(1, 0).status_code, 403)
        profile = self.request("GET", "social/profile/%d" % self.ids[0], 1).json()["profile"]
        self.assertEqual((profile["online"], profile["server"], profile["last_seen"]), (False, "", 0))
        self.follow(0, 1, "unblock")
        self.assertEqual(self.request("GET", "social/summary").json()["counts"]["friends"], 0)

    def test_presence_expires_and_logout_invalidates_it_immediately(self):
        sent = self.request("POST", "social/presence", 1, json={})
        self.assertEqual(sent.status_code, 200)
        with db.db() as c:
            viewer = social.actor(c, self.keys[0])
            self.assertTrue(social.profile(c, viewer, self.ids[1])["online"])
            with patch("czm.social.now", return_value=db.now()+social.PRESENCE_TTL+1):
                p = social.profile(c, viewer, self.ids[1])
                self.assertFalse(p["online"]); self.assertGreater(p["last_seen"], 0)
            accounts.logout(c, self.keys[1])
            self.assertFalse(social.profile(c, viewer, self.ids[1])["online"])

    def test_guest_can_view_profiles_but_cannot_create_persistent_social_links(self):
        headers = {"X-CZM-Key": self.guest}
        response = self.client.get("/api/v1/social/profile/%d" % self.ids[0], headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        response = self.client.post("/api/v1/social/action", headers=headers, json={"target": self.ids[0], "action": "follow"})
        self.assertEqual(response.json()["error"], "account_required")
        self.assertEqual(self.client.get("/api/v1/social/summary").status_code, 401)
        self.assertEqual(self.follow(0, 0).status_code, 400)
        guest_target = self.request("POST", "social/action", json={"target": self.guest_id, "action": "follow"})
        self.assertEqual(guest_target.status_code, 404)

    def test_profile_exposes_only_actual_public_data_and_status_survives_new_session(self):
        self.request("POST", "social/status", json={"text": "Ready for zombie escape"})
        with db.db() as c:
            token = accounts.login(c, "SocialPlayer0", "Password123", "new-ip")["token"]
            result = social.summary(c, token)["profile"]
        self.assertEqual(result["status"], "Ready for zombie escape")
        self.assertEqual(result["id"], self.ids[0])
        for field in ("email", "password_hash", "token", "device_hash", "key_hash", "kills", "wins", "level"):
            self.assertNotIn(field, result)

    def test_dm_reports_require_participation_and_moderator_deletion_does_not_touch_public_chat(self):
        self.friends(); message = self.send().json()["message"]["id"]
        with db.db() as c:
            stranger = social.actor(c, self.keys[2]); recipient = social.actor(c, self.keys[1])
            self.assertIsNone(service.report(c, stranger, None, None, message))
            info = service.report(c, recipient, None, None, message)
            self.assertEqual(info["message"], "Hello friend")
            self.assertEqual(info["room"], "Личное сообщение")
            self.assertIsNone(info["message_id"])
            service.delete_report_message(c, info)
        history = self.request("GET", "social/dialog/%d" % self.ids[0], 1).json()
        self.assertTrue(history["messages"][0]["deleted"])
        self.assertEqual(history["messages"][0]["t"], "")

    def test_game_invite_is_a_structured_message_only_between_friends(self):
        invite = {"server": "81.181.244.5:27015", "proto": "gs", "name": "Zombie Night", "nonce": "invite-unique-00001"}
        path = "social/invite/%d" % self.ids[1]
        self.assertEqual(self.request("POST", path, json=invite).status_code, 403)
        self.friends()
        r = self.request("POST", path, json=invite)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["message"]["t"], "czm:invite gs 81.181.244.5:27015 Zombie Night")
        history = self.request("GET", "social/dialog/%d" % self.ids[0], 1).json()["messages"]
        self.assertEqual(history[-1]["t"], "czm:invite gs 81.181.244.5:27015 Zombie Night")
        for bad in ("999.1.1.1:27015", "1.2.3.4", "1.2.3.4:0", "host.example:27015"):
            r = self.request("POST", path, json=dict(invite, server=bad, nonce="invite-bad-0000001"))
            self.assertIn(r.status_code, (400, 422), bad)
        # typed text can not pretend to be an invite: the address is masked
        r = self.send(text="czm:invite gs 81.181.244.5:27015 Fake", nonce="typed-invite-00001")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("81.181.244.5", r.json()["message"]["t"])

    def test_online_counts_players_with_fresh_presence(self):
        self.assertEqual(self.client.get("/api/v1/online").json()["online"], 0)
        with db.db() as c:
            self.assertEqual(social.online_count(c), 0)
            for i in range(2):
                c.execute("INSERT INTO social_presence VALUES(?,?,?,?,?)", ("owner-%d" % i, self.ids[i], db.now(), "", ""))
            c.execute("INSERT INTO social_presence VALUES(?,?,?,?,?)", ("old", self.ids[2], db.now() - 600, "", ""))
            self.assertEqual(social.online_count(c), 2)

    def test_invalid_addresses_and_repeated_init_are_safe(self):
        self.assertEqual(self.request("POST", "social/presence", json={"server": "https://site/path"}).status_code, 400)
        self.assertEqual(self.request("POST", "social/presence", json={"map": "x\nconnect evil"}).status_code, 400)
        self.assertEqual(self.send(nonce="short").status_code, 422)
        self.friends(); self.send(); db.init()
        self.assertEqual(len(self.request("GET", "social/dialogs").json()["people"]), 1)


if __name__ == "__main__": unittest.main()
