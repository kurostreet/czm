"""Run the CZM radar painter: the plate, the marks and the compass stay on the screen and inside the radar."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_game_hud import STUB

ROOT = Path(__file__).resolve().parents[1]

HARNESS = r'''
#include "hud.h"
#include "czm_hud.h"
#include <cassert>
#include <cmath>
#include <cstdlib>
#include <cstring>
Hud gHUD = { 1 }; int ScreenWidth, ScreenHeight, g_iXash = 1;
static float rx, ry, rscale, rstyle, rhidden;
float Float( const char *s )
{
	if( !strcmp( s, "czm_hud_radar_style" )) return rstyle;
	if( !strcmp( s, "czm_hud_radar_x" )) return rx;
	if( !strcmp( s, "czm_hud_radar_y" )) return ry;
	if( !strcmp( s, "czm_hud_radar_scale" )) return rscale;
	if( !strcmp( s, "czm_hud_radar_hidden" )) return rhidden;
	return 1;
}
const char *String( const char * ) { return "1"; }
static int quads, texture, plateTexture; static float minX, minY, maxX, maxY;
static float vx[4], vy[4]; static int vertices;
void Mode( int ) {} void Color( float, float, float, float ) {} void Begin( int ) { vertices = 0; }
void UV( float, float ) {}
void Vertex( float x, float y, float ) { assert( std::isfinite( x ) && std::isfinite( y )); vx[vertices] = x; vy[vertices] = y; vertices++; }
void End()
{
	assert( vertices == 4 ); quads++;
	for( int i = 0; i < 4; i++ ) { assert( vx[i] >= -1 && vy[i] >= -1 && vx[i] <= ScreenWidth + 1 && vy[i] <= ScreenHeight + 1 ); }
	if( texture == plateTexture ) { minX = vx[0]; minY = vy[0]; maxX = vx[2]; maxY = vy[2]; }
	else if( plateTexture ) for( int i = 0; i < 4; i++ ) { assert( vx[i] >= minX - 1 && vx[i] <= maxX + 1 && vy[i] >= minY - 1 && vy[i] <= maxY + 1 ); }
}
Tri tri = { Mode, Color, Begin, UV, Vertex, End }; Engine gEngfuncs = { Float, String, &tri };
static int nextTexture = 1;
int Load( const char *name, void *, int, int ) { int t = nextTexture++; if( strstr( name, "radar_" ) && !plateTexture ) {} return t; }
void Select( int ) {} void Bind( int, int t ) { texture = t; } Render gRenderAPI = { Load, Select, Bind };
void FillRGBA( int, int, int, int, int, int, int, int ) {} void FillRGBABlend( int, int, int, int, int, int, int, int ) {}
void CZM_AmmoReset() {}
int main( int argc, char **argv )
{
	ScreenWidth = atoi( argv[1] ); ScreenHeight = atoi( argv[2] );
	rx = atof( argv[3] ); ry = atof( argv[4] ); rscale = atof( argv[5] ); rstyle = atof( argv[6] ); rhidden = atof( argv[7] );
	CZM_HudVidInit(); // atlas 1, plates 2..4, marks 5..8
	plateTexture = 2 + (int)CzmHud::Clamp( rstyle, 0, 2, 0 );
	CzmRadarMark marks[] = {{ 1, 0, CZM_MARK_DOT, 255, 255, 255 }, { -1, 0, CZM_MARK_UP, 255, 255, 255 }, { 0, 1, CZM_MARK_DOWN, 255, 0, 0 },
		{ 0, -1, CZM_MARK_X, 255, 0, 0 }, { .7f, -.7f, CZM_MARK_DOT, 0, 0, 255 }};
	int labelX, labelY;
	assert( CZM_RadarDraw( 37.f, marks, 5, &labelX, &labelY ));
	if( rhidden > .5f ) { assert( quads == 0 && labelY == -1 ); return 0; }
	assert( quads >= 6 );
	assert( labelX >= 0 && labelX <= ScreenWidth && labelY >= 0 && labelY <= ScreenHeight );
	return 0;
}
'''


class RadarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("g++"):
            raise unittest.SkipTest("g++ required")
        cls.temp = tempfile.TemporaryDirectory()
        root = Path(cls.temp.name)
        (root / "hud.h").write_text(STUB)
        for name in ["cl_util.h", "draw_util.h", "triangleapi.h"]:
            (root / name).write_text("")
        (root / "main.cpp").write_text(HARNESS)
        cls.exe = root / "radar"
        subprocess.run(["g++", "-std=c++11", "-w", "-I" + str(root), "-I" + str(ROOT / "cl_dll/hud"), str(root / "main.cpp"),
                        str(ROOT / "cl_dll/hud/czm_hud.cpp"), str(ROOT / "cl_dll/hud/czm_radar.cpp"), "-o", str(cls.exe)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_every_style_size_and_place_stays_on_screen(self):
        for w, h in [(640, 360), (1600, 720), (2340, 1080), (2000, 1200)]:
            for x, y in [(0, 0), (.01, .01), (.5, .5), (.99, .99), (2, -3), (float("nan"), .5)]:
                for scale in [.1, .6, 1, 2, 9, float("nan")]:
                    for style in [0, 1, 2, 7]:
                        with self.subTest(w=w, h=h, x=x, y=y, scale=scale, style=style):
                            subprocess.run([str(self.exe), str(w), str(h), str(x), str(y), str(scale), str(style), "0"], check=True)

    def test_hidden_radar_draws_nothing(self):
        subprocess.run([str(self.exe), "2340", "1080", ".1", ".1", "1", "0", "1"], check=True)


if __name__ == "__main__":
    unittest.main()
