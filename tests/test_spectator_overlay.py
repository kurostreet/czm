"""The spectator overlay looks and the download indicator stay on any screen, with any name."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

HARNESS = r'''
#include "czm_hud_overlay.h"
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <initializer_list>
static float SW, SH;
static int calls;
static void In( float x, float y, float w, float h )
{
	assert( std::isfinite( x + y + w + h ) && w >= 0 && h >= 0 );
	assert( x >= -1 && y >= -1 && x + w <= SW + 1 && y + h <= SH + 1 );
	calls++;
}
static bool Utf8( const char *s )
{
	for( const unsigned char *p = (const unsigned char *)s; *p; )
	{
		int n = *p < 0x80 ? 0 : ( *p & 0xe0 ) == 0xc0 ? 1 : ( *p & 0xf0 ) == 0xe0 ? 2 : ( *p & 0xf8 ) == 0xf0 ? 3 : -1;
		if( n < 0 ) return false;
		for( p++; n--; p++ ) if(( *p & 0xc0 ) != 0x80 ) return false;
	}
	return true;
}
struct Check : CzmHud::Canvas
{
	int lh;
	Check( int l ) : lh( l ) {}
	void Blend( int x, int y, int w, int h, int, int, int, int a ) override { assert( a >= 0 && a <= 255 ); In( x, y, w, h ); }
	void Glyphs( float x, float y, float h, const char *s, int, int, int, float ) override
	{
		for( const char *c = s; *c; c++ ) assert( *c >= 32 && *c <= 95 ); // only what the atlas has
		In( x, y, CzmHud::GlyphWidth( s, h ), h );
	}
	int LabelWidth( const char *s ) override { int n = 0; for( ; *s; s++ ) if(( *s & 0xc0 ) != 0x80 ) n++; return n * lh / 2; }
	int LabelHeight() override { return lh; }
	void Label( int x, int y, const char *s, int, int, int ) override { assert( Utf8( s )); In( x, y, LabelWidth( s ), lh ); }
	bool Avatar( int x, int y, int size ) override { In( x, y, size, size ); return size % 2; }
};
int main()
{
	const float screens[][2] = { { 640, 360 }, { 1600, 720 }, { 2000, 932 }, { 2340, 1080 }, { 2000, 1200 }, { 1024, 768 } };
	const int lines[] = { 8, 16, 26, 40 };
	const char *names[] = { "Big-Show", "", "Свага", "[Xash3D]AURA TILAPUDO???",
		"ОченьДлинныйНикИгрокаКоторыйНеВлезаетНаКарточкуНикакИНикогда", "a{b}", "Zombie_Killer_2000_Pro_Max_Ultra_Edition_X" };
	for( auto &s : screens ) for( int lh : lines ) for( const char *name : names ) for( int style = -1; style <= 3; style++ )
		for( int hp : { -1, 0, 7, 73, 100, 2400 } )
		{
			SW = s[0]; SH = s[1];
			Check c( lh );
			CzmHud::SpecInfo info = { name, hp % 3, hp, 12, 105, hp < 0 ? "" : "12:45", "Наблюдение", hp != 0 };
			CzmHud::PaintSpectator( c, style, SW, SH, info );
			for( float x : { -1.f, 0.f, .5f, 1.f, 3.f, NAN } ) for( float k : { .1f, 1.f, 9.f } )
			{
				CzmHud::Rect p = CzmHud::DownloadLayout( SW, SH, x, x, k, k, lh );
				CzmHud::PaintDownload( c, p, name[0] ? name : "Файлы сервера: 2", hp );
			}
		}
	// the card stays narrow so the buttons around the bottom middle keep their places
	{
		SW = 2000; SH = 932;
		Check c( 26 );
		CzmHud::SpecInfo info = { "Big-Show", 2, 73, 3, 5, "1:45", "Наблюдение", true };
		CzmHud::PaintSpectator( c, CzmHud::SPEC_CARD, SW, SH, info );
	}
	char out[64];
	assert( CzmHud::AtlasName( "Big-Show", out, sizeof( out )) && !strcmp( out, "BIG-SHOW" ));
	assert( !CzmHud::AtlasName( "Свага", out, sizeof( out )));
	assert( !CzmHud::AtlasName( "a{b}", out, sizeof( out )));
	Check c( 10 );
	char fit[160];
	CzmHud::Fit( c, "Свага Свага Свага", 40, fit, sizeof( fit ));
	assert( Utf8( fit ) && c.LabelWidth( fit ) <= 40 && strstr( fit, "..." ));
	CzmHud::Fit( c, "Свага", 1, fit, sizeof( fit ));
	assert( !fit[0] );
	CzmHud::Rect d = CzmHud::DownloadLayout( 2000, 932, CzmHud::defaults[CzmHud::DOWNLOADS][0], CzmHud::defaults[CzmHud::DOWNLOADS][1], 1, 1, 20 );
	assert( fabsf( d.x + d.w / 2 - 1000 ) < 1 && d.y > 932 * .1f && d.y + d.h < 932 * .3f );
	printf( "OVERLAY_OK %d\n", calls );
	return 0;
}
'''


class SpectatorOverlayTests(unittest.TestCase):
    def test_overlay_geometry(self):
        if not shutil.which("g++"):
            self.skipTest("g++ required")
        with tempfile.TemporaryDirectory(prefix="czm-overlay-") as folder:
            path = Path(folder)
            (path / "check.cpp").write_text(HARNESS)
            subprocess.run(["g++", "-std=c++11", "-Wall", "-Wextra", "-Werror", "-I" + str(ROOT / "common"),
                            str(path / "check.cpp"), "-o", str(path / "check")], check=True)
            result = subprocess.run([str(path / "check")], check=True, capture_output=True, text=True)
            self.assertIn("OVERLAY_OK", result.stdout)

    def test_hooked_into_the_game_and_the_menu(self):
        spectator = (ROOT / "cl_dll/hud/spectator_gui.cpp").read_text()
        self.assertIn("CZM_SpectatorDraw(", spectator)
        self.assertIn("if( !czm )", spectator)
        self.assertIn("CZM_DownloadsDraw();", (ROOT / "cl_dll/hud_redraw.cpp").read_text())
        menu = (ROOT / "czm/menu/CzmMenu.cpp").read_text()
        self.assertIn('CvarRegister( "czm_hud_spec_style", "1"', menu)
        self.assertIn("ROW_SPECSTYLE", (ROOT / "czm/menu/CzmSettings.cpp").read_text())
        engine = (ROOT / "patches/xash3d-fwgs/0018-czm-download-indicator.patch").read_text()
        self.assertIn("&& host.allow_console", engine)
        self.assertIn("czm_download_files", engine)


if __name__ == "__main__":
    unittest.main()
