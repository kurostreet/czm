"""Exercise the actual data-only cache IO with files, hostile ZIPs and TLS transport adapters."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import struct
import zipfile

ROOT = Path(__file__).resolve().parents[1]
JAVA = ROOT / "android/app/src/main/java/ru/kurostreet/counterzombiemobile/ServerResourceStore.java"


class ServerResourceStoreTest(unittest.TestCase):
    def test_io(self):
        java = shutil.which("java")
        if not java:
            self.skipTest("Java runtime unavailable")
        compiler = [shutil.which("javac")] if shutil.which("javac") else [java, "com.sun.tools.javac.Main"]
        with tempfile.TemporaryDirectory(prefix="czm-resource-store-") as tmp:
            result = subprocess.run(compiler + ["-source", "11", "-target", "11", "-d", tmp, str(JAVA), str(ROOT / "tests/ServerResourceStoreTest.java")], text=True, capture_output=True)
            if result.returncode and "ClassNotFoundException: com.sun.tools.javac.Main" in result.stderr:
                self.skipTest("Java compiler unavailable")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            data = b"RIFF" + struct.pack("<I", 1234 - 8) + b"WAVE" + bytes((i * 13) & 255 for i in range(12, 1234))
            local64 = Path(tmp) / "publisher-local64.zip"
            with zipfile.ZipFile(local64, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                entry = zipfile.ZipInfo("sound/test.wav")
                entry.create_system = 3
                entry.external_attr = 0o100644 << 16
                with archive.open(entry, "w", force_zip64=True) as output:
                    output.write(data)
            raw = local64.read_bytes()
            end = len(raw) - 22
            central_size, central_offset = struct.unpack_from("<II", raw, end + 12)
            tail = bytearray(raw[end:])
            struct.pack_into("<II", tail, 12, 0xFFFFFFFF, 0xFFFFFFFF)
            record = struct.pack("<IQHHIIQQQQ", 0x06064B50, 44, 45, 45, 0, 0, 1, 1, central_size, central_offset)
            locator = struct.pack("<IIQI", 0x07064B50, 0, end, 1)
            global64 = Path(tmp) / "publisher-global64.zip"
            global64.write_bytes(raw[:end] + record + locator + tail)
            result = subprocess.run([java, "-cp", tmp, "ru.kurostreet.counterzombiemobile.ServerResourceStoreTest", str(Path(tmp) / "cache"), str(local64), str(global64)], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("checks passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
