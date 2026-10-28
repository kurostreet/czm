"""News about Google Play releases: every release on the public track, never a site build or an internal one."""
import os
import tempfile
import unittest
from unittest import mock
from unittest.mock import patch

from czm import db, play_feed, service
from czm.config import get_settings


def track(code, version="1.35-abc1234", notes="Новый профиль.", status="completed"):
    return {"name": f"{code} ({version})", "versionCodes": [str(code)], "status": status,
            "releaseNotes": [{"language": "en-US", "text": "New profile."}, {"language": "ru-RU", "text": notes}]}


class PlayFeedTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        env = patch.dict(os.environ, {"CZM_DATA_DIR": temp.name, "CZM_PLAY_SERVICE_ACCOUNT_FILE": "/nonexistent"})
        env.start(); self.addCleanup(env.stop)
        get_settings.cache_clear(); self.addCleanup(get_settings.cache_clear)
        db.init()
        self.clock = 1_800_000_000
        for where in ("czm.play_feed.now", "czm.service.now"):
            clock = patch(where, side_effect=lambda: self.clock)
            clock.start(); self.addCleanup(clock.stop)

    def player(self, n, version="1.35-old"):
        with db.db() as conn:
            return service.hello(conn, f"feed-key-{n:04d}-abcdefgh", f"feed-device-{n}", f"P{n}", "", "ru", version)

    def update(self, n, version, code, store=None):
        """A hello of player n after an update; returns whether the release became news."""
        with db.db() as conn:
            before = service.player_by_key(conn, f"feed-key-{n:04d}-abcdefgh")
            after = service.hello(conn, f"feed-key-{n:04d}-abcdefgh", f"feed-device-{n}", f"P{n}", "", "ru", version)
            return play_feed.witness(conn, before, after, code, store)

    def test_old_site_build_news_leave_once_and_stay_gone(self):
        with db.db() as conn:
            welcome = service.add_news(conn, "Тут будут новости")
            old = service.add_news(conn, "Обновление 1.35-98356ab\nЭта версия больше не поддерживается.")
            conn.execute("INSERT INTO releases(version,code,file,size,sha256,notes,created,published,news_id,channel) "
                         "VALUES ('1.35-98356ab',1,'a.apk',1,'x','Эта версия больше не поддерживается.',1,2,?,'migration')", (old,))
            conn.execute("DELETE FROM site_counters WHERE name='news_feed_play'")
        db.init()
        with db.db() as conn:
            self.assertEqual([n["id"] for n in service.news(conn)], [welcome])
            # the migration screen of old installs keeps its release and text
            row = conn.execute("SELECT channel, published, notes FROM releases WHERE code=1").fetchone()
            self.assertEqual((row["channel"], bool(row["published"])), ("migration", True))
            # a later news item is kept by later starts
            later = service.add_news(conn, "Турнир в субботу")
        db.init()
        with db.db() as conn:
            self.assertEqual([n["id"] for n in service.news(conn)], [later, welcome])

    def test_site_builds_never_make_news(self):
        with db.db() as conn:
            before = service.last_news_id(conn)
            for channel in ("legacy", "migration", "development"):
                rid = conn.execute("INSERT INTO releases(version,code,file,size,sha256,created,channel) VALUES (?,?,?,?,?,?,?)",
                                   (f"1.35-{channel}", len(channel), f"{channel}.apk", 1, "x", 1, channel)).lastrowid
                service.publish_release(conn, rid, "Что нового")
                self.assertTrue(conn.execute("SELECT published FROM releases WHERE id=?", (rid,)).fetchone()[0])
            self.assertEqual(service.last_news_id(conn), before)

    def test_a_release_is_news_as_soon_as_it_is_on_the_public_track(self):
        for n in range(1, 4):
            self.player(n)
        with db.db() as conn:
            # first look: what testers already have is listed on the site, the bell stays quiet
            play_feed.sync(conn, {"internal": [track(100, "1.35-aaa1111")], "alpha": [track(100, "1.35-aaa1111", "Старое.")],
                                  "production": []})
            self.assertEqual([n["version"] for n in play_feed.site_news(conn, 3)], ["1.35"])
            self.assertEqual(play_feed.unnotified(conn), [])
            news_before = service.last_news_id(conn)
            # a new candidate on internal only: nobody hears about it, even after updates
            self.clock += 600
            play_feed.sync(conn, {"internal": [track(101, "1.35-bbb2222", "Новый профиль и SUPPORT.")], "alpha": [track(100)]})
            self.assertEqual([r["code"] for r in play_feed.latest(conn)], [101, 100])  # notes for the code Play offers
        self.assertFalse(self.update(1, "1.35-bbb2222", 101))
        with db.db() as conn:
            self.assertEqual(service.last_news_id(conn), news_before)
            self.assertEqual(play_feed.unnotified(conn), [])
            # sent to the closed test: the next look makes it news everywhere at once
            self.clock += 600
            play_feed.sync(conn, {"internal": [track(101, "1.35-bbb2222", "Новый профиль и SUPPORT.")],
                                  "alpha": [track(101, "1.35-bbb2222", "Новый профиль и SUPPORT.")]})
            items = service.news(conn)
            self.assertEqual(items[0]["text"], "Обновление в Google Play, версия 1.35\nНовый профиль и SUPPORT.")
            self.assertNotIn("bbb2222", items[0]["text"])
            self.assertEqual([n["version"] for n in play_feed.site_news(conn, 3)], ["1.35", "1.35"])
            self.assertEqual(play_feed.site_news(conn, 3)[0]["notes"], "Новый профиль и SUPPORT.")
            self.assertEqual([r["code"] for r in play_feed.unnotified(conn)], [101])
            play_feed.mark_notified(conn, 101)
            self.assertEqual(play_feed.unnotified(conn), [])
            last = service.last_news_id(conn)
        # updates and more looks never repeat it
        self.assertFalse(self.update(2, "1.35-bbb2222", 101, store=1))
        self.assertFalse(self.update(3, "1.35-bbb2222", 101))
        with db.db() as conn:
            self.clock += 900
            play_feed.sync(conn, {"internal": [track(101)], "alpha": [track(101, "1.35-bbb2222", "Новый профиль и SUPPORT.")]})
            self.assertEqual(service.last_news_id(conn), last)
            # a draft or a halted rollout on the closed test reaches nobody: not news
            self.clock += 900
            play_feed.sync(conn, {"alpha": [track(101), track(102, "1.35-ccc3333", status="draft")]})
            self.assertEqual(service.last_news_id(conn), last)
            # the next one is news again, once
            self.clock += 900
            play_feed.sync(conn, {"alpha": [track(103, "1.35-ddd4444", "Русские буквы в HUD.")]})
            self.assertEqual(service.news(conn)[0]["text"], "Обновление в Google Play, версия 1.35\nРусские буквы в HUD.")
            self.assertEqual([r["code"] for r in play_feed.unnotified(conn)], [103])

    def test_a_news_item_keeps_only_what_is_new(self):
        before = ("Новый раздел «Топ 100»: рейтинг по времени на игровых серверах с коронами для первой сотни. "
                  "Новая карточка профиля: место в топе, статус меняется прямо в карточке, жалоба и блокировка в меню. "
                  "«Об игре» теперь в настройках. Правила сообщества и жалобы в лобби, заблокированные игроки не видны "
                  "и не слышны. Индикатор загрузки больше не зависает. В колокольчике видно, что нового в обновлении.")
        now_notes = ("Новый раздел «Топ 100»: рейтинг по времени на серверах с коронами для первой сотни. Новая карточка "
                     "профиля: место в топе, статус меняется прямо в карточке, жалоба и блокировка в меню. «Об игре» теперь "
                     "в настройках. Правила сообщества и жалобы в лобби. Русские буквы в сообщениях сервера на экране больше "
                     "не пропадают, кнопки управления не сдвигаются после чата. Индикатор загрузки не зависает. В колокольчике "
                     "видно, что нового в обновлении.")
        self.assertEqual(play_feed.fresh_notes(now_notes, ["Обновление в Google Play, версия 1.35\n" + before]),
                         "Русские буквы в сообщениях сервера на экране больше не пропадают, кнопки управления не сдвигаются после чата.")
        # a new fix that shares a few words with an old line stays
        self.assertEqual(play_feed.fresh_notes("Индикатор загрузки снова показывает скорость.", [before]),
                         "Индикатор загрузки снова показывает скорость.")
        with db.db() as conn:
            play_feed.sync(conn, {"alpha": [track(500, "1.35-aaa", "Старое.")]})
            self.clock += 600
            play_feed.sync(conn, {"alpha": [track(501, "1.35-bbb", before)]})
            self.clock += 600
            play_feed.sync(conn, {"alpha": [track(502, "1.35-ccc", now_notes)]})
            items = service.news(conn)
            self.assertEqual(items[0]["text"], "Обновление в Google Play, версия 1.35\nРусские буквы в сообщениях сервера на "
                                               "экране больше не пропадают, кнопки управления не сдвигаются после чата.")
            self.assertEqual(items[1]["text"], "Обновление в Google Play, версия 1.35\n" + before)
            # one item per release, and one with nothing new still says something
            self.clock += 600
            play_feed.sync(conn, {"alpha": [track(503, "1.35-ddd", now_notes)]})
            self.assertEqual(service.news(conn)[0]["text"], "Обновление в Google Play, версия 1.35\nИсправления и улучшения.")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM play_releases WHERE news_id IS NOT NULL").fetchone()[0], 3)

    def test_the_site_says_what_the_bell_says(self):
        with db.db() as conn:
            play_feed.sync(conn, {"alpha": [track(300, "1.35-aaa", "Старое.")]})
            self.clock += 600
            play_feed.sync(conn, {"alpha": [track(301, "1.35-bbb", "Топ 100. Профиль. Русские буквы в HUD.")]})
            item = service.news(conn)[0]
            self.assertEqual(play_feed.site_news(conn, 3)[0]["notes"], "Топ 100. Профиль. Русские буквы в HUD.")
            # the owner keeps only what is new in this version: the bell and the site change together
            self.assertTrue(service.edit_news(conn, item["id"], "Обновление в Google Play, версия 1.35\nРусские буквы в HUD."))
            self.assertEqual(service.news(conn)[0]["text"], "Обновление в Google Play, версия 1.35\nРусские буквы в HUD.")
            self.assertEqual(play_feed.site_news(conn, 3)[0]["notes"], "Русские буквы в HUD.")
            # a later look at the tracks with the old Play notes does not bring them back
            self.clock += 900
            play_feed.sync(conn, {"alpha": [track(301, "1.35-bbb", "Топ 100. Профиль. Русские буквы в HUD.")]})
            self.assertEqual(play_feed.site_news(conn, 3)[0]["notes"], "Русские буквы в HUD.")
            # a text without the title is shown as it is
            service.edit_news(conn, item["id"], "Буквы и кнопки.")
            self.assertEqual(play_feed.site_news(conn, 3)[0]["notes"], "Буквы и кнопки.")
            self.assertFalse(service.edit_news(conn, item["id"], "   "))
            self.assertFalse(service.edit_news(conn, 999999, "Нет такой."))
            # removed from the bell: gone from the site too; what players had on the first look stays
            self.assertTrue(service.delete_news(conn, item["id"]))
            self.assertFalse(service.edit_news(conn, item["id"], "Поздно."))
            self.assertEqual([(n["version"], n["notes"]) for n in play_feed.site_news(conn, 3)], [("1.35", "Старое.")])

    def test_production_becomes_the_public_track(self):
        for n in range(1, 4):
            self.player(n)
        with db.db() as conn:
            play_feed.sync(conn, {"alpha": [track(200)]})
            self.clock += 600
            play_feed.sync(conn, {"alpha": [track(201)], "production": [track(200)]})
        self.assertEqual(play_feed.public_track({"production": [track(1, status="draft")]}), "alpha")
        # 201 is only in the closed test while production exists: not news for everyone
        self.assertFalse(self.update(1, "1.35-c201", 201))
        self.assertFalse(self.update(2, "1.35-c201", 201))
        with db.db() as conn:
            self.assertIsNone(conn.execute("SELECT public_since FROM play_releases WHERE code=201").fetchone()[0])
            self.assertIsNone(conn.execute("SELECT announced FROM play_releases WHERE code=201").fetchone()[0])

    def test_tracks_are_read_in_a_throwaway_edit(self):
        calls = []

        class Response:
            def __init__(self, status, body): self.status_code, self._body, self.content = status, body, b"x"
            def json(self): return self._body

        class Client:
            def __init__(self, *a, **k): pass
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def post(self, url, **k): calls.append(("POST", url)); return Response(200, {"id": "edit-1"})
            def get(self, url, **k):
                calls.append(("GET", url))
                return Response(200, {"tracks": [{"track": "alpha", "releases": [track(300)]}, {"track": "production"}]})
            def delete(self, url, **k): calls.append(("DELETE", url)); return Response(204, {})

        with patch("httpx.Client", Client), patch("czm.play_publish.access_token", return_value="token"):
            tracks = play_feed.read_tracks()
        self.assertEqual(tracks["alpha"][0]["versionCodes"], ["300"])
        self.assertEqual(tracks["production"], [])
        self.assertEqual([c[0] for c in calls], ["POST", "GET", "DELETE"])
        self.assertTrue(calls[2][1].endswith("/edits/edit-1"))


try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
except ImportError:  # the logic above runs anywhere; the API part needs the service's packages
    FastAPI = None


@unittest.skipIf(FastAPI is None, "fastapi is not installed")
class PlayFeedApiTests(unittest.TestCase):
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

    def hello(self, n, version, code, store=None):
        body = {"key": f"feed-api-key-{n:04d}-abcdef", "device": f"d{n}", "nick": f"P{n}", "version": version, "code": code}
        if store is not None:
            body["store"] = store
        r = self.client.post("/api/v1/hello", json=body)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_hello_gives_the_notes_and_the_news_of_a_public_release(self):
        for n in (1, 2):
            self.assertEqual(self.hello(n, "1.35-old", 400)["play"], [])
        news = self.hello(1, "1.35-old", 400)["news"]
        with db.db() as conn:
            play_feed.sync(conn, {"alpha": [track(400, "1.35-old", "Было.")]})
            self.assertEqual(service.last_news_id(conn), news)          # what players already have stays quiet
            play_feed.sync(conn, {"alpha": [track(401, "1.35-new", "Стало лучше.")]})
        first = self.hello(1, "1.35-old", 400, store=1)
        self.assertEqual(first["play"], [{"code": 401, "version": "1.35", "notes": "Стало лучше."}])
        self.assertGreater(first["news"], news)                          # the bell rings before the update
        self.assertEqual(self.hello(2, "1.35-new", 401)["news"], first["news"])
        site = self.client.get("/api/v1/site/news").json()["news"]
        self.assertEqual([(n["version"], n["notes"]) for n in site][0], ("1.35", "Стало лучше."))
        # only 0 or 1 (the service's own handler turns validation errors into 400)
        self.assertIn(self.client.post("/api/v1/hello", json={"key": "feed-api-key-0009-abcdef", "store": 2}).status_code, (400, 422))

if __name__ == "__main__":
    unittest.main()
