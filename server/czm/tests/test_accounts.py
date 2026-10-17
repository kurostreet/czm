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
        env = patch.dict(os.environ, {"CZM_DATA_DIR": folder.name, "CZM_SMTP_HOST": "", "CZM_SMTP_PASSWORD": ""})
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


if __name__ == "__main__":
    unittest.main()
