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
        answer = self.request("POST", "game/ticket", json={"address": "194.226.112.249:27016"})
        self.assertEqual(answer.status_code, 401)

    def test_no_key_on_the_host_means_no_ticket(self):
        self.key_file.write_text("")
        answer = self.ask(1, "194.226.112.249:27016")
        self.assertEqual((answer.status_code, answer.json()), (503, {"error": "ticket_unavailable"}))


if __name__ == "__main__":
    unittest.main()
