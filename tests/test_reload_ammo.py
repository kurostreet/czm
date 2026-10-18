"""The clip on the reload button: the client publishes it, the engine patch draws it."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches/xash3d-fwgs/0015-czm-reload-ammo.patch"

ENGINE_STUB = r'''
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
typedef unsigned char byte; typedef unsigned int uint;
#define bound(lo,v,hi) ((v)>=(lo)?((v)<(hi)?(v):(hi)):(lo))
#define Q_min(a,b) ((a)<(b)?(a):(b))
#define Q_max(a,b) ((a)>(b)?(a):(b))
#define ARRAYSIZE(a) (sizeof(a)/sizeof((a)[0]))
#define M_PI_F 3.14159265f
#define M_PI2_F 6.2831853f
#define TF_IMAGE 1
#define XASH_TEXTURE0 0
#define REF_WHITE_TEXTURE "*white"
#define TRI_QUADS 7
enum { kRenderNormal, kRenderTransColor, kRenderTransTexture };
#define Q_snprintf snprintf
#define Q_strcmp strcmp
#define Q_strlen strlen
#define TO_SCRN_X(x) ((x)*1000.0f)
#define TO_SCRN_Y(y) ((y)*500.0f)
struct { int height = 500; } refState;
struct { double realtime = 0; } host;
struct { std::string value; const char *string; } czm_ammo_state_holder;
struct Cvar { const char *string; } czm_ammo_state = { "" };
struct touch_button_t { float x1, y1, x2, y2; char command[64]; char texture[64]; float fade; bool visible; touch_button_t *next; };
struct touchbuttonlist_t { touch_button_t *first; };
static bool Touch_IsVisible( touch_button_t *b ) { return b->visible; }
static int R_GetBuiltinTexture( const char * ) { return 99; }
struct Pic { float x, y, w, h, s1, t1, s2, t2; int tex; byte r, g, b, a; };
static std::vector<Pic> pics; static std::vector<std::vector<float>> quads; static std::vector<float> vertex;
static byte cr, cg, cb, ca; static int loads;
struct Ref {
	int ( *GL_LoadTexture )( const char *, const byte *, size_t, int );
	void ( *Color4ub )( byte, byte, byte, byte );
	void ( *R_DrawStretchPic )( float, float, float, float, float, float, float, float, int );
	void ( *GL_SetRenderMode )( int );
	void ( *GL_Bind )( int, unsigned int );
	void ( *Begin )( int );
	void ( *End )( void );
	void ( *Vertex3f )( float, float, float );
};
static int Load( const char *path, const byte *, size_t, int ) { loads++; return strstr( path, "hud_glyphs" ) ? 5 : 6; }
static void Color( byte r, byte g, byte b, byte a ) { cr = r; cg = g; cb = b; ca = a; }
static void Stretch( float x, float y, float w, float h, float s1, float t1, float s2, float t2, int tex ) { pics.push_back({ x, y, w, h, s1, t1, s2, t2, tex, cr, cg, cb, ca }); }
static void Mode( int ) {}
static void Bind( int, unsigned int ) {}
static void Begin( int ) {}
static void End( void ) {}
static void Vertex( float x, float y, float ) { vertex.push_back( x ); vertex.push_back( y ); if( vertex.size() == 8 ) { vertex.push_back( cr ); vertex.push_back( cg ); vertex.push_back( ca ); quads.push_back( vertex ); vertex.clear(); } }
struct { Ref dllFuncs; } ref = {{ Load, Color, Stretch, Mode, Bind, Begin, End, Vertex }};
'''

HARNESS = r'''
static touch_button_t Button( const char *command, const char *texture )
{
	touch_button_t b = {};
	b.x1 = 0.7f; b.y1 = 0.7f; b.x2 = 0.76f; b.y2 = 0.82f; // 60 x 60 px
	strcpy( b.command, command ); strcpy( b.texture, texture ); b.fade = 1; b.visible = true;
	return b;
}
static void Run( const char *state, touch_button_t *first )
{
	pics.clear(); quads.clear(); czm_ammo_state.string = state;
	touchbuttonlist_t list = { first };
	Touch_CzmDrawAmmo( &list );
}
int main()
{
	touch_button_t reload = Button( "+reload", "gfx/czm/touch/reload" ), jump = Button( "+jump", "gfx/czm/touch/jump" );
	reload.next = &jump;

	Run( "", &reload );
	assert( pics.empty() && quads.empty());

	// a full clip: every tick lit and green, the digits "30" big and "/90" small
	Run( "30 90 30", &reload );
	assert( quads.size() == 30 );
	for( auto &q : quads ) assert( q[9] > 200 && q[8] < 120 ); // green, opaque
	int glyphs = 0;
	for( auto &p : pics ) if( p.tex == 5 ) glyphs++;
	assert( glyphs == 5 );
	for( auto &p : pics ) { assert( p.x >= 600 && p.x + p.w <= 860 ); assert( p.y + p.h <= 500 ); }

	// three rounds of thirty: three ticks lit, red-orange
	Run( "3 60 30", &reload );
	int lit = 0;
	for( auto &q : quads ) if( q[10] > 200 ) lit++;
	assert( lit == 3 );
	assert( quads[0][8] == 255 && quads[0][9] < 120 );

	// empty: nothing lit, the plate is red
	Run( "0 0 30", &reload );
	lit = 0;
	for( auto &q : quads ) if( q[10] > 200 ) lit++;
	assert( lit == 0 );

	// a 100-round machine gun keeps the ring readable
	Run( "100 200 100", &reload );
	assert( quads.size() == 30 );

	// hidden or text buttons, and a broken state, draw nothing
	reload.visible = false; Run( "30 90 30", &reload ); assert( pics.empty());
	reload.visible = true; strcpy( reload.texture, "#text" ); Run( "30 90 30", &reload ); assert( pics.empty());
	strcpy( reload.texture, "gfx/czm/touch/reload" ); Run( "abc", &reload ); assert( pics.empty());
	Run( "5 10 0", &reload ); assert( pics.empty());

	// textures load once
	assert( loads == 2 );
	return 0;
}
'''

CLIENT_HARNESS = r'''
#include <cassert>
#include <cstring>
#include <string>
struct Hud { bool m_fPlayerDead; } gHUD;
static std::string published; static int sets;
struct Engine { void ( *Cvar_Set )( const char *, const char * ); } gEngfuncs;
static void Set( const char *name, const char *value ) { assert( !strcmp( name, "czm_ammo_state" )); published = value; sets++; }
#define CZM_HUD_TEST 1
'''

CLIENT_MAIN = r'''
static void Frame( int weapon, int clip, int reserve )
{
	CZM_AmmoFrameBegin();
	if( weapon >= 0 ) CZM_AmmoReport( weapon, clip, reserve );
	CZM_AmmoFrameEnd();
}
int main()
{
	gEngfuncs.Cvar_Set = Set;
	CZM_AmmoReset();
	Frame( 28, 30, 90 ); assert( published == "30 90 30" );      // AK-47
	Frame( 28, 29, 90 ); assert( published == "29 90 30" );
	int before = sets; Frame( 28, 29, 90 ); assert( sets == before ); // unchanged: no cvar write
	Frame( 29, -1, 0 ); assert( published == "" );               // knife has no clip
	Frame( -1, 0, 0 ); assert( published == "" );                // nothing reported
	Frame( 28, 50, 100 ); assert( published == "50 100 50" );    // a server with bigger clips
	Frame( 28, 20, 100 ); assert( published == "20 100 50" );
	CZM_AmmoReset();
	Frame( 28, 20, 100 ); assert( published == "20 100 30" );    // a new map forgets them
	gHUD.m_fPlayerDead = true; Frame( 28, 20, 100 ); assert( published == "" );
	return 0;
}
'''


class ReloadAmmoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("g++"):
            raise unittest.SkipTest("g++ required")

    def build(self, source):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path / "main.cpp").write_text(source)
            subprocess.run(["g++", "-std=c++11", "-w", "-I" + str(path), str(path / "main.cpp"), "-o", str(path / "run")], check=True)
            subprocess.run([str(path / "run")], check=True)

    def test_engine_draws_ring_and_plate_on_reload_buttons_only(self):
        added = "\n".join(line[1:] for line in PATCH.read_text().splitlines() if line.startswith("+") and not line.startswith("+++"))
        start = added.index("static int czm_ammo_glyphs")
        code = added[start:added.index("\tif( touch.state == state_none )")]
        self.assertIn("Touch_CzmDrawAmmo( &touch.list_user )", added)
        self.assertIn('CVAR_DEFINE_AUTO( czm_ammo_state, "", FCVAR_PRIVILEGED', added)
        self.build(ENGINE_STUB + code + HARNESS)

    def test_client_publishes_clip_reserve_and_full_clip(self):
        source = (ROOT / "cl_dll/hud/czm_ammo.cpp").read_text()
        source = re.sub(r'#include "[^"]+"\n', "", source)
        prototypes = "void CZM_AmmoReset();void CZM_AmmoFrameBegin();void CZM_AmmoReport(int,int,int);void CZM_AmmoFrameEnd();\n"
        self.build(CLIENT_HARNESS + "#include <cstdio>\n" + prototypes + source + CLIENT_MAIN)


if __name__ == "__main__":
    unittest.main()
