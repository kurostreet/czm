"""Exercise shared-layout validation and the real UDP widget query on the JVM."""
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
JAVA = ROOT / "android/app/src/main/java/ru/kurostreet/counterzombiemobile"


class SettingsDataTests(unittest.TestCase):
    def test_client_server_schema_match(self):
        schema = json.loads((ROOT / "czm/settings_schema.json").read_text())
        self.assertEqual(schema, json.loads((ROOT / "server/czm/czm/settings_schema.json").read_text()))
        source = (JAVA / "SettingsSchema.java").read_text()
        for field, key in [("KEYS", "cvars"), ("COMMANDS", "commands")]:
            array = re.search(field+r"=\{(.*?)\}", source).group(1)
            self.assertEqual(schema[key], json.loads("["+array+"]"))
        native = (ROOT / "common/czm_settings_names.h").read_text()
        self.assertEqual(schema["cvars"], re.findall(r'"([^"\n]+)"', native))

    def test_every_editor_action_and_czm_preset_can_be_shared(self):
        commands = set(json.loads((ROOT / "czm/settings_schema.json").read_text())["commands"])
        for command in ("czm_props", "czm_lasermine", "czm_skill_g", "czm_skill_r", "+czm_skill_e"):
            self.assertIn(command, commands)

        def supported(command):
            return command in commands or re.fullmatch(r'say(?:_team)? [^";\\\x00-\x1f]{1,96}', command)

        source = (ROOT / "czm/menu/CzmTouch.cpp").read_text()
        catalogue = re.search(r'static const CzmAction s_actions\[\] =\s*\{(.*?)\n\};', source, re.S).group(1)
        actions = re.findall(r'\{\s*"[^"]+",\s*"[^"]+",\s*"[^"]+",\s*"([^"]+)"', catalogue)
        self.assertGreater(len(actions), 60)
        for command in actions:
            with self.subTest(catalogue=command):
                self.assertTrue(supported(command), "Editor action missing from shared-layout schema: " + command)

        # The current CZM schemes are shareable. Legacy third-party examples may
        # contain aliases or command scripts, which remain outside this data schema.
        presets = sorted((ROOT / "3rdparty/czm_project/touch_presets").glob("czm_scheme[123].cfg"))
        self.assertEqual(len(presets), 3)
        for preset in presets:
            for line in preset.read_text().splitlines():
                if not line.startswith("touch_addbutton "):
                    continue
                command = shlex.split(line)[3]
                with self.subTest(preset=preset.name, command=command):
                    self.assertTrue(supported(command))
        for fixture in sorted((ROOT / "scripts/layouts").glob("scheme*.json")):
            for buttons in json.loads(fixture.read_text())["layouts"].values():
                for button in buttons:
                    with self.subTest(fixture=fixture.name, command=button[2]):
                        self.assertTrue(supported(button[2]))
        for command in ("czm_unknown", "czm_props;quit", "czm_lasermine\nquit", "+czm_skill_e\nquit",
                        "czm_props 1", "czm_lasermine arbitrary", "exec stolen.cfg", "czm_fort_buttons"):
            with self.subTest(rejected=command):
                self.assertFalse(supported(command))

    def test_safe_layouts_and_udp_challenge(self):
        jar = os.environ.get("CZM_JSON_JAR", "/missing")
        java = shutil.which("java")
        if not java or not Path(jar).is_file():
            self.skipTest("Java runtime and JSON jar required")
        javac = shutil.which("javac")
        compiler = [javac] if javac else [java, "com.sun.tools.javac.Main"]
        language = ["--release", "11"] if javac else ["-source", "11", "-target", "11"]
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            stub = folder / "CzmNet.java"
            stub.write_text('package ru.kurostreet.counterzombiemobile; public class CzmNet { public static String gameDir(){return System.getProperty("czm.test.dir","");} }')
            files = [JAVA / (name+".java") for name in ["SettingsSchema", "SettingsData", "ServerQuery"]]
            tests = ["SettingsDataTest", "ServerQueryTest"]
            compiled = subprocess.run(compiler + language + ["-encoding", "UTF-8", "-cp", jar, "-d", temporary,
                                     str(stub)]+[str(f) for f in files]+[str(ROOT/"tests"/(t+".java")) for t in tests],
                                      capture_output=True, text=True)
            if compiled.returncode and "ClassNotFoundException: com.sun.tools.javac.Main" in compiled.stderr:
                self.skipTest("Java compiler unavailable")
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            for test in tests:
                result = subprocess.run([java, "-Dczm.test.dir="+temporary, "-Dczm.test.repo="+str(ROOT),
                                         "-cp", temporary+os.pathsep+jar,
                                         "ru.kurostreet.counterzombiemobile."+test],
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("_OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
