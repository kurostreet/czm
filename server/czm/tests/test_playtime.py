"""Time on game servers and the Top 100: only real play counts, once, and the board ranks it."""
import os
import tempfile
import unittest
from unittest.mock import patch

from czm import db, playtime, service
from czm.config import get_settings


class PlaytimeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        env = patch.dict(os.environ, {"CZM_DATA_DIR": temp.name, "CZM_PLAY_SERVICE_ACCOUNT_FILE": "/nonexistent"})
        env.start(); self.addCleanup(env.stop)
        get_settings.cache_clear(); self.addCleanup(get_settings.cache_clear)
        db.init()
        self.ids = []
        with db.db() as conn:
            for n in range(1, 6):
                self.ids.append(service.hello(conn, f"playtime-key-{n:04d}-abcdef", f"d{n}", f"P{n}", str(n), "ru", "1")["id"])

    def report(self, player, owner, playing, t):
        with db.db() as conn:
            return playtime.accrue(conn, player, owner, playing, t)

    def seconds(self, player):
        with db.db() as conn:
            row = conn.execute("SELECT seconds FROM playtime WHERE player=?", (player,)).fetchone()
            return row["seconds"] if row else 0

    def test_only_reports_from_a_game_server_count_and_gaps_are_capped(self):
        p = self.ids[0]
        self.assertEqual(self.report(p, "phone", False, 1000), 0)   # the menu
        self.assertEqual(self.report(p, "phone", True, 1010), 0)    # connected: counting starts now
        self.assertEqual(self.report(p, "phone", True, 1040), 30)
        self.assertEqual(self.report(p, "phone", True, 1070), 30)
        self.assertEqual(self.report(p, "phone", True, 2070), playtime.CAP)  # asleep for 1000 s: one report's worth
        self.assertEqual(self.report(p, "phone", False, 2090), 0)   # back to the menu: the pause starts
        self.assertEqual(self.report(p, "phone", True, 2600), 0)    # the menu time is never credited
        self.assertEqual(self.report(p, "phone", True, 2630), 30)
        self.assertEqual(self.report(p, "phone", True, 2620), 0)    # a late, reordered report adds nothing
        self.assertEqual(self.seconds(p), 30 + 30 + playtime.CAP + 30)

    def test_two_phones_of_one_account_credit_the_time_once(self):
        p = self.ids[0]
        for t, owner in ((0, "a"), (10, "b"), (30, "a"), (40, "b"), (60, "a"), (70, "b")):
            self.report(p, owner, True, 1000 + t)
        self.assertEqual(self.seconds(p), 70)                       # 70 s of wall-clock time, not 120
        # the other phone sits in the menu: the playing one keeps counting
        self.report(p, "b", False, 1075)
        self.assertEqual(self.report(p, "a", True, 1090), 20)        # 1060..1090, the first 10 s were the other's
        self.report(p, "a", False, 1100)
        self.assertEqual(self.report(p, "a", True, 1500), 0)

    def test_the_board_ranks_tiers_and_the_own_place(self):
        times = {self.ids[0]: 500, self.ids[1]: 9000, self.ids[2]: 9000, self.ids[3]: 120}
        with db.db() as conn:
            for player, seconds in times.items():
                conn.execute("INSERT INTO playtime(player, seconds) VALUES (?,?)", (player, seconds))
            board = playtime.board(conn, self.ids[3])
            self.assertEqual([r["id"] for r in board["top"]], [self.ids[1], self.ids[2], self.ids[0], self.ids[3]])
            self.assertEqual([r["tier"] for r in board["top"]], ["top1", "top2", "top3", "top10"])
            self.assertEqual(board["top"][0]["nick"], "P2")
            self.assertEqual(board["me"], {"place": 4, "seconds": 120, "tier": "top10"})
            self.assertEqual(board["players"], 4)
            self.assertIsNone(playtime.board(conn, self.ids[4])["me"])   # no minute on a server yet
            # a banned player leaves the board; a lifted ban brings him back
            conn.execute("INSERT INTO bans(player, device_hash, until, reason, created, kind) VALUES (?, '', NULL, 'x', 1, 'ban')",
                         (self.ids[1],))
            self.assertEqual(playtime.places(conn), {self.ids[2]: 1, self.ids[0]: 2, self.ids[3]: 3})
            conn.execute("UPDATE bans SET lifted=1")
            self.assertEqual(playtime.places(conn)[self.ids[1]], 1)
        self.assertEqual([playtime.tier(n) for n in (1, 2, 3, 4, 10, 11, 50, 51, 100, 101, None)],
                         ["top1", "top2", "top3", "top10", "top10", "top50", "top50", "top100", "top100", "", ""])

    def test_beyond_the_hundred_the_own_card_says_how_far(self):
        with db.db() as conn:
            for n in range(110):
                pid = service.hello(conn, f"playtime-more-{n:04d}-abcdef", f"m{n}", f"M{n}", "", "ru", "1")["id"]
                conn.execute("INSERT INTO playtime(player, seconds) VALUES (?,?)", (pid, 10000 - n * 10))
            conn.execute("INSERT INTO playtime(player, seconds) VALUES (?,?)", (self.ids[0], 100))
            board = playtime.board(conn, self.ids[0])
            self.assertEqual(len(board["top"]), 100)
            self.assertEqual(board["top"][-1]["place"], 100)
            self.assertEqual(board["me"]["place"], 111)
            self.assertEqual(board["me"]["tier"], "")
            self.assertEqual(board["me"]["behind"], board["top"][-1]["seconds"] - 100 + 1)
            self.assertNotIn(self.ids[0], playtime.places(conn))

    def test_chat_and_profiles_show_the_place(self):
        from czm import social
        with db.db() as conn:
            conn.execute("INSERT INTO playtime(player, seconds) VALUES (?, 3600)", (self.ids[1],))
            conn.execute("INSERT INTO messages(room, player, text, created) VALUES ('global', ?, 'hi', 1)", (self.ids[1],))
            conn.execute("INSERT INTO messages(room, player, text, created) VALUES ('global', ?, 'hey', 2)", (self.ids[2],))
            items = service.messages(conn, "global", 0)
            self.assertEqual([m.get("k") for m in items], [1, None])
            viewer = conn.execute("SELECT * FROM players WHERE id=?", (self.ids[0],)).fetchone()
            card = social.profile(conn, viewer, self.ids[1])
            self.assertEqual(card["top"], {"place": 1, "seconds": 3600, "tier": "top1"})
            self.assertEqual(social.profile(conn, viewer, self.ids[1], True)["top"], {"place": 1, "tier": "top1"})
            self.assertNotIn("top", social.profile(conn, viewer, self.ids[2]))


try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
except ImportError:
    FastAPI = None


@unittest.skipIf(FastAPI is None, "fastapi is not installed")
class TopApiTests(unittest.TestCase):
    def setUp(self):
        from czm import api
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        env = patch.dict(os.environ, {"CZM_DATA_DIR": temp.name, "CZM_PLAY_SERVICE_ACCOUNT_FILE": "/nonexistent"})
        env.start(); self.addCleanup(env.stop)
        get_settings.cache_clear(); self.addCleanup(get_settings.cache_clear)
        for value in vars(api).values():
            if isinstance(value, api._Limiter):
                value.calls.clear()
        db.init()
        app = FastAPI(); app.include_router(api.router)
        self.client = TestClient(app); self.addCleanup(self.client.close)

    def test_presence_in_a_game_fills_the_board(self):
        key = "top-api-key-0001-abcdef"
        self.assertEqual(self.client.post("/api/v1/hello", json={"key": key, "nick": "Kuro"}).status_code, 200)
        clock = [1_900_000_000]
        with patch("czm.social.now", side_effect=lambda: clock[0]), patch("czm.playtime.now", side_effect=lambda: clock[0]):
            for step in range(4):
                r = self.client.post("/api/v1/social/presence", headers={"X-CZM-Key": key},
                                     json={"server": "203.0.113.5:27015", "map": "zm_alpha"})
                self.assertEqual(r.status_code, 200, r.text)
                clock[0] += 30
            self.client.post("/api/v1/social/presence", headers={"X-CZM-Key": key}, json={"server": "", "map": ""})
            board = self.client.get("/api/v1/top", headers={"X-CZM-Key": key}).json()
        self.assertEqual(board["top"][0]["nick"], "Kuro")
        self.assertEqual(board["top"][0]["seconds"], 90)
        self.assertEqual(board["me"]["place"], 1)
        anonymous = self.client.get("/api/v1/top").json()
        self.assertNotIn("me", anonymous)


if __name__ == "__main__":
    unittest.main()
