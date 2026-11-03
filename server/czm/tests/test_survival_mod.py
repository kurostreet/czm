"""Order on the Survival server: bans, mutes, the staff, messages to the staff, the news."""
import os
import tempfile
import unittest
from unittest.mock import patch

from czm import admin, community, db, service, survival_mod
from czm.config import get_settings


class SurvivalOrderTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        env = patch.dict(os.environ, {"CZM_DATA_DIR": folder.name, "CZM_ADMIN_PLAYER_IDS": ""})
        env.start(); self.addCleanup(env.stop); get_settings.cache_clear(); self.addCleanup(get_settings.cache_clear)
        db.init()
        self.t = 1_800_000_000
        clock = patch.object(survival_mod, "now", side_effect=lambda: self.t)
        clock.start(); self.addCleanup(clock.stop)
        with db.db() as c:
            self.boss = service.hello(c, "a" * 24, "", "Boss", "", "ru", "1")["id"]
            self.mod = service.hello(c, "b" * 24, "", "Moder", "", "ru", "1")["id"]
            self.p = service.hello(c, "c" * 24, "", "Player", "", "ru", "1")["id"]
            self.q = service.hello(c, "d" * 24, "", "Other", "", "ru", "1")["id"]
        allowed = patch.object(admin, "allowed", side_effect=lambda c, player: player == self.boss)
        has = patch.object(community, "has", side_effect=lambda c, player, role: player == self.mod and role == "moderator")
        allowed.start(); has.start(); self.addCleanup(allowed.stop); self.addCleanup(has.stop)

    def run_in(self, fn, *args, **kwargs):
        with db.db() as c:
            return fn(c, *args, **kwargs)

    def test_roles(self):
        self.assertEqual(self.run_in(survival_mod.role, self.boss), "admin")
        self.assertEqual(self.run_in(survival_mod.role, self.mod), "moderator")
        self.assertEqual(self.run_in(survival_mod.role, self.p), "")
        self.assertEqual(self.run_in(survival_mod.role, 0), "")

    def test_a_ban_holds_the_profile_until_it_ends(self):
        self.run_in(survival_mod.add, "ban", self.p, "10.0.0.5", "Player", 1800, "cheats", self.mod, "Moder")
        state = self.run_in(survival_mod.check, self.p, "10.0.0.5")
        self.assertEqual(state["ban"]["left"], 1800)
        self.assertEqual(state["ban"]["reason"], "cheats")
        self.assertIsNone(state["mute"])
        # the address of a profile is never banned: phones share it behind the carrier
        self.assertIsNone(self.run_in(survival_mod.check, self.q, "10.0.0.5")["ban"])
        self.assertIsNone(self.run_in(survival_mod.check, 0, "10.0.0.5")["ban"])
        self.t += 1801
        self.assertIsNone(self.run_in(survival_mod.check, self.p, "10.0.0.5")["ban"])

    def test_a_guest_is_banned_by_the_address(self):
        self.run_in(survival_mod.add, "ban", 0, "10.0.0.7:27005", "guest", 600, "", self.mod, "Moder")
        self.assertIsNotNone(self.run_in(survival_mod.check, 0, "10.0.0.7")["ban"])
        self.assertIsNone(self.run_in(survival_mod.check, self.p, "10.0.0.7")["ban"])
        with self.assertRaises(survival_mod.Error):
            self.run_in(survival_mod.add, "ban", 0, "not an address", "guest", 600, "", self.mod, "Moder")

    def test_who_may_judge_whom(self):
        add = lambda kind, target, seconds, by: self.run_in(survival_mod.add, kind, target, "", "x", seconds, "", by, "x")
        with self.assertRaises(survival_mod.Error) as e:
            add("ban", self.q, 600, self.p)                  # a player is not staff
        self.assertEqual(e.exception.code, "staff_only")
        with self.assertRaises(survival_mod.Error) as e:
            add("ban", self.boss, 600, self.mod)             # the head administrators are immune
        self.assertEqual(e.exception.code, "immune")
        with self.assertRaises(survival_mod.Error) as e:
            add("ban", self.q, survival_mod.FOREVER, self.mod)
        self.assertEqual(e.exception.code, "too_long")
        with self.assertRaises(survival_mod.Error):
            add("mute", self.mod, 600, 0)                    # the vote cannot touch staff
        with self.assertRaises(survival_mod.Error):
            add("ban", self.q, survival_mod.FOREVER, 0)      # nor ban forever
        self.assertTrue(add("ban", self.mod, 600, self.boss)["ok"])
        self.assertEqual(add("ban", self.q, survival_mod.FOREVER, self.boss)["left"], -1)
        self.assertEqual(self.run_in(survival_mod.check, self.q)["ban"]["left"], -1)

    def test_vote_mute_and_lifting(self):
        out = self.run_in(survival_mod.add, "mute", self.p, "", "Player", 3600, "vote", 0, "")
        board = self.run_in(survival_mod.board)
        self.assertEqual(board[0]["kind"], "mute")
        self.assertTrue(board[0]["vote"])
        self.assertEqual(board[0]["by"], "vote")
        self.assertNotIn("ip", board[0])
        with self.assertRaises(survival_mod.Error):
            self.run_in(survival_mod.lift, out["id"], self.p)
        self.assertTrue(self.run_in(survival_mod.lift, out["id"], self.mod)["changed"])
        self.assertFalse(self.run_in(survival_mod.lift, out["id"], self.mod)["changed"])
        self.assertIsNone(self.run_in(survival_mod.check, self.p)["mute"])
        self.assertEqual(self.run_in(survival_mod.board), [])
        # what a head administrator gave, a moderator cannot lift; the owner's bot can
        out = self.run_in(survival_mod.add, "ban", self.p, "", "Player", 600, "", self.boss, "Boss")
        with self.assertRaises(survival_mod.Error):
            self.run_in(survival_mod.lift, out["id"], self.mod)
        self.assertTrue(self.run_in(survival_mod.lift, out["id"], 0, owner=True)["changed"])

    def test_messages_to_the_staff(self):
        for n in range(survival_mod.MESSAGE_LIMIT):
            self.run_in(survival_mod.message, self.p, "", "Player", f"help {n} ^1\x00", "survival")
        with self.assertRaises(survival_mod.Error) as e:
            self.run_in(survival_mod.message, self.p, "", "Player", "one more", "survival")
        self.assertEqual(e.exception.code, "message_limit")
        with self.assertRaises(survival_mod.Error):
            self.run_in(survival_mod.message, self.q, "", "Other", " a ", "survival")
        pending = self.run_in(survival_mod.pending_messages)
        self.assertEqual([m["text"] for m in pending], ["help 0 1", "help 1 1", "help 2 1"])
        self.run_in(survival_mod.messages_delivered, [m["id"] for m in pending])
        self.assertEqual(self.run_in(survival_mod.pending_messages), [])
        self.t += survival_mod.MESSAGE_WINDOW + 1
        self.assertTrue(self.run_in(survival_mod.message, self.p, "", "Player", "again", "survival")["ok"])

    def test_news(self):
        first = self.run_in(survival_mod.news_add, "Новая карта", "New map")
        self.run_in(survival_mod.news_add, "Только по-русски")
        news = self.run_in(survival_mod.news)
        self.assertEqual([n["ru"] for n in news], ["Только по-русски", "Новая карта"])
        self.assertEqual(news[0]["en"], "Только по-русски")
        self.assertTrue(self.run_in(survival_mod.news_delete, first["id"]))
        self.assertEqual(len(self.run_in(survival_mod.news)), 1)
        with self.assertRaises(survival_mod.Error):
            self.run_in(survival_mod.news_add, "  ")

    def test_privileges(self):
        with self.assertRaises(survival_mod.Error):
            self.run_in(survival_mod.set_privilege, self.p, "vip", 86400, self.mod, "Moder")    # head admins only
        self.run_in(survival_mod.set_privilege, self.p, "vip", 86400, self.boss, "Boss")
        state = self.run_in(survival_mod.check, self.p)["privilege"]
        self.assertEqual((state["kind"], state["name"], state["left"]), ("vip", "VIP+", 86400))
        self.run_in(survival_mod.set_privilege, self.p, "deluxe", survival_mod.FOREVER, 0, "bot", owner=True)
        self.assertEqual(self.run_in(survival_mod.privilege, self.p)["left"], -1)
        self.assertEqual([r["kind"] for r in self.run_in(survival_mod.privileges)], ["deluxe"])
        with self.assertRaises(survival_mod.Error):
            self.run_in(survival_mod.set_privilege, self.p, "god", 60, self.boss, "Boss")
        self.run_in(survival_mod.set_privilege, self.p, "", 0, self.boss, "Boss")
        self.assertIsNone(self.run_in(survival_mod.check, self.p)["privilege"])
        self.run_in(survival_mod.set_privilege, self.q, "tester", 60, self.boss, "Boss")
        self.t += 61
        self.assertIsNone(self.run_in(survival_mod.privilege, self.q))
        self.assertIsNone(self.run_in(survival_mod.privilege, 0))

    def test_staff_log(self):
        self.run_in(survival_mod.staff_log, self.mod, "Moder", "kick", self.p, "Player", "spam ^1", "survival")
        self.run_in(survival_mod.staff_log, self.boss, "Boss", "airdrop")
        rows = self.run_in(survival_mod.staff_log_list)
        self.assertEqual([r["action"] for r in rows], ["airdrop", "kick"])
        self.assertEqual(rows[1]["detail"], "spam 1")
        self.t += 91 * 86400
        self.run_in(survival_mod.staff_log, self.boss, "Boss", "say")
        self.assertEqual(len(self.run_in(survival_mod.staff_log_list)), 1)


if __name__ == "__main__":
    unittest.main()
