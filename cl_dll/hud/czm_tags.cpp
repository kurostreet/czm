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
#include "czm_hud.h"
#include "../../common/czm_hud_overlay.h"
#include "../../common/czm_aim.h"
#include <stdio.h>
#include <string.h>

static inline int CzmMax( int a, int b ) { return a > b ? a : b; }
static inline int CzmMin( int a, int b ) { return a < b ? a : b; }

static CzmTag s_tags[MAX_PLAYERS + 1];
static bool s_have[MAX_PLAYERS + 1];
static bool s_aimShown, s_aimReceived;
static CzmAim::Target s_aim;
static CzmHud::ProgressInfo s_progress;

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

static int MsgFunc_CzmProgress( const char *pszName, int iSize, void *pbuf )
{
	if( iSize != 24 )
		return 1;
	BufferReader reader( pszName, pbuf, iSize );
	s_progress.level = reader.ReadLong();
	s_progress.tokens = reader.ReadLong();
	s_progress.killsLeft = reader.ReadLong();
	s_progress.killsStep = reader.ReadLong();
	s_progress.secondsLeft = reader.ReadLong();
	s_progress.secondsStep = reader.ReadLong();
	return 1;
}

static int MsgFunc_CzmAim( const char *name, int size, void *buffer )
{
	if( size != 9 ) return 1;
	BufferReader reader( name, buffer, size );
	s_aim.index = reader.ReadByte();
	s_aim.health = reader.ReadLong();
	s_aim.maximum = reader.ReadLong();
	s_aim.received = gHUD.m_flTime;
	s_aimReceived = true;
	return 1;
}

void CZM_TagsInit( void )
{
	gEngfuncs.pfnHookUserMsg( "CzmAim", MsgFunc_CzmAim );
	gEngfuncs.pfnHookUserMsg( "CzmTag", MsgFunc_CzmTag );
	gEngfuncs.pfnHookUserMsg( "CzmToast", MsgFunc_CzmToast );
	gEngfuncs.pfnHookUserMsg( "CzmProgress", MsgFunc_CzmProgress );
	CZM_TagsReset();
}

void CZM_TagsReset( void )
{
	memset( s_tags, 0, sizeof( s_tags ));
	memset( s_have, 0, sizeof( s_have ));
	memset( s_toasts, 0, sizeof( s_toasts ));
	memset( &s_progress, 0, sizeof( s_progress ));
	s_progress.level = -1; // unset is separate from a server reporting level zero
	s_aimShown = s_aimReceived = false;
	memset( &s_aim, 0, sizeof( s_aim ));
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

// The visible aimed player: actual HP/max HP, level and win rate.
static void DrawAimTag( void )
{
	int index = s_aimReceived ? ( s_aim.Live( gHUD.m_flTime ) ? s_aim.index : 0 ) : gHUD.m_StatusBar.Value( 2 );
	const CzmTag empty = {};
	const CzmTag *tag = CZM_TagFor( index );
	bool ranked = tag != NULL;
	if( !tag ) tag = &empty;

	s_aimShown = false;
	if( index < 1 || index > MAX_PLAYERS || g_iUser1 )
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
	if( ranked )
		snprintf( wr, sizeof( wr ), "  WR %d%%", tag->wr );

	int fh = 0, tw = 0;
	gEngfuncs.pfnDrawConsoleStringLen( "Ag", &tw, &fh );
	if( !ranked )
	{
		snprintf( lvl, sizeof( lvl ), "  LVL —" );
		snprintf( wr, sizeof( wr ), "  WR —" );
	}
	int health = s_aimReceived ? s_aim.health : ( gHUD.m_StatusBar.Value( 1 ) == 1 ? gHUD.m_StatusBar.Value( 3 ) : -1 );
	int maximum = s_aimReceived ? s_aim.maximum : 100;
	char hpText[40] = "";
	if( health >= 0 ) snprintf( hpText, sizeof( hpText ), "%d / %d HP", health, maximum );
	int pad = fh / 2;
	int lineW = Width( prefix ) + Width( name ) + Width( lvl ) + Width( wr );
	int privW = tag->priv[0] ? Width( tag->priv ) + pad * 2 : 0;
	int w = CzmMax( lineW + privW + ( privW ? pad : 0 ), Width( hpText ) ) + pad * 2;
	int barH = health >= 0 ? CzmMax( 4, fh / 3 ) : 0;
	int h = fh + pad * 2 + ( barH ? barH + pad + fh : 0 );
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
		float fraction = CzmAim::Fraction( health, maximum );
		FillRGBABlend( x + pad, by, bw, barH, 255, 255, 255, 40 );
		int r, g, b;
		CzmAim::Color( fraction, r, g, b );
		FillRGBA( x + pad, by, (int)( bw * fraction ), barH, r, g, b, 240 );
		Draw( x + ( w - Width( hpText ) ) / 2, by + barH + pad / 2, hpText, 205, 213, 224 );
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
	CZM_ProgressDraw( s_progress );
	DrawAimTag();
	DrawToasts( flTime );
}
