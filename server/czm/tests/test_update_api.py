import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from czm import api, db, service
from czm.assemble import remove_old_files
from czm.config import get_settings


class UpdateApiTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.env = patch.dict(os.environ, {"CZM_DATA_DIR": temp.name, "CZM_BUILD_KEEP": "3"})
        self.env.start()
        self.addCleanup(self.env.stop)
        get_settings.cache_clear()
        self.addCleanup(get_settings.cache_clear)
        db.init()
        self.folder = get_settings().apk_dir
        self.folder.mkdir()
        app = FastAPI()
        app.include_router(api.router)
        app.include_router(api.download_router)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def release(self, code, published=True):
        name = f"test-{code}.apk"
        (self.folder / name).write_bytes(b"a" * 100)
        with db.db() as conn:
            return conn.execute("INSERT INTO releases(version,code,file,size,sha256,created,published) VALUES (?,?,?,?,?,?,?)",
                                (str(code), code, name, 100, "a" * 64, 1, 1 if published else None)).lastrowid

    def add_patch(self, release_id, base_code):
        name = f"patch-{release_id}-{base_code}.czmpatch"
        (self.folder / name).write_bytes(b"p" * 20)
        with db.db() as conn:
            conn.execute("INSERT INTO release_patches VALUES (?,?,?,?,?,?)", (release_id, base_code, "b" * 64, name, 20, "c" * 64))
        return self.folder / name

    def test_update_and_hello_select_base_and_keep_full_metadata(self):
        release_id = self.release(200)
        self.add_patch(release_id, 100)
        response = self.client.get("/api/v1/update?code=100").json()["update"]
        self.assertEqual(response["patch_format"], 1)
        self.assertEqual(response["patch_size"], 20)
        self.assertEqual(response["size"], 100)
        self.assertTrue(response["url"].endswith(".apk"))
        self.assertTrue(response["url"].startswith(get_settings().public_url + "/dl/"))
        self.assertTrue(response["patch_url"].startswith(get_settings().public_url + "/dl/"))
        self.assertEqual(response["sha256"], "a" * 64)
        self.assertEqual(response["base_sha256"], "b" * 64)
        hello = self.client.post("/api/v1/hello", json={"key": "test-hello-secret-key-for-updates", "nick": "Test", "code": 100})
        self.assertEqual(hello.status_code, 200)
        self.assertEqual(hello.json()["update"], response)
        self.assertNotIn("patch_url", self.client.get("/api/v1/update?code=99").json()["update"])
        self.assertIsNone(self.client.get("/api/v1/update?code=200").json()["update"])

    def test_missing_or_truncated_patch_is_not_advertised(self):
        release_id = self.release(200)
        file = self.add_patch(release_id, 100)
        file.write_bytes(b"short")
        self.assertNotIn("patch_url", self.client.get("/api/v1/update?code=100").json()["update"])
        file.unlink()
        self.assertNotIn("patch_url", self.client.get("/api/v1/update?code=100").json()["update"])

    def test_public_apk_download_stays_disabled_during_publication_and_rollback(self):
        self.release(100)
        draft = self.release(200, published=False)

        def check():
            for route in ("/download", "/download/CounterZombieMobile.apk"):
                for method in ("GET", "HEAD"):
                    with self.subTest(route=route, method=method):
                        response = self.client.request(method, route, follow_redirects=False)
                        self.assertEqual(response.status_code, 410)
                        self.assertNotIn("location", response.headers)
                        self.assertEqual(response.headers["cache-control"], "no-store")
                        if method == "GET":
                            self.assertEqual(response.json()["error"], "google_play_only")

        check()  # published APK and a newer draft both remain inaccessible
        with db.db() as conn:
            service.publish_release(conn, draft, "New version")
        check()  # publishing a new APK must not reopen direct downloads
        with db.db() as conn:
            service.unpublish_release(conn, draft)
        check()  # rolling back must not reopen direct downloads

    def test_public_apk_download_rejects_absent_draft_or_damaged_release(self):
        for state in ("absent", "draft", "missing", "truncated"):
            with self.subTest(state=state):
                if state == "draft":
                    release = self.release(100, published=False)
                elif state == "missing":
                    with db.db() as conn:
                        service.publish_release(conn, release, "Published")
                    (self.folder / "test-100.apk").unlink()
                elif state == "truncated":
                    (self.folder / "test-100.apk").write_bytes(b"incomplete")
                for route in ("/download", "/download/CounterZombieMobile.apk"):
                    for method in ("GET", "HEAD"):
                        response = self.client.request(method, route, follow_redirects=False)
                        self.assertEqual(response.status_code, 410)
                        self.assertNotIn("location", response.headers)
                        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_retention_removes_all_patches_of_expired_targets(self):
        for code in range(1, 6):
            release_id = self.release(code)
            self.add_patch(release_id, 100)
            self.add_patch(release_id, 101)
        with db.db() as conn:
            remove_old_files(conn)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM release_patches").fetchone()[0], 6)
        self.assertEqual(len(list(self.folder.glob("*.apk"))), 3)
        self.assertEqual(len(list(self.folder.glob("*.czmpatch"))), 6)

    def test_rollback_and_published_release_outside_retention_stay_available(self):
        old = self.release(1)
        old_patch = self.add_patch(old, 100)
        for code in range(2, 6):
            self.release(code, published=False)
        with db.db() as conn:
            remove_old_files(conn)
            self.assertEqual(service.latest_release(conn)["id"], old)
        self.assertTrue(old_patch.is_file())
        self.assertTrue((self.folder / "test-1.apk").is_file())


if __name__ == "__main__":
    unittest.main()
