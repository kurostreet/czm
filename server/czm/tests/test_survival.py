"""LVL MOD of the Survival server: levels, tokens, shop, battle pass, transfers, promo codes, market."""
import os
import tempfile
import unittest
from unittest.mock import patch

from czm import db, service, survival
from czm.config import get_settings


class SurvivalTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        env = patch.dict(os.environ, {"CZM_DATA_DIR": folder.name, "CZM_ADMIN_PLAYER_IDS": ""})
        env.start(); self.addCleanup(env.stop); get_settings.cache_clear(); self.addCleanup(get_settings.cache_clear)
        db.init()
        self.t = 1_800_000_000
        clock = patch.object(survival, "now", side_effect=lambda: self.t)
        clock.start(); self.addCleanup(clock.stop)
        with db.db() as c:
            self.a = service.hello(c, "a" * 24, "", "Alpha", "", "ru", "1")["id"]
            self.b = service.hello(c, "b" * 24, "", "Bravo", "", "ru", "1")["id"]
        self.ops = 0

    def run_in(self, fn, *args):
        with db.db() as c:
            return fn(c, *args)

    def act(self, player, name, **args):
        self.ops += 1
        return self.run_in(survival.action, player, f"test-op-{self.ops:05d}", name, args)

    def give(self, player, tokens=0, **fields):
        with db.db() as c:
            survival.ensure(c, player)
            c.execute("UPDATE survival_players SET tokens=tokens+? WHERE player=?", (tokens, player))
            for k, v in fields.items():
                c.execute(f"UPDATE survival_players SET {k}=? WHERE player=?", (v, player))

    def report(self, batch, **entry):
        return self.run_in(survival.report, batch, [{"player": self.a, "nick": "Alpha", **entry}])

    def state(self, player=None):
        return self.run_in(survival.state, player or self.a)

    def test_levels_and_tokens_follow_kontra_rules(self):
        out = self.report("b1", time=1200, kills=10, zkills=10, survived=1, rounds=1, wins=1)
        s = out["states"][self.a]
        self.assertEqual(s["lvl"], 3)                       # 2 for 20 minutes, 1 for 10 kills
        self.assertEqual(s["tokens"], 10 + 3 + 2 * 2)       # kills, a round survived, two 10-minute marks
        self.assertIn({"type": "level", "lvl": 3}, out["events"][self.a])
        # the same batch twice changes nothing
        self.assertTrue(self.report("b1", time=1200, kills=10)["repeat"])
        self.assertEqual(self.state()["tokens"], 17)

    def test_boosts_double_tokens_and_earned_levels(self):
        self.give(self.a, tokens=survival.PRICE_BOOST_TOK + survival.PRICE_BOOST_LVL)
        self.act(self.a, "upgrade", item="tok_boost")
        self.act(self.a, "upgrade", item="lvl_boost")
        s = self.report("b2", kills=10, zkills=10)["states"][self.a]
        self.assertEqual(s["tokens"], 20)
        self.assertEqual(s["lvl"], 2)                        # 1 earned, doubled
        self.t += 3 * 3600
        s = self.report("b3", kills=10, zkills=10)["states"][self.a]
        self.assertEqual((s["tokens"], s["lvl"]), (30, 3))  # both boosts are over

    def test_shop_spends_once_and_equips(self):
        self.give(self.a, tokens=3000)
        with self.assertRaises(survival.Error) as e:
            self.act(self.a, "buy", cat="skin", item="gign")
        self.assertEqual(e.exception.code, "tokens")
        r = self.act(self.a, "buy", cat="prefix", item="pro")
        self.assertEqual((r["price"], r["state"]["tokens"], r["state"]["equipped"]["prefix"]), (2500, 500, "pro"))
        # buying what one owns only puts it on
        self.assertFalse(self.act(self.a, "buy", cat="prefix", item="pro")["bought"])
        self.assertEqual(self.state()["tokens"], 500)
        for cat, it, code in (("prefix", "battlepass", "not_for_sale"), ("knife", "sickle", "admin_only"),
                              ("skin", "nothing", "item")):
            with self.assertRaises(survival.Error) as e:
                self.act(self.a, "buy", cat=cat, item=it)
            self.assertEqual(e.exception.code, code)
        self.act(self.a, "equip", cat="prefix", item="")
        self.assertNotIn("prefix", self.state()["equipped"])

    def test_an_operation_runs_once(self):
        self.give(self.a, tokens=5000)
        with db.db() as c:
            first = survival.action(c, self.a, "same-operation-1", "buy", {"cat": "skin", "item": "gign"})
            again = survival.action(c, self.a, "same-operation-1", "buy", {"cat": "skin", "item": "gign"})
        self.assertEqual(first, again)
        self.assertEqual(self.state()["tokens"], 0)
        with self.assertRaises(survival.Error):
            self.run_in(survival.action, self.b, "same-operation-1", "buy", {"cat": "skin", "item": "gign"})

    def test_transfers_need_level_ten_and_keep_the_daily_limit(self):
        self.give(self.a, tokens=500)
        self.give(self.b)
        with self.assertRaises(survival.Error) as e:
            self.act(self.a, "pay", target=self.b, amount=50)
        self.assertEqual(e.exception.code, "pay_lvl")
        self.give(self.a, bonus_lvl=10)
        self.act(self.a, "pay", target=self.b, amount=60)
        with self.assertRaises(survival.Error) as e:
            self.act(self.a, "pay", target=self.b, amount=50)
        self.assertEqual(e.exception.code, "pay_limit")
        self.assertEqual((self.state()["tokens"], self.state(self.b)["tokens"]), (440, 60))
        self.t += 86400
        self.act(self.a, "pay", target=self.b, amount=50)
        self.assertEqual(self.state(self.b)["tokens"], 110)

    def test_battle_pass(self):
        self.give(self.a, tokens=survival.BP_PRICE)
        self.act(self.a, "bp_buy")
        s = self.state()
        self.assertTrue(s["battlepass"]["active"] and s["battlepass"]["daily"])
        self.assertEqual(self.act(self.a, "bp_daily")["amount"], survival.BP_DAILY)
        with self.assertRaises(survival.Error):
            self.act(self.a, "bp_daily")
        # a task pays itself when it is done
        s = self.report("bp1", kills=50, zkills=0)["states"][self.a]
        self.assertIn("k50", s["battlepass"]["claimed"])
        self.assertEqual(s["tokens"], survival.BP_DAILY + 100)
        with self.assertRaises(survival.Error) as e:
            self.act(self.a, "bp_final", item="lvl")
        self.assertEqual(e.exception.code, "bp_tasks")
        with db.db() as c:
            c.execute("UPDATE survival_players SET bp=json_set(bp, '$.claimed', json(?)) WHERE player=?",
                      ('["' + '","'.join(t[0] for t in survival.BP_TASKS) + '"]', self.a))
        self.act(self.a, "bp_final", item="prefix")
        self.assertIn("battlepass", self.state()["owned"]["prefix"])
        self.t += survival.BP_DAYS * 86400
        self.assertFalse(self.state()["battlepass"]["active"])

    def test_promo_codes(self):
        self.run_in(survival.promo_create, "Free20LVL", "lvl", 20, 0)
        self.assertEqual(self.act(self.a, "promo", code=" free20lvl ")["amount"], 20)
        self.assertEqual(self.state()["lvl"], 20)
        with self.assertRaises(survival.Error) as e:
            self.act(self.a, "promo", code="free20lvl")
        self.assertEqual(e.exception.code, "promo_used")
        with self.assertRaises(survival.Error):
            self.run_in(survival.promo_create, "free20lvl", "tokens", 5, 0)

    def test_market_holds_the_item_and_takes_its_tax(self):
        self.give(self.a, tokens=2500)
        self.give(self.b, tokens=1000)
        self.act(self.a, "buy", cat="prefcolor", item="#ffd700")
        listing = self.act(self.a, "market_sell", cat="prefcolor", item="#FFD700", price=1000)["listing"]
        self.assertEqual(self.state()["owned"]["prefcolor"], [])
        self.assertNotIn("prefcolor", self.state()["equipped"])
        self.act(self.b, "market_buy", listing=listing)
        self.assertEqual(self.state(self.b)["owned"]["prefcolor"], ["#FFD700"])
        self.assertEqual((self.state()["tokens"], self.state(self.b)["tokens"]), (950, 0))
        # an offer nobody takes comes back after a week
        self.act(self.b, "market_sell", cat="prefcolor", item="#FFD700", price=5)
        self.t += survival.MARKET_DAYS * 86400
        self.assertEqual(self.run_in(survival.market, self.b)["listings"], [])
        self.assertEqual(self.state(self.b)["owned"]["prefcolor"], ["#FFD700"])

    def test_weapon_crate_lasts_half_an_hour(self):
        self.give(self.a, tokens=1000)
        s = self.act(self.a, "crate", item="arm100")["state"]
        self.assertEqual((s["tokens"], s["crate"]), (900, {"arm100": survival.CRATE_SECONDS}))
        s = self.act(self.a, "crate", item="invis")["state"]
        self.assertEqual(s["crate"]["charges"], 3)
        # charges are spent by the game server only
        with self.assertRaises(survival.Error):
            self.act(self.a, "crate_use")
        self.ops += 1
        s = self.run_in(survival.action, self.a, "game-use-1", "crate_use", {}, True)["state"]
        self.assertEqual(s["crate"]["charges"], 2)
        self.t += survival.CRATE_SECONDS
        self.assertEqual(self.state()["crate"], {})

    def test_airdrop_pays_only_known_packs(self):
        self.give(self.a)
        s = self.run_in(survival.action, self.a, "game-air-1", "reward", {"kind": "airdrop", "amount": 25}, True)["state"]
        self.assertEqual(s["tokens"], 25)
        for args in ({"kind": "airdrop", "amount": 26}, {"kind": "gift", "amount": 25}):
            with self.assertRaises(survival.Error):
                self.run_in(survival.action, self.a, "game-air-2", "reward", args, True)
        with self.assertRaises(survival.Error):
            self.act(self.a, "reward", kind="airdrop", amount=25)

    def test_map_top_pays_the_best_three(self):
        for p in (self.a, self.b):
            self.give(p)
        top = self.run_in(survival.map_end, "map1", {self.a: 12, self.b: 30})
        self.assertEqual([(t["player"], t["reward"]) for t in top], [(self.b, 15), (self.a, 10)])
        self.assertEqual(self.run_in(survival.map_end, "map1", {self.a: 99}), [])
        self.assertEqual(self.state(self.b)["tokens"], 15)


if __name__ == "__main__":
    unittest.main()
