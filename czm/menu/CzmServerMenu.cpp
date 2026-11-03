/*
CzmServerMenu.cpp - Counter Zombie Mobile: server menus as big cards over the game
Copyright (C) 2026 Counter Zombie Mobile authors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.
*/

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "extdll_menu.h"
#include "BaseMenu.h"
#include "BaseClientWindow.h"
#include "Utils.h"
#include "keydefs.h"
#include "CzmMenu.h"

#define UI_DIR "gfx/czm/ui/"
#define MAX_CARDS 10
#define MAX_LINES 3

/*
Menus from plugins, votes and the classic buy menu come as text: a title, then lines
like "\r1. \wItem" with colour codes (\y \r \w \d, \R moves the rest to the right).
The client hands the text over in the czm_menu cvar ("serial validslots", a new line,
the text). Each item becomes a card; invisible client touch buttons over the cards
send slot1..slot10, so the rest of the screen keeps working: the player can walk
and look around while the menu is open.
*/
struct CzmCard
{
	int key;          // 1..10 (10 is key 0)
	char text[96];
	char right[48];
	bool enabled;
	CzmRect rect;
};

static struct
{
	int serial;       // the menu on the screen, -1 none
	int validSlots;
	char title[96];
	char lines[MAX_LINES][96];
	int numLines;
	CzmCard cards[MAX_CARDS];
	int numCards;
	CzmRect panel;
	bool buttons;     // touch buttons are in place
	int layoutW, layoutH;
} s_menu = { -1 };

static void TrimCopy( char *out, size_t size, const char *from, const char *to )
{
	while( from < to && ( *from == ' ' || *from == '\t' ))
		from++;
	while( to > from && ( to[-1] == ' ' || to[-1] == '\t' || to[-1] == '\r' ))
		to--;

	size_t len = Q_min( (size_t)( to - from ), size - 1 );
	memcpy( out, from, len );
	out[len] = 0;
}

// one line of the menu: visible text without colour codes, the part after \R, and the colour of the first letter
static void SplitLine( const char *line, char *text, size_t textSize, char *right, size_t rightSize, char *firstColor )
{
	char buf[512], rbuf[128];
	int n = 0, rn = 0;
	bool toRight = false;
	char color = 'w';

	*firstColor = 0;
	for( const char *p = line; *p && *p != '\n'; p++ )
	{
		if( p[0] == '\\' && p[1] && strchr( "yrwdR", p[1] ))
		{
			if( p[1] == 'R' )
				toRight = true;
			else
				color = p[1];
			p++;
			continue;
		}

		if( !toRight )
		{
			if( !*firstColor && *p != ' ' )
				*firstColor = color;
			if( n < (int)sizeof( buf ) - 1 )
				buf[n++] = *p;
		}
		else if( rn < (int)sizeof( rbuf ) - 1 )
			rbuf[rn++] = *p;
	}

	TrimCopy( text, textSize, buf, buf + n );
	TrimCopy( right, rightSize, rbuf, rbuf + rn );
}

static void ParseMenu( const char *value )
{
	const char *text = strchr( value, '\n' );
	const char *line;
	bool seenItem = false;

	s_menu.title[0] = 0;
	s_menu.numLines = 0;
	s_menu.numCards = 0;
	s_menu.validSlots = 0;
	sscanf( value, "%d %d", &s_menu.serial, &s_menu.validSlots );

	if( !text )
		return;

	for( line = text + 1; *line; )
	{
		const char *end = strchr( line, '\n' );
		char visible[128], right[48], color;

		SplitLine( line, visible, sizeof( visible ), right, sizeof( right ), &color );
		line = end ? end + 1 : line + strlen( line );

		if( !visible[0] )
			continue;

		// "1. Item", "1) Item"
		if( visible[0] >= '0' && visible[0] <= '9' && ( visible[1] == '.' || visible[1] == ')' ) && s_menu.numCards < MAX_CARDS )
		{
			CzmCard &card = s_menu.cards[s_menu.numCards++];
			int key = visible[0] == '0' ? 10 : visible[0] - '0';

			card.key = key;
			TrimCopy( card.text, sizeof( card.text ), visible + 2, visible + strlen( visible ));
			Q_strncpy( card.right, right, sizeof( card.right ));
			card.enabled = ( s_menu.validSlots & ( 1 << ( key - 1 ))) && color != 'd';
			seenItem = true;
			continue;
		}

		if( !seenItem && !s_menu.title[0] )
			Q_strncpy( s_menu.title, visible, sizeof( s_menu.title ));
		else if( s_menu.numLines < MAX_LINES )
			Q_strncpy( s_menu.lines[s_menu.numLines++], visible, sizeof( s_menu.lines[0] ));
	}
}

static void RemoveButtons( void )
{
	if( !s_menu.buttons )
		return;

	EngFuncs::ClientCmd( false, "touch_removebutton \"_menu_czm*\"\n" );
	s_menu.buttons = false;
}

static void Layout( void )
{
	int W = ScreenWidth, H = ScreenHeight;
	int columns = s_menu.numCards > 6 ? 2 : 1;
	int perColumn = ( s_menu.numCards + columns - 1 ) / columns;
	int x = W * 0.025f, top = H * 0.16f;
	int colW = columns > 1 ? Q_min( (int)( W * 0.22f ), (int)( H * 0.50f )) : Q_min( (int)( W * 0.30f ), (int)( H * 0.66f ));
	int cardH = H * 0.074f, gap = H * 0.012f;
	int y;

	// title, extra lines, then the cards
	y = top + CZM_FontHeight( CZM_Font( CZMF_SMALL )) + CZM_FontHeight( CZM_Font( CZMF_MENU_TITLE )) + H * 0.02f;
	y += s_menu.numLines * ( CZM_FontHeight( CZM_Font( CZMF_SMALL )) + H * 0.006f );

	for( int i = 0; i < s_menu.numCards; i++ )
	{
		int col = i / perColumn, row = i % perColumn;
		s_menu.cards[i].rect = CZM_Rect( x + col * ( colW + gap ), y + row * ( cardH + gap ), colW, cardH );
	}

	s_menu.panel = CZM_Rect( 0, 0, x + columns * colW + ( columns - 1 ) * gap + W * 0.03f, H );
	s_menu.layoutW = W;
	s_menu.layoutH = H;
}

static void AddButtons( void )
{
	float W = ScreenWidth, H = ScreenHeight;

	RemoveButtons();
	for( int i = 0; i < s_menu.numCards; i++ )
	{
		const CzmCard &card = s_menu.cards[i];

		if( !card.enabled )
			continue;

		// client button (flag 4): not saved, removed with the other menu buttons
		EngFuncs::ClientCmdF( false, "touch_addbutton \"_menu_czm%d\" \"\" \"slot%d\" %f %f %f %f 255 255 255 0 4\n",
			card.key, card.key, card.rect.x / W, card.rect.y / H, ( card.rect.x + card.rect.w ) / W, ( card.rect.y + card.rect.h ) / H );
	}
	s_menu.buttons = true;
}

static void DrawMenu( void )
{
	int H = ScreenHeight;
	HFont labelFont = CZM_Font( CZMF_SMALL );
	HFont titleFont = CZM_Font( CZMF_MENU_TITLE );
	HFont textFont = CZM_Font( CZMF_LANG );
	HFont rightFont = CZM_Font( CZMF_TILE_STATUS );
	HFont keyFont = CZM_Font( CZMF_SHOP_PRICE );
	int x = ScreenWidth * 0.025f, y = H * 0.16f, w = s_menu.panel.w - x * 2;
	int corner = H * 0.022f;

	// a dark fade behind the menu keeps it readable over any map
	CZM_DrawImage( "gfx/czm/fade_left.png", 0, 0, s_menu.panel.w + ScreenWidth * 0.08f, H, CZM_White( 210 ));

	CZM_DrawText( labelFont, x, y, w, CZM_IsRussian() ? "МЕНЮ СЕРВЕРА" : "SERVER MENU", PackRGBA( 154, 163, 175, 255 ));
	y += CZM_FontHeight( labelFont );
	if( s_menu.title[0] )
		CZM_DrawText( titleFont, x, y, w, s_menu.title, CZM_White());
	y += CZM_FontHeight( titleFont ) + H * 0.01f;

	for( int i = 0; i < s_menu.numLines; i++ )
	{
		CZM_DrawText( labelFont, x, y, w, s_menu.lines[i], PackRGBA( 203, 210, 220, 255 ));
		y += CZM_FontHeight( labelFont ) + H * 0.006f;
	}

	for( int i = 0; i < s_menu.numCards; i++ )
	{
		const CzmCard &card = s_menu.cards[i];
		const CzmRect &r = card.rect;
		int badge = r.h * 0.62f, pad = ( r.h - badge ) / 2;
		int textX = r.x + pad * 2 + badge;
		int rightW = card.right[0] ? CZM_TextWidth( rightFont, card.right ) + pad : 0;
		char key[4];

		CZM_DrawSliced( UI_DIR "card.png", r.x, r.y, r.w, r.h, 30, corner, CZM_White( card.enabled ? 245 : 140 ));
		CZM_DrawImage( UI_DIR "dot.png", r.x + pad, r.y + pad, badge, badge,
			card.enabled ? PackRGBA( 220, 38, 38, 255 ) : PackRGBA( 63, 70, 82, 255 ));
		snprintf( key, sizeof( key ), "%d", card.key % 10 );
		CZM_DrawText( keyFont, r.x + pad, r.y + ( r.h - CZM_FontHeight( keyFont )) / 2, badge, key, CZM_White(), QM_CENTER );

		CZM_DrawText( textFont, textX, r.y + ( r.h - CZM_FontHeight( textFont )) / 2, r.x + r.w - textX - pad - rightW, card.text,
			card.enabled ? CZM_White() : PackRGBA( 124, 133, 146, 255 ));
		if( card.right[0] )
			CZM_DrawText( rightFont, r.x + r.w - pad - rightW, r.y + ( r.h - CZM_FontHeight( rightFont )) / 2, rightW, card.right,
				PackRGBA( 154, 163, 175, 255 ), QM_RIGHT );
	}
}

/*
=================
The window of our server menu (czm_menu.amxx on the server): a header, the tabs of the plugins on
the left, cards with an icon, a subtitle and a badge. The menu text starts with "#czm1":

	#czm1<TAB>menu<TAB>section<TAB>head<TAB>sub<TAB>chip<TAB>foot
	#tabs<TAB>key:name:icon:badge<TAB>...
	\r1.\w name<TAB>sub<TAB>icon<TAB>RRGGBB<TAB>badge

A card sends slotN like a key, a tab asks the server for its section (czm_menu_tab), the cross
sends slot10. The window is modal: the menu is opened on purpose and closes with a pick.
=================
*/
#define SM_MAX_TABS  32
#define SM_MAX_CARDS 10

struct CzmMenuTab
{
	char key[16], name[40], icon[16], badge[8];
	CzmRect rect;
};

struct CzmMenuCard
{
	int key;                 // 1..9
	char name[64], sub[96], icon[16], badge[16];
	unsigned int color;
	bool enabled;
	CzmRect rect;
};

struct CzmRichMenu
{
	int serial, validSlots;
	char tab[16], head[64], sub[96], chip[96], foot[192], parent[16], root[16];
	CzmMenuTab tabs[SM_MAX_TABS];
	int numTabs;
	CzmMenuCard cards[SM_MAX_CARDS];
	int numCards;
};

static bool IsRichMenu( const char *value )
{
	const char *text = value ? strchr( value, '\n' ) : NULL;
	return text && !strncmp( text + 1, "#czm1\t", 6 );
}

// the next tab-separated field of [p, end)
static void NextField( const char *&p, const char *end, char *out, size_t size )
{
	const char *tab = p;

	while( tab < end && *tab != '\t' )
		tab++;
	TrimCopy( out, size, p, tab );
	p = tab < end ? tab + 1 : end;
}

static unsigned int HexColor( const char *hex, unsigned int fallback )
{
	unsigned int v;

	if( strlen( hex ) != 6 || sscanf( hex, "%6x", &v ) != 1 )
		return fallback;
	return PackRGBA(( v >> 16 ) & 255, ( v >> 8 ) & 255, v & 255, 255 );
}

static unsigned int Tint( unsigned int color, int alpha )
{
	return ( color & 0x00FFFFFF ) | ((unsigned int)Q_max( 0, Q_min( alpha, 255 )) << 24 );
}

// an icon name from the server: letters, digits and _ only
static const char *MenuIcon( const char *name )
{
	static char path[64];
	char clean[16];
	int n = 0;

	for( const char *p = name; *p && n < (int)sizeof( clean ) - 1; p++ )
	{
		if(( *p >= 'a' && *p <= 'z' ) || ( *p >= '0' && *p <= '9' ) || *p == '_' )
			clean[n++] = *p;
	}
	clean[n] = 0;

	// ours, then one the server gave with the map (gfx/czm/menu/<name>.png), else the star
	if( clean[0] )
	{
		snprintf( path, sizeof( path ), UI_DIR "icon_%s.png", clean );
		if( CZM_ImageAspect1000( path ))
			return path;
		snprintf( path, sizeof( path ), "gfx/czm/menu/%s.png", clean );
		if( CZM_ImageAspect1000( path ))
			return path;
	}
	return UI_DIR "icon_star.png";
}

static void ParseRich( const char *value, CzmRichMenu &m )
{
	const char *line;

	memset( &m, 0, sizeof( m ));
	m.serial = -1;
	sscanf( value, "%d %d", &m.serial, &m.validSlots );
	line = strchr( value, '\n' );
	if( !line )
		return;

	for( line++; *line; )
	{
		const char *end = strchr( line, '\n' );

		if( !end )
			end = line + strlen( line );

		if( !strncmp( line, "#czm1\t", 6 ))
		{
			const char *p = line + 6;
			char kind[16];

			NextField( p, end, kind, sizeof( kind ));
			NextField( p, end, m.tab, sizeof( m.tab ));
			NextField( p, end, m.head, sizeof( m.head ));
			NextField( p, end, m.sub, sizeof( m.sub ));
			NextField( p, end, m.chip, sizeof( m.chip ));
			NextField( p, end, m.foot, sizeof( m.foot ));
			NextField( p, end, m.parent, sizeof( m.parent ));
			NextField( p, end, m.root, sizeof( m.root ));
		}
		else if( !strncmp( line, "#tabs", 5 ))
		{
			const char *p = line + 5;

			if( p < end && *p == '\t' )
				p++;
			while( p < end && m.numTabs < SM_MAX_TABS )
			{
				char field[128], *part[4] = { field, NULL, NULL, NULL };
				int parts = 1;

				NextField( p, end, field, sizeof( field ));
				if( !field[0] )
					continue;
				for( char *c = field; *c && parts < 4; c++ )
				{
					if( *c == ':' )
					{
						*c = 0;
						part[parts++] = c + 1;
					}
				}
				CzmMenuTab &t = m.tabs[m.numTabs++];
				Q_strncpy( t.key, part[0], sizeof( t.key ));
				Q_strncpy( t.name, part[1] ? part[1] : part[0], sizeof( t.name ));
				Q_strncpy( t.icon, part[2] ? part[2] : "", sizeof( t.icon ));
				Q_strncpy( t.badge, part[3] ? part[3] : "", sizeof( t.badge ));
			}
		}
		else if( *line != '#' )
		{
			char visible[512], right[48], color;

			SplitLine( line, visible, sizeof( visible ), right, sizeof( right ), &color );
			// "1. name<TAB>sub<TAB>icon<TAB>color<TAB>badge"; 0 is the exit, the cross does it
			if( visible[0] >= '1' && visible[0] <= '9' && visible[1] == '.' && m.numCards < SM_MAX_CARDS )
			{
				CzmMenuCard &c = m.cards[m.numCards++];
				const char *p = visible + 2, *e = visible + strlen( visible );
				char hex[16];

				c.key = visible[0] - '0';
				NextField( p, e, c.name, sizeof( c.name ));
				NextField( p, e, c.sub, sizeof( c.sub ));
				NextField( p, e, c.icon, sizeof( c.icon ));
				NextField( p, e, hex, sizeof( hex ));
				NextField( p, e, c.badge, sizeof( c.badge ));
				c.color = HexColor( hex, PackRGBA( 229, 63, 77, 255 ));
				c.enabled = ( m.validSlots & ( 1 << ( c.key - 1 ))) && color != 'd';
			}
		}
		line = *end ? end + 1 : end;
	}
}

// Native AMXX selectors (players, duration, shop categories) keep their real slot
// commands while using the same window as the registered server sections.
static void PlainAsRich( const char *value, const CzmRichMenu *previous, CzmRichMenu &m )
{
	ParseMenu( value );
	if( previous )
		m = *previous;
	else
		memset( &m, 0, sizeof( m ));
	m.serial = s_menu.serial;
	m.validSlots = s_menu.validSlots;
	Q_strncpy( m.parent, previous && previous->tab[0] ? previous->tab : previous && previous->parent[0] ? previous->parent : "main", sizeof( m.parent ));
	Q_strncpy( m.root, previous && previous->root[0] ? previous->root : previous && previous->tab[0] ? previous->tab : "main", sizeof( m.root ));
	m.tab[0] = 0;
	Q_strncpy( m.head, CZM_IsRussian() ? "МЕНЮ СЕРВЕРА" : "SERVER MENU", sizeof( m.head ));
	Q_strncpy( m.sub, s_menu.title, sizeof( m.sub ));
	if( !previous )
		Q_strncpy( m.foot, "COUNTER ZOMBIE MOBILE", sizeof( m.foot ));
	// Plain menus can carry a selected player or a confirmation above the choices.
	// Preserve it visibly instead of hiding that context in the underlying HUD.
	if( s_menu.numLines )
	{
		char context[256];
		snprintf( context, sizeof( context ), "%s · %s", s_menu.title, s_menu.lines[0] );
		Q_strncpy( m.sub, context, sizeof( m.sub ));
	}
	m.numCards = 0;
	for( int i = 0; i < s_menu.numCards && m.numCards < SM_MAX_CARDS; i++ )
	{
		const CzmCard &plain = s_menu.cards[i];
		if( plain.key == 10 )
			continue;
		CzmMenuCard &card = m.cards[m.numCards++];
		memset( &card, 0, sizeof( card ));
		card.key = plain.key;
		card.enabled = plain.enabled;
		card.color = PackRGBA( 229, 63, 77, 255 );
		Q_strncpy( card.name, plain.text, sizeof( card.name ));
		Q_strncpy( card.sub, plain.right, sizeof( card.sub ));
		Q_strncpy( card.icon, "chevron_right", sizeof( card.icon ));
	}
}

class CCzmServerWindow : public CMenuBaseClientWindow
{
public:
	typedef CMenuBaseClientWindow BaseClass;
	CCzmServerWindow();

	void Open( const CzmRichMenu &menu );
	void Update( const CzmRichMenu &menu );
	void Close( bool exitMenu );
	// a card was picked: the next menu of the server may still come
	bool Waiting( void ) const { return m_iPicked >= 0 && uiStatic.realTime - m_iPickTime < 700; }
	int Serial( void ) const { return m_menu.serial; }
	const CzmRichMenu &Menu( void ) const { return m_menu; }

	void Show() override;
	void Hide() override;
	void Draw() override;
	bool KeyDown( int key ) override;
	bool KeyUp( int key ) override;

private:
	enum
	{
		HIT_NONE = 0,
		HIT_CLOSE,
		HIT_BACK,
		HIT_TABS_UP,
		HIT_TABS_DOWN,
		HIT_TAB = 10,    // + tab
		HIT_CARD = 100,  // + card, separate from all 32 possible tabs
	};

	void Layout( int shift );
	int HitTest( void ) const;
	bool IsPressed( int hit ) const { return m_iPressed == hit && HitTest() == hit; }
	void Activate( int hit );
	void DrawHeader( int a );
	void DrawTabs( int a );
	void DrawCards( int a );
	void DrawFooter( int a );

	CzmRichMenu m_menu;
	char m_szTab[16];        // the tab asked for, lit before the server answers
	int m_iPressed;
	int m_iPicked;           // card, -1 none
	int m_iOpenTime, m_iChangeTime, m_iPickTime;
	int m_iTabFirst, m_iTabRows;
	bool m_bClosing;

	int W, H;
	CzmRect m_win, m_head, m_side, m_body, m_foot, m_close, m_back, m_tabsUp, m_tabsDown;
};

static int s_iClosedSerial = -1;

CCzmServerWindow::CCzmServerWindow() : BaseClass( "CzmServerWindow" )
{
	memset( &m_menu, 0, sizeof( m_menu ));
	m_szTab[0] = 0;
	m_iPressed = HIT_NONE;
	m_iPicked = -1;
	m_iOpenTime = m_iChangeTime = m_iPickTime = 0;
	m_iTabFirst = 0;
	m_iTabRows = 10;
	m_bClosing = false;
	W = H = 0;
}

void CCzmServerWindow::Open( const CzmRichMenu &menu )
{
	m_menu = menu;
	Q_strncpy( m_szTab, menu.root[0] ? menu.root : menu.tab, sizeof( m_szTab ));
	m_iTabFirst = 0;
	m_iPressed = HIT_NONE;
	m_iPicked = -1;
	m_iOpenTime = m_iChangeTime = uiStatic.realTime;
	m_bClosing = false;
	CZM_KeepClientMenu( this );
	Show();
}

void CCzmServerWindow::Update( const CzmRichMenu &menu )
{
	bool sameTab = !strcmp( menu.tab, m_menu.tab );

	m_menu = menu;
	Q_strncpy( m_szTab, menu.root[0] ? menu.root : menu.tab, sizeof( m_szTab ));
	for( int i = 0; i < menu.numTabs; i++ )
		if( !strcmp( menu.tabs[i].key, m_szTab ) && ( i < m_iTabFirst || i >= m_iTabFirst + m_iTabRows ))
			m_iTabFirst = i;
	m_iPressed = HIT_NONE;
	m_iPicked = -1;
	// another section slides in, the same one (a toggle, a new count) just changes
	if( !sameTab )
		m_iChangeTime = uiStatic.realTime;
}

void CCzmServerWindow::Close( bool exitMenu )
{
	if( m_bClosing )
		return;
	if( exitMenu )
	{
		s_iClosedSerial = m_menu.serial;
		EngFuncs::ClientCmd( false, "slot10\n" );
	}
	Hide();
}

void CCzmServerWindow::Show()
{
	EngFuncs::KEY_SetDest( KEY_MENU );
	EngFuncs::ClientCmd( true, "touch_setclientonly 1" );
	BaseClass::Show();
}

// the stock way, on the next frame (Hide() on the only client window would leave it in the stack)
void CCzmServerWindow::Hide()
{
	if( m_bClosing )
		return;
	m_bClosing = true;
	CZM_CloseClientMenuSoon( this );
}

void CCzmServerWindow::Layout( int shift )
{
	W = ScreenWidth;
	H = ScreenHeight;

	int winW = Q_min( (int)( W * 0.60f ), (int)( H * 1.30f ));
	int winH = H * 0.86f;
	int headH = H * 0.12f, footH = H * 0.056f;
	int sideW = m_menu.numTabs ? winW * 0.20f : 0;

	m_win = CZM_Rect( W * 0.02f + shift, ( H - winH ) / 2, winW, winH );
	m_head = CZM_Rect( m_win.x, m_win.y, m_win.w, headH );
	m_foot = CZM_Rect( m_win.x, m_win.y + m_win.h - footH, m_win.w, footH );
	m_side = CZM_Rect( m_win.x, m_win.y + headH, sideW, m_win.h - headH - footH );
	m_body = CZM_Rect( m_win.x + sideW, m_win.y + headH, m_win.w - sideW, m_win.h - headH - footH );

	int closeS = headH * 0.48f;
	m_close = CZM_Rect( m_head.x + m_head.w - closeS - H * 0.025f, m_head.y + ( headH - closeS ) / 2, closeS, closeS );

	int pad = H * 0.016f, tabH = H * 0.064f, tabGap = H * 0.008f;
	int tabTop = m_side.y + pad;
	m_tabsUp = m_tabsDown = CZM_Rect( 0, 0, 0, 0 );
	if( m_menu.numTabs > 10 )
	{
		int scrollH = H * 0.036f;
		m_iTabRows = Q_max( 1, ( m_side.h - pad * 2 - scrollH * 2 - tabGap * 2 ) / ( tabH + tabGap ));
		m_iTabFirst = bound( 0, m_iTabFirst, Q_max( 0, m_menu.numTabs - m_iTabRows ));
		m_tabsUp = CZM_Rect( m_side.x + pad, tabTop, m_side.w - pad * 2, scrollH );
		m_tabsDown = CZM_Rect( m_side.x + pad, m_side.y + m_side.h - pad - scrollH, m_side.w - pad * 2, scrollH );
		tabTop += scrollH + tabGap;
	}
	else
	{
		m_iTabFirst = 0;
		m_iTabRows = m_menu.numTabs;
		if( m_menu.numTabs )
			tabH = Q_min( tabH, ( m_side.h - pad * 2 - tabGap * ( m_menu.numTabs - 1 )) / m_menu.numTabs );
	}
	for( int i = 0; i < m_menu.numTabs; i++ )
		m_menu.tabs[i].rect = i >= m_iTabFirst && i < m_iTabFirst + m_iTabRows
			? CZM_Rect( m_side.x + pad, tabTop + ( i - m_iTabFirst ) * ( tabH + tabGap ), m_side.w - pad * 2, tabH )
			: CZM_Rect( 0, 0, 0, 0 );

	// two columns, the first filled first, five rows at most like the server sends nine cards
	int cpad = H * 0.02f, gap = H * 0.015f;
	int cardW = ( m_body.w - cpad * 2 - gap ) / 2;
	int navigation = m_menu.parent[0] ? H * 0.066f : 0;
	m_back = navigation ? CZM_Rect( m_body.x + cpad, m_body.y + cpad, H * 0.24f, H * 0.05f ) : CZM_Rect( 0, 0, 0, 0 );
	int cardH = Q_min( (int)( H * 0.10f ), ( m_body.h - navigation - cpad * 2 - gap * 4 ) / 5 );
	int perColumn = Q_max( 1, ( m_menu.numCards + 1 ) / 2 );
	for( int i = 0; i < m_menu.numCards; i++ )
	{
		int col = i / perColumn, row = i % perColumn;
		m_menu.cards[i].rect = CZM_Rect( m_body.x + cpad + col * ( cardW + gap ), m_body.y + cpad + navigation + row * ( cardH + gap ), cardW, cardH );
	}
}

int CCzmServerWindow::HitTest( void ) const
{
	int x = uiStatic.cursorX, y = uiStatic.cursorY;

	if( m_close.Grown( H * 0.02f ).Contains( x, y ))
		return HIT_CLOSE;
	if( m_back.w && m_back.Contains( x, y ))
		return HIT_BACK;
	if( m_tabsUp.w && m_tabsUp.Contains( x, y ))
		return HIT_TABS_UP;
	if( m_tabsDown.w && m_tabsDown.Contains( x, y ))
		return HIT_TABS_DOWN;
	for( int i = 0; i < m_menu.numTabs; i++ )
	{
		if( m_menu.tabs[i].rect.w > 0 && m_menu.tabs[i].rect.Contains( x, y ))
			return HIT_TAB + i;
	}
	for( int i = 0; i < m_menu.numCards; i++ )
	{
		if( m_menu.cards[i].rect.Contains( x, y ))
			return HIT_CARD + i;
	}
	return HIT_NONE;
}

void CCzmServerWindow::Activate( int hit )
{
	if( hit == HIT_CLOSE )
	{
		CZM_PlayClick();
		Close( true );
		return;
	}
	if( hit == HIT_BACK && m_menu.parent[0] )
	{
		CZM_PlayClick();
		EngFuncs::ClientCmdF( false, "czm_menu_tab %s\n", m_menu.parent );
		return;
	}
	if( hit == HIT_TABS_UP || hit == HIT_TABS_DOWN )
	{
		m_iTabFirst = bound( 0, m_iTabFirst + ( hit == HIT_TABS_UP ? -1 : 1 ), Q_max( 0, m_menu.numTabs - m_iTabRows ));
		return;
	}

	if( hit >= HIT_TAB && hit < HIT_TAB + m_menu.numTabs )
	{
		const CzmMenuTab &t = m_menu.tabs[hit - HIT_TAB];

		if( !strcmp( t.key, m_menu.tab ))
			return;
		CZM_PlayClick();
		Q_strncpy( m_szTab, t.key, sizeof( m_szTab ));
		EngFuncs::ClientCmdF( false, "czm_menu_tab %s\n", t.key );
		return;
	}

	if( hit >= HIT_CARD && hit < HIT_CARD + m_menu.numCards && m_iPicked < 0 )
	{
		const CzmMenuCard &c = m_menu.cards[hit - HIT_CARD];

		if( !c.enabled )
			return;
		CZM_PlayClick();
		m_iPicked = hit - HIT_CARD;
		m_iPickTime = uiStatic.realTime;
		EngFuncs::ClientCmdF( false, "slot%d\n", c.key );
	}
}

bool CCzmServerWindow::KeyDown( int key )
{
	if( UI::Key::IsEscape( key ))
	{
		if( m_menu.parent[0] ) Activate( HIT_BACK );
		else Close( true );
		return true;
	}
	if( key == K_MWHEELUP || key == K_MWHEELDOWN )
	{
		Activate( key == K_MWHEELUP ? HIT_TABS_UP : HIT_TABS_DOWN );
		return true;
	}

	if( UI::Key::IsLeftMouse( key ))
	{
		Layout( 0 );
		m_iPressed = HitTest();
		return true;
	}

	// the keys of a keyboard still pick, like the text menu
	if( key >= '1' && key <= '9' )
	{
		for( int i = 0; i < m_menu.numCards; i++ )
		{
			if( m_menu.cards[i].key == key - '0' )
				Activate( HIT_CARD + i );
		}
		return true;
	}
	if( key == '0' )
		Close( true );
	return true;
}

bool CCzmServerWindow::KeyUp( int key )
{
	if( UI::Key::IsLeftMouse( key ))
	{
		int pressed = m_iPressed, hit;

		Layout( 0 );
		hit = HitTest();
		m_iPressed = HIT_NONE;
		if( hit == pressed && hit != HIT_NONE )
			Activate( hit );
	}
	return true;
}

void CCzmServerWindow::DrawHeader( int a )
{
	const CzmRect &h = m_head;
	HFont titleFont = CZM_Font( CZMF_MENU_TITLE ), subFont = CZM_Font( CZMF_UI_META ), chipFont = CZM_Font( CZMF_SMALL );
	int tile = h.h * 0.64f, tx = h.x + H * 0.025f, ty = h.y + ( h.h - tile ) / 2;
	const char *icon = UI_DIR "icon_star.png";

	for( int i = 0; i < m_menu.numTabs; i++ )
	{
		if( !strcmp( m_menu.tabs[i].key, m_szTab ))
			icon = MenuIcon( m_menu.tabs[i].icon );
	}

	// a red light in the corner, the lit tile with the icon of the open tab
	CZM_DrawImage( UI_DIR "glow.png", h.x - h.h * 0.6f, h.y - h.h * 0.9f, h.h * 3.2f, h.h * 2.4f, PackRGBA( 229, 63, 77, a * 60 / 255 ));
	CZM_DrawImage( UI_DIR "glow.png", tx - tile * 0.4f, ty - tile * 0.4f, tile * 1.8f, tile * 1.8f, PackRGBA( 229, 63, 77, a * 90 / 255 ));
	CZM_DrawSliced( UI_DIR "smenu_tile.png", tx, ty, tile, tile, 30, tile * 0.24f, PackRGBA( 240, 80, 92, a ));
	CZM_DrawSliced( UI_DIR "smenu_tile.png", tx, ty, tile, tile, 30, tile * 0.24f, PackRGBA( 229, 63, 77, a ));
	CZM_DrawSliced( UI_DIR "smenu_ring.png", tx, ty, tile, tile, 30, tile * 0.24f, PackRGBA( 255, 140, 150, a * 160 / 255 ));
	CZM_DrawImage( icon, tx + tile * 0.24f, ty + tile * 0.24f, tile * 0.52f, tile * 0.52f, CZM_White( a ));

	// the title in two colours: the last word red ("МЕНЮ СЕРВЕРА")
	int textX = tx + tile + H * 0.022f;
	int chipW = 0, chipH = h.h * 0.42f;
	if( m_menu.chip[0] )
		chipW = CZM_TextWidth( chipFont, m_menu.chip ) + chipH * 1.4f;
	int textW = m_close.x - textX - chipW - H * 0.05f;
	int titleY = h.y + h.h * 0.17f;
	const char *space = strrchr( m_menu.head, ' ' );
	if( space && space > m_menu.head )
	{
		char first[64];
		TrimCopy( first, sizeof( first ), m_menu.head, space + 1 );
		int fw = CZM_TextWidth( titleFont, first ) + CZM_TextWidth( titleFont, " " );
		CZM_DrawText( titleFont, textX, titleY, textW, first, CZM_White( a ));
		CZM_DrawText( titleFont, textX + fw, titleY, textW - fw, space + 1, PackRGBA( 229, 63, 77, a ));
	}
	else
		CZM_DrawText( titleFont, textX, titleY, textW, m_menu.head, CZM_White( a ));
	CZM_DrawText( subFont, textX, titleY + CZM_FontHeight( titleFont ) + h.h * 0.04f, textW, m_menu.sub, PackRGBA( 155, 166, 184, a ));

	// map, time, players; the cross
	if( chipW )
	{
		CzmRect c = CZM_Rect( m_close.x - H * 0.02f - chipW, h.y + ( h.h - chipH ) / 2, chipW, chipH );
		int dot = chipH * 0.2f;

		CZM_DrawPill( UI_DIR "button_secondary.png", c.x, c.y, c.w, c.h, CZM_White( a * 220 / 255 ));
		CZM_DrawImage( UI_DIR "glow.png", c.x + chipH * 0.42f - dot * 2, c.y + c.h / 2 - dot * 2, dot * 4, dot * 4, PackRGBA( 107, 218, 167, a * 160 / 255 ));
		CZM_DrawImage( UI_DIR "dot.png", c.x + chipH * 0.42f - dot / 2, c.y + ( c.h - dot ) / 2, dot, dot, PackRGBA( 107, 218, 167, a ));
		CZM_DrawText( chipFont, c.x + chipH * 0.72f, c.y + ( c.h - CZM_FontHeight( chipFont )) / 2, c.w - chipH, m_menu.chip, PackRGBA( 207, 214, 224, a ));
	}
	CZM_DrawImage( UI_DIR "chip_round.png", m_close.x, m_close.y, m_close.w, m_close.h,
		IsPressed( HIT_CLOSE ) ? PackRGBA( 229, 63, 77, a ) : CZM_White( a ));
	int ci = m_close.w * 0.42f;
	CZM_DrawImage( UI_DIR "icon_close.png", m_close.x + ( m_close.w - ci ) / 2, m_close.y + ( m_close.h - ci ) / 2, ci, ci, PackRGBA( 255, 180, 187, a ));

	UI_FillRect( h.x, h.y + h.h - 1, h.w, Q_max( 1, H / 700 ), PackRGBA( 255, 255, 255, a * 18 / 255 ));
}

void CCzmServerWindow::DrawTabs( int a )
{
	if( !m_menu.numTabs )
		return;

	HFont font = CZM_Font( CZMF_NAV ), badgeFont = CZM_Font( CZMF_UI_META );

	UI_FillRect( m_side.x, m_side.y, m_side.w, m_side.h, PackRGBA( 0, 0, 0, a * 46 / 255 ));
	UI_FillRect( m_side.x + m_side.w - 1, m_side.y, Q_max( 1, H / 700 ), m_side.h, PackRGBA( 255, 255, 255, a * 18 / 255 ));

	for( int i = 0; i < m_menu.numTabs; i++ )
	{
		const CzmMenuTab &t = m_menu.tabs[i];
		const CzmRect &r = t.rect;
		if( r.w <= 0 )
			continue;
		bool on = !strcmp( t.key, m_szTab ), pressed = IsPressed( HIT_TAB + i );
		int icon = r.h * 0.42f, ix = r.x + r.h * 0.30f;

		if( on )
		{
			CZM_DrawImage( UI_DIR "glow.png", r.x - r.h * 0.4f, r.y - r.h * 0.5f, r.w + r.h * 0.8f, r.h * 2.0f, PackRGBA( 229, 63, 77, a * 70 / 255 ));
			CZM_DrawSliced( UI_DIR "tab_on.png", r.x, r.y, r.w, r.h, 30, r.h * 0.24f, CZM_White( a ));
		}
		else if( pressed )
			CZM_DrawSliced( UI_DIR "card.png", r.x, r.y, r.w, r.h, 30, r.h * 0.24f, CZM_White( a ));

		CZM_DrawImage( MenuIcon( t.icon ), ix, r.y + ( r.h - icon ) / 2, icon, icon, on ? CZM_White( a ) : PackRGBA( 142, 153, 170, a ));
		int lx = ix + icon + r.h * 0.26f, lw = r.x + r.w - lx - r.h * 0.2f;
		if( t.badge[0] )
		{
			int bh = r.h * 0.40f, bw = Q_max( bh, CZM_TextWidth( badgeFont, t.badge ) + bh / 2 );
			int bx = r.x + r.w - bw - r.h * 0.18f;

			CZM_DrawPill( UI_DIR "pill_lang_on.png", bx, r.y + ( r.h - bh ) / 2, bw, bh, on ? PackRGBA( 255, 255, 255, a ) : CZM_White( a ));
			CZM_DrawText( badgeFont, bx, r.y + ( r.h - CZM_FontHeight( badgeFont )) / 2, bw, t.badge, on ? PackRGBA( 185, 28, 40, a ) : CZM_White( a ), QM_CENTER );
			lw -= bw + r.h * 0.1f;
		}
		CZM_DrawText( font, lx, r.y + ( r.h - CZM_FontHeight( font )) / 2, lw, t.name, on ? CZM_White( a ) : PackRGBA( 201, 209, 220, a ));
	}
	if( m_tabsUp.w )
	{
		CZM_DrawButton( UI_DIR "button_secondary.png", m_tabsUp, CZM_IsRussian() ? "Выше" : "Up",
			CZM_White( m_iTabFirst > 0 ? a : a / 3 ), IsPressed( HIT_TABS_UP ), CZMF_UI_META );
		CZM_DrawButton( UI_DIR "button_secondary.png", m_tabsDown, CZM_IsRussian() ? "Ниже" : "Down",
			CZM_White( m_iTabFirst + m_iTabRows < m_menu.numTabs ? a : a / 3 ), IsPressed( HIT_TABS_DOWN ), CZMF_UI_META );
	}
}

void CCzmServerWindow::DrawCards( int a )
{
	HFont numFont = CZM_Font( CZMF_SHOP_PRICE ), nameFont = CZM_Font( CZMF_SHOP_NAME ), subFont = CZM_Font( CZMF_UI_META );
	float t = Q_min( 1.0f, ( uiStatic.realTime - m_iChangeTime ) / 160.0f );
	int ca = a * t;
	int slide = ( 1.0f - t ) * H * 0.02f;
	if( m_back.w )
		CZM_DrawButton( UI_DIR "button_secondary.png", m_back, CZM_IsRussian() ? "‹ Назад" : "‹ Back",
			CZM_White( a ), IsPressed( HIT_BACK ), CZMF_UI_META );

	for( int i = 0; i < m_menu.numCards; i++ )
	{
		const CzmMenuCard &c = m_menu.cards[i];
		CzmRect r = c.rect;
		bool pressed = IsPressed( HIT_CARD + i ), picked = m_iPicked == i;
		int alpha = c.enabled ? ca : ca * 110 / 255;

		r.y += slide;
		if( pressed || picked )
		{
			// the card sinks and lights up in its colour
			int dx = r.w * 0.012f, dy = r.h * 0.03f;
			int m = r.h * 0.22f;

			r = CZM_Rect( r.x + dx, r.y + dy, r.w - dx * 2, r.h - dy * 2 );
			CZM_DrawSliced( UI_DIR "smenu_lit.png", r.x - m, r.y - m, r.w + m * 2, r.h + m * 2, 58, m + r.h * 0.2f, Tint( c.color, alpha * 200 / 255 ));
		}

		int corner = r.h * 0.2f;
		CZM_DrawSliced( UI_DIR "card.png", r.x, r.y, r.w, r.h, 30, corner, CZM_White( alpha * 245 / 255 ));
		UI_FillRect( r.x + Q_max( 1, H / 500 ), r.y + r.h * 0.2f, Q_max( 2, H / 300 ), r.h * 0.6f, Tint( c.color, alpha ));

		// the lit tile with the icon
		int tile = r.h * 0.70f, tx = r.x + r.h * 0.16f, ty = r.y + ( r.h - tile ) / 2;
		CZM_DrawImage( UI_DIR "glow.png", tx - tile * 0.25f, ty - tile * 0.25f, tile * 1.5f, tile * 1.5f, Tint( c.color, alpha * 55 / 255 ));
		CZM_DrawSliced( UI_DIR "smenu_tile.png", tx, ty, tile, tile, 30, tile * 0.24f, Tint( c.color, alpha * 150 / 255 ));
		CZM_DrawSliced( UI_DIR "smenu_ring.png", tx, ty, tile, tile, 30, tile * 0.24f, Tint( c.color, alpha * 150 / 255 ));
		CZM_DrawImage( MenuIcon( c.icon ), tx + tile * 0.22f, ty + tile * 0.22f, tile * 0.56f, tile * 0.56f, Tint( c.color, alpha ));

		// the number, the name and the subtitle
		char key[4];
		snprintf( key, sizeof( key ), "%d", c.key );
		int nx = tx + tile + r.h * 0.16f, nw = CZM_TextWidth( numFont, "8" );
		CZM_DrawText( numFont, nx, r.y + ( r.h - CZM_FontHeight( numFont )) / 2, nw * 2, key, Tint( c.color, alpha ));

		int chev = r.h * 0.26f, textX = nx + nw + r.h * 0.18f;
		int textW = r.x + r.w - textX - chev - r.h * 0.28f;
		int badgeW = 0;
		if( c.badge[0] )
		{
			bool red = c.badge[0] == '!';
			const char *text = red ? c.badge + 1 : c.badge;
			int bh = r.h * 0.30f;

			badgeW = Q_max( bh, CZM_TextWidth( subFont, text ) + bh * 0.8f );
			int bx = r.x + r.w - chev - r.h * 0.34f - badgeW, by = r.y + r.h * 0.14f;
			CZM_DrawPill( red ? UI_DIR "pill_lang_on.png" : UI_DIR "button_secondary.png", bx, by, badgeW, bh, CZM_White( alpha ));
			CZM_DrawText( subFont, bx, by + ( bh - CZM_FontHeight( subFont )) / 2, badgeW, text, red ? CZM_White( alpha ) : PackRGBA( 205, 213, 223, alpha ), QM_CENTER );
		}

		int nameH = CZM_FontHeight( nameFont ), subH = c.sub[0] ? CZM_FontHeight( subFont ) : 0;
		int top = r.y + ( r.h - nameH - subH - ( subH ? r.h * 0.05f : 0 )) / 2;
		CZM_DrawText( nameFont, textX, top, textW - ( badgeW ? badgeW + r.h * 0.1f : 0 ), c.name, c.enabled ? CZM_White( alpha ) : PackRGBA( 150, 158, 170, alpha ));
		if( subH )
			CZM_DrawText( subFont, textX, top + nameH + r.h * 0.05f, textW, c.sub, PackRGBA( 155, 166, 184, alpha ));

		CZM_DrawImage( UI_DIR "icon_chevron.png", r.x + r.w - chev - r.h * 0.22f, r.y + ( r.h - chev ) / 2, chev, chev, PackRGBA( 107, 118, 134, alpha ));
	}
}

void CCzmServerWindow::DrawFooter( int a )
{
	HFont font = CZM_Font( CZMF_UI_META );
	const CzmRect &f = m_foot;
	int icon = f.h * 0.40f, y = f.y + ( f.h - CZM_FontHeight( font )) / 2;
	int x = f.x + H * 0.025f;

	UI_FillRect( f.x, f.y, f.w, Q_max( 1, H / 700 ), PackRGBA( 255, 255, 255, a * 18 / 255 ));
	CZM_DrawImage( UI_DIR "icon_shield.png", x, f.y + ( f.h - icon ) / 2, icon, icon, PackRGBA( 125, 136, 153, a ));
	CZM_DrawText( font, x + icon + H * 0.012f, y, f.w * 0.4f, "COUNTER ZOMBIE MOBILE", PackRGBA( 125, 136, 153, a ));
	if( m_menu.foot[0] )
		CZM_DrawText( font, f.x + f.w * 0.4f, y, f.w * 0.6f - H * 0.025f, m_menu.foot, PackRGBA( 125, 136, 153, a ), QM_RIGHT );
}

void CCzmServerWindow::Draw()
{
	if( m_bClosing )
		return;
	if( !CL_IsActive( ))
	{
		Close( false );
		return;
	}

	// it opens from the left in a sixth of a second
	float t = Q_min( 1.0f, ( uiStatic.realTime - m_iOpenTime ) / 170.0f );
	float ease = 1.0f - ( 1.0f - t ) * ( 1.0f - t );
	int a = 255 * ease;

	Layout( -( 1.0f - ease ) * ScreenHeight * 0.05f );
	UI_FillRect( 0, 0, W, H, PackRGBA( 4, 6, 10, a * 110 / 255 ));
	CZM_DrawImage( UI_DIR "glow.png", m_win.x - H * 0.04f, m_win.y - H * 0.04f, m_win.w + H * 0.08f, m_win.h + H * 0.08f, PackRGBA( 229, 63, 77, a * 40 / 255 ));
	CZM_DrawSliced( UI_DIR "smenu_frame.png", m_win.x, m_win.y, m_win.w, m_win.h, 48, H * 0.028f, CZM_White( a ));
	UI_FillRect( m_win.x + m_win.w * 0.08f, m_win.y + Q_max( 1, H / 700 ), m_win.w * 0.84f, Q_max( 2, H / 320 ), PackRGBA( 229, 63, 77, a * 200 / 255 ));

	DrawHeader( a );
	DrawTabs( a );
	DrawCards( a );
	DrawFooter( a );
}

ADD_MENU3( menu_czmserver, CCzmServerWindow, UI_CzmServer_Menu );

void UI_CzmServer_Menu( void )
{
}

/*
=================
The team menu: a compact card instead of the stock window. The map with its picture, the mode
and the players, two lines about the map in the menu's language (maps/<map>.txt), then the
buttons: on our servers "Play" and "Spectate" (the side and the model are the server's business),
on other servers Terrorists / Auto / Counter-terrorists with the players of each side.
=================
*/
class CCzmTeamCard : public CMenuBaseClientWindow
{
public:
	typedef CMenuBaseClientWindow BaseClass;
	CCzmTeamCard() : BaseClass( "CzmTeamCard" ), m_bSpectate( false ), m_bCancel( false ), m_iSlot( -1 ),
		m_iPressed( 0 ), m_iOpenTime( 0 ), m_bClosing( false ), W( 0 ), H( 0 ) { m_szMap[0] = m_szText[0] = 0; }

	void Open( int param1 );
	void Show() override;
	void Hide() override;
	void Draw() override;
	bool KeyDown( int key ) override;
	bool KeyUp( int key ) override;

private:
	enum { BTN_PLAY = 1, BTN_SPECTATE, BTN_T, BTN_AUTO, BTN_CT, BTN_CLOSE, BTN_COUNT };
	void Layout( void );
	int HitTest( void ) const;
	void Press( int button );
	void ReadDescription( void );

	char m_szMap[64];
	char m_szText[512];
	bool m_bSpectate, m_bCancel;
	int m_iSlot;               // our server (CZM_OFFICIAL_*), -1 another
	int m_iCounts[2];
	int m_iPressed;
	int m_iOpenTime;
	bool m_bClosing;
	int W, H;
	CzmRect m_card, m_map, m_btn[BTN_COUNT];
	int m_iTextY;
};

void CCzmTeamCard::ReadDescription( void )
{
	char path[96];
	char *file;
	bool ru = CZM_IsRussian();

	m_szText[0] = 0;
	snprintf( path, sizeof( path ), "maps/%s.txt", m_szMap );
	file = (char *)EngFuncs::COM_LoadFile( path );
	if( !file )
		return;

	// ours: the map name, then a Russian and an English block; others: any text after the name
	const char *blocks[4] = { NULL, NULL, NULL, NULL };
	int count = 0;
	for( char *p = file; *p && count < 4; )
	{
		while( *p == '\n' || *p == '\r' )
			p++;
		if( !*p )
			break;
		blocks[count++] = p;
		char *end = strstr( p, "\n\n" );
		char *endr = strstr( p, "\r\n\r\n" );
		if( endr && ( !end || endr < end ))
			end = endr;
		if( !end )
			break;
		*end = 0;
		p = end + 1;
	}

	const char *text = NULL;
	if( count >= 3 )
		text = ru ? blocks[1] : blocks[2];
	else if( count == 2 )
		text = blocks[1];
	else if( count == 1 && strcmp( blocks[0], m_szMap ))
		text = blocks[0];
	if( text )
	{
		// the first line only: ours carry the commands on the next one, the card has them below
		size_t n = 0;
		for( const char *c = text; *c && *c != '\n' && *c != '\r' && n < sizeof( m_szText ) - 1; c++ )
			m_szText[n++] = *c;
		m_szText[n] = 0;
	}
	EngFuncs::COM_FreeFile( file );
}

void CCzmTeamCard::Open( int param1 )
{
	const char *map = g_pClient ? g_pClient->GetLevelName() : NULL;
	const char *counts = EngFuncs::GetCvarString( "czm_team_counts" );

	Q_strncpy( m_szMap, map && map[0] ? map : "", sizeof( m_szMap ));
	ReadDescription();
	m_bSpectate = ( param1 & 1 ) != 0;
	m_bCancel = ( param1 & 4 ) != 0;
	m_iSlot = CZM_OfficialSlotNow();
	m_iCounts[0] = m_iCounts[1] = 0;
	if( counts )
		sscanf( counts, "%d %d", &m_iCounts[0], &m_iCounts[1] );
	m_iPressed = 0;
	m_iOpenTime = uiStatic.realTime;
	m_bClosing = false;
	// our welcome is on the card: the MOTD box goes
	if( m_iSlot >= 0 )
		EngFuncs::CvarSetString( "czm_motd_off", "1" );
	CZM_KeepClientMenu( this );
	Show();
}

void CCzmTeamCard::Show()
{
	EngFuncs::KEY_SetDest( KEY_MENU );
	EngFuncs::ClientCmd( true, "touch_setclientonly 1" );
	BaseClass::Show();
}

void CCzmTeamCard::Hide()
{
	if( m_bClosing )
		return;
	m_bClosing = true;
	CZM_CloseClientMenuSoon( this );
}

void CCzmTeamCard::Layout( void )
{
	W = ScreenWidth;
	H = ScreenHeight;

	int cw = Q_min( (int)( W * 0.40f ), (int)( H * 0.80f ));
	int pad = H * 0.034f, mapH = cw * 0.27f, btnH = H * 0.088f, gap = H * 0.016f;
	HFont nameFont = CZM_Font( CZMF_MENU_TITLE ), textFont = CZM_Font( CZMF_PANEL_TEXT ), hintFont = CZM_Font( CZMF_UI_META );
	int starts[4], lines = m_szText[0] ? CZM_WrapText( textFont, m_szText, cw - pad * 2, starts, 3 ) : 0;
	int rows = m_iSlot >= 0 ? 1 : ( m_bSpectate ? 2 : 1 );
	int ch = H * 0.014f + mapH + CZM_FontHeight( nameFont ) * 0.6f + lines * ( CZM_FontHeight( textFont ) + H * 0.004f ) + gap * 1.6f
		+ rows * btnH + ( rows - 1 ) * gap + ( m_iSlot >= 0 ? CZM_FontHeight( hintFont ) + gap * 2 : 0 ) + pad;

	m_card = CZM_Rect(( W - cw ) / 2, ( H - ch ) / 2, cw, ch );
	m_map = CZM_Rect( m_card.x + H * 0.014f, m_card.y + H * 0.014f, cw - H * 0.028f, mapH );
	m_iTextY = m_map.y + mapH + CZM_FontHeight( nameFont ) * 0.6f;

	int y = m_iTextY + lines * ( CZM_FontHeight( textFont ) + H * 0.004f ) + gap * 1.6f;
	int x = m_card.x + pad, w = cw - pad * 2;

	for( int i = 0; i < BTN_COUNT; i++ )
		m_btn[i] = CZM_Rect( 0, 0, 0, 0 );

	if( m_iSlot >= 0 )
	{
		int playW = m_bSpectate ? ( w - gap ) * 0.62f : w;
		m_btn[BTN_PLAY] = CZM_Rect( x, y, playW, btnH );
		if( m_bSpectate )
			m_btn[BTN_SPECTATE] = CZM_Rect( x + playW + gap, y, w - playW - gap, btnH );
	}
	else
	{
		int third = ( w - gap * 2 ) / 3;
		m_btn[BTN_T] = CZM_Rect( x, y, third, btnH );
		m_btn[BTN_AUTO] = CZM_Rect( x + third + gap, y, third, btnH );
		m_btn[BTN_CT] = CZM_Rect( x + ( third + gap ) * 2, y, w - ( third + gap ) * 2, btnH );
		if( m_bSpectate )
			m_btn[BTN_SPECTATE] = CZM_Rect( x, y + btnH + gap, w, btnH );
	}

	if( m_bCancel )
	{
		int c = H * 0.06f;
		m_btn[BTN_CLOSE] = CZM_Rect( m_card.x + m_card.w - c - H * 0.024f, m_map.y + H * 0.014f, c, c );
	}
}

int CCzmTeamCard::HitTest( void ) const
{
	for( int i = 1; i < BTN_COUNT; i++ )
	{
		if( m_btn[i].Grown( i == BTN_CLOSE ? H * 0.02f : 0 ).Contains( uiStatic.cursorX, uiStatic.cursorY ))
			return i;
	}
	return 0;
}

void CCzmTeamCard::Press( int button )
{
	static const char *commands[BTN_COUNT] = { NULL, "jointeam 5", "jointeam 6", "jointeam 1", "jointeam 5", "jointeam 2", NULL };

	if( button <= 0 || button >= BTN_COUNT )
		return;
	CZM_PlayClick();
	if( commands[button] )
		EngFuncs::ClientCmdF( false, "%s\n", commands[button] );
	Hide();
}

bool CCzmTeamCard::KeyDown( int key )
{
	if( UI::Key::IsEscape( key ))
	{
		if( m_bCancel )
			Hide();
		return true;
	}
	if( UI::Key::IsLeftMouse( key ))
	{
		Layout();
		m_iPressed = HitTest();
		return true;
	}
	// the keys of the stock menu
	if( key == '1' && m_iSlot < 0 ) Press( BTN_T );
	else if( key == '2' && m_iSlot < 0 ) Press( BTN_CT );
	else if( key == '5' ) Press( m_iSlot >= 0 ? BTN_PLAY : BTN_AUTO );
	else if( key == '6' && m_bSpectate ) Press( BTN_SPECTATE );
	return true;
}

bool CCzmTeamCard::KeyUp( int key )
{
	if( UI::Key::IsLeftMouse( key ))
	{
		int pressed = m_iPressed;

		Layout();
		m_iPressed = 0;
		if( pressed && pressed == HitTest( ))
			Press( pressed );
	}
	return true;
}

void CCzmTeamCard::Draw()
{
	if( m_bClosing )
		return;
	if( !CL_IsActive( ))
	{
		Hide();
		return;
	}

	Layout();

	float t = Q_min( 1.0f, ( uiStatic.realTime - m_iOpenTime ) / 180.0f );
	int a = 255 * ( 1.0f - ( 1.0f - t ) * ( 1.0f - t ));
	bool ru = CZM_IsRussian();
	HFont nameFont = CZM_Font( CZMF_MENU_TITLE ), textFont = CZM_Font( CZMF_PANEL_TEXT ), chipFont = CZM_Font( CZMF_UI_LABEL );
	HFont btnFont = CZM_Font( CZMF_SHOP_CARD ), smallBtn = CZM_Font( CZMF_TILE_STATUS ), hintFont = CZM_Font( CZMF_UI_META );
	int pad = H * 0.034f;

	UI_FillRect( 0, 0, W, H, PackRGBA( 4, 6, 10, a * 170 / 255 ));
	CZM_DrawImage( UI_DIR "glow.png", m_card.x - H * 0.05f, m_card.y - H * 0.05f, m_card.w + H * 0.1f, m_card.h + H * 0.1f, PackRGBA( 229, 63, 77, a * 45 / 255 ));
	CZM_DrawSliced( UI_DIR "smenu_frame.png", m_card.x, m_card.y, m_card.w, m_card.h, 48, H * 0.03f, CZM_White( a ));

	// the map, fading into the card
	if( m_szMap[0] )
		CZM_DrawMapPreview( m_szMap, m_map.x, m_map.y, m_map.w, m_map.h );
	CZM_DrawImage( "gfx/czm/fade_bottom.png", m_map.x, m_map.y + m_map.h * 0.35f, m_map.w, m_map.h * 0.65f + 2, PackRGBA( 18, 22, 29, a ));

	// the mode and the players
	{
		char mode[48], online[48];
		int chH = H * 0.048f, cx = m_map.x + H * 0.02f, cy = m_map.y + H * 0.018f;

		if( m_iSlot >= 0 )
			Q_strncpy( mode, m_iSlot == CZM_OFFICIAL_ESCAPE ? "ZE · Escape" : "ZM · Survival", sizeof( mode ));
		else if( !strncmp( m_szMap, "zm_", 3 ))
			Q_strncpy( mode, ru ? "Зомби" : "Zombie", sizeof( mode ));
		else if( !strncmp( m_szMap, "ze_", 3 ))
			Q_strncpy( mode, "Escape", sizeof( mode ));
		else
			Q_strncpy( mode, ru ? "Классика" : "Classic", sizeof( mode ));
		int mw = CZM_TextWidth( chipFont, mode ) + chH;
		CZM_DrawImage( UI_DIR "glow.png", cx - chH * 0.5f, cy - chH * 0.5f, mw + chH, chH * 2, PackRGBA( 229, 63, 77, a * 90 / 255 ));
		CZM_DrawPill( UI_DIR "pill_lang_on.png", cx, cy, mw, chH, CZM_White( a ));
		CZM_DrawText( chipFont, cx, cy + ( chH - CZM_FontHeight( chipFont )) / 2, mw, mode, CZM_White( a ), QM_CENTER );

		int players = m_iCounts[0] + m_iCounts[1], max = 0;
		if( m_iSlot >= 0 )
		{
			CzmServer *server = CZM_OfficialServer( m_iSlot );
			if( server && server->answerTime > 0.0 )
			{
				players = server->players;
				max = server->maxplayers;
			}
		}
		if( max > 0 )
			snprintf( online, sizeof( online ), ru ? "%d/%d игроков" : "%d/%d players", players, max );
		else
			snprintf( online, sizeof( online ), ru ? "игроков: %d" : "players: %d", players );
		int ow = CZM_TextWidth( chipFont, online ) + chH * 1.2f;
		int ox = m_map.x + m_map.w - ow - H * 0.02f - ( m_bCancel ? m_btn[BTN_CLOSE].w + H * 0.016f : 0 );
		int dot = chH * 0.22f;
		CZM_DrawPill( UI_DIR "button_secondary.png", ox, cy, ow, chH, CZM_White( a ));
		CZM_DrawImage( UI_DIR "dot.png", ox + chH * 0.4f - dot / 2, cy + ( chH - dot ) / 2, dot, dot, PackRGBA( 107, 218, 167, a ));
		CZM_DrawText( chipFont, ox + chH * 0.62f, cy + ( chH - CZM_FontHeight( chipFont )) / 2, ow - chH * 0.8f, online, PackRGBA( 220, 226, 234, a ));
	}

	if( m_bCancel )
	{
		const CzmRect &c = m_btn[BTN_CLOSE];
		int ci = c.w * 0.42f;
		CZM_DrawImage( UI_DIR "chip_round.png", c.x, c.y, c.w, c.h, m_iPressed == BTN_CLOSE ? CZM_Grey() : CZM_White( a ));
		CZM_DrawImage( UI_DIR "icon_close.png", c.x + ( c.w - ci ) / 2, c.y + ( c.h - ci ) / 2, ci, ci, CZM_White( a ));
	}

	// the map's name over the bottom of its picture, then what it is about
	CZM_DrawText( nameFont, m_card.x + pad, m_map.y + m_map.h - CZM_FontHeight( nameFont ) * 0.55f, m_card.w - pad * 2,
		m_szMap[0] ? m_szMap : "Counter Zombie", CZM_White( a ));
	if( m_szText[0] )
	{
		int starts[4], lines = CZM_WrapText( textFont, m_szText, m_card.w - pad * 2, starts, 3 );
		for( int l = 0; l < lines; l++ )
		{
			char line[256];
			CZM_WrapLine( m_szText, starts, l, line, sizeof( line ));
			CZM_DrawText( textFont, m_card.x + pad, m_iTextY + l * ( CZM_FontHeight( textFont ) + H * 0.004f ), m_card.w - pad * 2, line,
				PackRGBA( 195, 203, 214, a ));
		}
	}

	// the buttons
	for( int i = 1; i < BTN_CLOSE; i++ )
	{
		const CzmRect &r = m_btn[i];
		if( r.w <= 0 )
			continue;

		bool pressed = m_iPressed == i && HitTest() == i;
		CzmRect b = pressed ? CZM_Rect( r.x + r.w * 0.01f, r.y + r.h * 0.04f, r.w - r.w * 0.02f, r.h - r.h * 0.08f ) : r;
		int corner = b.h * 0.24f;
		char label[48];
		const char *icon = NULL;
		unsigned int color = CZM_White( a );
		HFont font = smallBtn;

		switch( i )
		{
		case BTN_PLAY:
			Q_strncpy( label, ru ? "Играть" : "Play", sizeof( label ));
			icon = UI_DIR "icon_play.png";
			font = btnFont;
			CZM_DrawImage( UI_DIR "glow.png", b.x - b.h * 0.4f, b.y - b.h * 0.4f, b.w + b.h * 0.8f, b.h * 1.8f, PackRGBA( 229, 63, 77, a * ( pressed ? 170 : 110 ) / 255 ));
			CZM_DrawSliced( UI_DIR "tab_on.png", b.x, b.y, b.w, b.h, 30, corner, CZM_White( a ));
			break;
		case BTN_SPECTATE:
			Q_strncpy( label, ru ? "Наблюдать" : "Spectate", sizeof( label ));
			icon = UI_DIR "icon_users.png";
			color = PackRGBA( 207, 214, 224, a );
			CZM_DrawSliced( UI_DIR "card.png", b.x, b.y, b.w, b.h, 30, corner, CZM_White( a ));
			break;
		case BTN_T:
		case BTN_CT:
		{
			bool t = i == BTN_T;
			snprintf( label, sizeof( label ), "%s · %d", t ? ( ru ? "Т" : "T" ) : ( ru ? "КТ" : "CT" ), m_iCounts[t ? 0 : 1] );
			CZM_DrawSliced( UI_DIR "card.png", b.x, b.y, b.w, b.h, 30, corner, CZM_White( a ));
			UI_FillRect( b.x + b.w * 0.2f, b.y + b.h - Q_max( 3, H / 200 ) - b.h * 0.08f, b.w * 0.6f, Q_max( 3, H / 200 ),
				t ? PackRGBA( 248, 113, 80, a ) : PackRGBA( 96, 165, 250, a ));
			color = t ? PackRGBA( 254, 202, 186, a ) : PackRGBA( 191, 219, 254, a );
			break;
		}
		case BTN_AUTO:
			Q_strncpy( label, ru ? "Авто" : "Auto", sizeof( label ));
			CZM_DrawSliced( UI_DIR "tab_on.png", b.x, b.y, b.w, b.h, 30, corner, CZM_White( a ));
			break;
		}

		int tw = CZM_TextWidth( font, label ), iw = icon ? b.h * 0.36f : 0, space = icon ? b.h * 0.18f : 0;
		int sx = b.x + ( b.w - tw - iw - space ) / 2;
		if( icon )
			CZM_DrawImage( icon, sx, b.y + ( b.h - iw ) / 2, iw, iw, color );
		CZM_DrawText( font, sx + iw + space, b.y + ( b.h - CZM_FontHeight( font )) / 2, tw + 2, label, color );
	}

	// our servers: the welcome in one line
	if( m_iSlot >= 0 )
	{
		const char *hint = ru ? "Честная игра · Чистый сервер · Приятное общение"
			: "Fair play · Clean server · Friendly chat";
		int y = m_card.y + m_card.h - pad * 0.5f - CZM_FontHeight( hintFont ) - H * 0.012f;
		UI_FillRect( m_card.x + pad, y - H * 0.014f, m_card.w - pad * 2, Q_max( 1, H / 700 ), PackRGBA( 255, 255, 255, a * 20 / 255 ));
		CZM_DrawText( hintFont, m_card.x + pad, y, m_card.w - pad * 2, hint, PackRGBA( 141, 152, 168, a ));
	}
}

ADD_MENU3( menu_czmteam, CCzmTeamCard, UI_CzmTeam_Menu );

void UI_CzmTeam_Menu( void )
{
}

#define CZM_MENU_TEAM     2
#define CZM_MENU_CLASS_T  26
#define CZM_MENU_CLASS_CT 27

bool CZM_TeamShow( int menuType, int param1 )
{
	// our servers choose the model: no class menu after the team
	if(( menuType == CZM_MENU_CLASS_T || menuType == CZM_MENU_CLASS_CT ) && CZM_OfficialSlotNow() >= 0 )
	{
		EngFuncs::ClientCmd( false, "joinclass 5\n" );
		return true;
	}
	if( menuType != CZM_MENU_TEAM || !menu_czmteam )
		return false;
	menu_czmteam->Open( param1 );
	return true;
}

// Our menus get the window; returns true when the cards overlay must leave the menu alone.
static bool ServerWindowFrame( const char *value )
{
	bool rich = IsRichMenu( value );
	bool plain = !rich && value && value[0] && CL_IsActive() && CZM_OfficialSlotNow() >= 0 && !CZM_IsWeaponMenu( value );
	bool open = menu_czmserver && CZM_ClientMenuOpen( menu_czmserver );
	int serial = -1;

	if( value && value[0] )
		sscanf( value, "%d", &serial );

	if( open )
	{
		if( rich || plain )
		{
			if( serial != menu_czmserver->Serial( ))
			{
				CzmRichMenu menu;
				if( rich ) ParseRich( value, menu );
				else PlainAsRich( value, &menu_czmserver->Menu(), menu );
				menu_czmserver->Update( menu );
			}
			return true;
		}
		if( !value || !value[0] )
		{
			// after a pick the server may send the next section: keep the window for it a moment
			if( !menu_czmserver->Waiting( ))
				menu_czmserver->Close( false );
			return true;
		}
		// Weapon selection retains the shop's wheel/grid handling.
		menu_czmserver->Close( false );
		return false;
	}

	if(( rich || plain ) && serial != s_iClosedSerial && menu_czmserver && CL_IsActive() && !uiStatic.menu.IsActive()
		&& !uiStatic.client.IsActive( ))
	{
		CzmRichMenu menu;
		if( rich ) ParseRich( value, menu );
		else PlainAsRich( value, NULL, menu );
		menu_czmserver->Open( menu );
	}
	return rich || plain;
}

// A real spectator can return through the same auto-team action as the entry card.
// Dead T/CT players also have an observer camera, so use their team, not the camera mode.
static void SpectatorExitFrame( const char *menuValue )
{
	static bool added;
	static int oldW, oldH;
	int money = 0, team = 0;
	const char *state = EngFuncs::GetCvarString( "czm_buy_state" );
	if( state )
		sscanf( state, "%d %d", &money, &team );
	const bool show = team == 3 && CL_IsActive() && !gpGlobals->demoplayback
		&& !uiStatic.menu.IsActive() && !uiStatic.client.IsActive()
		&& !( menuValue && menuValue[0] ) && EngFuncs::GetCvarFloat( "hud_draw" ) != 0.0f;

	if( !show )
	{
		if( added )
			EngFuncs::ClientCmd( true, "touch_removebutton \"_czm_spec_exit\"\n" );
		added = false;
		return;
	}

	const int W = ScreenWidth, H = ScreenHeight;
	const char *label = CZM_IsRussian() ? "Выйти с наблюдателей" : "Leave spectator mode";
	const HFont font = CZM_Font( CZMF_TILE_NAME );
	const int icon = H * 0.032f, gap = H * 0.018f;
	const int w = Q_min( (int)( W * 0.55f ), Q_max( (int)( H * 0.48f ), CZM_TextWidth( font, label ) + icon + gap + (int)( H * 0.065f )));
	const int h = Q_max( (int)( H * 0.075f ), CZM_FontHeight( font ) + (int)( H * 0.035f ));
	const CzmRect r = CZM_Rect( ( W - w ) / 2, H * 0.735f, w, h );

	if( !added || oldW != W || oldH != H )
	{
		if( added )
			EngFuncs::ClientCmd( true, "touch_removebutton \"_czm_spec_exit\"\n" );
		EngFuncs::ClientCmdF( true, "touch_addbutton \"_czm_spec_exit\" \"\" \"jointeam 5\" %f %f %f %f 255 255 255 0 4\n",
			r.x / (float)W, r.y / (float)H, ( r.x + r.w ) / (float)W, ( r.y + r.h ) / (float)H );
		oldW = W;
		oldH = H;
		added = true;
	}

	CZM_DrawImage( UI_DIR "glow.png", r.x - gap, r.y - gap, r.w + gap * 2, r.h + gap * 2, PackRGBA( 229, 48, 62, 55 ));
	CZM_DrawSliced( UI_DIR "button_primary.png", r.x, r.y, r.w, r.h, 30, h * 0.24f, CZM_White() );
	const int textW = CZM_TextWidth( font, label ), x = r.x + ( r.w - textW - icon - gap ) / 2;
	CZM_DrawImage( UI_DIR "icon_play.png", x, r.y + ( h - icon ) / 2, icon, icon, CZM_White() );
	CZM_DrawText( font, x + icon + gap, r.y + ( h - CZM_FontHeight( font )) / 2, textW + 2, label, CZM_White() );
}

void CZM_DrawGameOverlay( void )
{
	const char *value = EngFuncs::GetCvarString( "czm_menu" );
	int serial = -1;

	SpectatorExitFrame( value );

	if( ServerWindowFrame( value ) || CZM_ShopWeaponFrame( value ))
	{
		RemoveButtons();
		return;
	}

	bool show = value && value[0] && CL_IsActive() && !uiStatic.menu.IsActive() && !uiStatic.client.IsActive()
		&& EngFuncs::GetCvarFloat( "czm_menu_cards" ) != 0.0f;

	if( !show )
	{
		RemoveButtons();
		if( !value || !value[0] )
			s_menu.serial = -1;
		return;
	}

	sscanf( value, "%d", &serial );
	if( serial != s_menu.serial )
	{
		ParseMenu( value );
		Layout();
		AddButtons();
	}
	else if( s_menu.layoutW != ScreenWidth || s_menu.layoutH != ScreenHeight || !s_menu.buttons )
	{
		Layout();
		AddButtons();
	}

	DrawMenu();
}
