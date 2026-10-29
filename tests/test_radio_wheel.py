"""Run the native radio wheel (czm/menu/CzmRadio.cpp): the slots, a slide from the touch button, taps and closing."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

STUB = r'''
#pragma once
#include <algorithm>
#include <cassert>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#define M_PI 3.14159265358979323846
typedef int HFont;
enum { CZMF_SHOP_NAME, CZMF_SMALL, CZMF_TILE_STATUS };
enum { QM_CENTER = 1, QM_TOP = 2, ETF_NO_WRAP = 4, ETF_FORCECOL = 8 };
enum { KEY_GAME, KEY_MENU };
template<class T> T Q_min( T a, T b ) { return a < b ? a : b; }
template<class T> T Q_max( T a, T b ) { return a > b ? a : b; }
#define bound( lo, v, hi ) ( std::max( (lo), std::min( (v), (hi) )))
inline unsigned PackRGBA( int r, int g, int b, int a ) { return r | g << 8 | b << 16 | (unsigned)a << 24; }
extern int ScreenWidth, ScreenHeight;
struct Point { int x, y; }; struct Size { int w, h; };
struct ClientStack { bool active = false; void *current = nullptr; bool IsActive() const { return active; } void *Current() const { return current; } };
struct UiStatic { int xOffset = 0, yOffset = 0, width = 1024, realTime = 0, cursorX = 0, cursorY = 0; ClientStack client; };
extern UiStatic uiStatic;
struct Stack { int count = 1; int Count() const { return count; } };
class CMenuBaseClientWindow {
public:
	CMenuBaseClientWindow( const char * ) {}
	virtual ~CMenuBaseClientWindow() {}
	virtual void Init() {} virtual void VidInit() {}
	virtual void Show() { shown = true; uiStatic.client.active = true; uiStatic.client.current = this; }
	virtual void Hide() { shown = false; uiStatic.client.active = false; uiStatic.client.current = nullptr; }
	virtual void Draw() {} virtual bool KeyDown( int ) { return false; } virtual bool KeyUp( int ) { return false; }
	virtual bool MouseMove( int, int ) { return false; }
	bool shown = false; Point pos; Size size; Stack stackStorage; Stack *m_pStack = &stackStorage;
};
namespace UI { namespace Key { inline bool IsEscape( int k ) { return k == 27; } inline bool IsLeftMouse( int k ) { return k == 1; } } }
extern std::vector<std::string> commands;
extern int keyDest;
struct EngFuncs {
	static void KEY_SetDest( int d ) { keyDest = d; }
	static void KEY_ClearStates() {}
	static void ClientCmd( bool, const char *s ) { commands.push_back( s ); }
	static void ClientCmdF( bool, const char *f, ... ) { char b[256]; va_list a; va_start( a, f ); vsnprintf( b, sizeof( b ), f, a ); va_end( a ); commands.push_back( b ); }
};
extern bool russian, active, trace;
inline bool CZM_IsRussian() { return russian; }
inline bool CL_IsActive() { return active; }
inline void CZM_PlayClick() {}
inline HFont CZM_Font( int id ) { return id; }
inline int CZM_FontHeight( HFont f ) { return ( f == CZMF_SMALL ? 17 : 21 ) * ScreenHeight / 768; }
inline int CZM_TextWidth( HFont f, const char *s ) { int n = 0; for( ; *s; s++ ) if(( *s & 0xc0 ) != 0x80 ) n++; return n * CZM_FontHeight( f ) * 56 / 100; }
inline unsigned CZM_White( int a = 255 ) { return PackRGBA( 255, 255, 255, a ); }
inline unsigned CZM_Grey() { return PackRGBA( 155, 166, 184, 255 ); }
void UI_FillRect( int x, int y, int w, int h, unsigned c );
void CZM_DrawImage( const char *p, int x, int y, int w, int h, unsigned c = 0xffffffff );
void CZM_DrawText( HFont f, int x, int y, int w, const char *s, unsigned c, int just = 0 );
void UI_DrawString( HFont f, int x, int y, int w, int h, const char *s, unsigned c, int ch, int just, int flags );
#define ADD_MENU3( cmd, type, fn ) static type *cmd = new type(); void fn( void )
'''

SCENARIOS = r'''
int ScreenWidth = 1536, ScreenHeight = 716, keyDest = KEY_GAME;
UiStatic uiStatic; std::vector<std::string> commands; bool russian = true, active = true, trace = false;
static bool inScreen( int x, int y, int w, int h ) { return x >= 0 && y >= 0 && x + w <= ScreenWidth && y + h <= ScreenHeight; }
void UI_FillRect( int x, int y, int w, int h, unsigned c ) { assert( w >= 0 && h >= 0 ); if( trace ) printf( "R\t%d\t%d\t%d\t%d\t%u\n", x, y, w, h, c ); }
void CZM_DrawImage( const char *p, int x, int y, int w, int h, unsigned c ) { assert( w > 0 && h > 0 ); if( !strstr( p, "wheel" )) assert( inScreen( x, y, w, h )); if( trace ) printf( "I\t%d\t%d\t%d\t%d\t%u\t%s\n", x, y, w, h, c, p ); }
void CZM_DrawText( HFont f, int x, int y, int w, const char *s, unsigned c, int j ) { assert( inScreen( x, y, w, CZM_FontHeight( f ))); if( trace ) printf( "T\t%d\t%d\t%d\t%d\t%u\t%d\t%s\n", x, y, w, CZM_FontHeight( f ), c, j, s ); }
void UI_DrawString( HFont, int x, int y, int w, int h, const char *s, unsigned c, int, int j, int ) { assert( inScreen( x, y, w, h )); if( trace ) printf( "T\t%d\t%d\t%d\t%d\t%u\t%d\t%s\n", x, y, w, h, c, j, s ); }
static CCzmRadio &w = *menu_czmradio;
static void point( int x, int y ) { uiStatic.cursorX = x; uiStatic.cursorY = y; }
static void centre( int slot ) { w.Layout(); float a = ( -90.0f + slot * 45.0f ) * M_PI / 180.0f; point( w.m_iX + cosf( a ) * w.m_iR * 0.64f, w.m_iY + sinf( a ) * w.m_iR * 0.64f ); }
static bool sent( const char *c ) { return std::find( commands.begin(), commands.end(), std::string( c )) != commands.end(); }
static void open() { commands.clear(); assert( CZM_RadioShow( 38 )); assert( w.shown && keyDest == KEY_MENU ); }
int main( int argc, char **argv ) {
	assert( !CZM_RadioShow( 28 ) && !CZM_RadioShow( 35 ) && !w.shown ); // buy menus and text radio menus stay as they are
	for( auto size : { std::pair<int,int>{ 1536, 716 }, { 2000, 932 }, { 960, 540 }, { 800, 360 }, { 1024, 768 } }) for( int lang = 0; lang < 2; lang++ ) {
		ScreenWidth = size.first; ScreenHeight = size.second; russian = lang == 0;
		open(); w.Layout();
		for( int i = 0; i < 8; i++ ) { centre( i ); assert( w.Slot( uiStatic.cursorX, uiStatic.cursorY ) == i && w.HitTest() == w.HIT_SLOT + i ); }
		point( w.m_iX, w.m_iY ); assert( w.HitTest() == w.HIT_HUB );
		point( 2, 2 ); assert( w.HitTest() == w.HIT_OUTSIDE );
		assert( w.m_iY - w.m_iR > 0 && w.m_iY + w.m_iR < ScreenHeight );
		w.Draw(); w.Hide();
	}
	ScreenWidth = 1536; ScreenHeight = 716; russian = true;
	// opened by the finger on the touch button: a plain tap leaves it open, even when it lands on a phrase
	open(); centre( 2 ); w.MouseMove( 0, 0 ); w.KeyUp( 1 ); assert( w.shown && commands.size() == 1 ); // only touch_setclientonly
	// then a tap on a phrase sends it and closes
	centre( 3 ); w.KeyDown( 1 ); w.KeyUp( 1 ); assert( !w.shown && sent( "coverme\n" ) && keyDest == KEY_GAME );
	// a slide from the button to a phrase and letting go there sends it
	open(); point( 100, 300 ); w.MouseMove( 0, 0 ); centre( 0 ); w.MouseMove( 0, 0 ); assert( w.m_iHover == 0 ); w.KeyUp( 1 );
	assert( !w.shown && sent( "enemyspot\n" ) );
	// pressed on one phrase and slid to another: the one under the finger goes
	open(); w.KeyUp( 1 ); centre( 6 ); w.KeyDown( 1 ); centre( 7 ); w.MouseMove( 0, 0 ); assert( w.m_iHover == 7 ); w.KeyUp( 1 );
	assert( sent( "holdpos\n" ) );
	// the thank-you goes to the chat in the menu language, the spray is drawn
	open(); w.KeyUp( 1 ); centre( 5 ); w.KeyDown( 1 ); w.KeyUp( 1 ); assert( sent( "say \"Спасибо!\"\n" ) );
	russian = false; open(); w.KeyUp( 1 ); centre( 5 ); w.KeyDown( 1 ); w.KeyUp( 1 ); assert( sent( "say \"Thanks!\"\n" ) ); russian = true;
	open(); w.KeyUp( 1 ); centre( 4 ); w.KeyDown( 1 ); w.KeyUp( 1 ); assert( sent( "impulse 201\n" ) );
	// the hub, a tap outside, Escape and a few quiet seconds close it without sending anything
	open(); w.KeyUp( 1 ); point( w.m_iX, w.m_iY ); w.KeyDown( 1 ); w.KeyUp( 1 ); assert( !w.shown && commands.size() == 2 );
	open(); w.KeyUp( 1 ); point( 2, 2 ); w.KeyDown( 1 ); w.KeyUp( 1 ); assert( !w.shown );
	open(); w.KeyDown( 27 ); assert( !w.shown );
	open(); uiStatic.realTime += 7000; w.Draw(); assert( !w.shown );
	// leaving the match closes it
	open(); active = false; w.Draw(); assert( !w.shown ); active = true;
	if( argc > 1 ) {
		std::string view = argv[1]; russian = view.find( "en" ) == std::string::npos;
		if( view.find( "wide" ) != std::string::npos ) { ScreenWidth = 2000; ScreenHeight = 932; }
		open(); w.KeyUp( 1 ); centre( 2 ); w.KeyDown( 1 ); trace = true; w.Draw();
	}
	puts( "RADIO_WHEEL_OK" );
}
'''


class RadioWheelTests(unittest.TestCase):
    def test_slots_slide_taps_and_closing(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            (p / "stub.h").write_text(STUB)
            for name in ["extdll_menu.h", "BaseMenu.h", "BaseClientWindow.h", "Utils.h", "keydefs.h", "CzmMenu.h"]:
                (p / name).write_text('#include "stub.h"\n')
            source = (ROOT / "czm/menu/CzmRadio.cpp").read_text()
            (p / "main.cpp").write_text("#include <cmath>\n" + source + SCENARIOS)
            exe = p / "radio"
            subprocess.run(["g++", "-std=c++11", "-Wall", "-Werror", "-Wno-unused-function", "-I" + folder,
                            str(p / "main.cpp"), "-o", str(exe)], check=True)
            result = subprocess.run([str(exe)], check=True, capture_output=True, text=True)
            self.assertIn("RADIO_WHEEL_OK", result.stdout)

    def test_the_radio_button_opens_it(self):
        menu = (ROOT / "cl_dll/menu.cpp").read_text()
        self.assertIn("case MENU_RADIOSELECTOR:\n\t\t\t// Counter Zombie Mobile: the radio wheel", menu)
        self.assertIn("CZM_RadioShow( menuType )", (ROOT / "scripts/brand_mainui.py").read_text())
        self.assertIn("czm/menu/CzmRadio.cpp", (ROOT / "cmake/CzmBranding.cmake").read_text())
        self.assertTrue((ROOT / "3rdparty/cs16client-extras/gfx/czm/ui/icon_spray.png").is_file())


if __name__ == "__main__":
    unittest.main()
