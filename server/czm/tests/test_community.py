"""Community permissions, the ten-action guard, scoped undo and private tester uploads."""
import base64
import io
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from PIL import Image
from czm import accounts, community, db, moderation, moderator_guard, server_moderation, service
import test_moderation as baseline


class CommunityTests(unittest.TestCase):
    request = baseline.ModerationTests.request
    act = baseline.ModerationTests.act
    chat = baseline.ModerationTests.chat

    def setUp(self):
        baseline.ModerationTests.setUp(self)
        with db.db() as c:
            for i, role in enumerate(community.ROLES, 1):
                community.grant(c, self.ids[i], role, "Project CZM")

    def test_roles_are_server_assigned_and_decorations_do_not_grant_permissions(self):
        for i, role in enumerate(("support", *community.ROLES)):
            hello = self.client.post("/api/v1/hello", json={"key": self.keys[i]}).json()
            self.assertEqual(hello["role"], role)
            self.assertEqual(hello["capabilities"]["moderate"], i < 2)
            profile = self.request("GET", "social/profile/%d" % self.ids[i]).json()["profile"]
            self.assertEqual(profile["role"], role)
        self.assertEqual(self.request("GET", "moderation/summary", 1).status_code, 200)
        for i in (2, 3):
            self.assertEqual(self.request("GET", "moderation/summary", i).status_code, 403)
            self.assertEqual(self.act("ban", actor=i, minutes=60, reason="x").status_code, 403)
        self.chat(1, "Moderator message")
        row = self.request("GET", "chat/global").json()["messages"][-1]
        self.assertEqual(row["r"], "moderator")

    def test_moderator_needs_a_reason_and_cannot_damage_staff_or_avatars(self):
        self.chat(2, "message")
        with db.db() as c:
            message = c.execute("SELECT MAX(id) FROM messages").fetchone()[0]
        self.assertEqual(self.act("delete_message", target=2, actor=1, message=message).json()["error"], "reason")
        self.assertEqual(self.act("remove_avatar", target=2, actor=1, reason="x").status_code, 403)
        self.assertEqual(self.act("ban", target=0, actor=1, minutes=60, reason="x").json()["error"], "staff")
        self.assertEqual(self.act("delete_message", target=2, actor=1, message=message, reason="Spam").status_code, 200)
        with db.db() as c:
            self.assertEqual(moderator_guard.status(c, self.ids[1])["count"], 1)

    def test_ten_unreviewed_actions_pause_the_actor_even_after_relogin_and_retries(self):
        for i in range(10):
            response = self.act("warn", target=2, actor=1, reason="Reason %d" % i, nonce="guard-action-%04d" % i)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["guard"]["count"], i + 1)
        self.assertTrue(response.json()["guard"]["paused"])
        retry = self.act("warn", target=2, actor=1, reason="Reason 9", nonce="guard-action-0009")
        self.assertTrue(retry.json()["repeated"])
        refused = self.act("warn", target=2, actor=1, reason="11")
        self.assertEqual((refused.status_code, refused.json()["error"]), (403, "moderator_paused"))
        with db.db() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM warnings WHERE player=?", (self.ids[2],)).fetchone()[0], 10)
            self.assertEqual(moderator_guard.status(c, self.ids[1])["count"], 10)
            community.revoke(c, self.ids[1], "moderator")
            community.grant(c, self.ids[1], "moderator")
            self.assertTrue(moderator_guard.paused(c, self.ids[1]))
            moderator_guard.resume(c, self.ids[1], "telegram:42")
        self.assertEqual(self.act("warn", target=2, actor=1, reason="After review").json()["guard"]["count"], 1)

    def test_parallel_requests_cannot_cross_the_ten_action_boundary(self):
        def punish(i):
            return self.client.post("/api/v1/moderation/act",headers={"X-CZM-Key":self.keys[1]},
                json={"target":self.ids[2],"action":"warn","reason":"Parallel action","nonce":f"parallel-guard-{i:04d}"}).status_code
        with ThreadPoolExecutor(max_workers=8) as pool:
            statuses=list(pool.map(punish,range(16)))
        self.assertEqual(statuses.count(200),10)
        self.assertEqual(statuses.count(403),6)
        with db.db() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM warnings WHERE player=?",(self.ids[2],)).fetchone()[0],10)

    def test_deleting_a_moderators_account_does_not_escape_undo(self):
        self.chat(2,"Restore after deletion")
        with db.db() as c:message=c.execute("SELECT MAX(id) FROM messages").fetchone()[0]
        self.act("delete_message",target=2,actor=1,message=message,reason="Wrong removal")
        with db.db() as c:
            batch=moderator_guard.status(c,self.ids[1])["batch"]
            accounts.delete_account(c,self.keys[1],"Password123","test-ip")
            result=moderator_guard.undo(c,self.ids[1],batch,"telegram:42")
            self.assertGreater(result["restored"],0)
            self.assertEqual(c.execute("SELECT deleted FROM messages WHERE id=?",(message,)).fetchone()[0],0)
            self.assertEqual(c.execute("PRAGMA foreign_key_check").fetchall(),[])

    def test_batch_undo_lifts_only_this_moderators_sanctions_and_restores_messages(self):
        self.chat(2, "restore this")
        with db.db() as c:
            message = c.execute("SELECT MAX(id) FROM messages").fetchone()[0]
        self.act("ban", target=3, minutes=60, reason="Owner decision")
        self.act("delete_message", target=2, actor=1, message=message, reason="Wrong delete")
        for action in ("mute_text", "mute_voice", "ban"):
            self.assertEqual(self.act(action, target=2, actor=1, minutes=60, reason="Wrong sanction").status_code, 200)
        for i in range(6):
            self.assertEqual(self.act("warn", target=2, actor=1, reason="Wrong warning").status_code, 200)
        with db.db() as c:
            batch = moderator_guard.status(c, self.ids[1])["batch"]
            result = moderator_guard.undo(c, self.ids[1], batch, "telegram:42")
            self.assertGreater(result["restored"], 0)
            self.assertTrue(moderator_guard.paused(c, self.ids[1]))
            self.assertIsNone(service.active_ban(c, c.execute("SELECT * FROM players WHERE id=?", (self.ids[2],)).fetchone()))
            self.assertIsNotNone(service.active_ban(c, c.execute("SELECT * FROM players WHERE id=?", (self.ids[3],)).fetchone()))
            self.assertEqual(c.execute("SELECT deleted FROM messages WHERE id=?", (message,)).fetchone()[0], 0)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM warnings WHERE player=? AND seen=0", (self.ids[2],)).fetchone()[0], 0)
            self.assertTrue(moderator_guard.undo(c, self.ids[1], batch, "telegram:42")["repeated"])

    def test_undo_preserves_later_owner_decisions(self):
        self.chat(2, "still hidden")
        with db.db() as c:
            message = c.execute("SELECT MAX(id) FROM messages").fetchone()[0]
        self.act("delete_message", target=2, actor=1, message=message, reason="Moderator")
        self.act("delete_message", target=2, actor=0, message=message, reason="Owner confirms")
        with db.db() as c:
            result = moderator_guard.undo(c, self.ids[1], moderator_guard.status(c, self.ids[1])["batch"], "telegram:42")
            self.assertGreater(result["skipped"], 0)
            self.assertEqual(c.execute("SELECT deleted FROM messages WHERE id=?", (message,)).fetchone()[0], 1)

    def test_moderator_cannot_lift_owner_sanctions(self):
        self.act("mute_text", target=2, minutes=60, reason="Owner")
        with db.db() as c:
            sanction = c.execute("SELECT MAX(id) FROM bans").fetchone()[0]
        self.assertEqual(self.request("POST", f"moderation/sanctions/{sanction}/lift", 1,
            json={"nonce": "moderator-lift-owner-01"}).status_code, 403)

    def test_full_undo_can_revert_reviewed_batches_without_overriding_later_owner_decisions(self):
        self.chat(2, "message")
        with db.db() as c:
            message = c.execute("SELECT MAX(id) FROM messages").fetchone()[0]
        self.act("delete_message", target=2, actor=1, message=message, reason="First batch")
        with db.db() as c:
            moderator_guard.resume(c, self.ids[1], "telegram:42")
        self.act("mute_text", target=2, actor=1, minutes=60, reason="Second batch")
        self.act("ban", target=2, actor=0, minutes=60, reason="Later owner decision")
        with db.db() as c:
            scope = moderator_guard.reviewable(c, self.ids[1])
            self.assertEqual(scope["count"], 2)
            result = moderator_guard.undo_all(c, self.ids[1], scope["last_log"], "telegram:42")
            self.assertTrue(result["paused"])
            self.assertEqual(c.execute("SELECT deleted FROM messages WHERE id=?", (message,)).fetchone()[0], 0)
            self.assertIsNone(moderation.sanction(c, self.ids[2], "text"))
            self.assertIsNotNone(service.active_ban(c, c.execute("SELECT * FROM players WHERE id=?", (self.ids[2],)).fetchone()))
            self.assertEqual(moderator_guard.reviewable(c, self.ids[1])["count"], 0)

    def test_ticket_receipts_survive_deletion_but_private_attachments_do_not(self):
        with db.db() as c:
            ticket = community.ticket(c, self.keys[2], "Bug", "Description", "", "", "", "deletion-ticket-first-001")
            community.ticket_delivered(c, ticket["id"], 42, 1, 101)
            c.execute("DELETE FROM tester_tickets WHERE id=?", (ticket["id"],))
            self.assertEqual(community.ticket_cleanup_pending(c, 42)[0]["message"], 101)
            new = community.ticket(c, self.keys[2], "Bug", "Other", "", "", "", "deletion-ticket-second-001")
            self.assertGreater(new["id"], ticket["id"])
            community.ticket_cleanup_done(c, 42, 101)
            self.assertEqual(community.ticket_cleanup_pending(c, 42), [])

    def test_optional_telegram_link_is_public_and_cannot_escape_telegram(self):
        with db.db() as c:
            community.revoke(c, self.ids[2], "tester")
        response = self.request("POST", "community/contact", 2, json={"telegram": "@CzmTester", "player": self.ids[3]})
        self.assertEqual(response.json()["telegram"], "https://t.me/CzmTester")
        self.assertEqual(self.request("GET", "social/profile/%d" % self.ids[2]).json()["profile"]["telegram"], "https://t.me/CzmTester")
        self.assertEqual(self.request("GET", "social/profile/%d" % self.ids[3]).json()["profile"]["telegram"], "")
        for bad in ("https://example.com/tester", "https://t.me.evil/auser", "https://t.me/auser?start=x", "https://evil@t.me/auser", "https://t.me/share"):
            self.assertEqual(self.request("POST", "community/contact", 2, json={"telegram": bad}).status_code, 400)
        self.assertEqual(self.request("POST", "community/contact", 2, json={"telegram": ""}).json()["telegram"], "")

    def test_role_accounts_never_expose_a_telegram_contact(self):
        with db.db() as c:
            community.revoke(c, self.ids[2], "tester")
            community.contact(c, self.keys[2], "@CzmTester")
            community.grant(c, self.ids[2], "tester")
        for i in range(4):
            profile = self.request("GET", "social/profile/%d" % self.ids[i]).json()["profile"]
            self.assertEqual(profile["telegram"], "")
            self.assertEqual(self.request("POST", "community/contact", i, json={"telegram": "@CzmTester"}).status_code, 403)

    def test_project_owner_can_manage_only_five_public_endpoints_and_names_are_probed(self):
        with patch("czm.api.game_probe.probe", return_value={"name": "^1Project <name>"}) as probe:
            for i in range(5):
                r = self.request("POST", "community/servers", 3, json={"server": f"8.8.8.8:{27015+i}"})
                self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(self.request("POST", "community/servers", 3, json={"server": "8.8.8.8:27020"}).json()["error"], "servers_limit")
            self.assertTrue(probe.called)
        profile = self.request("GET", "social/profile/%d" % self.ids[3]).json()["profile"]
        self.assertEqual((profile["project"], len(profile["servers"])), ("Project CZM", 5))
        self.assertEqual(profile["servers"][0]["name"], "Project <name>")
        self.assertEqual(self.request("POST", "community/servers", 2, json={"server": "8.8.8.8:27015", "remove": True}).status_code, 403)
        with patch("czm.api.game_probe.probe") as probe:
            self.assertEqual(self.request("POST", "community/servers", 3, json={"server": "127.0.0.1:27015"}).status_code, 400)
            probe.assert_not_called()
        with db.db() as c:
            server_moderation.set_blocked(c, "8.8.8.8:27015", True, "owner", "Review")
        self.assertEqual(len(self.request("GET", "social/profile/%d" % self.ids[3]).json()["profile"]["servers"]), 4)

    def test_project_server_copied_addresses_are_canonical_and_removable(self):
        endpoint = "131.196.196.196:27020"
        pasted = "\u200e131.196.196.196\u00a0: 27020\u200b"
        with patch("czm.api.game_probe.probe", return_value={"name": "Fantasy Gaming"}) as probe:
            response = self.request("POST", "community/servers", 3, json={"server": pasted})
            self.assertEqual(response.status_code, 200, response.text)
            probe.assert_called_once_with(endpoint)
            self.assertEqual(response.json()["servers"][0]["server"], endpoint)
            response = self.request("POST", "community/servers", 3, json={"server": endpoint})
            self.assertEqual(len(response.json()["servers"]), 1)
        with patch("czm.api.game_probe.probe") as probe:
            response = self.request("POST", "community/servers", 3, json={"server": pasted, "remove": True})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["servers"], [])
            probe.assert_not_called()

    def test_project_server_paste_cleanup_preserves_public_ip_and_port_checks(self):
        valid = {
            "131.196.196.196:27020": "131.196.196.196:27020",
            "\ufeff131.196.196.196\u200f": "131.196.196.196:27015",
            "１３１．１９６．１９６．１９６：２７０２０": "131.196.196.196:27020",
            "[ 2606:4700:4700::1111 ] : 27015": "[2606:4700:4700::1111]:27015",
        }
        for value, expected in valid.items():
            with self.subTest(value=value):
                self.assertEqual(community.public_endpoint(value), expected)
        invalid = (
            "\u200e127.0.0.1 : 27015", "192.168.1.1:27015", "100.64.0.1:27015",
            "[ ::1 ] : 27015", "131.196.196.196:0", "131.196.196.196:65536",
            "131.196.196.196:27 020", "1 31.196.196.196:27020", "256.196.196.196:27020",
            "https://131.196.196.196:27020", "example.com:27015", "131.196.196.196:27020/path",
            "131.196.196.196:27020\n8.8.8.8:27015",
        )
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(accounts.AuthError):
                community.public_endpoint(value)
        with patch("czm.api.game_probe.probe") as probe:
            response = self.request("POST", "community/servers", 3,
                                    json={"server": "\u200e127.0.0.1 : 27015"})
            self.assertEqual((response.status_code, response.json()["error"]), (400, "server"))
            probe.assert_not_called()

    def test_project_server_keeps_the_address_when_the_probe_times_out(self):
        from czm.game_probe import ProbeError
        with patch("czm.api.game_probe.probe", side_effect=ProbeError("unavailable")):
            response = self.request("POST", "community/servers", 3,
                                    json={"server": "\u200e131.196.196.196 : 27020"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["servers"][0]["name"], "131.196.196.196:27020")

    def test_tester_ticket_accepts_only_selected_photo_and_utf8_text_and_retries_once(self):
        image = io.BytesIO(); Image.new("RGB", (16, 16), "red").save(image, format="PNG")
        body = {"subject": "Bug", "text": "Steps to reproduce", "photo": base64.b64encode(image.getvalue()).decode(),
                "text_file": base64.b64encode("Log\nстрока".encode()).decode(), "file_name": "../report.txt", "nonce": "tester-ticket-nonce-001"}
        self.assertEqual(self.request("POST", "community/tickets", 3, json=body).status_code, 403)
        response = self.request("POST", "community/tickets", 2, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(self.request("POST", "community/tickets", 2, json=body).json()["duplicate"])
        self.assertEqual(self.request("POST", "community/tickets", 2, json={**body, "text": "changed"}).status_code, 409)
        with db.db() as c:
            ticket = community.tickets_pending(c, 42)[0]
            self.assertTrue(ticket["photo"].startswith(b"\xff\xd8"))
            self.assertEqual(ticket["text_file"].decode(), "Log\nстрока")
            self.assertEqual(ticket["file_name"], "report.txt")
            community.ticket_delivered(c, ticket["id"], 42)
            self.assertEqual(community.tickets_pending(c, 42), [])
        self.assertEqual(self.request("POST", "community/tickets", 2,
            json={**body, "nonce": "tester-ticket-nonce-002", "text_file": base64.b64encode(b"\x00\xff").decode()}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
