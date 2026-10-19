"""Regression: CI applies patches before Gradle, and Gradle calls it again."""
import contextlib
import difflib
import importlib.util
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("engine_patches", Path(__file__).resolve().parents[1] / "scripts/apply_engine_patches.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class EnginePatchTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.engine = Path(temp.name) / "engine"
        self.engine.mkdir()
        self.patches = Path(temp.name) / "patches"
        self.patches.mkdir()
        self.file = self.engine / "screen.c"
        self.original = "int before;\nint loading;\nint after;\n"
        self.middle = "int before;\nint loading;\nint first_patch;\nint after;\n"
        self.final = "int before;\nint loading;\nint first_patch;\nint next_patch;\nint after;\n"
        self.file.write_text(self.original)
        self.git("init", "-q")
        self.git("add", "screen.c")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "base")
        for name, old, new in [("0001.patch", self.original, self.middle), ("0002.patch", self.middle, self.final)]:
            content = "diff --git a/screen.c b/screen.c\n" + "".join(difflib.unified_diff(
                old.splitlines(True), new.splitlines(True), fromfile="a/screen.c", tofile="b/screen.c"))
            (self.patches / name).write_text(content)
        no_sdl = Path(temp.name) / "no-sdl-patches"
        no_sdl.mkdir()
        scope = patch.multiple(module, ENGINE=self.engine, ENGINE_PATCHES=self.patches, SDL_PATCHES=no_sdl)
        scope.start()
        self.addCleanup(scope.stop)

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.engine, check=True, stdout=subprocess.DEVNULL)

    def apply(self):
        with contextlib.redirect_stdout(io.StringIO()):
            module.apply_engine_patches()

    def test_overlapping_context_is_idempotent(self):
        self.apply()
        self.apply()
        self.assertEqual(self.file.read_text(), self.final)

    def test_known_partial_sequence_can_continue(self):
        self.git("apply", str(self.patches / "0001.patch"))
        self.apply()
        self.assertEqual(self.file.read_text(), self.final)

    def test_unknown_work_is_preserved(self):
        self.apply()
        self.file.write_text(self.final + "int user_change;\n")
        with self.assertRaisesRegex(RuntimeError, "nothing was overwritten"):
            self.apply()
        self.assertEqual(self.file.read_text(), self.final + "int user_change;\n")


if __name__ == "__main__":
    unittest.main()
