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
                         (f"1.35-{code}", code, name, size, "a" * 64, "Новая музыка.", 1, 100 + code))

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

    def test_website_apk_downloads_are_disabled(self):
        self.player(1, "Kuro")
        self.release()
        with db.db() as conn:
            conn.execute("UPDATE releases SET size = 10")
        for path in ("/download", "/download/CounterZombieMobile.apk"):
            for method in ("get", "head"):
                response = getattr(self.client, method)(path, follow_redirects=False)
                self.assertEqual(response.status_code, 410)
                self.assertNotIn("location", response.headers)
        with db.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM site_downloads").fetchone()[0], 0)

    def test_play_beta_count_uses_console_confirmed_value_only(self):
        initial = self.client.get("/api/v1/site/stats").json()
        self.assertIsNone(initial["play_beta_testers"])
        self.assertEqual(initial["play_beta_checked_at"], 0)
        self.assertIs(initial["play_beta_open"], False)
        with db.db() as conn:
            website.set_play_beta_testers(conn, 0)
        api._site_stats.update(time=0.0, data=None)
        zero = self.client.get("/api/v1/site/stats").json()
        self.assertEqual(zero["play_beta_testers"], 0)
        self.assertGreater(zero["play_beta_checked_at"], 0)
        with db.db() as conn:
            website.set_play_beta_testers(conn, 13)
            with self.assertRaises(ValueError):
                website.set_play_beta_testers(conn, -1)
        api._site_stats.update(time=0.0, data=None)
        updated = self.client.get("/api/v1/site/stats").json()
        self.assertEqual(updated["play_beta_testers"], 13)
        self.assertIs(updated["play_beta_open"], False)
        with db.db() as conn:
            website.set_play_beta_open(conn, True)
        api._site_stats.update(time=0.0, data=None)
        self.assertIs(self.client.get("/api/v1/site/stats").json()["play_beta_open"], True)
        with db.db() as conn:
            website.set_play_beta_open(conn, False)
        api._site_stats.update(time=0.0, data=None)
        self.assertIs(self.client.get("/api/v1/site/stats").json()["play_beta_open"], False)

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
        self.release(9)
        with db.db() as conn:
            conn.execute("UPDATE releases SET channel='migration' WHERE code=8")
            conn.execute("UPDATE releases SET channel='development', notes='Private test only' WHERE code=9")
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

    def test_beta_group_is_publicly_listed_but_play_links_start_locked(self):
        html = (self.base / "site" / "index.html").read_text()
        js = (self.base / "site" / "assets" / "site.js").read_text()
        self.assertIn('data-group="https://groups.google.com/g/counter-zombie-mobile-beta"', html)
        self.assertIn('id="sBetaTesters" class="count">—</span> / 50', html)
        self.assertIn('.beta-progress strong .count{font-size:1.2em;color:var(--gold)}', html)
        self.assertIn('data-step="2"', html)
        self.assertIn('data-step="3"', html)
        self.assertIn('play_beta_open === true', js)
        self.assertIn("link.removeAttribute('href')", js)
        self.assertIn("link.setAttribute('aria-disabled', 'true')", js)

    def test_beta_is_first_and_apk_ctas_are_gone(self):
        html = (self.base / "site" / "index.html").read_text()
        js = (self.base / "site" / "assets" / "site.js").read_text()
        caddy = (self.base / "deploy" / "czm.caddy").read_text()
        self.assertIn('href="#beta"', html)
        self.assertIn('data-i18n="downloadCta">Принять участие в бета-тесте', html)
        self.assertLess(html.index('id="beta"'), html.index('id="features"'))
        self.assertNotIn('href="/download"', html)
        self.assertNotIn('id="download"', html)
        self.assertNotIn('Скачать APK', html)
        self.assertNotIn('id="sDownloads"', html)
        self.assertIn("handle /dl/*", caddy)
        downloads = caddy.split("handle /dl/*", 1)[1].split("}", 1)[0]
        self.assertIn("reverse_proxy 127.0.0.1:8200", downloads)
        self.assertNotIn("file_server", downloads)
        self.assertIn("downloadCta: 'Join the beta test'", js)

    def test_gameplay_shots_carousel_is_separate_from_features(self):
        html = (self.base / "site" / "index.html").read_text()
        js = (self.base / "site" / "assets" / "site.js").read_text()
        self.assertIn('id="shots"', html)
        self.assertIn('id="strip"', html)
        self.assertIn('id="box"', html)
        self.assertIn('Кадры</h2>', html)
        self.assertIn('id="features"', html)
        self.assertIn('id="tabs"', html)
        self.assertIn('id="panels"', html)
        self.assertIn('FEAT_SHOTS[i] - 1', js)
        self.assertIn('function shotSrc(i)', js)
        self.assertIn('function gallerySrc(i)', js)
        self.assertIn('buildStrip()', js)
        self.assertIn("gallery: ['Игровая сцена: бой'", js)
        self.assertLess(html.index('id="beta"'), html.index('id="shots"'))
        self.assertLess(html.index('id="shots"'), html.index('id="features"'))
        for i in range(1, 5):
            self.assertTrue((self.base / 'site' / 'assets' / f'gameplay-{i}.webp').is_file())
        self.assertIn('scroll-snap-type:x mandatory', html)

    def test_beta_video_guide_is_embedded_not_preloaded(self):
        html = (self.base / "site" / "index.html").read_text()
        js = (self.base / "site" / "assets" / "site.js").read_text()
        caddy = (self.base / "deploy" / "czm.caddy").read_text()
        self.assertIn('data-i18n="betaVideo">Видео инструкция', html)
        self.assertIn('preload="none"', html)
        self.assertIn('controls playsinline', html)
        self.assertIn('src="/media/beta-instruction.mp4"', html)
        self.assertIn('poster="/media/beta-instruction.jpg"', html)
        self.assertIn("betaVideo: 'Video instructions'", js)
        self.assertIn('handle_path /media/*', caddy)
        self.assertIn('root * /var/lib/czm/tutorial', caddy)

    def test_build_uploads_get_the_large_body_limit(self):
        caddy = (self.base / "deploy" / "czm.caddy").read_text()
        for path in ("/api/v1/builds", "/api/v1/play-builds"):
            block = caddy.split(f"handle {path} {{", 1)[1].split("}\n\t}", 1)[0]   # exact path: before /api/*
            self.assertIn("max_size 700MB", block, path)

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
