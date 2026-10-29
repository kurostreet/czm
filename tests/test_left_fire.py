"""The second fire button on the left (patch czm-left-fire): always, only in the scope, or never."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches/xash3d-fwgs/0028-czm-left-fire.patch"

PROGRAM = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
typedef int qboolean;
typedef unsigned int uint;
#define true 1
#define false 0
#define FBitSet( a, b ) (( a ) & ( b ))
#define TOUCH_FL_HIDE 1
#define Q_strcmp strcmp
typedef struct touch_button_s { char command[64]; float x1, y1, x2, y2; int flags, finger; struct touch_button_s *next; } touch_button_t;
typedef struct { touch_button_t *first; } touchbuttonlist_t;
typedef struct { const char *name; float value; } convar_t;
static struct { touchbuttonlist_t list_user; } touch;
static struct { uint framecount; } host;
static struct { struct { float scr_fov; } local; } cl;
static convar_t mode = { "czm_fire_left", 0 };
static float defaultFov = 90;
static convar_t *Cvar_FindVar( const char *name ) { return !strcmp( name, mode.name ) ? &mode : NULL; }
static float Cvar_VariableValue( const char *name ) { return !strcmp( name, "default_fov" ) ? defaultFov : 0; }
FUNCTIONS
static touch_button_t left = { "+attack", .0f, .36f, .11f, .60f, 0, -1 }, right = { "+attack", .82f, .70f, .92f, .90f, 0, -1 }, jump = { "+jump", .9f, .4f, 1, .6f, 0, -1 };
static qboolean hidden( touch_button_t *b ) { host.framecount++; return Touch_CzmLeftFireHidden( b ); }
int main( void ) {
	touch.list_user.first = &left; left.next = &right; right.next = &jump;
	cl.local.scr_fov = 90;
	// always: nothing hidden
	assert( !hidden( &left ) && !hidden( &right ));
	// only in the scope
	mode.value = 1;
	assert( hidden( &left ) && !hidden( &right ) && !hidden( &jump ));
	cl.local.scr_fov = 40; assert( !hidden( &left ));
	cl.local.scr_fov = 10; assert( !hidden( &left ));
	cl.local.scr_fov = 0; assert( hidden( &left ));   // nothing reported yet: the open view
	defaultFov = 100; cl.local.scr_fov = 90; assert( !hidden( &left )); defaultFov = 90;
	// a finger on it keeps it until lifted (its "-attack" must still go out)
	cl.local.scr_fov = 90; left.finger = 3; assert( !hidden( &left )); left.finger = -1; assert( hidden( &left ));
	// never
	mode.value = 2; cl.local.scr_fov = 40; assert( hidden( &left ) && !hidden( &right ));
	// a lone fire button is never taken away, wherever it is
	right.flags = TOUCH_FL_HIDE; assert( !hidden( &left )); right.flags = 0;
	touch.list_user.first = &left; left.next = &jump; assert( !hidden( &left ));
	puts( "LEFT_FIRE_OK" );
	return 0;
}
'''


class LeftFireTests(unittest.TestCase):
    def test_left_fire_button_visibility(self):
        patch = PATCH.read_text()
        added = "\n".join(line[1:] for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++"))
        start = added.index("static qboolean Touch_CzmFireRight( void )")
        end = added.index("\tif( Touch_CzmLeftFireHidden( button ))")
        functions = added[start:end]
        functions = functions[:functions.rindex("}") + 1]
        self.assertIn("\tif( Touch_CzmLeftFireHidden( button ))\n\t\treturn false;", added)
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            (p / "main.c").write_text(PROGRAM.replace("FUNCTIONS", functions))
            subprocess.run(["gcc", "-std=gnu11", "-Wall", "-Werror", str(p / "main.c"), "-o", str(p / "fire")], check=True)
            self.assertIn("LEFT_FIRE_OK", subprocess.run([str(p / "fire")], check=True, capture_output=True, text=True).stdout)

    def test_settings_and_cloud_know_it(self):
        settings = (ROOT / "czm/menu/CzmSettings.cpp").read_text()
        for cvar in ("czm_fire_left", "czm_scope_mode", "czm_sniper_release"):
            self.assertIn('"%s"' % cvar, settings)
            self.assertIn('"%s"' % cvar, (ROOT / "czm/settings_schema.json").read_text())
            self.assertIn('pfnRegisterVariable( "%s"' % cvar, (ROOT / "cl_dll/input/czm_shooting.cpp").read_text())
        self.assertTrue(re.search(r'"s_fire_left", "s_fire_left_hint0", GetFireLeft, SetFireLeft', settings))


if __name__ == "__main__":
    unittest.main()
