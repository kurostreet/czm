import base64
import hashlib
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from czm import builds, db, play, play_publish, service
from czm.assemble import BuildError
from czm.config import get_settings

COMMIT = "a" * 40
DATA = b"game data " * 1000


def zip_bytes(entries: dict[str, bytes], stored: bool = False) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED) as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return out.getvalue()


class PlayBundleTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        env = patch.dict(os.environ, {"CZM_DATA_DIR": temp.name})
        env.start()
        self.addCleanup(env.stop)
        get_settings.cache_clear()
        self.addCleanup(get_settings.cache_clear)
        db.init()
        self.settings = get_settings()
        self.settings.apk_dir.mkdir()
        self.settings.incoming_dir.mkdir()
        self.root = Path(temp.name)

    def data_apk(self) -> Path:
        meta = json.dumps({"sha256": hashlib.sha256(DATA).hexdigest()}).encode()
        apk = self.settings.apk_dir / "CounterZombieMobile-1.35-old.apk"
        apk.write_bytes(zip_bytes({"AndroidManifest.xml": b"m", "assets/bundled/game-data.zip": DATA,
                                   "assets/bundled/game-data.json": meta}, stored=True))
        with db.db() as conn:
            conn.execute("INSERT INTO releases(version,code,file,size,sha256,notes,created,published) VALUES (?,?,?,?,?,?,?,?)",
                         ("1.35-old", 1, apk.name, apk.stat().st_size, "b" * 64, "", 1, 1))
        return apk

    def bundle(self, **extra) -> Path:
        entries = {"BundleConfig.pb": b"cfg", "base/manifest/AndroidManifest.xml": b"base",
                   "base/dex/classes.dex": b"dex", "base/assets/bundled/client-resources.zip": b"client",
                   play.PACK_MANIFEST: b"pack", f"{play.PACK}/assets/bundled/czm-gamedata-pending.txt": b"placeholder",
                   f"{play.PACK}/assets.pb": b"\n\n\n\x06assets\x12\x00\n\x12\n\x0eassets/bundled\x12\x00",
                   "META-INF/OLD.RSA": b"old signature", "META-INF/MANIFEST.MF": b"old manifest"}
        entries.update(extra)
        path = self.settings.incoming_dir / play.incoming_name(COMMIT)
        path.write_bytes(zip_bytes(entries))
        return path

    def test_game_data_goes_into_the_install_time_pack_and_old_signature_is_dropped(self):
        out = self.root / "out.aab"
        play.combine(self.bundle(), self.data_apk(), out)
        with zipfile.ZipFile(out) as z:
            names = set(z.namelist())
            self.assertEqual(z.read(f"{play.PACK}/assets/bundled/game-data.zip"), DATA)
            self.assertEqual(z.getinfo(f"{play.PACK}/assets/bundled/game-data.zip").compress_type, zipfile.ZIP_STORED)
            self.assertEqual(z.read("base/dex/classes.dex"), b"dex")
        self.assertNotIn(f"{play.PACK}/assets/bundled/czm-gamedata-pending.txt", names)
        self.assertNotIn("META-INF/OLD.RSA", names)
        self.assertNotIn("META-INF/MANIFEST.MF", names)       # jarsigner writes a fresh one
        self.assertFalse(any(n.startswith("base/assets/bundled/game-data") for n in names))

    def test_a_bundle_without_the_pack_or_with_data_in_base_is_refused(self):
        apk = self.data_apk()
        bundle = self.bundle()
        with zipfile.ZipFile(bundle) as z:
            entries = {n: z.read(n) for n in z.namelist() if n != play.PACK_MANIFEST}
        bundle.write_bytes(zip_bytes(entries))
        with self.assertRaises(BuildError):
            play.combine(bundle, apk, self.root / "a.aab")
        with self.assertRaises(BuildError):
            play.combine(self.bundle(**{"base/assets/bundled/game-data.zip": b"x"}), apk, self.root / "b.aab")
        with self.assertRaises(BuildError):           # an index without assets/bundled: Play would not see the data
            play.combine(self.bundle(**{f"{play.PACK}/assets.pb": b"\n\n\n\x06assets\x12\x00"}), apk, self.root / "c.aab")

    def test_pending_bundle_is_signed_kept_and_failures_stay_for_a_look(self):
        self.data_apk()
        bundle = self.bundle()
        bundle.with_suffix(".version").write_text("1.35-abc\n")

        def fake_sign(unsigned, out):
            Path(out).write_bytes(Path(unsigned).read_bytes())
        with patch.object(play, "sign", fake_sign):
            self.assertEqual(play.run_pending(), 1)
        target = self.settings.play_dir / "CounterZombieMobile-1.35-abc.aab"
        self.assertTrue(target.is_file())
        self.assertIn(hashlib.sha256(target.read_bytes()).hexdigest(), Path(str(target) + ".sha256").read_text())
        self.assertFalse(bundle.exists())
        broken = self.bundle()
        broken.write_bytes(b"not a zip")
        play.run_pending()
        self.assertTrue(broken.with_suffix(".failed").is_file())

    def test_signing_needs_the_upload_key(self):
        with patch.dict(os.environ, {"CZM_PLAY_KEY_PASSWORD": ""}), self.assertRaises(BuildError):
            play.sign(self.root / "a.aab", self.root / "b.aab")


def service_account(path: Path) -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    path.write_text(json.dumps({"type": "service_account", "client_email": "robot@czm-play.iam.gserviceaccount.com",
                                "private_key": pem.decode(), "token_uri": "https://oauth2.googleapis.com/token"}))


class FakePlay:
    """Google's token and Android Publisher endpoints, recording what the server sent."""
    def __init__(self, fail_track=None):
        self.calls, self.fail_track, self.deleted = [], fail_track, False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path, method = request.url.path, request.method
        self.calls.append((method, path, dict(request.url.params)))
        if path == "/token":
            return httpx.Response(200, json={"access_token": "secret-token"})
        assert request.headers["authorization"] == "Bearer secret-token"
        if method == "POST" and path.endswith("/edits"):
            return httpx.Response(200, json={"id": "e1"})
        if "/upload/" in path:
            self.uploaded = request.read()
            return httpx.Response(200, json={"versionCode": 4321})
        if method == "PUT" and "/tracks/" in path:
            track = path.rsplit("/", 1)[1]
            if track == self.fail_track:
                return httpx.Response(403, json={"error": {"message": "no access"}})
            self.release = json.loads(request.read())["releases"][0]
            return httpx.Response(200, json={"track": track})
        if path.endswith("/edits/e1:commit"):
            return httpx.Response(200, json={"id": "e1"})
        if method == "DELETE":
            self.deleted = True
            return httpx.Response(204)
        return httpx.Response(404)


class PlayPublishTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        key = self.root / "account.json"
        env = patch.dict(os.environ, {"CZM_DATA_DIR": temp.name, "CZM_PLAY_SERVICE_ACCOUNT_FILE": str(key)})
        env.start()
        self.addCleanup(env.stop)
        get_settings.cache_clear()
        self.addCleanup(get_settings.cache_clear)
        db.init()
        self.key = key
        self.bundle = self.root / "CounterZombieMobile-1.35-abc.aab"
        self.bundle.write_bytes(b"signed bundle" * 100)

    def test_without_the_key_nothing_is_sent(self):
        self.assertFalse(play_publish.configured())
        service_account(self.key)
        self.assertTrue(play_publish.configured())
        with patch.dict(os.environ, {"CZM_PLAY_PUBLISH": "false"}):
            get_settings.cache_clear()
            self.assertFalse(play_publish.configured())

    def test_bundle_goes_to_both_testing_tracks_and_is_committed(self):
        service_account(self.key)
        fake = FakePlay()
        with httpx.Client(transport=httpx.MockTransport(fake)) as client:
            code = play_publish.publish(self.bundle, "1.35-abc", "Новые карты.", client)
        self.assertEqual(code, 4321)
        self.assertEqual(fake.uploaded, self.bundle.read_bytes())
        upload = next(c for c in fake.calls if "/upload/" in c[1])
        self.assertEqual(upload[2], {"uploadType": "media", "ackBundleInstallationWarning": "true"})
        tracks = [c[1].rsplit("/", 1)[1] for c in fake.calls if c[0] == "PUT"]
        self.assertEqual(tracks, ["internal", "alpha"])
        self.assertEqual(fake.release, {"name": "4321 (1.35-abc)", "versionCodes": ["4321"], "status": "completed",
                                        "releaseNotes": [{"language": "ru-RU", "text": "Новые карты."}]})
        self.assertTrue(fake.calls[-1][1].endswith(":commit"))
        self.assertFalse(fake.deleted)

    def test_a_refused_step_drops_the_edit_and_says_why(self):
        service_account(self.key)
        fake = FakePlay(fail_track="alpha")
        with httpx.Client(transport=httpx.MockTransport(fake)) as client, \
                self.assertRaisesRegex(play_publish.PublishError, "alpha: 403 no access"):
            play_publish.publish(self.bundle, "1.35-abc", "", client)
        self.assertTrue(fake.deleted)
        self.assertFalse(any(c[1].endswith(":commit") for c in fake.calls))

    def test_notes_are_cut_to_the_play_limit_and_never_empty(self):
        self.assertEqual(play_publish.release_notes("  "), "Исправления и улучшения.")
        self.assertEqual(len(play_publish.release_notes("я" * 600)), play_publish.NOTES_LIMIT)

    def test_the_result_is_kept_for_the_bot(self):
        service_account(self.key)
        with patch.object(play_publish, "publish", return_value=4321):
            play.send_to_testers(self.bundle, "1.35-abc", "x")
        with patch.object(play_publish, "publish", side_effect=play_publish.PublishError("загрузка: 400 bad")):
            play.send_to_testers(self.bundle, "1.35-def", "x")
        with db.db() as conn:
            rows = service.unnotified_play_publishes(conn)
        self.assertEqual([(r["version"], r["version_code"], r["status"]) for r in rows],
                         [("1.35-abc", 4321, "sent"), ("1.35-def", None, "failed")])
        self.assertEqual(rows[0]["tracks"], "internal, alpha")
        self.assertIn("400 bad", rows[1]["error"])


class PlayUploadTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        env = patch.dict(os.environ, {"CZM_DATA_DIR": temp.name})
        env.start()
        self.addCleanup(env.stop)
        get_settings.cache_clear()
        self.addCleanup(get_settings.cache_clear)
        db.init()
        app = FastAPI()
        app.include_router(builds.router)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def claims(self, workflow):
        s = get_settings()
        return {"repository_id": str(s.build_repository_id), "repository": s.build_repository, "ref": s.build_ref,
                "workflow_ref": f"{s.build_repository}/{workflow}@{s.build_ref}", "event_name": "workflow_dispatch",
                "sha": COMMIT}

    def test_only_the_play_workflow_may_send_bundles(self):
        key = SimpleNamespace(key="k")
        with patch.object(builds._jwks, "get_signing_key_from_jwt", return_value=key), \
                patch("czm.builds.jwt.decode", return_value=self.claims(".github/workflows/play.yml")):
            self.assertEqual(builds.check_token("t", get_settings().play_workflow)["sha"], COMMIT)
            with self.assertRaises(builds.HTTPException):
                builds.check_token("t")                      # the players' build endpoint wants build.yml
        with patch.object(builds._jwks, "get_signing_key_from_jwt", return_value=key), \
                patch("czm.builds.jwt.decode", return_value=self.claims(".github/workflows/build.yml")):
            with self.assertRaises(builds.HTTPException):
                builds.check_token("t", get_settings().play_workflow)
        # after a players' build play.yml starts by itself (workflow_run); build.yml never may
        auto = self.claims(".github/workflows/play.yml") | {"event_name": "workflow_run"}
        with patch.object(builds._jwks, "get_signing_key_from_jwt", return_value=key), \
                patch("czm.builds.jwt.decode", return_value=auto):
            self.assertEqual(builds.check_token("t", get_settings().play_workflow)["sha"], COMMIT)
        auto = self.claims(".github/workflows/build.yml") | {"event_name": "workflow_run"}
        with patch.object(builds._jwks, "get_signing_key_from_jwt", return_value=key), \
                patch("czm.builds.jwt.decode", return_value=auto):
            with self.assertRaises(builds.HTTPException):
                builds.check_token("t")

    def test_bundle_upload_is_stored_for_assembly(self):
        body = b"bundle bytes"
        url = f"/api/v1/play-builds?version=1.35-abc&code=7&sha256={hashlib.sha256(body).hexdigest()}&commit={COMMIT}"
        with patch.object(builds, "check_token", return_value={"sha": COMMIT}):
            r = self.client.post(url, content=body, headers={"Authorization": "Bearer t",
                                                             "X-CZM-Notes": base64.b64encode("Новое.".encode()).decode()})
            self.assertEqual(r.status_code, 200, r.text)
            bad = self.client.post(url.replace("sha256=", "sha256=0"), content=body, headers={"Authorization": "Bearer t"})
            self.assertEqual(bad.status_code, 400)
        incoming = get_settings().incoming_dir
        self.assertEqual((incoming / play.incoming_name(COMMIT)).read_bytes(), body)
        self.assertEqual((incoming / play.incoming_name(COMMIT)).with_suffix(".version").read_text().strip(), "1.35-abc")
        self.assertEqual((incoming / play.incoming_name(COMMIT)).with_suffix(".notes").read_text(), "Новое.")
        self.assertTrue((incoming / ".trigger").is_file())
        self.assertEqual(self.client.post(url, content=body).status_code, 401)


if __name__ == "__main__":
    unittest.main()
