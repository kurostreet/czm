import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit, parse_qs

from fastapi import FastAPI
from fastapi.testclient import TestClient
from czm import accounts, api, db, distribution, service
from czm.config import get_settings
from czm.assemble import remove_old_files


class DistributionTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        env = patch.dict(os.environ, {"CZM_DATA_DIR": folder.name, "CZM_BUILD_KEEP": "3"})
        env.start(); self.addCleanup(env.stop)
        get_settings.cache_clear(); self.addCleanup(get_settings.cache_clear)
        db.init(); get_settings().apk_dir.mkdir()
        api._upload_limit.calls.clear(); api._hello_limit.calls.clear()
        app = FastAPI(); app.include_router(api.router); app.include_router(api.download_router)
        self.client = TestClient(app); self.addCleanup(self.client.close)
        self.owner, self.owner_token = self.account("Owner")
        self.other, self.other_token = self.account("Other")

    def account(self, name):
        key = "distribution-legacy-" + name + "-123456789"
        with db.db() as conn:
            player = service.hello(conn, key, "", name, "1", "ru", "old")["id"]
            result = accounts.register(conn, key, name, "Password123", "Password123", "test-" + name)
        return player, result["token"]

    def release(self, code, channel):
        filename = f"test-{code}.apk"; (get_settings().apk_dir / filename).write_bytes(b"a" * 100)
        with db.db() as conn:
            return conn.execute("INSERT INTO releases(version,code,file,size,sha256,created,published,channel) VALUES(?,?,?,?,?,?,?,?)",
                (str(code), code, filename, 100, "a" * 64, 1, 1, channel)).lastrowid

    def invite(self):
        with db.db() as conn: link = distribution.issue_invite(conn)
        return link, link.rsplit("/", 1)[-1]

    def activate(self, code, token=None):
        return self.client.post("/api/v1/development/activate", json={"invite": code},
                                headers={"X-CZM-Key": token or self.owner_token})

    def test_channels_and_hello_are_private_and_public_migration_stays_pinned(self):
        self.release(100, "legacy"); migration = self.release(200, "migration"); private = self.release(300, "development")
        _, code = self.invite(); self.assertEqual(self.activate(code).status_code, 200)
        public = self.client.get("/api/v1/update").json()["update"]
        self.assertEqual(public["id"], migration); self.assertNotIn("?ticket", public["url"])
        owner = self.client.get("/api/v1/update", headers={"X-CZM-Key": self.owner_token})
        self.assertEqual(owner.headers["cache-control"], "no-store")
        info = owner.json()["update"]; self.assertEqual(info["id"], private); self.assertIn("?ticket=", info["url"])
        self.assertEqual(self.client.get("/api/v1/update", headers={"X-CZM-Key": self.other_token}).json()["update"]["id"], migration)
        hello = self.client.post("/api/v1/hello", json={"key": self.owner_token, "code": 200})
        self.assertTrue(hello.json()["distribution"]["development"])
        self.assertEqual(hello.json()["update"]["id"], private)
        with db.db() as conn:
            before = service.last_news_id(conn); service.publish_release(conn, private, "Private only")
            self.assertEqual(service.last_news_id(conn), before)

    def test_invite_requires_account_is_one_use_and_replay_does_not_grant_other_account(self):
        _, code = self.invite()
        self.assertEqual(self.activate(code, "unknown-guest-key-123456789").status_code, 401)
        self.assertEqual(self.activate(code).status_code, 200)
        self.assertTrue(self.activate(code).json()["ok"])
        self.assertEqual(self.activate(code, self.other_token).status_code, 403)
        with db.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM development_access").fetchone()[0], 1)
            self.assertIsNone(conn.execute("SELECT 1 FROM development_invites WHERE token_hash=?", (code,)).fetchone())

    def test_expired_invite_and_malformed_codes_do_not_activate(self):
        _, code = self.invite()
        with patch("czm.distribution.now", return_value=db.now() + distribution.INVITE_LIFE + 1):
            self.assertEqual(self.activate(code).status_code, 403)
        self.assertEqual(self.activate("x" * 31).status_code, 422)
        self.assertEqual(self.activate("/" * 32).status_code, 422)

    def test_downloads_enforce_migration_or_scoped_expiring_account_ticket_and_ranges(self):
        self.release(100, "legacy"); self.release(200, "migration"); self.release(300, "development")
        _, code = self.invite(); self.activate(code)
        self.assertEqual(self.client.get("/dl/test-100.apk").status_code, 403)
        self.assertEqual(self.client.get("/dl/test-300.apk").status_code, 403)
        self.assertEqual(self.client.get("/dl/test-200.apk").content, b"a" * 100)
        link = self.client.get("/api/v1/update", headers={"X-CZM-Key": self.owner_token}).json()["update"]["url"]
        target = urlsplit(link).path + "?" + urlsplit(link).query
        self.assertEqual(self.client.head(target).status_code, 200)
        part = self.client.get(target, headers={"Range": "bytes=10-19"})
        self.assertEqual(part.status_code, 206); self.assertEqual(part.content, b"a" * 10)
        self.assertEqual(self.client.get(target.replace("test-300.apk", "test-100.apk")).status_code, 403)
        self.assertEqual(self.client.get(target[:-1] + ("0" if target[-1] != "0" else "1")).status_code, 403)
        with patch("czm.distribution.now", return_value=db.now() + distribution.DOWNLOAD_LIFE + 1):
            self.assertEqual(self.client.get(target).status_code, 403)
        with db.db() as conn: conn.execute("DELETE FROM development_access WHERE player=?", (self.owner,))
        self.assertEqual(self.client.get(target).status_code, 403)

    def test_invitation_page_bootstraps_only_latest_private_apk_and_expires(self):
        self.release(100, "legacy"); self.release(200, "development")
        link, code = self.invite(); target = urlsplit(link).path
        page = self.client.get(target); self.assertEqual(page.status_code, 200)
        self.assertEqual(page.headers["cache-control"], "no-store")
        self.assertIn("frame-ancestors 'none'", page.headers["content-security-policy"])
        self.assertIn("test-200.apk", page.text)
        self.assertEqual(self.client.get("/dl/test-200.apk?invite=" + code).status_code, 200)
        self.assertEqual(self.client.get("/dl/test-100.apk?invite=" + code).status_code, 403)
        with patch("czm.distribution.now", return_value=db.now() + distribution.INVITE_LIFE + 1):
            self.assertEqual(self.client.get(target).status_code, 404)
            self.assertEqual(self.client.get("/dl/test-200.apk?invite=" + code).status_code, 403)

    def test_retention_keeps_public_migration_as_private_builds_advance(self):
        self.release(100, "migration")
        for code in range(200, 206): self.release(code, "development")
        with db.db() as conn:
            remove_old_files(conn); self.assertEqual(service.latest_release(conn)["code"], 100)
            self.assertEqual(service.latest_release(conn, channel="development")["code"], 205)
        self.assertTrue((get_settings().apk_dir / "test-100.apk").is_file())
        self.assertTrue((get_settings().apk_dir / "test-205.apk").is_file())


if __name__ == "__main__": unittest.main()
