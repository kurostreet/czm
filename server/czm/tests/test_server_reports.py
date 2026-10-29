"""Unique server complaints, owner-only bot commands and reversible endpoint bans."""
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from czm import accounts, api, bot, db, lobbies, server_moderation as servers, service, social
from czm.config import get_settings

A = "203.0.113.5:27015"
B = "203.0.113.5:27016"


class ServerReportsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        env = patch.dict(os.environ, {"CZM_DATA_DIR": temp.name, "CZM_BOT_OWNER_IDS": "42",
                                     "CZM_PLAY_SERVICE_ACCOUNT_FILE": "/nonexistent"})
        env.start(); self.addCleanup(env.stop)
        get_settings.cache_clear(); self.addCleanup(get_settings.cache_clear)
        for value in vars(api).values():
            if isinstance(value, api._Limiter): value.calls.clear()
        db.init()
        self.keys = []; self.ids = []
        with db.db() as c:
            for i in range(4):
                key = "server-report-legacy-%02d" % i
                service.hello(c, key, "server-report-device-%d" % i, "Tester", "", "ru", "test")
                user = accounts.register(c, key, "SrvTester%d" % i, "Password123", "Password123", "ip%d" % i)
                self.keys.append(user["token"]); self.ids.append(user["profile"]["id"])
                c.execute("UPDATE accounts SET email=? WHERE player=?", (f"server-tester-{i}@example.com",self.ids[-1]))
            service.hello(c, "server-report-guest-key", "guest", "Guest", "", "ru", "test")
        app = FastAPI(); app.include_router(api.router)
        self.client = TestClient(app); self.addCleanup(self.client.close)

    def report(self, index=0, address=A, **fields):
        self._n = getattr(self, "_n", 0) + 1
        return self.client.post("/api/v1/servers/report", headers={"X-CZM-Key": self.keys[index]},
                                json={"server": address, "name": "^1Test <server>", "reason": "hate",
                                      "nonce": "server-report-request-%04d" % self._n, **fields})

    def info(self, address=A):
        with db.db() as c: return servers.info(c, address)

    def test_total_and_distinct_authors_are_visible_without_automatic_ban(self):
        for i in range(4): self.assertEqual(self.report(i).status_code, 200)
        self.assertTrue(self.report(nonce="server-report-request-0001").json()["duplicate"])
        self.assertEqual(self.info()["count"], 4)
        self.assertEqual(self.info()["reporters"], 4)
        self.assertEqual(self.report().json()["error"], "server_report_cooldown")
        self.assertEqual(self.info()["count"], 4)
        self.assertEqual(self.info()["reporters"], 4)
        self.assertFalse(self.info()["blocked"])
        self.assertEqual(self.client.get("/api/v1/servers/policy").json(), {"blocked": []})

    def test_multiple_reasons_and_own_reason_reach_bot_and_retry_is_order_independent(self):
        self.assertEqual(self.report(reasons=["spam","hate"],comment="Своя причина <проверить>").status_code,200)
        self.assertTrue(self.report(reasons=["hate","spam"],comment="Своя причина <проверить>",
                                   nonce="server-report-request-0001").json()["duplicate"])
        with db.db() as c:
            card=servers.pending(c,42)[0]
            self.assertEqual(card["reason"],"hate,spam")
            text=bot.server_report_text(card)
            self.assertIn("Нацизм / ненависть; Спам / обман",text)
            self.assertIn("Своя причина: Своя причина &lt;проверить&gt;",text)
        self.assertEqual(self.report(1,B,reasons=[],comment="Моя причина").status_code,200)
        self.assertEqual(self.report(2,B,reasons=[]).status_code,400)
        self.assertEqual(self.report(2,B,reasons=["other"]).status_code,400)
        self.assertEqual(self.report(2,B,reasons=["made-up"]).status_code,400)

    def test_repeat_and_same_phone_accounts_stay_visible_to_owner(self):
        self.report()
        with db.db() as c:
            device = c.execute("SELECT device_hash FROM players WHERE id=?", (self.ids[0],)).fetchone()[0]
            c.execute("UPDATE players SET device_hash=? WHERE id=?", (device, self.ids[1]))
        self.assertFalse(self.report(1).json()["duplicate"])
        self.assertEqual(self.info()["count"], 2)
        self.assertEqual(self.info()["reporters"], 2)

    def test_only_authenticated_accounts_and_valid_endpoints(self):
        for key in ("", "invalid", "server-report-guest-key"):
            response = self.client.post("/api/v1/servers/report", headers={"X-CZM-Key": key},
                                        json={"server": A, "nonce": "server-report-guest-test"})
            self.assertIn(response.status_code, (401, 403))
        for address in ("example.com:27015", "999.1.1.1:2", "203.0.113.5:0", "203.0.113.5:65536", A + ";quit"):
            self.assertEqual(self.report(address=address).status_code, 400, address)
        self.assertEqual(self.report(reason="made-up").status_code, 400)
        self.assertEqual(self.report(comment="x" * 501).status_code, 422)
        self.assertEqual(self.info()["count"], 0)

    def test_rate_limit_and_duplicate_retry(self):
        for port in range(27015, 27035): self.assertEqual(self.report(address=f"203.0.113.5:{port}").status_code, 200)
        self.assertEqual(self.report(address="203.0.113.5:27035").status_code, 429)
        self.assertTrue(self.report(nonce="server-report-request-0001").json()["duplicate"])

    def test_banned_account_cannot_keep_sending_new_complaints(self):
        self.report()
        with db.db() as c: service.ban(c,self.ids[0],"week","Спам жалобами")
        self.assertEqual(self.report(address=B).json()["error"],"banned")
        self.assertTrue(self.report(nonce="server-report-request-0001").json()["duplicate"])

    def test_verified_email_is_required_and_cannot_bypass_cooldown_by_changing_accounts(self):
        with db.db() as c: c.execute("UPDATE accounts SET email=NULL WHERE player=?",(self.ids[0],))
        self.assertEqual(self.report(email="forged@example.com").json()["error"],"email_required")
        with db.db() as c: c.execute("UPDATE accounts SET email='shared-server-test@example.com' WHERE player=?",(self.ids[0],))
        self.assertEqual(self.report().status_code,200)
        with db.db() as c:
            c.execute("UPDATE accounts SET email=NULL WHERE player=?",(self.ids[0],))
            c.execute("UPDATE accounts SET email='shared-server-test@example.com' WHERE player=?",(self.ids[1],))
        self.assertEqual(self.report(1).json()["error"],"server_report_cooldown")
        self.assertEqual(self.report(1,B).status_code,200)
        with db.db() as c:
            row=c.execute("SELECT * FROM server_reports ORDER BY id LIMIT 1").fetchone()
            self.assertEqual(len(row["email_hash"]),64)
            self.assertNotIn("@",row["email_hash"])
            self.assertNotIn("shared-server-test",str(dict(row)))
            changed=servers.pending(c,42)[-1]
            self.assertEqual((changed["reporter"],changed["author_count"],changed["author_servers"]),(self.ids[1],2,2))

    def test_email_fingerprint_expires_without_losing_report_or_author_history(self):
        self.report()
        with patch("czm.server_moderation.now",return_value=db.now()+servers.REPORT_COOLDOWN):
            with db.db() as c:
                servers.cleanup(c)
                self.assertEqual(c.execute("SELECT email_hash FROM server_reports").fetchone()[0],"")
                self.assertEqual(servers.info(c,A)["count"],1)

    def test_ban_is_specific_to_port_and_unban_preserves_counts_and_cooldown(self):
        self.report(); self.report(1)
        with db.db() as c:
            result = servers.set_blocked(c, A, True, "telegram:42", "Проверено")
            self.assertTrue(result["changed"])
            self.assertFalse(servers.set_blocked(c, A, True, "telegram:42", "Повтор")["changed"])
            self.assertEqual(servers.policy(c), {"blocked": [A]})
            servers.require_allowed(c, B)
            with self.assertRaises(accounts.AuthError): servers.require_allowed(c, A)
        # Public policy contains endpoints only, never counts, comments or identities.
        self.assertEqual(self.client.get("/api/v1/servers/policy").json(), {"blocked": [A]})
        with db.db() as c:
            self.assertTrue(servers.set_blocked(c, A, False, "telegram:42")["changed"])
            self.assertFalse(servers.set_blocked(c, A, False, "telegram:42")["changed"])
            self.assertEqual(servers.info(c, A)["count"], 2)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM server_reports").fetchone()[0], 2)
            self.assertEqual(c.execute("SELECT action FROM server_moderation_log ORDER BY id").fetchall()[0][0], "ban")
            self.assertEqual(c.execute("SELECT COUNT(*) FROM server_moderation_log").fetchone()[0], 2)
        self.assertEqual(self.report().json()["error"], "server_report_cooldown")
        # Exactly 30 days after the original complaint, another may be submitted.
        with patch("czm.server_moderation.now", return_value=db.now() + servers.REPORT_COOLDOWN):
            self.assertFalse(self.report().json()["duplicate"])
        self.assertEqual(self.info()["count"], 3)

    def test_cooldown_spans_review_rounds_has_exact_boundary_and_never_recounts_retries(self):
        start = db.now()
        with patch("czm.server_moderation.now", return_value=start): self.assertEqual(self.report().status_code, 200)
        with patch("czm.server_moderation.now", return_value=start + servers.REPORT_COOLDOWN - 1):
            self.assertEqual(self.report().status_code, 429)
            self.assertTrue(self.report(nonce="server-report-request-0001").json()["duplicate"])
            self.assertEqual(self.report(address=B).status_code, 200)
            self.assertEqual(self.report(address=B, nonce="server-report-request-0001").status_code, 409)
        with patch("czm.server_moderation.now", return_value=start + servers.REPORT_COOLDOWN):
            self.assertEqual(self.report().status_code, 200)
        self.assertEqual(self.info()["count"], 2)
        self.assertEqual(self.info()["reporters"], 1)

    def test_author_history_counts_reports_and_different_servers_without_secrets(self):
        self.report(0); self.report(0, B); self.report(1)
        with db.db() as c:
            cards = servers.pending(c, 42)
            first, second, third = cards
            self.assertEqual((first["count"], first["reporters"], first["reporter"]), (1, 1, self.ids[0]))
            self.assertEqual((second["author_count"], second["author_servers"], second["reporter_nick"]), (2, 2, "Tester"))
            self.assertEqual((third["count"], third["reporters"], third["reporter"]), (2, 2, self.ids[1]))
            self.assertEqual((third["author_count"], third["author_servers"]), (1, 1))
            for card in cards:
                text = bot.server_report_text(card)
                self.assertIn("От:", text)
                self.assertIn("От автора:", text)
                self.assertLess(len(text), 500)
                for key in self.keys: self.assertNotIn(key, text)

    def test_ipv6_normalization_and_no_hostname_resolution(self):
        with db.db() as c:
            servers.set_blocked(c, "[2001:0db8:0:0:0:0:0:1]:27015", True, "telegram:42", "Проверено")
            self.assertTrue(servers.info(c, "[2001:db8::1]:27015")["blocked"])
            with self.assertRaises(accounts.AuthError): servers.set_blocked(c, "example.com:27015", True, "x", "x")

    def test_list_order_pagination_and_pending_delivery_are_per_owner(self):
        self.report(0, B); self.report(0); self.report(1)
        with db.db() as c:
            self.assertEqual([s["count"] for s in servers.listing(c)["servers"]], [2, 1])
            pending = servers.pending(c, 42); self.assertEqual(len(pending), 3)
            item = [s for s in pending if s["server"] == A][-1]
            servers.delivered(c, item["id"], 42, item["last_report"])
            self.assertEqual(len(servers.pending(c, 42)), 1)
            self.assertEqual(len(servers.pending(c, 43)), 3)
        self.report(2)
        with db.db() as c:
            self.assertEqual(next(s for s in servers.pending(c, 42) if s["server"] == A)["count"], 3)
            for port in range(10000, 10030): servers.set_blocked(c, f"203.0.113.6:{port}", True, "x", "Проверено")
            first = servers.listing(c); second = servers.listing(c, 1)
            self.assertEqual(len(first["servers"]), 25); self.assertTrue(first["more"])
            self.assertFalse({x["server"] for x in first["servers"]} & {x["server"] for x in second["servers"]})

    def test_blocked_servers_cannot_be_invited_or_used_by_lobbies(self):
        with db.db() as c:
            room = lobbies.create(c, self.keys[0], "Test room", "", "public", 2, A, "gs", "server-report-room-01")["lobby"]
            lobbies.join(c, self.keys[1], room["id"])
            lobbies.ready(c, self.keys[1], room["id"], room["revision"], True)
            snapshot = lobbies.launch_snapshot(c, self.keys[0], room["id"], "server-report-launch-01", room["revision"])
            servers.set_blocked(c, A, True, "telegram:42", "Проверено")
        for operation in (
            lambda c: social.invite(c, self.keys[0], self.ids[1], A, "gs", "x", "server-report-invite-01"),
            lambda c: lobbies.create(c, self.keys[2], "Other room", "", "public", 2, A, "gs", "server-report-room-02"),
            lambda c: lobbies.change_server(c, self.keys[0], room["id"], A, "gs"),
            lambda c: lobbies.launch_snapshot(c, self.keys[0], room["id"], "server-report-launch-01", room["revision"]),
            lambda c: lobbies.commit_launch_snapshot(c, self.keys[0], room["id"], "server-report-launch-01", room["revision"], snapshot),
        ):
            with db.db() as c:
                with self.assertRaises(accounts.AuthError) as error: operation(c)
                self.assertEqual(error.exception.code, "server_blocked")
        # Another port stays usable and preserves the room's membership.
        with db.db() as c:
            self.assertEqual(lobbies.change_server(c, self.keys[0], room["id"], B, "gs")["lobby"]["server"], B)

    def test_account_deletion_preserves_only_the_moderation_record(self):
        self.report()
        with db.db() as c:
            accounts.delete_account(c, self.keys[0], "Password123", "test-ip")
            self.assertEqual(c.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertIsNone(c.execute("SELECT id FROM players WHERE id=?", (self.ids[0],)).fetchone())
            self.assertEqual(servers.info(c, A)["count"], 1)

    def hidden_request(self, actor=0, method="GET", **body):
        return self.client.request(method,"/api/v1/servers/hidden",headers={"X-CZM-Key":self.keys[actor]},
                                   **({"json":body} if method=="POST" else {}))

    def test_report_hides_server_only_for_reporter_and_switch_and_removal_preserve_complaint(self):
        response=self.report()
        self.assertEqual(response.json()["hidden"][0]["server"],A)
        self.assertEqual(response.json()["hidden"][0]["enabled"],1)
        self.assertEqual(self.hidden_request(1).json(),{"hidden":[]})
        self.assertEqual(self.hidden_request(method="POST",server=A,enabled=False).json()["hidden"][0]["enabled"],0)
        self.assertEqual(self.hidden_request(method="POST",server=A,enabled=True).json()["hidden"][0]["enabled"],1)
        self.assertEqual(self.hidden_request(1,method="POST",server=A,remove=True).json(),{"ok":True,"hidden":[]})
        self.assertEqual(len(self.hidden_request().json()["hidden"]),1)
        self.assertEqual(self.hidden_request(method="POST",server=A,remove=True).json(),{"ok":True,"hidden":[]})
        self.assertEqual(self.info()["count"],1)
        self.assertEqual(self.report().json()["error"],"server_report_cooldown")
        retry=self.report(nonce="server-report-request-0001").json()
        self.assertTrue(retry["duplicate"]);self.assertEqual(retry["hidden"],[])

    def test_personal_switch_cannot_lift_global_moderation_and_preferences_follow_account(self):
        self.report()
        self.hidden_request(method="POST",server=A,enabled=False)
        with db.db() as c:
            servers.set_blocked(c,A,True,"telegram:42","Проверено")
            signed=accounts.login(c,"SrvTester0","Password123","other-device-ip")
        fresh=self.client.get("/api/v1/servers/hidden",headers={"X-CZM-Key":signed["token"]})
        self.assertEqual(fresh.json()["hidden"][0]["enabled"],0)
        self.assertEqual(fresh.json()["hidden"][0]["restricted"],1)
        self.hidden_request(method="POST",server=A,remove=True)
        self.assertTrue(self.info()["blocked"])
        self.assertEqual(self.client.get("/api/v1/servers/policy").json(),{"blocked":[A]})

    def test_private_list_needs_auth_and_is_deleted_with_account_only(self):
        self.report(0,A);self.report(1,B)
        for key in ("","server-report-guest-key"):
            self.assertIn(self.client.get("/api/v1/servers/hidden",headers={"X-CZM-Key":key}).status_code,(401,403))
        with db.db() as c:
            accounts.delete_account(c,self.keys[0],"Password123","test-ip")
            self.assertEqual(c.execute("SELECT COUNT(*) FROM server_hidden WHERE player=?",(self.ids[0],)).fetchone()[0],0)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM server_hidden WHERE player=?",(self.ids[1],)).fetchone()[0],1)
            self.assertEqual(c.execute("PRAGMA foreign_key_check").fetchall(),[])


class FakeMessage:
    def __init__(self, user=42, chat="private"):
        self.from_user = SimpleNamespace(id=user); self.chat = SimpleNamespace(type=chat); self.answers = []
    async def answer(self, text, **kwargs): self.answers.append(text)


class ServerBotTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        env = patch.dict(os.environ, {"CZM_DATA_DIR": temp.name, "CZM_BOT_OWNER_IDS": "42", "CZM_PLAY_SERVICE_ACCOUNT_FILE": "/nonexistent"})
        env.start(); self.addCleanup(env.stop); get_settings.cache_clear(); self.addCleanup(get_settings.cache_clear)
        db.init(); self.sender = SimpleNamespace(send_message=AsyncMock())
        self.owner = bot.OwnerBot(self.sender, get_settings())

    async def send(self, method, args=None, user=42, chat="private"):
        message = FakeMessage(user, chat)
        await getattr(self.owner, method)(message, SimpleNamespace(args=args))
        return message.answers

    async def test_commands_are_owner_only_and_private(self):
        for command, args in (("on_server_reports", ""), ("on_server", A),
                              ("on_server_ban", A + " reason"), ("on_server_unban", A)):
            self.assertEqual(await self.send(command, args, 7), [])
            self.assertEqual(await self.send(command, args, 42, "group"), [])
        with db.db() as c: self.assertEqual(servers.policy(c), {"blocked": []})

    async def test_compact_read_ban_and_unban_commands(self):
        self.assertIn("Жалоб на серверы нет", (await self.send("on_server_reports"))[0])
        self.assertIn("Жалоб: <b>0</b>", (await self.send("on_server", A))[0])
        self.assertIn("/server_ban", (await self.send("on_server_ban", A))[0])
        self.assertIn("заблокирован", (await self.send("on_server_ban", A + " Проверено"))[0])
        self.assertIn("Причина блокировки: Проверено", (await self.send("on_server", A))[0])
        self.assertIn(A, (await self.send("on_server_reports"))[0])
        self.assertIn("разблокирован", (await self.send("on_server_unban", A))[0])
        self.assertIn("/server ", (await self.send("on_server", "bad"))[0])

    async def test_notifications_are_short_escaped_and_retried(self):
        with db.db() as c:
            row = servers._case(c, A, "<b>untrusted</b>")
            c.execute("INSERT INTO server_reports(server_id,epoch,reporter,nonce,reason,comment,created) VALUES(?,1,1,'first-report-nonce','other','Проверить <сервер>',1)", (row["id"],))
        await self.owner.notify_server_reports()
        self.sender.send_message.assert_awaited_once()
        text = self.sender.send_message.await_args.args[1]
        self.assertEqual(len(text.splitlines()), 6)
        self.assertIn("&lt;b&gt;untrusted&lt;/b&gt;", text)
        self.assertIn("Жалоб: <b>1</b>", text)
        self.assertIn("Своя причина: Проверить &lt;сервер&gt;",text)
        await self.owner.notify_server_reports()
        self.sender.send_message.assert_awaited_once()
        with db.db() as c:
            c.execute("INSERT INTO server_reports(server_id,epoch,reporter,nonce,reason,created) VALUES(?,1,2,'second-report-nonce','other',1)", (row["id"],))
        from aiogram.exceptions import TelegramNetworkError
        self.sender.send_message.side_effect = TelegramNetworkError(method=None, message="offline")
        await self.owner.notify_server_reports()
        with db.db() as c: self.assertEqual(servers.pending(c, 42)[0]["count"], 2)
        self.sender.send_message.side_effect = None
        await self.owner.notify_server_reports()
        with db.db() as c: self.assertEqual(servers.pending(c, 42), [])


if __name__ == "__main__": unittest.main()
