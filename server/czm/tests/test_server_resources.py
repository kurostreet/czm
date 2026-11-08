"""Real pack publication, trust/catalog and immutable HTTPS delivery boundaries."""
import hashlib
import io
import json
import os
import struct
import tempfile
import unittest
import wave
import zipfile
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from czm import api, db, official, resource_publish as publisher, server_resources as resources
from czm.config import get_settings


def wav_bytes():
    out = io.BytesIO()
    with wave.open(out, "wb") as sound:
        sound.setnchannels(1); sound.setsampwidth(1); sound.setframerate(8000)
        sound.writeframes(bytes(range(100)))
    return out.getvalue()


def mdl_bytes():
    data = bytearray(244); data[:4] = b"IDST"
    struct.pack_into("<I", data, 4, 10); struct.pack_into("<I", data, 72, len(data))
    return bytes(data)


class ServerResourceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name); self.data = self.folder / "data"
        env = patch.dict(os.environ, {"CZM_DATA_DIR": str(self.data)})
        env.start(); self.addCleanup(env.stop); get_settings.cache_clear(); self.addCleanup(get_settings.cache_clear)
        db.init()
        self.source = self.folder / "game"; self.source.mkdir()
        self.asset("sound/music/round.wav", wav_bytes()); self.asset("models/player/test/test.mdl", mdl_bytes())
        api._read_limit.calls.clear()
        app = FastAPI(); app.include_router(api.router); app.include_router(api.download_router)
        self.client = TestClient(app); self.addCleanup(self.client.close)

    def asset(self, name, value):
        path = self.source / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(value)
        return path

    def publish(self, revision="r1"):
        return publisher.publish(self.source, "survival", revision)

    def configure(self, address="176.118.222.43:27016", visible=False):
        with db.db() as conn:
            official.update(conn, visible, address, "", 1)

    def activate(self, revision="r1", slot="survival"):
        with db.db() as conn:
            return resources.activate(conn, slot, "survival", revision)

    def catalog(self):
        answer = self.client.get("/api/v1/server-resources/catalog")
        self.assertEqual(answer.status_code, 200, answer.text)
        self.assertEqual(answer.headers["cache-control"], "no-store")
        return answer.json()

    def test_catalog_off_until_explicit_activation_independent_of_visibility(self):
        self.assertEqual(self.catalog(), {"schema": 1, "max_age_seconds": 60, "servers": [
            {"server_id": "survival", "address": "", "resources_enabled": False},
            {"server_id": "escape", "address": "", "resources_enabled": False}]})
        self.configure(); self.publish()
        self.assertFalse(self.catalog()["servers"][0]["resources_enabled"])
        self.activate(); slot = self.catalog()["servers"][0]
        self.assertTrue(slot["resources_enabled"])
        self.assertEqual((slot["server_id"], slot["pack_id"], slot["revision"]), ("survival", "survival", "r1"))
        self.assertEqual(slot["address"], "176.118.222.43:27016")
        with db.db() as conn:
            self.assertFalse(official.state(conn)["enabled"])
        self.assertFalse(self.catalog()["servers"][1]["resources_enabled"])

    def test_address_changes_keep_logical_slot_but_empty_address_revokes_eligibility(self):
        self.configure(); self.publish(); self.activate()
        self.configure("8.8.8.8:27015")
        slot = self.catalog()["servers"][0]
        self.assertEqual(slot["address"], "8.8.8.8:27015"); self.assertTrue(slot["resources_enabled"])
        self.configure("")
        self.assertEqual(self.catalog()["servers"][0], {"server_id": "survival", "address": "", "resources_enabled": False})

    def test_activation_requires_configured_known_slot_and_integrity(self):
        self.publish()
        with self.assertRaises(ValueError): self.activate()
        self.configure()
        with self.assertRaises(ValueError): self.activate(slot="attacker")
        file = resources.root() / "published/survival/r1/files"
        next(file.iterdir()).write_bytes(b"corrupt")
        with self.assertRaises(ValueError): self.activate()
        self.assertFalse(self.catalog()["servers"][0]["resources_enabled"])

    def test_disable_does_not_change_server_or_visibility(self):
        self.configure(visible=True); self.publish(); self.activate()
        with db.db() as conn: resources.disable(conn, "survival")
        self.assertFalse(self.catalog()["servers"][0]["resources_enabled"])
        with db.db() as conn:
            self.assertEqual(official.state(conn), {"enabled": True, "survival": "176.118.222.43:27016", "escape": ""})

    def test_manifest_missing_or_changed_fails_closed(self):
        self.configure(); self.publish(); self.activate()
        manifest = resources.root() / "published/survival/r1/manifest.json"
        original = manifest.read_bytes(); manifest.write_bytes(original + b" ")
        self.assertFalse(self.catalog()["servers"][0]["resources_enabled"])
        manifest.unlink()
        self.assertFalse(self.catalog()["servers"][0]["resources_enabled"])

    def test_import_ignores_private_and_executable_server_files_and_does_not_touch_source(self):
        private = self.asset("addons/amxmodx/configs/server.cfg", b"secret password")
        self.asset("server.cfg", b"server password"); self.asset("models/plugin.so", b"ELF executable")
        before = {p.relative_to(self.source).as_posix(): p.read_bytes() for p in self.source.rglob("*") if p.is_file()}
        receipt = self.publish()
        self.assertEqual(receipt["files"], 2)
        manifest = json.loads((Path(receipt["path"]) / "manifest.json").read_bytes())
        self.assertEqual({v["path"] for v in manifest["files"]}, {"sound/music/round.wav", "models/player/test/test.mdl"})
        with zipfile.ZipFile(Path(receipt["path"]) / "bundle.zip") as archive:
            self.assertEqual(set(archive.namelist()), {v["path"] for v in manifest["files"]})
            self.assertTrue(all(not i.is_dir() for i in archive.infolist()))
        after = {p.relative_to(self.source).as_posix(): p.read_bytes() for p in self.source.rglob("*") if p.is_file()}
        self.assertEqual(before, after); self.assertTrue(private.exists())
        self.assertEqual(publisher.verify_revision("survival", "r1", resources.root())["manifest_sha256"], receipt["manifest_sha256"])

    def test_same_revision_cannot_be_overwritten_and_failed_import_leaves_no_revision(self):
        first = self.publish(); old = (Path(first["path"]) / "manifest.json").read_bytes()
        with self.assertRaises(ValueError): self.publish()
        self.assertEqual((Path(first["path"]) / "manifest.json").read_bytes(), old)
        self.asset("models/fake.mdl", b"MZ executable renamed as model")
        with self.assertRaises(ValueError): self.publish("r2")
        self.assertFalse((resources.root() / "published/survival/r2").exists())
        self.assertEqual(list((resources.root() / "staging").iterdir()), [])

    def test_bounded_sizes_and_count_abort_atomically(self):
        for name, value in (("MAX_FILE_BYTES", 10), ("MAX_TOTAL_BYTES", 200), ("MAX_FILES", 1), ("MAX_MANIFEST_BYTES", 20)):
            with self.subTest(name=name), patch.object(resources, name, value), self.assertRaises(ValueError):
                self.publish(name.lower())
        self.assertEqual(list((resources.root() / "staging").iterdir()), [])

    def test_path_traversal_hidden_names_case_collisions_and_symlinks_rejected(self):
        for path in ("../server.cfg", "/models/a.mdl", "models/../a.mdl", "models//a.mdl", "models/.hidden/a.mdl", "models/a.mdl ", "models/a\\b.mdl", "models/тест.mdl"):
            with self.subTest(path=path), self.assertRaises(ValueError): resources.asset_path(path)
        self.asset("models/PLAYER/TEST/test.mdl", mdl_bytes())
        with self.assertRaises(ValueError): self.publish("case")
        shutil_path = self.source / "models/PLAYER/TEST/test.mdl"; shutil_path.unlink()
        linked = self.source / "sound/private.wav"; linked.symlink_to(self.source / "sound/music/round.wav")
        with self.assertRaises((ValueError, OSError)): self.publish("link")
        linked.unlink()
        (self.source / "sound/external").symlink_to(self.source / "models", target_is_directory=True)
        with self.assertRaises(ValueError): self.publish("dirlink")

    def test_empty_pack_is_not_a_fake_ready_revision(self):
        empty = self.folder / "empty"; empty.mkdir()
        with self.assertRaises(ValueError): publisher.publish(empty, "escape", "r1")
        self.assertFalse((resources.root() / "published/escape/r1").exists())

    def test_signature_validation_for_supported_formats(self):
        self.asset("maps/tiny.bsp", struct.pack("<I", 30) + bytes(120))
        spr = b"IDSP" + struct.pack("<I", 2) + bytes(32)
        self.asset("sprites/tiny.spr", spr)
        seq = bytearray(76); seq[:4] = b"IDSQ"; struct.pack_into("<I", seq, 4, 10); struct.pack_into("<I", seq, 72, 76)
        self.asset("models/player/test/test01.mdl", seq)
        self.asset("halflife.wad", b"WAD3" + struct.pack("<II", 0, 12))
        self.asset("sound/music/song.mp3", b"ID3\x04\x00\x00\x00\x00\x00\x00" + bytes(20))
        self.asset("sound/music/song.ogg", b"OggS\x00" + bytes(22))
        self.asset("gfx/env/sky.tga", bytes([0, 0, 2]) + bytes(9) + struct.pack("<HH", 1, 1) + bytes([24, 0, 0, 0, 0]))
        self.publish()
        for path in ("maps/no.bsp", "models/no.mdl", "sprites/no.spr", "root.wad", "sound/no.wav", "sound/no.mp3", "sound/no.ogg", "gfx/no.png", "gfx/no.bmp", "gfx/no.tga"):
            with self.subTest(path=path), self.assertRaises(ValueError): publisher.validate_format(path, b"MZ" + bytes(254), 256)

    def test_download_is_only_immutable_public_objects_and_supports_resume(self):
        self.publish()
        base = "/server-resources/survival/r1/"
        answer = self.client.get(base + "manifest.json")
        self.assertEqual(answer.status_code, 200)
        self.assertIn("immutable", answer.headers["cache-control"])
        self.assertEqual(answer.headers["x-content-type-options"], "nosniff")
        manifest = answer.json(); record = manifest["files"][0]
        full = self.client.get(base + "files/" + record["sha256"])
        self.assertEqual(hashlib.sha256(full.content).hexdigest(), record["sha256"])
        resumed = self.client.get(base + "files/" + record["sha256"], headers={"Range": "bytes=3-8"})
        self.assertEqual(resumed.status_code, 206); self.assertEqual(resumed.content, full.content[3:9])
        self.assertEqual(resumed.headers["content-range"], f"bytes 3-8/{record['size']}")
        for leaf in ("copy.part", "files/", "files/not-a-hash", "files/" + "a" * 64 + "/other", "server.cfg"):
            self.assertEqual(self.client.get(base + leaf).status_code, 404, leaf)
        self.assertEqual(self.client.get("/server-resources/staging/r1/manifest.json").status_code, 404)

    def test_archive_tampering_prevents_activation_and_init_preserves_assignments(self):
        self.configure(); receipt = self.publish()
        archive = Path(receipt["path"]) / "bundle.zip"
        original = archive.read_bytes(); archive.write_bytes(original + b"tamper")
        with self.assertRaises(ValueError): self.activate()
        archive.write_bytes(original); self.activate(); db.init()
        self.assertTrue(self.catalog()["servers"][0]["resources_enabled"])

    def test_manifest_and_archive_are_reproducible_for_same_inventory(self):
        first = self.publish()
        other_store = self.folder / "other-store"
        second = publisher.publish(self.source, "survival", "r1", other_store)
        self.assertEqual(first["manifest_sha256"], second["manifest_sha256"])
        self.assertEqual((Path(first["path"]) / "bundle.zip").read_bytes(), (Path(second["path"]) / "bundle.zip").read_bytes())

    def test_symlinked_published_objects_are_not_served(self):
        self.publish(); manifest = resources.root() / "published/survival/r1/manifest.json"
        raw = self.folder / "outside.json"; raw.write_bytes(manifest.read_bytes())
        manifest.unlink(); manifest.symlink_to(raw)
        self.assertEqual(self.client.get("/server-resources/survival/r1/manifest.json").status_code, 404)


if __name__ == "__main__":
    unittest.main()
