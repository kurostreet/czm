"""Run the native wheels (czm/menu/CzmWheels.cpp): the touch wheels drawn over the game from the
engine's czm_wheel, the picks the engine sends, and the radio window for the console."""
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
#include <map>
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
struct MenuStack { bool active = false; bool IsActive() const { return active; } };
struct UiStatic { int xOffset = 0, yOffset = 0, width = 1024, realTime = 0, cursorX = 0, cursorY = 0; ClientStack client; MenuStack menu; };
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
extern std::vector<std::string> commands, args;
extern std::map<std::string, std::string> cvars;
extern int keyDest;
struct EngFuncs {
	static void KEY_SetDest( int d ) { keyDest = d; }
	static void KEY_ClearStates() {}
	static void ClientCmd( bool, const char *s ) { commands.push_back( s ); }
	static void ClientCmdF( bool, const char *f, ... ) { char b[256]; va_list a; va_start( a, f ); vsnprintf( b, sizeof( b ), f, a ); va_end( a ); commands.push_back( b ); }
	static const char *GetCvarString( const char *k ) { return cvars[k].c_str(); }
	static int CmdArgc() { return (int)args.size(); }
	static const char *CmdArgv( int i ) { return i < (int)args.size() ? args[i].c_str() : ""; }
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
bool CZM_ShopCarried( unsigned int bits, int slot, const char **name, const char **image, int *weapon );
void CZM_ShopDrawSilhouette( const char *image, int x, int y, int w, int h, unsigned int color );
struct MenuEntry { MenuEntry( const char *n, void ( *f )( void )) { entries()[n] = f; } static std::map<std::string, void ( * )( void )> &entries() { static std::map<std::string, void ( * )( void )> m; return m; } };
#define ADD_COMMAND( cmd, fn ) static MenuEntry entry_##cmd( #cmd, fn )
#define ADD_MENU3( cmd, type, fn ) static type *cmd = new type(); void fn( void )
'''

SCENARIOS = r'''
int ScreenWidth = 1536, ScreenHeight = 716, keyDest = KEY_GAME;
UiStatic uiStatic; std::vector<std::string> commands, args; std::map<std::string, std::string> cvars;
bool russian = true, active = true, trace = false;
static std::vector<std::string> drawn; static std::string lastTint;
static bool inScreen( int x, int y, int w, int h ) { return x >= 0 && y >= 0 && x + w <= ScreenWidth && y + h <= ScreenHeight; }
void UI_FillRect( int x, int y, int w, int h, unsigned c ) { assert( w >= 0 && h >= 0 ); if( trace ) printf( "R\t%d\t%d\t%d\t%d\t%u\n", x, y, w, h, c ); }
void CZM_DrawImage( const char *p, int x, int y, int w, int h, unsigned c ) { assert( w > 0 && h > 0 ); drawn.push_back( p ); if( trace ) printf( "I\t%d\t%d\t%d\t%d\t%u\t%s\n", x, y, w, h, c, p ); }
void CZM_DrawText( HFont f, int x, int y, int w, const char *s, unsigned c, int j ) { assert( inScreen( x, y, w, CZM_FontHeight( f ))); drawn.push_back( s ); if( trace ) printf( "T\t%d\t%d\t%d\t%d\t%u\t%d\t%s\n", x, y, w, CZM_FontHeight( f ), c, j, s ); }
void UI_DrawString( HFont, int x, int y, int w, int h, const char *s, unsigned c, int, int j, int ) { assert( inScreen( x, y, w, h )); drawn.push_back( s ); if( trace ) printf( "T\t%d\t%d\t%d\t%d\t%u\t%d\t%s\n", x, y, w, h, c, j, s ); }
// the shop knows weapon 28 (AK-47) as a primary, 17 (Glock) as a pistol, 4 (HE) as a grenade
bool CZM_ShopCarried( unsigned int bits, int slot, const char **name, const char **image, int *weapon ) {
	static const int ids[] = { 28, 17, 4 }; static const char *names[] = { "AK-47", "Glock-18", "Осколочная" }, *images[] = { "ak47", "glock18", "hegrenade" };
	if( !( bits & ( 1u << ids[slot] )))
		return false;
	*name = names[slot];
	*image = images[slot];
	*weapon = ids[slot];
	return true;
}
void CZM_ShopDrawSilhouette( const char *image, int x, int y, int w, int h, unsigned int c ) { assert( w > 0 && h > 0 ); drawn.push_back( std::string( "vgui/" ) + image + ( ( c >> 24 ) < 255 ? " pale" : "" )); if( trace ) printf( "I\t%d\t%d\t%d\t%d\t%u\t%s\n", x, y, w, h, c, image ); }
static bool saw( const std::string &s ) { return std::find( drawn.begin(), drawn.end(), s ) != drawn.end(); }
static bool sent( const char *c ) { return std::find( commands.begin(), commands.end(), std::string( c )) != commands.end(); }
static void pick( const char *a ) { char b[128]; snprintf( b, sizeof( b ), "czm_wheel_pick %s", a ); args.clear(); for( char *t = strtok( b, " " ); t; t = strtok( NULL, " " )) args.push_back( t ); commands.clear(); MenuEntry::entries()["czm_wheel_pick"](); }
// draws it, and again once it has grown in
static void wheel( const char *v ) { cvars["czm_wheel"] = v; CZM_DrawTouchWheel(); uiStatic.realTime += 200; drawn.clear(); CZM_DrawTouchWheel(); }
static CCzmRadio &w = *menu_czmradio;
static void point( int x, int y ) { uiStatic.cursorX = x; uiStatic.cursorY = y; }
static void centre( int slot ) { w.Layout(); float a = ( -90.0f + slot * 45.0f ) * M_PI / 180.0f; point( w.m_iX + cosf( a ) * w.m_iR * 0.64f, w.m_iY + sinf( a ) * w.m_iR * 0.64f ); }
static void open() { commands.clear(); assert( CZM_RadioShow( 38 )); assert( w.shown && keyDest == KEY_MENU ); }
int main( int argc, char **argv ) {
	// the engine's picks: a tap is the last weapon, a slide picks by its direction (up primary, then clockwise)
	pick( "weapons 1 0 0 200" ); assert( sent( "lastinv\n" ));
	// nothing carried: the slot command; carried: that very weapon in hand at once
	pick( "weapons 1 0 -90 200" ); assert( sent( "slot1\n" ));
	pick( "weapons 1 80 -30 200" ); assert( sent( "slot2\n" ));
	pick( "weapons 1 50 60 200" ); assert( sent( "slot4\n" ));
	pick( "weapons 1 -50 60 200" ); assert( sent( "buy\n" ));
	pick( "weapons 1 -80 -30 200" ); assert( sent( "weapon_knife\n" ));
	cvars["czm_buy_state"] = "800 2 " + std::to_string(( 1u << 28 ) | ( 1u << 17 ) | ( 1u << 4 ) | ( 1u << 29 )) + " 0 0 1";
	pick( "weapons 1 0 -90 200" ); assert( sent( "weapon_ak47\n" ));
	pick( "weapons 1 80 -30 200" ); assert( sent( "weapon_glock18\n" ));
	pick( "weapons 1 50 60 200" ); assert( sent( "weapon_hegrenade\n" ));
	cvars["czm_buy_state"] = "";
	// the open radio wheel: the place counts, the hub and outside pick nothing
	pick( "radio 2 0 -120 200" ); assert( sent( "enemyspot\n" ));
	pick( "radio 2 0 30 200" ); assert( commands.empty());
	pick( "radio 2 0 -260 200" ); assert( commands.empty());
	pick( "radio 2 -120 0 200" ); assert( sent( "roger\n" ));
	pick( "radio 1 -60 60 200" ); assert( sent( "say \"Спасибо!\"\n" ));
	russian = false; pick( "radio 1 -60 60 200" ); assert( sent( "say \"Thanks!\"\n" )); russian = true;
	pick( "radio 2 0 0 200" ); assert( commands.empty()); // a tap on the radio wheel picks nothing
	pick( "nothing 1 0 -90 200" ); assert( commands.empty());

	// drawn over the game from czm_wheel; nothing while it is empty, not shown yet or a menu is up
	wheel( "" ); assert( drawn.empty());
	wheel( "weapons 1 700 400 214 0 0 0 0" ); assert( drawn.empty()); // held, not shown yet (a quick tap)
	cvars["czm_buy_state"] = "800 2 " + std::to_string(( 1u << 17 ) | ( 1u << 29 )) + " 0 0 1"; // a Glock and a knife
	wheel( "weapons 1 700 400 214 0 0 0 1" );
	assert( saw( "gfx/czm/shop/wheel5.png" ) && saw( "vgui/glock18" ) && saw( "Glock-18" ) && saw( "vgui/ak47 pale" ) && saw( "нет" ));
	assert( saw( "gfx/czm/ui/icon_knife.png" ) && saw( "gfx/czm/ui/icon_cart.png" ) && saw( "gfx/czm/ui/icon_refresh.png" ));
	assert( !saw( "gfx/czm/shop/wheel5_1.png" ));
	wheel( "weapons 1 700 400 214 90 -30 1 1" ); assert( saw( "gfx/czm/shop/wheel5_1.png" )); // sliding right and up: the pistol
	uiStatic.menu.active = true; wheel( "weapons 1 700 400 214 90 -30 1 1" ); assert( drawn.empty()); uiStatic.menu.active = false;
	wheel( "radio 2 700 400 214 0 -150 1 1" );
	assert( saw( "gfx/czm/shop/wheel8.png" ) && saw( "gfx/czm/shop/wheel8_0.png" ) && saw( "Враг замечен" ) && saw( "Нажми на фразу. Мимо колеса — закрыть" ));
	// it grows in during a tenth of a second
	wheel( "" ); uiStatic.realTime = 5000; wheel( "radio 2 700 400 214 0 0 0 1" ); uiStatic.realTime = 5200; wheel( "radio 2 700 400 214 0 0 0 1" );
	// near the bottom the hint goes above the wheel
	for( auto size : { std::pair<int,int>{ 1536, 716 }, { 2000, 932 }, { 800, 360 } }) {
		ScreenWidth = size.first; ScreenHeight = size.second; int r = ScreenHeight * 0.3f, m = r * 1.12f;
		char v[96]; snprintf( v, sizeof( v ), "radio 2 %d %d %d 0 0 0 1", ScreenWidth - m, ScreenHeight - m, r ); wheel( v );
		snprintf( v, sizeof( v ), "radio 2 %d %d %d 0 0 0 1", m, m, r ); wheel( v );
	}
	ScreenWidth = 1536; ScreenHeight = 716;

	// the radio window for "showvguimenu 38" typed in the console
	assert( !CZM_RadioShow( 28 ) && !CZM_RadioShow( 35 ) && !w.shown ); // buy menus and text radio menus stay as they are
	for( auto size : { std::pair<int,int>{ 1536, 716 }, { 2000, 932 }, { 960, 540 }, { 800, 360 }, { 1024, 768 } }) for( int lang = 0; lang < 2; lang++ ) {
		ScreenWidth = size.first; ScreenHeight = size.second; russian = lang == 0;
		open(); w.Layout();
		for( int i = 0; i < 8; i++ ) { centre( i ); assert( w.Slot( uiStatic.cursorX, uiStatic.cursorY ) == i && w.HitTest() == w.HIT_SLOT + i ); }
		point( w.m_iX, w.m_iY ); assert( w.HitTest() == w.HIT_HUB );
		point( 2, 2 ); assert( w.HitTest() == w.HIT_OUTSIDE );
		w.Draw(); w.Hide();
	}
	ScreenWidth = 1536; ScreenHeight = 716; russian = true;
	open(); centre( 3 ); w.KeyDown( 1 ); w.KeyUp( 1 ); assert( !w.shown && sent( "coverme\n" ) && keyDest == KEY_GAME );
	open(); centre( 6 ); w.KeyDown( 1 ); centre( 7 ); w.MouseMove( 0, 0 ); assert( w.m_iHover == 7 ); w.KeyUp( 1 ); assert( sent( "holdpos\n" ));
	open(); centre( 4 ); w.KeyDown( 1 ); w.KeyUp( 1 ); assert( sent( "impulse 201\n" ));
	open(); point( w.m_iX, w.m_iY ); w.KeyDown( 1 ); w.KeyUp( 1 ); assert( !w.shown && commands.size() == 2 );
	open(); point( 2, 2 ); w.KeyDown( 1 ); w.KeyUp( 1 ); assert( !w.shown );
	open(); w.KeyDown( 27 ); assert( !w.shown );
	open(); uiStatic.realTime += 7000; w.Draw(); assert( !w.shown );
	open(); active = false; w.Draw(); assert( !w.shown ); active = true;

	if( argc > 1 ) {
		std::string view = argv[1]; russian = view.find( "en" ) == std::string::npos;
		ScreenWidth = 2000; ScreenHeight = 932; uiStatic.realTime += 1000;
		cvars["czm_buy_state"] = "800 2 " + std::to_string(( 1u << 28 ) | ( 1u << 17 ) | ( 1u << 4 ) | ( 1u << 29 )) + " 0 0 1";
		wheel( "" ); uiStatic.realTime += 1000; wheel( view.rfind( "radio", 0 ) == 0 ? "radio 2 1000 466 279 0 -150 1 1" : "weapons 1 1500 600 279 0 -150 1 1" );
		uiStatic.realTime += 1000; trace = true;
		CZM_DrawTouchWheel();
	}
	puts( "WHEELS_OK" );
}
'''


def build(folder):
    p = Path(folder)
    (p / "stub.h").write_text(STUB)
    for name in ["extdll_menu.h", "BaseMenu.h", "BaseClientWindow.h", "Utils.h", "keydefs.h", "CzmMenu.h"]:
        (p / name).write_text('#include "stub.h"\n')
    source = (ROOT / "czm/menu/CzmWheels.cpp").read_text()
    (p / "main.cpp").write_text("#include <cmath>\n" + source + SCENARIOS)
    exe = p / "wheels"
    subprocess.run(["g++", "-std=c++11", "-Wall", "-Werror", "-Wno-unused-function", "-I" + folder,
                    str(p / "main.cpp"), "-o", str(exe)], check=True)
    return exe


class WheelsTests(unittest.TestCase):
    def test_touch_wheels_picks_and_radio_window(self):
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run([str(build(folder))], check=True, capture_output=True, text=True)
            self.assertIn("WHEELS_OK", result.stdout)

    def test_the_buttons_and_the_menu_frame_use_them(self):
        menu = (ROOT / "cl_dll/menu.cpp").read_text()
        self.assertIn("case MENU_RADIOSELECTOR:\n\t\t\t// Counter Zombie Mobile: the radio wheel", menu)
        brand = (ROOT / "scripts/brand_mainui.py").read_text()
        self.assertIn("CZM_RadioShow( menuType )", brand)
        self.assertIn("CZM_DrawTouchWheel();", brand)
        self.assertIn("czm/menu/CzmWheels.cpp", (ROOT / "cmake/CzmBranding.cmake").read_text())
        touch = (ROOT / "czm/menu/CzmTouch.cpp").read_text()
        self.assertIn('{ "wheel", "Колесо оружия", "Weapon wheel", "_czmwheel weapons", GROUP_COMBAT },', touch)
        self.assertIn('"_czmwheel weapons"', (ROOT / "czm/settings_schema.json").read_text())
        for picture in ("ui/icon_spray.png", "ui/icon_knife.png", "ui/icon_cart.png", "ui/touch_ripple.png", "touch/wheel.png",
                        "shop/wheel5.png", "shop/wheel8.png"):
            self.assertTrue((ROOT / "3rdparty/cs16client-extras/gfx/czm" / picture).is_file(), picture)


if __name__ == "__main__":
    unittest.main()
