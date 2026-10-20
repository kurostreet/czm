/* Counter Zombie Mobile spectator overlay and download indicator. GPL-2.0-or-later. */
#include "hud.h"
#include "cl_util.h"
#include "draw_util.h"
#include "czm_hud.h"
#include "czm_avatars.h"
#include "../../common/czm_hud_overlay.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

namespace {
bool Russian()
{
	const char *lang = gEngfuncs.pfnGetCvarString( "czm_lang" );
	if( !lang || !*lang ) lang = getenv( "CZM_LOCALE" );
	return !lang || !*lang || !strncmp( lang, "ru", 2 ) || !strncmp( lang, "uk", 2 )
		|| !strncmp( lang, "be", 2 ) || !strncmp( lang, "kk", 2 );
}

// player and server names without colour escapes and control characters
void Clean( const char *src, char *out, size_t size )
{
	size_t n = 0, i = 0;
	if( !src ) src = "";
	for( ; src[i] && n + 1 < size; i++ )
	{
		unsigned char c = (unsigned char)src[i];
		if( c == '^' && src[i + 1] >= '0' && src[i + 1] <= '9' ) { i++; continue; }
		if( c < 32 || c == 127 ) continue;
		out[n++] = c;
	}
	// cut short: no half of a UTF-8 character at the end
	if( src[i] )
	{
		while( n && ((unsigned char)out[n - 1] & 0xc0) == 0x80 ) n--;
		if( n && (unsigned char)out[n - 1] >= 0xc0 ) n--;
	}
	out[n] = 0;
}

// the match: alpha-blended plates, the glyph atlas, the console font for words
struct GameCanvas : CzmHud::Canvas
{
	int slot;
	bool self;

	GameCanvas( int s = 0, bool me = false ) : slot( s ), self( me ) {}
	void Blend( int x, int y, int w, int h, int r, int g, int b, int a ) override
	{
		if( w > 0 && h > 0 && a > 0 )
			FillRGBABlend( x, y, w, h, r, g, b, a > 255 ? 255 : a );
	}
	void Glyphs( float x, float y, float height, const char *s, int r, int g, int b, float alpha ) override
	{
		CZM_HudText( x, y, height, s, r, g, b, alpha );
	}
	int LabelWidth( const char *s ) override
	{
		int w = 0, h = 0;
		DrawUtils::ConsoleStringSize( s, &w, &h );
		return w;
	}
	int LabelHeight() override
	{
		int w = 0, h = 0;
		DrawUtils::ConsoleStringSize( "Ag", &w, &h );
		return h > 0 ? h : 12;
	}
	void Label( int x, int y, const char *s, int r, int g, int b ) override
	{
		if( !s || !*s ) return;
		DrawUtils::SetConsoleTextColor( (unsigned char)r, (unsigned char)g, (unsigned char)b );
		DrawUtils::DrawConsoleString( x, y, s );
	}
	bool Avatar( int x, int y, int size ) override
	{
		return slot > 0 && CZM_DrawTabAvatar( slot, self, x, y, size );
	}
};
}

int CZM_SpectatorStyle( void )
{
	return (int)CzmHud::Clamp( gEngfuncs.pfnGetCvarFloat( "czm_hud_spec_style" ), 0, CzmHud::SPEC_STYLES - 1, CzmHud::defaultSpecStyle );
}

bool CZM_SpectatorDraw( int target, const char *timer, int scoreCT, int scoreT, bool status )
{
	if( !CZM_HudReady( ))
		return false;

	char name[128] = "";
	int health = -1, team = 0;
	bool self = false;

	if( target > 0 && target <= MAX_PLAYERS )
	{
		hud_player_info_t info = {};
		GetPlayerInfo( target, &info );
		if( info.name && info.name[0] )
		{
			Clean( info.name, name, sizeof( name ));
			health = g_PlayerExtraInfo[target].sb_health > 255 ? g_PlayerExtraInfo[target].sb_health : g_PlayerExtraInfo[target].health;
			team = g_PlayerExtraInfo[target].teamnumber;
			self = info.thisplayer != 0;
		}
	}

	CzmHud::SpecInfo s;
	s.name = name;
	s.team = team;
	s.health = health;
	s.scoreCT = scoreCT;
	s.scoreT = scoreT;
	s.timer = timer ? timer : "";
	s.watching = Russian() ? "Наблюдение" : "Spectating";
	s.status = status;

	GameCanvas canvas( name[0] ? target : 0, self );
	CzmHud::PaintSpectator( canvas, CZM_SpectatorStyle(), ScreenWidth, ScreenHeight, s );
	return true;
}

// server files downloading in a match: the engine keeps the percent in scr_download and the
// number of files left in czm_download_files; the place comes from the editor (czm_hud_dl_*)
void CZM_DownloadsDraw( void )
{
	const float percent = gEngfuncs.pfnGetCvarFloat( "scr_download" );

	if( percent < 0.0f || !CZM_HudReady( ))
		return;
	if( CZM_HudValue( CzmHud::DOWNLOADS, "hidden", CzmHud::defaultHidden[CzmHud::DOWNLOADS] ) > 0.5f )
		return;

	GameCanvas canvas;
	const int files = (int)gEngfuncs.pfnGetCvarFloat( "czm_download_files" );
	const bool ru = Russian();
	char words[96];

	if( files > 0 )
		snprintf( words, sizeof( words ), ru ? "Файлы сервера: %d" : "Server files: %d", files );
	else
		snprintf( words, sizeof( words ), "%s", ru ? "Загрузка файлов" : "Downloading files" );

	CzmHud::Rect p = CzmHud::DownloadLayout( ScreenWidth, ScreenHeight,
		CZM_HudValue( CzmHud::DOWNLOADS, "x", CzmHud::defaults[CzmHud::DOWNLOADS][0] ),
		CZM_HudValue( CzmHud::DOWNLOADS, "y", CzmHud::defaults[CzmHud::DOWNLOADS][1] ),
		CZM_HudValue( CzmHud::DOWNLOADS, "scale", CzmHud::defaultScale[CzmHud::DOWNLOADS] ),
		CZM_HudValue( CzmHud::DOWNLOADS, "opacity", 1 ), (float)canvas.LabelHeight( ));
	CzmHud::PaintDownload( canvas, p, words, percent );
}
