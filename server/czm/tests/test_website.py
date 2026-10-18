import base64
import hashlib
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from czm import api, db, service, website
from czm.config import get_settings
from czm.db import now


class WebsiteTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        env = patch.dict(os.environ, {"CZM_DATA_DIR": temp.name})
        env.start()
        self.addCleanup(env.stop)
        get_settings.cache_clear()
        self.addCleanup(get_settings.cache_clear)
        api._site_stats.update(time=0.0, data=None)
        db.init()
        get_settings().apk_dir.mkdir()
        app = FastAPI()
        app.include_router(api.router)
        app.include_router(api.download_router)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def player(self, n, nick, avatar=""):
        with db.db() as conn:
            row = service.hello(conn, f"key-{n:04d}-abcdefghijklmnop", f"device-{n}", nick, avatar, "ru", "1")
            return row["id"]

    def message(self, player, room, text, deleted=0):
        with db.db() as conn:
            return conn.execute("INSERT INTO messages(room, player, text, created, deleted) VALUES (?,?,?,?,?)",
                                (room, player, text, now(), deleted)).lastrowid

    def release(self, code=7, size=415 * 1048576):
        name = f"r{code}.apk"
        (get_settings().apk_dir / name).write_bytes(b"a" * 10)
        with db.db() as conn:
            conn.execute("INSERT INTO releases(version,code,file,size,sha256,notes,created,published) VALUES (?,?,?,?,?,?,?,?)",
                         (f"1.35-{code}", code, name, 10, "a" * 64, "Новая музыка.", 1, 100 + code))

    def test_numbers_are_real_and_downloads_start_from_known_installs(self):
        a = self.player(1, "Kuro", "7")
        self.player(2, "hunter", "4")
        self.player(3, "свага")
        with db.db() as conn:
            conn.execute("INSERT INTO social_presence(owner, player, seen) VALUES ('x', ?, ?)", (a, now()))
        self.release()
        stats = self.client.get("/api/v1/site/stats").json()
        self.assertEqual((stats["online"], stats["offline"], stats["downloads"]), (1, 2, 3))
        self.assertEqual((stats["version"], stats["size_mb"]), ("1.35-7", 415))
        # a later install does not move the base: only counted downloads add up
        self.player(4, "new")
        with db.db() as conn:
            self.assertEqual(website.stats(conn)["downloads"], 3)

    def test_download_counts_once_per_address_and_day_and_head_does_not_count(self):
        self.player(1, "Kuro")
        self.release()
        name = "r7.apk"
        with db.db() as conn:
            conn.execute("UPDATE releases SET size = 10")
        for ip, method in (("1.1.1.1", "get"), ("1.1.1.1", "get"), ("2.2.2.2", "get"), ("3.3.3.3", "head")):
            r = getattr(self.client, method)("/download", headers={"X-Forwarded-For": ip}, follow_redirects=False)
            self.assertEqual(r.status_code, 307, r.text)
            self.assertTrue(r.headers["location"].endswith(name))
        with db.db() as conn:
            self.assertEqual(website.stats(conn)["downloads"], 1 + 2)
            stored = [row[0] for row in conn.execute("SELECT ip_hash FROM site_downloads")]
        self.assertEqual(len(stored), 2)
        self.assertFalse(any("1.1.1.1" in h or "2.2.2.2" in h for h in stored))

    def test_chat_broadcast_merges_rooms_hides_masked_and_deleted_lines(self):
        a = self.player(1, "Kuro", "7")
        b = self.player(2, "свага")
        with db.db() as conn:
            service.set_photo(conn, b)
        first = self.message(a, "global", "Прывэт")
        self.message(a, "ru", "*** ***")
        self.message(b, "en", "visit example.com now")
        gone = self.message(a, "global", "removed", deleted=1)
        data = self.client.get("/api/v1/site/chat").json()
        texts = [(m["room"], m["nick"], m["text"]) for m in data["messages"]]
        self.assertEqual(texts, [("global", "Kuro", "Прывэт"), ("en", "свага", "visit *** now")])
        self.assertEqual(data["messages"][0]["avatar"], "/assets/avatar-7.png")
        self.assertEqual(data["messages"][1]["avatar"], f"/avatars/{b}.png?v=1")
        self.assertIn(gone, data["deleted"])
        later = self.client.get(f"/api/v1/site/chat?after={first}").json()["messages"]
        self.assertEqual([m["room"] for m in later], ["en"])
        self.assertNotIn("p", data["messages"][0])

    def test_news_lists_the_latest_published_releases(self):
        for code in (5, 6, 7, 8):
            self.release(code)
        news = self.client.get("/api/v1/site/news").json()["news"]
        self.assertEqual([n["version"] for n in news], ["1.35-8", "1.35-7", "1.35-6"])
        self.assertEqual(news[0]["notes"], "Новая музыка.")


class InstallListTests(unittest.TestCase):
    """install.sh downloads files one by one: a file missing from its lists would be missing on the server."""
    base = Path(__file__).resolve().parent.parent

    def listed(self, name):
        text = (self.base / "deploy" / "install.sh").read_text()
        match = re.search(name + r'="([^"]*)"', text)
        self.assertIsNotNone(match, name)
        return set(match.group(1).split())

    def test_every_module_and_site_file_is_installed(self):
        modules = {f"czm/{p.name}" for p in (self.base / "czm").glob("*.py")}
        self.assertEqual(modules - self.listed("FILES"), set())
        site = {p.relative_to(self.base).as_posix() for p in (self.base / "site").rglob("*") if p.is_file()}
        self.assertEqual(site, self.listed("SITE"))

    def test_pages_have_no_inline_code_beyond_the_allowed_line(self):
        caddy = (self.base / "deploy" / "czm.caddy").read_text()
        for page in ("index.html", "privacy.html"):
            html = (self.base / "site" / page).read_text()
            self.assertNotRegex(html, r"\son[a-z]+=", page)
            for code in re.findall(r"<script>(.*?)</script>", html, re.S):
                digest = base64.b64encode(hashlib.sha256(code.encode()).digest()).decode()
                self.assertIn(f"'sha256-{digest}'", caddy, page)


if __name__ == "__main__":
    unittest.main()
