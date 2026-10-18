import os
import tempfile
import unittest
from contextlib import ExitStack, contextmanager
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from czm import accounts, api, db, service
from czm.config import get_settings


class AccountTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        env = patch.dict(os.environ, {"CZM_DATA_DIR": folder.name, "CZM_SMTP_HOST": "", "CZM_SMTP_PASSWORD": "", "CZM_RESEND_KEY": ""})
        env.start(); self.addCleanup(env.stop)
        get_settings.cache_clear(); self.addCleanup(get_settings.cache_clear)
        db.init()
        app = FastAPI(); app.include_router(api.router)
        self.client = TestClient(app); self.addCleanup(self.client.close)
        self.key = "legacy-profile-secret-123456789"
        with db.db() as conn:
            self.player = service.hello(conn, self.key, "device", "OldName", "3", "ru", "old")["id"]
            conn.execute("INSERT INTO messages(player,room,text,created) VALUES(?,?,?,?)", (self.player, "global", "old message", 1))

    def post(self, action, token=None, **fields):
        return self.client.post("/api/v1/auth/" + action, json=fields, headers={"X-CZM-Key": token or self.key})

    def register(self, name="Kuro"):
        r = self.post("register", nick=name, password="Password123", repeat="Password123")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.headers["cache-control"], "no-store")
        return r.json()["token"]

    @contextmanager
    def mail(self):
        sent = []
        with ExitStack() as stack:
            for name, value in {"smtp_host": "smtp.example.com", "smtp_user": "user",
                                "smtp_password": "secret", "smtp_from": "sender@example.com"}.items():
                stack.enter_context(patch.object(get_settings(), name, value))
            stack.enter_context(patch.object(accounts, "send_code", side_effect=lambda address, code, purpose: sent.append((address, code, purpose))))
            yield sent

    def verified_email(self, address="test@example.com"):
        token = self.register()
        with db.db() as conn:
            conn.execute("UPDATE accounts SET email=? WHERE player=?", (address, self.player))
        return token

    def test_migration_preserves_profile_photo_history_and_bans(self):
        cfg = get_settings(); cfg.avatar_dir.mkdir(); (cfg.avatar_dir / f"{self.player}.png").write_bytes(b"photo")
        with db.db() as conn:
            service.set_photo(conn, self.player); service.ban(conn, self.player, "week", "reason")
        token = self.register()
        info = self.post("me", token).json()
        self.assertEqual((info["id"], info["nick"], info["avatar"]), (self.player, "OldName", "photo:1"))
        with db.db() as conn:
            self.assertEqual(conn.execute("SELECT player FROM messages").fetchone()[0], self.player)
            self.assertIsNotNone(service.active_ban(conn, service.player_by_key(conn, token)))
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM players").fetchone()[0], 1)
        self.assertEqual((cfg.avatar_dir / f"{self.player}.png").read_bytes(), b"photo")

    def test_legacy_secret_and_forged_session_cannot_reclaim_registered_profile(self):
        token = self.register()
        for key in (self.key, "czms1_" + "x" * 43):
            self.assertEqual(self.client.post("/api/v1/hello", json={"key": key}).status_code, 401)
            self.assertEqual(self.client.get("/api/v1/chat/global", headers={"X-CZM-Key": key}).status_code, 401)
        self.assertEqual(self.client.get("/api/v1/chat/global", headers={"X-CZM-Key": token}).status_code, 200)

    def test_account_deletion_needs_the_password_and_removes_the_profile(self):
        cfg = get_settings(); cfg.avatar_dir.mkdir(); (cfg.avatar_dir / f"{self.player}.png").write_bytes(b"photo")
        token = self.register()
        friend_key = "friend-profile-secret-123456789"
        with db.db() as conn:
            service.set_photo(conn, self.player)
            friend = service.hello(conn, friend_key, "device-2", "Friend", "1", "ru", "1")["id"]
            conn.execute("INSERT INTO accounts(player,login,nick_key,password_hash,created) VALUES(?,?,?,?,?)",
                         (friend, "Friend", "friend", "x", 1))
            conn.execute("INSERT INTO social_follows(source,target,created) VALUES(?,?,1)", (friend, self.player))
            dialog = conn.execute("INSERT INTO private_dialogs(low,high) VALUES(?,?)", tuple(sorted((friend, self.player)))).lastrowid
            conn.execute("INSERT INTO private_messages(dialog,sender,text,created,nonce) VALUES(?,?,?,?,?)", (dialog, friend, "hi", 1, "n"))
            conn.execute("INSERT INTO player_settings VALUES(?,?,?,?)", (self.player, 1, "{}", 1))
            service.ban(conn, self.player, "week", "reason")
        self.assertEqual(self.post("delete-account", token, password="WrongPassword1").status_code, 401)
        self.assertEqual(self.post("delete-account", self.key, password="Password123").status_code, 401)  # a session is required
        r = self.post("delete-account", token, password="Password123")
        self.assertEqual(r.status_code, 200, r.text)
        with db.db() as conn:
            for table, column in (("players", "id"), ("accounts", "player"), ("messages", "player"), ("player_settings", "player"),
                                  ("account_sessions", "player")):
                self.assertIsNone(conn.execute(f"SELECT 1 FROM {table} WHERE {column}=?", (self.player,)).fetchone(), table)
            self.assertIsNone(conn.execute("SELECT 1 FROM social_follows WHERE target=?", (self.player,)).fetchone())
            self.assertIsNone(conn.execute("SELECT 1 FROM private_messages").fetchone())
            self.assertIsNotNone(conn.execute("SELECT 1 FROM players WHERE id=?", (friend,)).fetchone())
            self.assertIsNotNone(conn.execute("SELECT 1 FROM bans WHERE player=?", (self.player,)).fetchone())
        self.assertFalse((cfg.avatar_dir / f"{self.player}.png").exists())
        self.assertEqual(self.post("me", token).status_code, 401)

    def test_login_casefold_unicode_and_logout_sessions(self):
        first = self.register("Ｋuro")
        second = self.post("login", nick="kURO", password="Password123").json()["token"]
        self.assertNotEqual(first, second)
        self.assertEqual(self.post("me", second).json()["id"], self.player)
        self.assertEqual(self.post("logout", first).status_code, 200)
        self.assertEqual(self.post("me", first).status_code, 401)
        self.assertEqual(self.post("me", second).status_code, 200)
        third = self.post("login", nick="kuro", password="Password123").json()["token"]
        self.assertEqual(self.post("logout-all", second).status_code, 200)
        self.assertEqual(self.post("me", third).status_code, 401)

    def test_guest_with_same_nick_cannot_claim_or_change_account(self):
        token = self.register()
        other = "different-secret-key-123456789"
        with db.db() as conn:
            guest = service.hello(conn, other, "device", "Kuro", "", "en", "old")
            self.assertNotEqual(guest["id"], self.player)
        r = self.post("register", other, nick="KURO", password="AnotherPassword", repeat="AnotherPassword")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(self.post("me", token).json()["nick"], "OldName")

    def test_limits_persist_across_failures_and_api_instances(self):
        self.register()
        for _ in range(12):
            self.assertEqual(self.post("login", nick="Kuro", password="WrongPassword").status_code, 401)
        self.assertEqual(self.post("login", nick="Kuro", password="Password123").status_code, 429)
        with db.db() as conn:
            self.assertGreater(conn.execute("SELECT count FROM auth_limits ORDER BY count DESC").fetchone()[0], 0)

    def test_password_storage_salted_and_no_raw_tokens(self):
        token = self.register()
        with db.db() as conn:
            stored = conn.execute("SELECT password_hash FROM accounts").fetchone()[0]
            self.assertNotIn("Password123", stored); self.assertTrue(stored.startswith("scrypt1$"))
            self.assertNotEqual(stored, accounts.password_hash("Password123"))
            self.assertNotEqual(conn.execute("SELECT token_hash FROM account_sessions").fetchone()[0], token)

    def test_expired_session_does_not_create_new_profile(self):
        token = self.register()
        with db.db() as conn:
            conn.execute("UPDATE account_sessions SET expires=1")
        self.assertEqual(self.post("me", token).status_code, 401)
        self.assertEqual(self.client.post("/api/v1/hello", json={"key": token}).status_code, 401)
        with db.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM players").fetchone()[0], 1)

    def test_session_hello_updates_same_id_and_keeps_unavailable_photo(self):
        cfg = get_settings(); cfg.avatar_dir.mkdir(); (cfg.avatar_dir / f"{self.player}.png").write_bytes(b"photo")
        with db.db() as conn:
            service.set_photo(conn, self.player)
        token = self.register()
        result = self.client.post("/api/v1/hello", json={"key": token, "nick": "NewGameNick", "avatar": "", "keep_avatar": True})
        self.assertEqual(result.status_code, 200)
        self.assertEqual((result.json()["id"], result.json()["avatar"]), (self.player, "photo:1"))
        self.assertEqual(self.post("me", token).json()["nick"], "NewGameNick")
        self.assertEqual(self.post("login", nick="Kuro", password="Password123").status_code, 200)

    def test_idle_expiry_and_bad_password_validation(self):
        with self.assertRaises(accounts.AuthError):
            accounts.valid_password("bad\ud800password")
        self.assertEqual(self.post("register", nick="Kuro", password="short", repeat="short").status_code, 400)
        self.assertEqual(self.post("register", nick="Kuro", password="Password123", repeat="other").status_code, 400)
        token = self.register()
        with db.db() as conn:
            conn.execute("UPDATE account_sessions SET seen=?", (db.now()-accounts.SESSION_IDLE-1,))
        self.assertEqual(self.post("me", token).status_code, 401)

    def test_optional_mail_is_honest_when_sender_missing(self):
        token = self.register()
        self.assertFalse(self.post("me", token).json()["mail_ready"])
        self.assertEqual(self.post("email", token, email="test@example.com").json()["error"], "mail_unavailable")
        self.assertEqual(self.post("recover", nick="Kuro").status_code, 503)
        self.assertEqual(self.post("email-login", email="test@example.com").status_code, 503)
        self.assertEqual(self.post("email-login", email="unknown@example.com").status_code, 503)
        with db.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM auth_codes").fetchone()[0], 0)

    def test_email_code_signin_keeps_identity_password_and_existing_session(self):
        token = self.register()
        with self.mail() as sent:
            # An unconfirmed address cannot be used for sign-in.
            self.assertEqual(self.post("email", token, email="Test@example.com").status_code, 200)
            binding_code = sent[-1][1]
            self.assertEqual(self.post("email-login", email="test@example.com").json(), {"ok": True})
            self.assertEqual(len(sent), 1)
            self.assertEqual(self.post("email-confirm", token, code=binding_code).status_code, 200)
            known = self.post("email-login", email=" TEST@example.com ")
            unknown = self.post("email-login", email="unknown@example.com")
            self.assertEqual((known.status_code, known.json()), (unknown.status_code, unknown.json()))
            self.assertEqual(known.json(), {"ok": True})
            self.assertEqual(known.headers["cache-control"], "no-store")
            address, code, purpose = sent[-1]
            self.assertEqual((address, purpose), ("test@example.com", "login"))
            self.assertRegex(code, r"^\d{6}$")
            self.assertNotIn(code, known.text)
            with db.db() as conn:
                self.assertNotEqual(conn.execute("SELECT code_hash FROM auth_codes WHERE purpose='login'").fetchone()[0], code)
            result = self.post("email-login-confirm", email=address, code=code)
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(result.json()["profile"]["id"], self.player)
            self.assertNotEqual(result.json()["token"], token)
            self.assertEqual(self.post("me", token).status_code, 200)
            self.assertEqual(self.post("email-login-confirm", email=address, code=code).status_code, 400)
            self.assertEqual(self.post("login", nick="Kuro", password="Password123").status_code, 200)
            with db.db() as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM players").fetchone()[0], 1)

    def test_email_signin_wrong_purpose_expiry_and_attempt_limit(self):
        token = self.verified_email()
        with self.mail() as sent:
            self.post("recover", nick="Kuro")
            self.assertEqual(self.post("email-login-confirm", email="test@example.com", code=sent[-1][1]).status_code, 400)
            self.post("email-login", email="test@example.com"); code = sent[-1][1]
            with db.db() as conn:
                conn.execute("UPDATE auth_codes SET expires=1 WHERE purpose='login'")
            self.assertEqual(self.post("email-login-confirm", email="test@example.com", code=code).status_code, 400)
            self.post("email-login", email="test@example.com"); code = sent[-1][1]
            for _ in range(5):
                self.assertEqual(self.post("email-login-confirm", email="test@example.com", code="wrong").status_code, 400)
            self.assertEqual(self.post("email-login-confirm", email="test@example.com", code=code).status_code, 400)
            self.assertEqual(self.post("me", token).status_code, 200)

    def test_email_change_revokes_pending_signin_and_recovery_codes(self):
        token = self.verified_email()
        with self.mail() as sent:
            self.post("email-login", email="test@example.com"); old = sent[-1][1]
            self.post("recover", nick="Kuro")
            self.post("email", token, email="new@example.com")
            self.assertEqual(self.post("email-confirm", token, code=sent[-1][1]).status_code, 200)
            self.assertEqual(self.post("email-login-confirm", email="test@example.com", code=old).status_code, 400)
            with db.db() as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM auth_codes").fetchone()[0], 0)

    def test_email_signin_delivery_failure_does_not_disclose_account(self):
        self.verified_email()
        with self.mail(), patch.object(accounts, "send_code", side_effect=accounts.AuthError("mail_unavailable", 503)):
            known = self.post("email-login", email="test@example.com")
            unknown = self.post("email-login", email="unknown@example.com")
            self.assertEqual((known.status_code, known.json()), (200, {"ok": True}))
            self.assertEqual((known.status_code, known.json()), (unknown.status_code, unknown.json()))

    def test_email_signin_request_limit_applies_to_unknown_addresses(self):
        with self.mail() as sent:
            for _ in range(3):
                self.assertEqual(self.post("email-login", email="unknown@example.com").status_code, 200)
            self.assertEqual(self.post("email-login", email="unknown@example.com").status_code, 429)
            self.assertEqual(sent, [])

    def test_verified_mail_reset_is_one_use_and_revokes_all_sessions(self):
        token = self.register(); sent = []
        with patch.object(get_settings(), "smtp_host", "smtp.example.com"), patch.object(get_settings(), "smtp_user", "user"), \
             patch.object(get_settings(), "smtp_password", "secret"), patch.object(get_settings(), "smtp_from", "sender@example.com"), \
             patch.object(accounts, "send_code", side_effect=lambda address, code, purpose: sent.append((address, code, purpose))):
            self.assertEqual(self.post("email", token, email="Test@example.com").status_code, 200)
            self.assertEqual(self.post("me", token).json()["email"], "")
            code = sent[-1][1]
            self.assertEqual(self.post("email-confirm", token, code=code).json()["email"], "test@example.com")
            self.assertEqual(self.post("email-confirm", token, code=code).status_code, 400)
            self.assertEqual(self.post("recover", nick="Kuro").status_code, 200)
            code = sent[-1][1]
            with db.db() as conn:
                self.assertNotEqual(conn.execute("SELECT code_hash FROM auth_codes").fetchone()[0], code)
            self.assertEqual(self.post("reset", nick="Kuro", code=code, password="NewPassword123", repeat="NewPassword123").status_code, 200)
            self.assertEqual(self.post("me", token).status_code, 401)
            self.assertEqual(self.post("reset", nick="Kuro", code=code, password="NewPassword123", repeat="NewPassword123").status_code, 400)
            self.assertEqual(self.post("login", nick="Kuro", password="Password123").status_code, 401)
            self.assertEqual(self.post("login", nick="Kuro", password="NewPassword123").json()["profile"]["id"], self.player)

    def test_code_bruteforce_attempts_commit(self):
        token = self.register()
        with db.db() as conn:
            conn.execute("INSERT INTO auth_codes VALUES (?,?,?,?,?,0)", (self.player, "email", "a@b.com", service.hash_secret(f"{self.player}:email:123456"), db.now()+600))
        for _ in range(5):
            self.assertEqual(self.post("email-confirm", token, code="wrong").status_code, 400)
        self.assertEqual(self.post("email-confirm", token, code="123456").status_code, 400)
        self.assertEqual(self.post("me", token).json()["email"], "")

    def test_idempotent_schema_and_session_cap(self):
        self.register(); db.init(); db.init()
        for _ in range(6):
            self.assertEqual(self.post("login", nick="Kuro", password="Password123").status_code, 200)
        with db.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM account_sessions").fetchone()[0], 5)


class FakeResponse:
    def __init__(self, status, body):
        self.status_code, self.body = status, body

    def json(self):
        return self.body


class MailDeliveryTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"CZM_RESEND_KEY": "", "CZM_SMTP_HOST": "", "CZM_SMTP_USER": "",
                                      "CZM_SMTP_PASSWORD": "", "CZM_SMTP_FROM": ""})
        env.start(); self.addCleanup(env.stop)
        get_settings.cache_clear(); self.addCleanup(get_settings.cache_clear)

    def configure(self, resend=False, smtp=False):
        cfg = get_settings()
        if resend:
            cfg.resend_key = "re_test_key"
        if smtp:
            cfg.smtp_host, cfg.smtp_user, cfg.smtp_password, cfg.smtp_from = "smtp.example.com", "user", "secret", "sender@example.com"
        return cfg

    def test_nothing_configured_offers_no_mail(self):
        self.assertFalse(get_settings().mail_ready)
        with self.assertRaises(accounts.AuthError) as error:
            accounts.send_code("player@example.com", "123456", "email")
        self.assertEqual(error.exception.status, 503)

    def test_resend_alone_is_enough_and_sends_the_code(self):
        cfg = self.configure(resend=True)
        self.assertTrue(cfg.mail_ready)
        calls = []
        with patch.object(accounts.httpx, "post", side_effect=lambda url, **kw: calls.append((url, kw)) or FakeResponse(200, {"id": "x"})):
            accounts.send_code("player@example.com", "042917", "login")
        url, kw = calls[0]
        self.assertEqual(url, "https://api.resend.com/emails")
        self.assertEqual(kw["headers"]["Authorization"], "Bearer re_test_key")
        mail = kw["json"]
        self.assertEqual((mail["to"], mail["from"]), (["player@example.com"], "Counter Zombie Mobile <noreply@counter-zombie.ru>"))
        self.assertIn("вход", mail["subject"])
        self.assertIn("042917", mail["text"]); self.assertIn("042917", mail["html"])

    def test_resend_refusal_falls_back_to_smtp_and_logs_no_secrets(self):
        self.configure(resend=True, smtp=True)
        smtp = []
        refusal = FakeResponse(403, {"message": "The counter-zombie.ru domain is not verified, mail player@example.com"})
        with patch.object(accounts.httpx, "post", return_value=refusal), \
             patch.object(accounts, "send_smtp", side_effect=lambda cfg, address, *rest: smtp.append(address)), \
             self.assertLogs("czm.mail", "WARNING") as logs:
            accounts.send_code("player@example.com", "111222", "email")
        self.assertEqual(smtp, ["player@example.com"])
        text = "\n".join(logs.output)
        self.assertIn("403", text); self.assertIn("not verified", text)
        self.assertNotIn("re_test_key", text); self.assertNotIn("player@example.com", text)

    def test_both_failing_reports_mail_unavailable(self):
        self.configure(resend=True, smtp=True)
        with patch.object(accounts.httpx, "post", side_effect=OSError("network")), \
             patch.object(accounts, "send_smtp", side_effect=OSError("secret dialogue")), \
             self.assertLogs("czm.mail", "WARNING") as logs:
            with self.assertRaises(accounts.AuthError) as error:
                accounts.send_code("player@example.com", "111222", "reset")
        self.assertEqual(error.exception.status, 503)
        self.assertNotIn("secret dialogue", "\n".join(logs.output))

    def test_letter_escapes_and_names_each_purpose(self):
        for purpose, word in (("email", "почты"), ("login", "вход"), ("reset", "пароля")):
            subject, text, body = accounts.mail_texts("<b>", purpose)
            self.assertIn(word, subject)
            self.assertIn("&lt;b&gt;", body); self.assertNotIn("<b>", body)


if __name__ == "__main__":
    unittest.main()
