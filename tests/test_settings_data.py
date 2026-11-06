"""Exercise shared-layout validation and the real UDP widget query on the JVM."""
import json
import os
from pathlib import Path
import re
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

    def test_safe_layouts_and_udp_challenge(self):
        jar = os.environ.get("CZM_JSON_JAR", "/missing")
        if not shutil.which("javac") or not Path(jar).is_file():
            self.skipTest("javac and JSON jar required")
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            stub = folder / "CzmNet.java"
            stub.write_text('package ru.kurostreet.counterzombiemobile; public class CzmNet { public static String gameDir(){return System.getProperty("czm.test.dir","");} }')
            files = [JAVA / (name+".java") for name in ["SettingsSchema", "SettingsData", "ServerQuery"]]
            tests = ["SettingsDataTest", "ServerQueryTest"]
            subprocess.run(["javac", "--release", "11", "-encoding", "UTF-8", "-cp", jar, "-d", temporary,
                            str(stub)]+[str(f) for f in files]+[str(ROOT/"tests"/(t+".java")) for t in tests], check=True)
            for test in tests:
                result = subprocess.run(["java", "-Dczm.test.dir="+temporary, "-cp", temporary+os.pathsep+jar,
                                         "ru.kurostreet.counterzombiemobile."+test], check=True,
                                        capture_output=True, text=True, timeout=10)
                self.assertIn("_OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
