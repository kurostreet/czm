"""Tickets for our game servers: only for our addresses, signed for that address, short-lived."""
import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from czm import db, game_ticket, official
from czm.config import get_settings
import test_community as baseline


class GameTicketTests(unittest.TestCase):
    request = baseline.CommunityTests.request

    def setUp(self):
        baseline.CommunityTests.setUp(self)
        env = patch.dict(os.environ, {"CZM_ADMIN_PLAYER_IDS": str(self.ids[0])})
        env.start(); self.addCleanup(env.stop); get_settings.cache_clear(); self.addCleanup(get_settings.cache_clear)
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        self.key_file = Path(folder.name) / "game-ticket.key"
        self.key_file.write_text("ab" * 32 + "\n")
        keyed = patch.object(game_ticket, "KEY_FILE", self.key_file)
        keyed.start(); self.addCleanup(keyed.stop)
        with db.db() as c:
            official.update(c, True, "194.226.112.249:27016", "", 0)

    def ask(self, player, address):
        return self.request("POST", "game/ticket", player, json={"address": address})

    def test_ticket_names_the_profile_and_is_signed_for_that_server(self):
        with patch.object(game_ticket, "now", return_value=1_000_000):
            answer = self.ask(1, " 194.226.112.249:27016 ")
        self.assertEqual(answer.status_code, 200, answer.text)
        profile, expires, signature = answer.json()["ticket"].split(".")
        self.assertEqual((int(profile), int(expires)), (self.ids[1], 1_000_000 + 15 * 60))
        key = "ab" * 32
        expected = hashlib.sha256(f"{key}|v1|{profile}|{expires}|194.226.112.249:27016|{key}".encode()).hexdigest()[:32]
        self.assertEqual(signature, expected)
        # the same ticket would not pass on another address
        self.assertNotEqual(game_ticket.sign(key, int(profile), int(expires), "8.8.8.8:27015"), signature)

    def test_only_for_our_servers(self):
        answer = self.ask(1, "8.8.8.8:27015")
        self.assertEqual((answer.status_code, answer.json()), (403, {"error": "not_official"}))
        self.assertEqual(self.ask(1, "127.0.0.1:27015").status_code, 400)

    def test_needs_a_player(self):
        answer = self.client.post("/api/v1/game/ticket", json={"address": "194.226.112.249:27016"})
        self.assertEqual(answer.status_code, 401)

    def test_no_key_on_the_host_means_no_ticket(self):
        self.key_file.write_text("")
        answer = self.ask(1, "194.226.112.249:27016")
        self.assertEqual((answer.status_code, answer.json()), (503, {"error": "ticket_unavailable"}))

    def test_survival_profile_proof_requires_account_and_connection_challenge(self):
        address, escape, challenge = "194.226.112.249:27016", "194.226.112.249:27017", "de" * 16
        body = {"address": address, "challenge": challenge}
        guest = self.client.post("/api/v1/game/ticket", headers={"X-CZM-Key": self.guest}, json=body)
        self.assertEqual(guest.status_code, 401)
        with db.db() as conn:
            official.update(conn, False, address, escape, 0)
        headers = {"X-CZM-Key": self.keys[1]}
        with patch.object(game_ticket, "now", return_value=1_000_000):
            answer = self.client.post("/api/v1/game/ticket", headers=headers, json=body)
        self.assertEqual(answer.status_code, 200, answer.text)
        profile, expires, signature = answer.json()["ticket"].split(".")
        self.assertEqual((int(profile), int(expires)), (self.ids[1], 1_000_060))
        key = "ab" * 32
        expected = hashlib.sha256(f"{key}|profile-v1|{profile}|{expires}|{address}|{challenge}|{key}".encode()).hexdigest()[:32]
        self.assertEqual(signature, expected)
        self.assertNotEqual(signature, game_ticket.sign_profile(key, int(profile), int(expires), address, "ef" * 16))
        self.assertEqual(self.client.post("/api/v1/game/ticket", headers=headers, json={**body, "address": escape}).status_code, 403)
        self.assertEqual(self.client.post("/api/v1/game/ticket", headers=headers, json={**body, "challenge": "x" * 32}).status_code, 400)


if __name__ == "__main__":
    unittest.main()


class SurvivalApiTests(GameTicketTests):
    """The LVL MOD endpoints: game servers prove themselves with the ticket key, players with their key."""

    def server(self, path, body, token=None):
        from czm import survival
        token = token if token is not None else survival.server_token("ab" * 32)
        return self.client.post("/api/v1/survival/server/" + path, json=body, headers={"X-CZM-Server": token})

    def test_only_our_game_server_reports(self):
        body = {"batch": "api-batch-0001", "entries": [{"player": self.ids[1], "nick": "One", "kills": 10, "zkills": 10}]}
        self.assertEqual(self.server("report", body, token="0" * 64).status_code, 401)
        answer = self.server("report", body)
        self.assertEqual(answer.status_code, 200, answer.text)
        state = answer.json()["states"][str(self.ids[1])]
        self.assertEqual((state["lvl"], state["tokens"]), (1, 10))
        me = self.request("GET", "survival/me", 1).json()["state"]
        self.assertEqual(me["tokens"], 10)

    def test_a_player_buys_from_the_site_and_the_game_sees_it(self):
        from czm import survival
        with db.db() as c:
            survival.ensure(c, self.ids[1])
            c.execute("UPDATE survival_players SET tokens=3000 WHERE player=?", (self.ids[1],))
        bought = self.request("POST", "survival/action", 1, json={"op": "site-buy-0001", "action": "buy",
                                                                  "args": {"cat": "prefix", "item": "pro"}})
        self.assertEqual(bought.status_code, 200, bought.text)
        joined = self.server("join", {"player": self.ids[1], "op": "join-00000000", "action": "join", "args": {"nick": "One"}})
        self.assertEqual(joined.json()["state"]["equipped"], {"prefix": "pro"})
        catalog = self.client.get("/api/v1/survival/catalog").json()
        self.assertEqual(catalog["categories"][0]["key"], "prefix")
        self.assertEqual(self.client.get("/api/v1/survival/top").json()["top"][0]["id"], self.ids[1])

    def test_each_server_mode_has_its_own_economy(self):
        from czm import survival
        body = {"batch": "api-batch-ze01", "entries": [{"player": self.ids[1], "nick": "One", "kills": 5, "zkills": 5}],
                "live": {"map": "ze_test", "players": [], "max": 32}}
        answer = self.client.post("/api/v1/survival/server/report?mode=escape", json=body,
                                  headers={"X-CZM-Server": survival.server_token("ab" * 32)})
        self.assertEqual(answer.status_code, 200, answer.text)
        self.assertEqual(self.request("GET", "survival/me?mode=escape", 1).json()["state"]["tokens"], 5)
        self.assertEqual(self.request("GET", "survival/me", 1).json()["state"]["tokens"], 0)
        self.assertEqual(self.request("GET", "survival/me?mode=nope", 1).status_code, 404)
        servers = {s["mode"]: s for s in self.client.get("/api/v1/survival/servers").json()["servers"]}
        self.assertEqual(sorted(servers), ["escape", "survival"])
        self.assertEqual(servers["escape"]["live"]["map"], "ze_test")
        self.assertEqual(self.client.get("/api/v1/survival/top?mode=escape").json()["top"][0]["id"], self.ids[1])
