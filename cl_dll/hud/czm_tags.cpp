/*
Counter Zombie Mobile: the LVL MOD tags of our servers. GPL-2.0-or-later.

czm_lvl.amxx tells every CZM game what each player wears (CzmTag: the level, the wins in %, the
prefix in its colour, the privilege) and gives a player toasts for "+N tokens" and a new level
(CzmToast). The player list shows the tags (czm_scoreboard.cpp), the chat the prefix in its colour
(saytext.cpp, \x07RRGGBB), and here: the player in the crosshair with his tag and health, the toasts.
*/
#include "hud.h"
#include "cl_util.h"
#include "parsemsg.h"
#include "draw_util.h"
#include "czm_tags.h"
#include <stdio.h>
#include <string.h>

static inline int CzmMax( int a, int b ) { return a > b ? a : b; }
static inline int CzmMin( int a, int b ) { return a < b ? a : b; }

static CzmTag s_tags[MAX_PLAYERS + 1];
static bool s_have[MAX_PLAYERS + 1];
static bool s_aimShown;

struct CzmToast
{
	int kind;        // 1 tokens, 2 level
	int value;
	char text[96];
	float start;
};
#define CZM_TOASTS 3
static CzmToast s_toasts[CZM_TOASTS];

static bool Russian( void )
{
	const char *lang = gEngfuncs.pfnGetCvarString( "czm_lang_ui" );
	return !lang || strcmp( lang, "en" );
}

static int MsgFunc_CzmTag( const char *pszName, int iSize, void *pbuf )
{
	BufferReader reader( pszName, pbuf, iSize );
	int index = reader.ReadByte();
	CzmTag tag;

	memset( &tag, 0, sizeof( tag ));
	tag.lvl = reader.ReadShort();
	tag.wr = reader.ReadByte();
	strncpy( tag.prefix, reader.ReadString(), sizeof( tag.prefix ) - 1 );
	int color = reader.ReadLong();
	tag.r = ( color >> 16 ) & 255;
	tag.g = ( color >> 8 ) & 255;
	tag.b = color & 255;
	strncpy( tag.priv, reader.ReadString(), sizeof( tag.priv ) - 1 );

	if( index < 1 || index > MAX_PLAYERS )
		return 1;
	s_tags[index] = tag;
	s_have[index] = tag.lvl > 0 || tag.prefix[0] || tag.priv[0];
	return 1;
}

static int MsgFunc_CzmToast( const char *pszName, int iSize, void *pbuf )
{
	BufferReader reader( pszName, pbuf, iSize );
	CzmToast toast;

	toast.kind = reader.ReadByte();
	toast.value = reader.ReadShort();
	strncpy( toast.text, reader.ReadString(), sizeof( toast.text ) - 1 );
	toast.text[sizeof( toast.text ) - 1] = 0;
	toast.start = gHUD.m_flTime;

	// the newest on top, the oldest goes
	memmove( &s_toasts[1], &s_toasts[0], sizeof( CzmToast ) * ( CZM_TOASTS - 1 ));
	s_toasts[0] = toast;
	return 1;
}

void CZM_TagsInit( void )
{
	gEngfuncs.pfnHookUserMsg( "CzmTag", MsgFunc_CzmTag );
	gEngfuncs.pfnHookUserMsg( "CzmToast", MsgFunc_CzmToast );
	CZM_TagsReset();
}

void CZM_TagsReset( void )
{
	memset( s_tags, 0, sizeof( s_tags ));
	memset( s_have, 0, sizeof( s_have ));
	memset( s_toasts, 0, sizeof( s_toasts ));
}

const CzmTag *CZM_TagFor( int index )
{
	if( index < 1 || index > MAX_PLAYERS || !s_have[index] )
		return NULL;
	return &s_tags[index];
}

// the level colours of Kontra
void CZM_LevelColor( int lvl, int *r, int *g, int *b )
{
	static const struct { int upto, color; } tiers[] =
	{
		{ 10, 0xFFFFFF }, { 20, 0x00FFAA }, { 40, 0x00FFFF }, { 80, 0x0088FF }, { 160, 0xAA00FF },
		{ 320, 0xFF8800 }, { 640, 0xFFD700 }, { 1280, 0xFF4500 }, { 1 << 30, 0xFF0000 },
	};
	int color = 0xFFFFFF;

	for( size_t i = 0; i < sizeof( tiers ) / sizeof( tiers[0] ); i++ )
	{
		if( lvl <= tiers[i].upto )
		{
			color = tiers[i].color;
			break;
		}
	}
	*r = ( color >> 16 ) & 255;
	*g = ( color >> 8 ) & 255;
	*b = color & 255;
}

bool CZM_AimTagShown( void )
{
	return s_aimShown;
}

static int Width( const char *s )
{
	int w = 0, h = 0;
	gEngfuncs.pfnDrawConsoleStringLen( s, &w, &h );
	return w;
}

static int Draw( int x, int y, const char *s, int r, int g, int b )
{
	DrawUtils::SetConsoleTextColor( (unsigned char)r, (unsigned char)g, (unsigned char)b );
	return DrawUtils::DrawConsoleString( x, y, s );
}

// the player in the crosshair: [prefix] nick, LVL and wins, the health of a team mate
static void DrawAimTag( void )
{
	int index = gHUD.m_StatusBar.Value( 2 ), type = gHUD.m_StatusBar.Value( 1 );
	const CzmTag *tag = CZM_TagFor( index );

	s_aimShown = false;
	if( !tag || g_iUser1 )
		return;

	GetPlayerInfo( index, &g_PlayerInfoList[index] );
	const char *name = g_PlayerInfoList[index].name;
	if( !name || !name[0] )
		return;

	char prefix[40] = "", lvl[24] = "", wr[16] = "";
	if( tag->prefix[0] )
		snprintf( prefix, sizeof( prefix ), "[%s] ", tag->prefix );
	if( tag->lvl > 0 )
		snprintf( lvl, sizeof( lvl ), "  LVL %d", tag->lvl );
	if( tag->lvl > 0 && tag->wr > 0 )
		snprintf( wr, sizeof( wr ), "  WR %d%%", tag->wr );

	int fh = 0, tw = 0;
	gEngfuncs.pfnDrawConsoleStringLen( "Ag", &tw, &fh );
	int health = type == 1 ? gHUD.m_StatusBar.Value( 3 ) : -1;
	int pad = fh / 2;
	int lineW = Width( prefix ) + Width( name ) + Width( lvl ) + Width( wr );
	int privW = tag->priv[0] ? Width( tag->priv ) + pad * 2 : 0;
	int w = lineW + privW + ( privW ? pad : 0 ) + pad * 2;
	int barH = health >= 0 ? CzmMax( 4, fh / 3 ) : 0;
	int h = fh + pad * 2 + ( barH ? barH + pad : 0 );
	int x = ( ScreenWidth - w ) / 2, y = ScreenHeight / 2 + ScreenHeight / 14;

	FillRGBABlend( x, y, w, h, 10, 14, 22, 190 );
	FillRGBA( x, y, w, CzmMax( 1, fh / 10 ), 224, 37, 50, 230 );

	int cx = x + pad, ty = y + pad;
	if( privW )
	{
		FillRGBABlend( cx, ty, privW, fh, 231, 187, 96, 230 );
		Draw( cx + pad, ty, tag->priv, 28, 20, 8 );
		cx += privW + pad;
	}
	if( prefix[0] )
		cx = Draw( cx, ty, prefix, tag->r, tag->g, tag->b );
	cx = Draw( cx, ty, name, 240, 243, 248 );
	if( lvl[0] )
	{
		int r, g, b;
		CZM_LevelColor( tag->lvl, &r, &g, &b );
		cx = Draw( cx, ty, lvl, r, g, b );
	}
	if( wr[0] )
		Draw( cx, ty, wr, 155, 166, 184 );

	if( barH )
	{
		int bw = w - pad * 2, by = ty + fh + pad / 2 + 1;
		int hp = CzmMax( 0, CzmMin( 100, health ));
		FillRGBABlend( x + pad, by, bw, barH, 255, 255, 255, 40 );
		// green, yellow at half, red when low
		int r = hp > 50 ? ( 100 - hp ) * 5 : 255, g = hp > 50 ? 220 : hp * 4;
		FillRGBA( x + pad, by, bw * hp / 100, barH, CzmMin( 255, r ), CzmMin( 220, g ), 70, 240 );
	}
	s_aimShown = true;
}

// "+5 tokens for a kill", "LVL 38 — a new level!", top centre, three seconds each
static void DrawToasts( float flTime )
{
	bool ru = Russian();
	int fh = 0, tw = 0;
	gEngfuncs.pfnDrawConsoleStringLen( "Ag", &tw, &fh );
	int pad = fh / 2, y = ScreenHeight * 0.17f;

	for( int i = 0; i < CZM_TOASTS; i++ )
	{
		CzmToast &t = s_toasts[i];
		float age = flTime - t.start;
		if( !t.kind || age < 0 || age > 3.2f )
			continue;

		// in and out in a fifth of a second
		float fade = age < 0.2f ? age / 0.2f : age > 3.0f ? ( 3.2f - age ) / 0.2f : 1.0f;
		int a = 220 * fade;
		char lead[40], rest[128];
		int lr = 231, lg = 187, lb = 96;

		if( t.kind == 2 )
		{
			snprintf( lead, sizeof( lead ), "LVL %d", t.value );
			snprintf( rest, sizeof( rest ), ru ? "  ·  новый уровень!" : "  ·  a new level!" );
			CZM_LevelColor( t.value, &lr, &lg, &lb );
		}
		else
		{
			snprintf( lead, sizeof( lead ), "+%d", t.value );
			snprintf( rest, sizeof( rest ), ru ? " токенов  %s" : " tokens  %s", t.text );
		}

		int w = Width( lead ) + Width( rest ) + pad * 3, h = fh + pad * 2;
		int x = ( ScreenWidth - w ) / 2;
		FillRGBABlend( x, y, w, h, 10, 14, 22, a );
		FillRGBA( x, y, CzmMax( 3, fh / 6 ), h, t.kind == 2 ? lr : 224, t.kind == 2 ? lg : 37, t.kind == 2 ? lb : 50, a );
		int cx = Draw( x + pad * 2, y + pad, lead, lr, lg, lb );
		Draw( cx, y + pad, rest, 220, 226, 234 );
		y += h + pad / 2;
	}
}

void CZM_TagsDraw( float flTime )
{
	DrawAimTag();
	DrawToasts( flTime );
}
