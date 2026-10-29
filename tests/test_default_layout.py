"""The default layout for new players comes from scripts/layouts/scheme1.json (made in the game):
the scheme 1 preset, the HUD defaults in common/czm_hud_layout.h and the style cvars agree with it."""
from pathlib import Path
import json
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAYOUT = json.loads((ROOT / "scripts/layouts/scheme1.json").read_text())

DUMP = r'''
#include "czm_hud_layout.h"
#include <cstdio>
int main()
{
	for( int i = 0; i < CzmHud::BLOCKS; i++ )
		printf( "%s %.6f %.6f %.6f %d\n", CzmHud::keys[i], CzmHud::defaults[i][0], CzmHud::defaults[i][1], CzmHud::defaultScale[i], CzmHud::defaultHidden[i] ? 1 : 0 );
	printf( "styles %d %d %d\n", CzmHud::defaultHudStyle, CzmHud::defaultRadarStyle, CzmHud::defaultMessageStyle );
	return 0;
}
'''


class DefaultLayoutTests(unittest.TestCase):
    def test_scheme1_preset_is_the_shared_layout_with_round_buttons(self):
        self.check_preset(1, LAYOUT)

    def test_scheme2_preset_is_the_owners_layout(self):
        # 29.10.2026: the owner's layout with the weapon wheel is the default of scheme 2
        layout = json.loads((ROOT / "scripts/layouts/scheme2.json").read_text())
        self.check_preset(2, layout)
        self.assertIn("_czmwheel weapons", [button[2] for button in layout["layouts"]["2"]])

    def check_preset(self, number, layout):
        lines = [l for l in (ROOT / f"3rdparty/cs16client-extras/touch_presets/czm_scheme{number}.cfg").read_text().splitlines()
                 if l.startswith("touch_addbutton")]
        buttons = layout["layouts"][str(number)]
        self.assertEqual(len(lines), len(buttons))
        for line, button in zip(lines, buttons):
            t = shlex.split(line)
            self.assertEqual(t[1:4], button[:3])
            for a, b in zip(map(float, t[4:8]), button[3:7]):
                self.assertAlmostEqual(a, b, places=5)
            self.assertEqual(list(map(int, t[8:13])), button[7:12])
            textured = bool(button[1]) and not button[1].startswith("#")
            self.assertEqual(t[13:] == ["1"], textured, line)

    def test_hud_defaults_match_the_shared_layout(self):
        if not shutil.which("g++"):
            self.skipTest("g++ required")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path / "dump.cpp").write_text(DUMP)
            subprocess.run(["g++", "-std=c++11", "-I" + str(ROOT / "common"), str(path / "dump.cpp"), "-o", str(path / "dump")], check=True)
            out = subprocess.check_output([str(path / "dump")], text=True).splitlines()
        cvars = LAYOUT["cvars"]
        for line in out[:-1]:
            key, x, y, scale, hidden = line.split()
            self.assertAlmostEqual(float(x), float(cvars[f"czm_hud_{key}_x"]), places=5, msg=key)
            self.assertAlmostEqual(float(y), float(cvars[f"czm_hud_{key}_y"]), places=5, msg=key)
            self.assertAlmostEqual(float(scale), float(cvars[f"czm_hud_{key}_scale"]), places=5, msg=key)
            self.assertEqual(int(hidden), int(float(cvars[f"czm_hud_{key}_hidden"])), key)
        hud, radar, msg = map(int, out[-1].split()[1:])
        self.assertEqual((hud, radar, msg), (int(cvars["czm_hud_style"]), int(cvars["czm_hud_radar_style"]), int(cvars["czm_hud_msg_style"])))
        menu = (ROOT / "czm/menu/CzmMenu.cpp").read_text()
        for name, value in (("czm_hud_style", hud), ("czm_hud_radar_style", radar), ("czm_hud_msg_style", msg)):
            self.assertRegex(menu, r'CvarRegister\( "%s", "%d"' % (name, value))


if __name__ == "__main__":
    unittest.main()
