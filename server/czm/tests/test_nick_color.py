"""Nickname colour preferences never change identity, badges or chat permissions."""
import unittest
from unittest.mock import patch

from czm import accounts, api, community, db, moderation, service, social
from czm.config import get_settings
import test_social as baseline


def clear_limits():
    for value in vars(api).values():
        if isinstance(value, api._Limiter):
            value.calls.clear()


class NickColorTests(unittest.TestCase):
    request = baseline.SocialTests.request

    def setUp(self):
        baseline.SocialTests.setUp(self)
        clear_limits()
        self.addCleanup(clear_limits)

    def color(self, value, actor=0, **extra):
        return self.request("POST", "social/nick-color", actor, json={"nick_color": value, **extra})

    def profile(self, target=0, actor=0):
        return self.request("GET", "social/profile/%d" % self.ids[target], actor).json()["profile"]

    def test_color_is_canonical_persistent_public_and_resettable(self):
        self.assertEqual(self.profile()["nick_color"], "")
        with db.db() as c:
            social.update_status(c, self.keys[0], "Help Support")
            social.update_theme(c, self.keys[0], "lab")
        before = self.profile()
        response = self.color("#3dd6fF")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.json()["profile"]["nick_color"], "#3DD6FF")
        with db.db() as c:
            token = accounts.login(c, "SocialPlayer0", "Password123", "new-color-ip")["token"]
            own = social.summary(c, token)["profile"]
        self.assertEqual(own["nick_color"], "#3DD6FF")
        public = self.profile(actor=1)
        self.assertEqual(public["nick_color"], "#3DD6FF")
        for field in ("id", "nick", "avatar", "status", "theme", "counts"):
            self.assertEqual(public[field], before[field], field)
        for value in ("#000000", "#FFFFFF", ""):
            self.assertEqual(self.color(value).json()["profile"]["nick_color"], value)

    def test_people_and_dialog_profiles_use_each_players_own_color(self):
        self.color("#12AB34", 1)
        self.color("#FEDCBA", 2)
        with db.db() as c:
            for target in (1, 2):
                social.action(c, self.keys[0], self.ids[target], "follow")
        people = self.request("GET", "social/people/following").json()["people"]
        self.assertEqual({p["id"]: p["nick_color"] for p in people},
                         {self.ids[1]: "#12AB34", self.ids[2]: "#FEDCBA"})
        profile = self.request("GET", "social/dialog/%d" % self.ids[1]).json()["profile"]
        self.assertEqual(profile["nick_color"], "#12AB34")
        self.assertEqual(self.profile()["nick_color"], "")

    def test_chat_history_and_sent_message_use_current_color_in_every_room(self):
        self.color("#A1B2C3")
        with patch.object(get_settings(), "message_interval_seconds", 0):
            for room in ("global", "ru", "en"):
                sent = self.request("POST", "chat/" + room, json={"text": "Hello " + room})
                self.assertEqual(sent.status_code, 200, sent.text)
                item = sent.json()
                self.assertEqual(item["nick_color"], "#A1B2C3")
                self.assertEqual(set(item), {"id", "p", "n", "a", "t", "ts", "nick_color"})
                history = self.request("GET", "chat/" + room).json()["messages"]
                self.assertEqual(history[-1], item)
        self.color("#FEDCBA")
        for room in ("global", "ru", "en"):
            history = self.request("GET", "chat/" + room).json()["messages"]
            self.assertEqual(history[-1]["nick_color"], "#FEDCBA")
            self.assertEqual(self.request("GET", "chat/" + room + "?after=" + str(history[-1]["id"])).json()["messages"], [])
        self.color("")
        self.assertEqual(self.request("GET", "chat/global").json()["messages"][0]["nick_color"], "")

    def test_old_client_default_and_profile_updates_preserve_color_and_payload(self):
        with db.db() as c:
            guest = service.player_by_key(c, self.guest)
            sent = service.post_message(c, guest, "global", "Guest without a social profile")
            self.assertEqual(sent["nick_color"], "")
            self.assertEqual(service.messages(c, "global", 0)[0]["nick_color"], "")
        guest = self.client.get("/api/v1/social/profile/%d" % self.guest_id,
                                headers={"X-CZM-Key": self.guest}).json()["profile"]
        self.assertEqual(guest["nick_color"], "")
        self.color("#654321")
        hello = self.client.post("/api/v1/hello", json={"key": self.keys[0], "nick": "Old client", "avatar": "2"})
        self.assertEqual(hello.status_code, 200, hello.text)
        self.assertEqual(hello.json()["id"], self.ids[0])
        self.assertEqual(self.request("POST", "social/status", json={"text": "Legacy bio"}).status_code, 200)
        self.assertEqual(self.request("POST", "social/theme", json={"theme": "city"}).status_code, 200)
        profile = self.profile()
        self.assertEqual((profile["nick"], profile["avatar"], profile["status"], profile["theme"], profile["nick_color"]),
                         ("Old client", "2", "Legacy bio", "city", "#654321"))

    def test_invalid_colors_and_extra_identity_or_role_fields_are_rejected(self):
        self.color("#ABCDEF")
        invalid = (None, 123456, True, [], {}, "red", "ABCDEF", "#ABC", "#12345678", "#12345G",
                   " #123456", "#123456 ", "#123456\n", "#１２３４５６", "#12345\x00", "#123456;DROP TABLE players", "^1Kuro")
        for value in invalid:
            with self.subTest(value=value):
                self.assertEqual(self.color(value).status_code, 422)
        self.assertEqual(self.request("POST", "social/nick-color", json={}).status_code, 422)
        for extra in ({"target": self.ids[1]}, {"player": self.ids[1]}, {"role": "support"},
                      {"r": "support"}, {"nick": "Official"}, {"status": "spoof"}):
            with self.subTest(extra=extra):
                self.assertEqual(self.color("#112233", **extra).status_code, 422)
        with db.db() as c:
            for value in invalid:
                with self.assertRaises(accounts.AuthError) as error:
                    social.update_nick_color(c, self.keys[0], value)
                self.assertEqual(error.exception.code, "nick_color")
            self.assertEqual(c.execute("SELECT COUNT(*) FROM staff").fetchone()[0], 0)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM community_roles").fetchone()[0], 0)
        self.assertEqual(self.profile()["nick_color"], "#ABCDEF")
        self.assertEqual(self.profile(1)["nick_color"], "")

    def test_only_current_authenticated_account_can_change_its_own_color(self):
        for key, expected in (("", 401), ("unknown-color-key-0000", 401),
                              ("social-player-legacy-key-0", 401), (self.guest, 403)):
            response = self.client.post("/api/v1/social/nick-color", json={"nick_color": "#123456"},
                                        headers={"X-CZM-Key": key})
            self.assertEqual(response.status_code, expected, key)
        self.assertEqual(self.color("#123456", 1).status_code, 200)
        self.assertEqual(self.profile()["nick_color"], "")
        self.assertEqual(self.profile(1)["nick_color"], "#123456")
        with db.db() as c:
            accounts.logout(c, self.keys[1])
        self.assertEqual(self.color("#ABCDEF", 1).status_code, 401)
        self.assertEqual(self.profile(1)["nick_color"], "#123456")

    def test_color_preserves_real_roles_and_does_not_bypass_sanctions(self):
        with db.db() as c:
            moderation.grant(c, self.ids[0])
            community.grant(c, self.ids[1], "server_owner", "CZM")
        for actor, color, role in ((0, "#123456", "support"), (1, "#ABCDEF", "server_owner")):
            changed = self.color(color, actor)
            self.assertEqual(changed.json()["profile"]["role"], role)
            self.assertEqual(self.profile(actor)["role"], role)
            self.assertEqual(self.request("POST", "chat/global", actor, json={"text": "Role message " + role}).status_code, 200)
        history = self.request("GET", "chat/global").json()["messages"]
        self.assertEqual([(m["r"], m["rp"], m["nick_color"]) for m in history],
                         [("support", "", "#123456"), ("server_owner", "CZM", "#ABCDEF")])
        with db.db() as c:
            c.execute("INSERT INTO bans(player,kind,reason,created) VALUES(?,?,?,?)", (self.ids[1], "text", "Mute", db.now()))
        self.assertEqual(self.color("#FEDCBA", 1).status_code, 200)  # cosmetic, like the theme picker
        self.assertEqual(self.request("POST", "chat/global", 1, json={"text": "Muted message"}).json()["error"], "muted")
        with db.db() as c:
            service.ban(c, self.ids[1], "week", "Ban")
        for color in ("#FF0000", ""):
            refused = self.color(color, 1)
            self.assertEqual((refused.status_code, refused.json()["error"]), (403, "banned"))
        self.assertEqual(self.profile(1)["nick_color"], "#FEDCBA")

    def test_block_and_deleted_message_filters_remain_in_force(self):
        self.color("#123456", 1)
        with db.db() as c:
            social.heartbeat(c, self.keys[1], "203.0.113.5:27015", "zm_test")
        sent = self.request("POST", "chat/global", 1, json={"text": "Hidden author"}).json()
        with db.db() as c:
            social.action(c, self.keys[0], self.ids[1], "block")
        profile = self.profile(1)
        self.assertEqual((profile["online"], profile["server"], profile["map"], profile["last_seen"]), (False, "", "", 0))
        self.assertEqual(self.request("GET", "chat/global").json()["messages"], [])
        with db.db() as c:
            social.action(c, self.keys[0], self.ids[1], "unblock")
            c.execute("UPDATE messages SET deleted=1 WHERE id=?", (sent["id"],))
        history = self.request("GET", "chat/global").json()
        self.assertEqual(history["messages"], [])
        self.assertIn(sent["id"], history["deleted"])

    def test_color_updates_are_rate_limited_per_account(self):
        for i in range(12):
            self.assertEqual(self.color("#%06X" % i).status_code, 200)
        response = self.color("#FFFFFF")
        self.assertEqual((response.status_code, response.json()["error"]), (429, "slow"))
        self.assertEqual(self.profile()["nick_color"], "#00000B")
        self.assertEqual(self.color("#FFFFFF", 1).status_code, 200)

    def test_migration_is_additive_idempotent_and_preserves_existing_records(self):
        with db.db() as c:
            social.update_status(c, self.keys[0], "Keep Help Support")
            social.update_theme(c, self.keys[0], "frost")
            social.heartbeat(c, self.keys[0])
            service.post_message(c, service.player_by_key(c, self.keys[0]), "global", "Keep history")
            before = dict(c.execute("SELECT player,status,theme,last_seen FROM social_profiles WHERE player=?", (self.ids[0],)).fetchone())
            players = [tuple(row) for row in c.execute("SELECT * FROM players ORDER BY id")]
            messages = [tuple(row) for row in c.execute("SELECT * FROM messages ORDER BY id")]
            c.execute("ALTER TABLE social_profiles RENAME TO old_social_profiles")
            c.execute("CREATE TABLE social_profiles (player INTEGER PRIMARY KEY REFERENCES players(id), status TEXT NOT NULL DEFAULT '', theme TEXT NOT NULL DEFAULT 'ember', last_seen INTEGER NOT NULL DEFAULT 0)")
            c.execute("INSERT INTO social_profiles SELECT player,status,theme,last_seen FROM old_social_profiles")
            c.execute("DROP TABLE old_social_profiles")
        db.init()
        self.assertEqual(self.profile()["nick_color"], "")
        self.color("#3DD6FF")
        db.init()
        db.init()
        with db.db() as c:
            self.assertEqual(dict(c.execute("SELECT player,status,theme,last_seen FROM social_profiles WHERE player=?", (self.ids[0],)).fetchone()), before)
            self.assertEqual(c.execute("SELECT nick_color FROM social_profiles WHERE player=?", (self.ids[0],)).fetchone()[0], "#3DD6FF")
            self.assertEqual([tuple(row) for row in c.execute("SELECT * FROM players ORDER BY id")], players)
            self.assertEqual([tuple(row) for row in c.execute("SELECT * FROM messages ORDER BY id")], messages)
            self.assertFalse(c.execute("PRAGMA foreign_key_check").fetchall())


if __name__ == "__main__":
    unittest.main()
