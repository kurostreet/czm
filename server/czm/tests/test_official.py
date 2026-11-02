"""The project's own servers: set in the head administrator panel, sent to every game with hello."""
import os
import unittest
from unittest.mock import patch
from czm import db, official
from czm.config import get_settings
import test_community as baseline


class OfficialServerTests(unittest.TestCase):
    request = baseline.CommunityTests.request

    def setUp(self):
        baseline.CommunityTests.setUp(self)
        env = patch.dict(os.environ, {"CZM_ADMIN_PLAYER_IDS": str(self.ids[0])})
        env.start(); self.addCleanup(env.stop); get_settings.cache_clear(); self.addCleanup(get_settings.cache_clear)
        self.sequence = 0

    def change(self, actor=0, **fields):
        self.sequence += 1
        return self.request("POST", "admin/action", actor, json={"action": "official_servers",
                                                                 "nonce": f"official-change-{self.sequence:04d}", **fields})

    def hello(self, player=1):
        return self.request("POST", "hello", json={"key": self.keys[player]}).json()["official"]

    def test_off_and_empty_until_the_owner_sets_them(self):
        self.assertEqual(self.hello(), {"enabled": False, "survival": "", "escape": ""})
        self.assertEqual(self.request("GET", "admin/official").json(), {"enabled": False, "survival": "", "escape": ""})

    def test_owner_sets_both_slots_and_every_game_gets_them(self):
        answer = self.change(enabled=True, survival=" 194.226.112.249:27016 ", escape="")
        self.assertEqual(answer.status_code, 200, answer.text)
        expected = {"enabled": True, "survival": "194.226.112.249:27016", "escape": ""}
        self.assertEqual(self.hello(1), expected)
        self.assertEqual(self.hello(2), expected)
        # a bare IP gets the default port; turning off keeps the addresses for later
        self.change(enabled=False, survival="194.226.112.249:27016", escape="8.8.8.8")
        self.assertEqual(self.hello(), {"enabled": False, "survival": "194.226.112.249:27016", "escape": "8.8.8.8:27015"})
        with db.db() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM admin_actions WHERE action='official_servers'").fetchone()[0], 2)

    def test_only_the_head_administrator_and_only_public_addresses(self):
        for i in range(1, 4):
            self.assertEqual(self.change(i, enabled=True, survival="194.226.112.249:27016").status_code, 403)
            self.assertEqual(self.request("GET", "admin/official", i).status_code, 403)
        for bad in ("127.0.0.1:27015", "192.168.1.5:27015", "example.com:27015", "not an ip"):
            self.assertEqual(self.change(enabled=True, survival=bad).status_code, 400, bad)
        self.assertEqual(self.change(enabled=True, survival="194.226.112.249:27016", escape="194.226.112.249:27016").status_code, 400)
        self.assertEqual(self.hello(), {"enabled": False, "survival": "", "escape": ""})

    def test_state_without_rows(self):
        with db.db() as c:
            self.assertEqual(official.state(c), {"enabled": False, "survival": "", "escape": ""})


if __name__ == "__main__":
    unittest.main()
