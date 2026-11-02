import hashlib
import io
import json
import os
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from czm import db, rustore
from czm.assemble import BuildError
from czm.config import get_settings

DATA = b"game data " * 1000
PACKAGE = "ru.kurostreet.counterzombiemobile".encode("utf-16-le")


def zip_bytes(entries: dict[str, bytes], stored: bool = False) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED) as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return out.getvalue()


def fake_apksigner(*args: str) -> str:
    """apksigner sign --out <out> <in>: the copy stands for the signed file; verify passes."""
    if args[0] == "sign":
        assert "--ks-pass" in args and args[args.index("--ks-pass") + 1] == "env:CZM_RUSTORE_KEY_PASSWORD"
        assert not any("secret" in a for a in args), "the password never goes into the arguments"
        shutil.copy(args[-1], args[args.index("--out") + 1])
    return ""


class RuStoreTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        env = patch.dict(os.environ, {"CZM_DATA_DIR": temp.name, "CZM_RUSTORE_KEY_PASSWORD": "secret"})
        env.start()
        self.addCleanup(env.stop)
        get_settings.cache_clear()
        self.addCleanup(get_settings.cache_clear)
        db.init()
        self.settings = get_settings()
        self.settings.apk_dir.mkdir()
        self.root = Path(temp.name)
        meta = json.dumps({"sha256": hashlib.sha256(DATA).hexdigest()}).encode()
        data_apk = self.settings.apk_dir / "CounterZombieMobile-1.35-old.apk"
        data_apk.write_bytes(zip_bytes({"AndroidManifest.xml": b"site", "assets/bundled/game-data.zip": DATA,
                                        "assets/bundled/game-data.json": meta, "META-INF/CERT.RSA": b"old"}, stored=True))
        with db.db() as conn:
            conn.execute("INSERT INTO releases(version,code,file,size,sha256,notes,created,published) VALUES (?,?,?,?,?,?,?,?)",
                         ("1.35-old", 1, data_apk.name, data_apk.stat().st_size, "b" * 64, "", 1, 1))

    def core(self, manifest: bytes = b"\x03\x00" + PACKAGE, dex: bytes = b"dex\nru/kurostreet") -> Path:
        path = self.root / "core.apk"
        path.write_bytes(zip_bytes({"AndroidManifest.xml": manifest, "classes.dex": dex, "lib/arm64-v8a/libxash.so": b"elf"}))
        return path

    def key(self):
        key = rustore.keystore_file()
        key.parent.mkdir(parents=True, exist_ok=True)
        key.write_bytes(b"pkcs12")

    def test_only_the_rustore_core_is_taken(self):
        site = "android.permission.REQUEST_INSTALL_PACKAGES".encode("utf-16-le")
        with self.assertRaisesRegex(BuildError, "ядро сайта"):
            rustore.check_core(self.core(manifest=PACKAGE + site))
        with self.assertRaisesRegex(BuildError, "Google Play"):
            rustore.check_core(self.core(dex=b"Lcom/google/android/play/core/appupdate;"))
        with self.assertRaisesRegex(BuildError, "нет пакета"):
            rustore.check_core(self.core(manifest=b"dev.gaming.czm"))
        rustore.check_core(self.core())

    def test_without_the_key_nothing_is_signed(self):
        with self.assertRaisesRegex(BuildError, "нет ключа RuStore"):
            rustore.assemble(self.core(), "1.35-abc1234")
        self.assertEqual(list(rustore.output_dir().glob("*.apk")), [])

    def test_the_apk_gets_the_game_data_and_stays_off_the_site(self):
        self.key()
        with patch.object(rustore, "CERT_SHA256", "c" * 64), patch.object(rustore, "apksigner", side_effect=fake_apksigner), \
                patch.object(rustore, "signer_digest", return_value="c" * 64):
            apk, digest = rustore.assemble(self.core(), "1.35-abc1234")
        self.assertEqual(digest, "c" * 64)
        self.assertEqual(apk, self.root / "rustore" / "CounterZombieMobile-1.35-abc1234-rustore.apk")
        self.assertFalse(str(apk).startswith(str(self.settings.apk_dir)), "players get it from RuStore, not from the site")
        with zipfile.ZipFile(apk) as z:
            self.assertEqual(z.read("assets/bundled/game-data.zip"), DATA)
            self.assertEqual(z.read("classes.dex"), b"dex\nru/kurostreet")
            self.assertNotIn("META-INF/CERT.RSA", z.namelist())
        line = (apk.parent / (apk.name + ".sha256")).read_text()
        self.assertEqual(line.split()[0], hashlib.sha256(apk.read_bytes()).hexdigest())
        self.assertEqual(sorted(p.name for p in apk.parent.iterdir()), sorted([apk.name, apk.name + ".sha256"]))

    def test_the_first_release_certificate_is_pinned(self):
        self.assertRegex(rustore.CERT_SHA256, r"^[0-9a-f]{64}$")

    def test_another_key_than_the_first_release_is_refused(self):
        self.key()
        with patch.object(rustore, "CERT_SHA256", "a" * 64), patch.object(rustore, "apksigner", side_effect=fake_apksigner), \
                patch.object(rustore, "signer_digest", return_value="c" * 64):
            with self.assertRaisesRegex(BuildError, "не тот"):
                rustore.assemble(self.core(), "1.35-abc1234")
        self.assertEqual(list(rustore.output_dir().iterdir()), [])

    def test_bad_versions_and_missing_data_are_refused(self):
        self.key()
        for version in ("", "../x", "1.35 abc", "-1"):
            with self.assertRaisesRegex(BuildError, "версия"):
                rustore.assemble(self.core(), version)
        for apk in self.settings.apk_dir.iterdir():
            apk.unlink()
        with self.assertRaisesRegex(BuildError, "игровыми файлами"):
            rustore.assemble(self.core(), "1.35-abc1234")


if __name__ == "__main__":
    unittest.main()
