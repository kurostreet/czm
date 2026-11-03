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
#define SM_MAX_TABS  12
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
	char tab[16], head[64], sub[64], chip[96], foot[192];
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
		HIT_TAB = 10,    // + tab
		HIT_CARD = 40,   // + card
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
	bool m_bClosing;

	int W, H;
	CzmRect m_win, m_head, m_side, m_body, m_foot, m_close;
};

static int s_iClosedSerial = -1;

CCzmServerWindow::CCzmServerWindow() : BaseClass( "CzmServerWindow" )
{
	memset( &m_menu, 0, sizeof( m_menu ));
	m_szTab[0] = 0;
	m_iPressed = HIT_NONE;
	m_iPicked = -1;
	m_iOpenTime = m_iChangeTime = m_iPickTime = 0;
	m_bClosing = false;
	W = H = 0;
}

void CCzmServerWindow::Open( const CzmRichMenu &menu )
{
	m_menu = menu;
	Q_strncpy( m_szTab, menu.tab, sizeof( m_szTab ));
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
	Q_strncpy( m_szTab, menu.tab, sizeof( m_szTab ));
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
	for( int i = 0; i < m_menu.numTabs; i++ )
		m_menu.tabs[i].rect = CZM_Rect( m_side.x + pad, m_side.y + pad + i * ( tabH + tabGap ), m_side.w - pad * 2, tabH );

	// two columns, the first filled first, five rows at most like the server sends nine cards
	int cpad = H * 0.02f, gap = H * 0.015f;
	int cardW = ( m_body.w - cpad * 2 - gap ) / 2;
	int cardH = Q_min( (int)( H * 0.10f ), ( m_body.h - cpad * 2 - gap * 4 ) / 5 );
	int perColumn = Q_max( 1, ( m_menu.numCards + 1 ) / 2 );
	for( int i = 0; i < m_menu.numCards; i++ )
	{
		int col = i / perColumn, row = i % perColumn;
		m_menu.cards[i].rect = CZM_Rect( m_body.x + cpad + col * ( cardW + gap ), m_body.y + cpad + row * ( cardH + gap ), cardW, cardH );
	}
}

int CCzmServerWindow::HitTest( void ) const
{
	int x = uiStatic.cursorX, y = uiStatic.cursorY;

	if( m_close.Grown( H * 0.02f ).Contains( x, y ))
		return HIT_CLOSE;
	for( int i = 0; i < m_menu.numTabs; i++ )
	{
		if( m_menu.tabs[i].rect.Contains( x, y ))
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

	if( hit >= HIT_TAB && hit < HIT_TAB + m_menu.numTabs )
	{
		const CzmMenuTab &t = m_menu.tabs[hit - HIT_TAB];

		if( !strcmp( t.key, m_szTab ))
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
		Close( true );
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
}

void CCzmServerWindow::DrawCards( int a )
{
	HFont numFont = CZM_Font( CZMF_SHOP_PRICE ), nameFont = CZM_Font( CZMF_SHOP_NAME ), subFont = CZM_Font( CZMF_UI_META );
	float t = Q_min( 1.0f, ( uiStatic.realTime - m_iChangeTime ) / 160.0f );
	int ca = a * t;
	int slide = ( 1.0f - t ) * H * 0.02f;

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

// Our menus get the window; returns true when the cards overlay must leave the menu alone.
static bool ServerWindowFrame( const char *value )
{
	bool rich = IsRichMenu( value );
	bool open = menu_czmserver && CZM_ClientMenuOpen( menu_czmserver );
	int serial = -1;

	if( value && value[0] )
		sscanf( value, "%d", &serial );

	if( open )
	{
		if( rich )
		{
			if( serial != menu_czmserver->Serial( ))
			{
				CzmRichMenu menu;
				ParseRich( value, menu );
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
		// a menu of another plugin: the cards take it
		menu_czmserver->Close( false );
		return false;
	}

	if( rich && serial != s_iClosedSerial && menu_czmserver && CL_IsActive() && !uiStatic.menu.IsActive( ))
	{
		CzmRichMenu menu;
		ParseRich( value, menu );
		menu_czmserver->Open( menu );
	}
	return rich;
}

void CZM_DrawGameOverlay( void )
{
	const char *value = EngFuncs::GetCvarString( "czm_menu" );
	int serial = -1;

	if( ServerWindowFrame( value ))
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
