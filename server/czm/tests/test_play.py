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
from czm import builds, db, play
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

    def test_bundle_upload_is_stored_for_assembly(self):
        body = b"bundle bytes"
        url = f"/api/v1/play-builds?version=1.35-abc&code=7&sha256={hashlib.sha256(body).hexdigest()}&commit={COMMIT}"
        with patch.object(builds, "check_token", return_value={"sha": COMMIT}):
            r = self.client.post(url, content=body, headers={"Authorization": "Bearer t"})
            self.assertEqual(r.status_code, 200, r.text)
            bad = self.client.post(url.replace("sha256=", "sha256=0"), content=body, headers={"Authorization": "Bearer t"})
            self.assertEqual(bad.status_code, 400)
        incoming = get_settings().incoming_dir
        self.assertEqual((incoming / play.incoming_name(COMMIT)).read_bytes(), body)
        self.assertEqual((incoming / play.incoming_name(COMMIT)).with_suffix(".version").read_text().strip(), "1.35-abc")
        self.assertTrue((incoming / ".trigger").is_file())
        self.assertEqual(self.client.post(url, content=body).status_code, 401)


if __name__ == "__main__":
    unittest.main()
