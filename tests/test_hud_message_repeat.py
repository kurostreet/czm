"""Server texts on the screen (cl_dll/message.cpp): a text the server sends again and again stays up
instead of blinking, and the flicker effect keeps the Russian letters."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

HUD = r'''
#pragma once
#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
typedef int qboolean;
typedef struct client_textmessage_s
{
	int effect;
	unsigned char r1, g1, b1, a1, r2, g2, b2, a2;
	float x, y, fadein, fadeout, holdtime, fxtime;
	const char *pName;
	const char *pMessage;
} client_textmessage_t;
#define HUD_DRAW 1
#define CHudMsgFunc(x) int MsgFunc_##x(const char *pszName, int iSize, void *buf)
class CHudBase { public: int m_iFlags = 0; virtual ~CHudBase() {} virtual int Init() { return 0; } virtual int VidInit() { return 0; }
	virtual int Draw( float ) { return 0; } virtual void Reset() {} };
@@CLASSES@@
struct wrect_t { int left, right, top, bottom; int Width() const { return right - left; } int Height() const { return bottom - top; } };
struct Hud {
	float m_flTime = 0;
	CHudMessage m_Message;
	void AddHudElem( CHudBase * ) {}
	int GetSpriteIndex( const char * ) { return 0; }
	int GetCharWidth( int ) { return 10; }
	int GetCharHeight() { return 20; }
	int GetSprite( int ) { return 0; }
	wrect_t &GetSpriteRect( int ) { static wrect_t r = { 0, 10, 0, 10 }; return r; }
};
extern Hud gHUD;
'''

CL_UTIL = r'''
#pragma once
#define ScreenWidth 1600
#define ScreenHeight 720
#define HOOK_MESSAGE( a, b )
client_textmessage_t *TextMessageGet( const char *name );
inline const char *Localize( const char *s ) { return s; }
inline void SPR_Set( int, int, int, int ) {}
inline void SPR_DrawAdditive( int, int, int, const wrect_t * ) {}
inline void FillRGBABlend( int, int, int, int, int, int, int, int ) {}
struct EngineFuncs { float ( *pfnGetCvarFloat )( const char * ); };
extern EngineFuncs gEngfuncs;
'''

PARSEMSG = r'''
#pragma once
struct BufferReader {
	const char *text; int pos = 0;
	BufferReader( const char *, void *buf, int ) : text( (const char *)buf ) {}
	char *ReadString() { return (char *)text; }
	int ReadByte() { return 0; }
};
'''

DRAW_UTIL = r'''
#pragma once
int Con_UtfProcessChar( int in );
namespace DrawUtils { int TextMessageDrawChar( int x, int y, int number, int r, int g, int b, float scale = 0.0f ); }
'''

CZM_HUD = r'''
#pragma once
#include "czm_hud_layout.h"
inline float CZM_HudValue( int, const char *, float fallback ) { return fallback; }
'''

SCENARIOS = r'''
#include <cassert>
Hud gHUD;
EngineFuncs gEngfuncs = { []( const char * ) { return 0.0f; } };
char *CHudTextMessage::BufferedLocaliseTextString( const char *msg ) { return (char *)msg; }

// UTF-8 decoders: the client's own one, and the engine's one behind its character drawing (shared state)
struct Utf { int need = 0, code = 0; int Feed( int in ) {
	if( !in ) { need = 0; return 0; }
	if( in < 0x80 ) { need = 0; return in; }
	if(( in & 0xC0 ) == 0x80 ) { if( !need ) return 0; code = ( code << 6 ) | ( in & 0x3F ); return --need ? 0 : code; }
	need = ( in & 0xE0 ) == 0xC0 ? 1 : ( in & 0xF0 ) == 0xE0 ? 2 : 3; code = in & ( 0x3F >> need ); return 0; } };
static Utf client, engine;
int Con_UtfProcessChar( int in ) { return client.Feed( in ); }
struct Glyph { int x, code, r, g, b; };
static std::vector<Glyph> glyphs;
int DrawUtils::TextMessageDrawChar( int x, int, int number, int r, int g, int b, float ) {
	int code = engine.Feed( number & 255 );
	if( !code ) return 0;
	glyphs.push_back( { x, code, r, g, b } );
	return 10;
}

// the engine keeps one message per channel and writes a new text into the same place (cl_game.c)
static char buffer[2048];
static client_textmessage_t channel = { 0, 40, 120, 255, 255, 255, 255, 255, 255, 0.1f, 0.2f, 0, 0, 1.0f, 0, "TextMessage1", buffer };
client_textmessage_t *TextMessageGet( const char *name ) { return !strcmp( name, channel.pName ) ? &channel : nullptr; }

static void Send( float now, const char *text ) {
	gHUD.m_flTime = now;
	strcpy( buffer, text );
	gHUD.m_Message.MsgFunc_HudText( "HudText", 0, (void *)channel.pName );
}
static int Draw( float now ) { gHUD.m_flTime = now; glyphs.clear(); gHUD.m_Message.Draw( now ); return (int)glyphs.size(); }
static std::vector<int> Codes( bool second ) { std::vector<int> v; for( auto &g : glyphs ) if(( g.r == 255 ) == second ) v.push_back( g.code ); return v; }
static std::vector<int> Expect( const char *s ) { Utf u; std::vector<int> v; for( ; *s; s++ ) { int c = u.Feed( (unsigned char)*s ); if( c > ' ' ) v.push_back( c ); } return v; }
static std::vector<int> NoSpaces( std::vector<int> v ) { std::vector<int> o; for( int c : v ) if( c > ' ' ) o.push_back( c ); return o; }

int main() {
	gHUD.m_Message.Reset();
	// a panel sent every 0.95 s with a hold time of 1 s: it never goes away, its numbers change in place
	channel.effect = 0; channel.fadein = channel.fadeout = 0; channel.holdtime = 1.0f;
	float next = 0; int n = 0;
	for( float t = 0; t < 6.0f; t += 0.05f ) {
		if( t >= next ) { char text[64]; snprintf( text, sizeof( text ), "Здоровье: %d", 100 - n++ ); Send( t, text ); next += 0.95f; }
		assert( Draw( t + 0.01f ) > 0 );
	}
	// once the server stops, it runs out after its hold time
	assert( Draw( next - 0.95f + 1.0f + 0.05f ) == 0 );

	// sent again when fully shown: no new fade-in
	gHUD.m_Message.Reset(); channel.fadein = 0.5f; channel.fadeout = 0.2f;
	Send( 10.0f, "Броня: 50" ); Draw( 10.2f ); assert( !glyphs.empty() && glyphs[0].b < 200 ); // fading in
	Draw( 10.8f ); assert( glyphs[0].b >= 254 );
	Send( 11.0f, "Броня: 50" ); Draw( 11.05f ); assert( glyphs[0].b >= 254 );
	assert( Draw( 11.95f ) > 0 && glyphs[0].b >= 254 ); // held from 11.0 for its hold time, then 0.2 s of fade-out
	assert( Draw( 12.15f ) > 0 && glyphs[0].b < 200 );
	assert( Draw( 12.25f ) == 0 );
	// sent again while still fading in: the fade goes on as it was
	Send( 20.0f, "Броня: 50" ); Send( 20.2f, "Броня: 50" ); Draw( 20.3f ); assert( glyphs[0].b < 220 && glyphs[0].b > 100 );

	// write-out (effect 2): the same text again is not written anew, another text on the channel is
	gHUD.m_Message.Reset(); channel.effect = 2; channel.fadein = 0.1f; channel.fxtime = 0.05f; channel.fadeout = 0.2f;
	Send( 30.0f, "AB" ); Draw( 30.5f ); assert( glyphs.size() == 2 && glyphs[1].b >= 254 );
	Send( 30.6f, "AB" ); Draw( 30.62f ); assert( glyphs.size() == 2 && glyphs[1].b >= 254 );
	Send( 30.7f, "CD" ); Draw( 30.72f ); assert( glyphs.size() == 2 && glyphs[1].code == 'D' && glyphs[1].b == 0 );

	// flicker (effect 1): some frames draw the text once more in the second colour; letters stay whole
	gHUD.m_Message.Reset(); channel.effect = 1; channel.fadein = channel.fadeout = 0; channel.holdtime = 100;
	channel.r1 = 40; channel.r2 = 255;
	const char *text = "[Здоровье: 100]\n[Класс: Фантом]";
	Send( 40.0f, text );
	int flickers = 0;
	for( int frame = 0; frame < 400; frame++ ) {
		Draw( 40.0f + frame * 0.016f );
		std::vector<int> main = NoSpaces( Codes( false )), extra = NoSpaces( Codes( true ));
		assert( main == Expect( text ));
		if( !extra.empty()) { flickers++; assert( extra == Expect( text )); }
	}
	assert( flickers > 10 && flickers < 100 );
	puts( "HUD_MESSAGES_OK" );
}
'''


def hud_classes():
    hud = (ROOT / "cl_dll/hud.h").read_text()
    start = hud.index("const int maxHUDMessages")
    end = hud.index("};", hud.index("int m_HUD_title_half;")) + 2
    return hud[start:end]


class HudMessageRepeatTests(unittest.TestCase):
    def test_repeated_and_flickering_texts(self):
        if not shutil.which("g++"):
            self.skipTest("g++ required")
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            (p / "hud").mkdir()
            (p / "hud.h").write_text(HUD.replace("@@CLASSES@@", hud_classes()))
            (p / "cl_util.h").write_text(CL_UTIL)
            (p / "parsemsg.h").write_text(PARSEMSG)
            (p / "vgui_parser.h").write_text("#pragma once\n")
            (p / "draw_util.h").write_text(DRAW_UTIL)
            (p / "hud" / "czm_hud.h").write_text(CZM_HUD)
            source = (ROOT / "cl_dll/message.cpp").read_text()
            (p / "main.cpp").write_text(source + SCENARIOS)
            exe = p / "messages"
            subprocess.run(["g++", "-std=c++11", "-Wall", "-Werror", "-Wno-unused-function", "-Wno-sign-compare", "-I" + folder,
                            "-I" + str(ROOT / "common"), str(p / "main.cpp"), "-o", str(exe)], check=True)
            self.assertIn("HUD_MESSAGES_OK", subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout)

    def test_the_stock_drop_of_repeats_is_gone(self):
        source = (ROOT / "cl_dll/message.cpp").read_text()
        self.assertIn("MessageKeep( j, message, time );", source)
        self.assertNotRegex(source, re.compile(r"MessageScanNextChar\( void \)\n\{(?:(?!\n\}\n).)*TextMessageDrawChar", re.S))


if __name__ == "__main__":
    unittest.main()
