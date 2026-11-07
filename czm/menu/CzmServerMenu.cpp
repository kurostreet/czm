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
#include "CzmJson.h"
#include "CzmDesign.h"
#include "PlayerModelView.h"
#include "../../common/czm_player_model.h"
#include "../../common/czm_weapon_menu.h"
#include "../../common/czm_server_view.h"

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

A card sends slotN like a key. A tab asks the server for its section (czm_menu_tab).
Standalone menus add #nav<TAB>hasParent<TAB>page<TAB>pages<TAB>icon and use a footer
for navigation. Closing dismisses the menu without selecting an item.
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
	int key;                 // 1..10 (10 is the server's 0 action)
	char name[64], sub[96], icon[16], badge[16];
	unsigned int color;
	bool enabled;
	CzmRect rect;
};

struct CzmRichMenu
{
	int serial, validSlots;
	bool plain, hasTokens;
	int tokens;
	char tab[16], head[64], sub[96], chip[96], foot[192], parent[16], root[16];
	CzmMenuTab tabs[SM_MAX_TABS];
	int numTabs;
	CzmMenuCard cards[SM_MAX_CARDS];
	int numCards;
	bool navigation, canGoBack;
	int menuPage, menuPages, prevSlot, nextSlot;
	char headerIcon[16];
	CzmServerView::Kind kind;
	char pageTitle[96], body[2048], command[24], hint[160], prefill[724];
	struct Facts
	{
		enum { None, Statistics, Progress, Profile } kind;
		bool russian;
		struct { int kills, deaths, wins, rounds, seconds, saved; } stats;
		struct { int level, next, killsLeft, killGoal, timeLeft, timeGoal; } progress;
		struct { int state, level, tokens; char name[64]; } profile;
	} facts;
	bool Compact() const { return kind == CzmServerView::Cards && facts.kind == Facts::None; }
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
		else if( !strncmp( line, "#nav\t", 5 ))
		{
			const char *p = line + 5;
			char back[4], page[8], pages[8];
			NextField( p, end, back, sizeof( back ));
			NextField( p, end, page, sizeof( page ));
			NextField( p, end, pages, sizeof( pages ));
			const int current = atoi( page ), total = atoi( pages );
			if( current >= 1 && current <= total && total <= 32 )
			{
				m.navigation = true;
				m.canGoBack = !strcmp( back, "1" );
				m.menuPage = current;
				m.menuPages = total;
				m.nextSlot = current < total && ( m.validSlots & ( 1 << 8 )) ? 9 : 0;
				NextField( p, end, m.headerIcon, sizeof( m.headerIcon ));
			}
		}
		else if( !strncmp( line, "#tokens\t", 8 ))
		{
			// A typed value belongs only to this complete packet. Never infer a
			// balance from a translated title or a token-like number in body text.
			char number[16] = {};
			const size_t length = end - ( line + 8 );
			if( length > 0 && length < sizeof( number )) memcpy( number, line + 8, length );
			m.hasTokens = false;
			m.tokens = 0;
			const unsigned long value = strtoul( number, nullptr, 10 );
			if( number[0] && !number[strspn( number, "0123456789" )] && value <= 2147483647UL )
			{
				m.hasTokens = true;
				m.tokens = (int)value;
			}
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
		else if( !strncmp( line, "#facts\t", 7 ) )
		{
			const char *p = line + 7;
			char kind[16], language[4];
			NextField( p, end, kind, sizeof( kind ));
			NextField( p, end, language, sizeof( language ));
			auto &facts = m.facts;
			const bool profile = !strcmp( kind, "profile" );
			int values[6] = {};
			bool valid = !strcmp( language, "ru" ) || !strcmp( language, "en" );
			for( int i = 0; valid && i < ( profile ? 3 : 6 ); ++i )
			{
				char field[16];
				NextField( p, end, field, sizeof( field ));
				const unsigned long number = strtoul( field, nullptr, 10 );
				valid = field[0] && !field[strspn( field, "0123456789" )] && number <= 2147483647UL;
				if( valid ) values[i] = (int)number;
			}
			if( valid )
			{
				facts.russian = !strcmp( language, "ru" );
				if( !strcmp( kind, "stats" ) && values[2] <= values[3] && values[5] <= 1 )
				{
					facts.kind = CzmRichMenu::Facts::Statistics;
					facts.stats = { values[0], values[1], values[2], values[3], values[4], values[5] };
				}
				else if( !strcmp( kind, "progress" ) && values[0] > 0 && values[1] >= values[0] &&
					values[3] > 0 && values[2] <= values[3] && values[5] > 0 && values[4] <= values[5] )
				{
					facts.kind = CzmRichMenu::Facts::Progress;
					facts.progress = { values[0], values[1], values[2], values[3], values[4], values[5] };
				}
				else if( profile && values[0] <= 3 && values[1] > 0 )
				{
					facts.kind = CzmRichMenu::Facts::Profile;
					facts.profile.state = values[0];
					facts.profile.level = values[1];
					facts.profile.tokens = values[2];
					NextField( p, end, facts.profile.name, sizeof( facts.profile.name ));
				}
			}
		}
		else if( !strncmp( line, "#page\t", 6 ))
		{
			const char *p = line + 6; char kind[16];
			NextField( p, end, kind, sizeof( kind ));
			NextField( p, end, m.pageTitle, sizeof( m.pageTitle ));
			NextField( p, end, m.command, sizeof( m.command ));
			NextField( p, end, m.hint, sizeof( m.hint ));
			NextField( p, end, m.prefill, sizeof( m.prefill ));
			m.kind = CzmServerView::ParseKind( kind, m.command );
			Q_strncpy( m.parent, m.tab, sizeof( m.parent ));
		}
		else if( !strncmp( line, "#body\t", 6 ))
		{
			char part[2048]; TrimCopy( part, sizeof( part ), line + 6, end );
			size_t used = strlen( m.body );
			snprintf( m.body + used, sizeof( m.body ) - used, "%s\n", part );
		}
		else if( *line != '#' )
		{
			char visible[512], right[48], color;

			SplitLine( line, visible, sizeof( visible ), right, sizeof( right ), &color );
			// "1. name<TAB>sub<TAB>icon<TAB>color<TAB>badge"; 0 is the exit, the cross does it
			if( visible[0] >= '1' && visible[0] <= '9' && visible[1] == '.' && m.numCards < SM_MAX_CARDS )
			{
				if( m.navigation && visible[0] >= '8' )
				{
					line = *end ? end + 1 : end;
					continue;
				}
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
			else if( m.navigation && visible[0] && strncmp( visible, "0.", 2 )
				&& strcmp( visible, m.head ) && strcmp( visible, m.chip ))
			{
				size_t used = strlen( m.body );
				snprintf( m.body + used, sizeof( m.body ) - used, "%s\n", visible );
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
	m.plain = true;
	m.hasTokens = false;
	m.tokens = 0;
	m.chip[0] = 0;
	Q_strncpy( m.parent, previous && previous->tab[0] ? previous->tab : previous && previous->parent[0] ? previous->parent : "", sizeof( m.parent ));
	Q_strncpy( m.root, previous && previous->root[0] ? previous->root : previous && previous->tab[0] ? previous->tab : "", sizeof( m.root ));
	m.tab[0] = 0;
	m.kind = CzmServerView::Cards;
	m.facts.kind = CzmRichMenu::Facts::None;
	m.pageTitle[0] = m.body[0] = m.command[0] = m.hint[0] = 0;
	m.prefill[0] = 0;
	if( m.navigation )
	{
		m.canGoBack = true;
		m.menuPage = m.menuPages = m.prevSlot = m.nextSlot = 0;
	}
	const bool zombie = strstr( s_menu.title, "Zombie Plague" ) != NULL;
	Q_strncpy( m.head, zombie ? ( CZM_IsRussian() ? "МЕНЮ ЗОМБИ" : "ZOMBIE MENU" ) : s_menu.title, sizeof( m.head ));
	Q_strncpy( m.sub, zombie ? "Zombie Plague" : "", sizeof( m.sub ));
	if( !previous )
		Q_strncpy( m.foot, "COUNTER ZOMBIE MOBILE", sizeof( m.foot ));
	// Plain menus can carry a selected player or a confirmation above the choices.
	// Preserve it visibly instead of hiding that context in the underlying HUD.
	for( int i = 0; i < s_menu.numLines; ++i )
	{
		const size_t used = strlen( m.body );
		snprintf( m.body + used, sizeof( m.body ) - used, "%s\n", s_menu.lines[i] );
	}
	m.numCards = 0;
	for( int i = 0; i < s_menu.numCards && m.numCards < SM_MAX_CARDS; i++ )
	{
		const CzmCard &plain = s_menu.cards[i];
		if( m.navigation && plain.enabled )
		{
			const bool more = plain.key == 9 &&
				( !strcmp( plain.text, "More..." ) || !strcmp( plain.text, "Next" )
				|| !strcmp( plain.text, "Дальше..." ) || !strcmp( plain.text, "Далее" ));
			const bool prev = ( plain.key == 8 || plain.key == 10 ) &&
				( !strcmp( plain.text, "Back" ) || !strcmp( plain.text, "Назад" ));
			if( more || prev )
			{
				if( more ) m.nextSlot = plain.key;
				else m.prevSlot = plain.key;
				continue;
			}
		}
		if( plain.key == 10 && ( m.navigation || m.parent[0] || m.numTabs ))
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
	bool MouseMove( int x, int y ) override;
	void Char( int key ) override;

private:
	enum
	{
		HIT_NONE = 0,
		HIT_CLOSE,
		HIT_BACK,
		HIT_TABS_UP,
		HIT_TABS_DOWN,
		HIT_FIELD,
		HIT_SUBMIT,
		HIT_PREV,
		HIT_NEXT,
		HIT_REFRESH,
		HIT_MENU_PREV,
		HIT_MENU_NEXT,
		HIT_RETURN,
		HIT_TAB = 16,    // + tab
		HIT_CARD = 100,  // + card, separate from all 32 possible tabs
	};

	void Layout( int shift );
	int HitTest( void ) const;
	bool IsPressed( int hit ) const { return m_iPressed == hit && HitTest() == hit; }
	void Activate( int hit );
	void DrawHeader( int a );
	void DrawTabs( int a );
	void DrawCards( int a );
	void DrawFacts( int a );
	void DrawFooter( int a );
	void DrawPage( int a );
	void EndInput();
	void Submit();
	void FriendsFrame();
	void FetchFriends( int offset );
	void InviteFriend( int index );
	void ResetPage();

	CzmRichMenu m_menu;
	char m_szTab[16];        // the tab asked for, lit before the server answers
	int m_iPressed;
	int m_iPicked;           // card, -1 none
	int m_iOpenTime, m_iChangeTime, m_iPickTime;
	int m_iTabFirst, m_iTabRows, m_iCardRows;
	bool m_bClosing;
	bool m_typing, m_drag, m_moved, m_friendsLoaded, m_formPending;
	int m_formTime;
	int m_scroll, m_downY, m_downScroll, m_scrollMax;
	char m_input[768], m_notice[192], m_requestNonce[80];
	int m_request, m_requestKind, m_requestIdentity, m_friendOffset, m_nextOffset, m_friendPage, m_friendCount, m_sentFriend, m_successFriend;
	struct Friend { int id; bool online; char nick[100]; } m_friends[40];
	CUtlVector<int> m_abandoned;

	int W, H;
	CzmRect m_win, m_head, m_side, m_body, m_foot, m_close, m_back, m_tabsUp, m_tabsDown;
	CzmRect m_navPrev, m_navNext, m_cardInfo, m_return;
	CzmRect m_content, m_field, m_submit, m_prev, m_next, m_refresh, m_friendRows[6];
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
	m_iCardRows = 7;
	m_bClosing = false;
	m_typing = m_drag = m_moved = false;
	m_friendsLoaded = m_formPending = false; m_formTime = 0;
	m_scroll = m_downY = m_downScroll = m_scrollMax = 0;
	m_request = m_requestKind = m_friendOffset = m_friendPage = m_friendCount = m_sentFriend = 0;
	m_requestIdentity = -1; m_nextOffset = -1;
	m_successFriend = 0;
	m_input[0] = m_notice[0] = m_requestNonce[0] = 0;
	W = H = 0;
}

void CCzmServerWindow::Open( const CzmRichMenu &menu )
{
	ResetPage();
	m_menu = menu;
	if( menu.kind == CzmServerView::Form ) for( const unsigned char *p = (const unsigned char *)menu.prefill; *p; ++p ) CzmServerView::Append( m_input, sizeof( m_input ), *p );
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
	ResetPage();

	m_menu = menu;
	if( menu.kind == CzmServerView::Form ) for( const unsigned char *p = (const unsigned char *)menu.prefill; *p; ++p ) CzmServerView::Append( m_input, sizeof( m_input ), *p );
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
		EngFuncs::ClientCmd( false, !m_menu.plain || CZM_OnSurvivalServer()
			? "client_buy_close\nczm_menu_close\n" : "client_buy_close\n" );
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
	EndInput();
	if( m_request ) { m_abandoned.AddToTail( m_request ); m_request = 0; }
	CZM_CloseClientMenuSoon( this );
}

void CCzmServerWindow::Layout( int shift )
{
 W=ScreenWidth;H=ScreenHeight;
 const bool compact=m_menu.Compact();
 const int pad=Q_max(4,(int)(H*.018f)),gap=Q_max(3,(int)(H*.010f));
 const int headH=H*(compact?.165f:.135f),footH=H*(compact?.185f:m_menu.navigation?.14f:.075f);
 const int winW=Q_min((int)(W*.94f),(int)(H*(compact?(m_menu.numTabs?1.30f:.96f):1.80f)));
 const int sideW=m_menu.numTabs?(compact?Q_min((int)(H*.30f),(int)(winW*.28f)):(int)(winW*.225f)):0;
 int context=0;
 if(compact&&m_menu.body[0]){
  int starts[8];const HFont font=CZM_Font(CZMF_UI_META);
  context=CZM_WrapText(font,m_menu.body,winW-sideW-pad*2,starts,7)*Q_max(1,CZM_FontHeight(font))+gap;
 }
 const int rowH=Q_max((int)(H*.066f),CZM_FontHeight(CZM_Font(CZMF_UI_LABEL))+H/60);
 const int rows=Q_min(7,Q_max(1,m_menu.numCards));
 const int wanted=headH+footH+pad*2+context+(m_menu.numCards?rows*rowH+(rows-1)*gap:0);
 const int winH=compact?Q_max((int)(H*.45f),Q_min((int)(H*.92f),wanted)):(int)(H*.88f);
 m_win=CZM_Rect((W-winW)/2+shift,(H-winH)/2,winW,winH);
 m_head=CZM_Rect(m_win.x,m_win.y,winW,headH);
 m_foot=CZM_Rect(m_win.x,m_win.y+winH-footH,winW,footH);
 m_side=CZM_Rect(m_win.x,m_win.y+headH,sideW,winH-headH-footH);
 m_body=CZM_Rect(m_side.x+sideW,m_side.y,winW-sideW,m_side.h);
 const int closeS=H*(compact?.060f:m_menu.navigation?.078f:.055f);
 m_close=CZM_Rect(m_head.x+winW-closeS-pad,m_head.y+pad,closeS,closeS);
 const int tabGap=Q_max(2,(int)(H*.009f)),tabH=H*(compact?.062f:.070f);
 int tabTop=m_side.y+pad;
 m_tabsUp=m_tabsDown=CZM_Rect(0,0,0,0);
 const int capacity=Q_max(1,(m_side.h-pad*2)/(tabH+tabGap));
 if(m_menu.numTabs>capacity){
  const int scrollH=Q_max(10,(int)(H*.036f));
  m_iTabRows=Q_max(1,(m_side.h-pad*2-scrollH*2-tabGap*2)/(tabH+tabGap));
  m_iTabFirst=bound(0,m_iTabFirst,Q_max(0,m_menu.numTabs-m_iTabRows));
  m_tabsUp=CZM_Rect(m_side.x+pad,tabTop,m_side.w-pad*2,scrollH);
  m_tabsDown=CZM_Rect(m_side.x+pad,m_side.y+m_side.h-pad-scrollH,m_side.w-pad*2,scrollH);
  tabTop+=scrollH+tabGap;
 }else{m_iTabFirst=0;m_iTabRows=m_menu.numTabs;}
 for(int i=0;i<m_menu.numTabs;i++)m_menu.tabs[i].rect=i>=m_iTabFirst&&i<m_iTabFirst+m_iTabRows?
  CZM_Rect(m_side.x+pad,tabTop+(i-m_iTabFirst)*(tabH+tabGap),sideW-pad*2,tabH):CZM_Rect(0,0,0,0);
 const int cpad=H*.025f,navigation=!compact&&!m_menu.navigation&&m_menu.parent[0]?H*.065f:0;
 m_back=navigation?CZM_Rect(m_body.x+cpad,m_body.y+cpad,H*.21f,H*.045f):CZM_Rect(0,0,0,0);
 m_navPrev=m_navNext=m_cardInfo=m_return=CZM_Rect(0,0,0,0);
 if(compact){
  const int back=H*.050f;
  if(m_menu.navigation?m_menu.canGoBack:m_menu.parent[0]!=0)
   m_back=CZM_Rect(m_head.x+pad,m_head.y+headH*.43f,back,back);
  const int navH=H*.053f,navY=m_foot.y+pad,navW=(m_foot.w-pad*2)*.38f;
  m_navPrev=CZM_Rect(m_foot.x+pad,navY,navW,navH);
  m_navNext=CZM_Rect(m_foot.x+m_foot.w-pad-navW,navY,navW,navH);
  const int returnH=H*.073f;
  m_return=CZM_Rect(m_foot.x+pad,m_foot.y+m_foot.h-pad-returnH,m_foot.w-pad*2,returnH);
  const int minimum=Q_max((int)(H*.045f),CZM_FontHeight(CZM_Font(CZMF_UI_LABEL))+H/100);
  context=Q_min(context,Q_max(0,m_body.h-pad*2-minimum));
  if(context)m_cardInfo=CZM_Rect(m_body.x+pad,m_body.y+pad,m_body.w-pad*2,context);
  m_content=CZM_Rect(m_body.x+pad,m_body.y+pad+context,m_body.w-pad*2,m_body.h-pad*2-context);
  m_iCardRows=Q_min(7,Q_max(1,(m_content.h+gap)/(minimum+gap)));
  const int visible=Q_min(m_iCardRows,Q_max(1,m_menu.numCards));
  const int height=Q_min(rowH,(m_content.h-gap*(visible-1))/visible),step=height+gap;
  m_scrollMax=Q_max(0,m_menu.numCards-visible)*step;
  m_scroll=bound(0,m_scroll,m_scrollMax);
  const int first=m_scroll/step;
  for(int i=0;i<m_menu.numCards;i++)m_menu.cards[i].rect=i>=first&&i<first+visible?
   CZM_Rect(m_content.x,m_content.y+(i-first)*step,m_content.w,height):CZM_Rect(0,0,0,0);
 }else{
  if(m_menu.navigation){
   const int height=H*.091f,y=m_foot.y+(m_foot.h-height)/2,width=m_foot.w*.365f;
   if(m_menu.canGoBack)m_back=CZM_Rect(m_foot.x+cpad,y,width,height);
   if(m_menu.prevSlot||m_menu.menuPage>1)m_navPrev=CZM_Rect(m_foot.x+m_foot.w*.398f,y,Q_min((int)(H*.087f),(int)(m_foot.w*.062f)),height);
   if(m_menu.nextSlot)m_navNext=CZM_Rect(m_foot.x+m_foot.w-cpad-width,y,width,height);
  }
  context=0;
  if(m_menu.kind==CzmServerView::Cards&&m_menu.facts.kind!=CzmRichMenu::Facts::None){
   const int height=m_body.h-cpad*2;
   const int panel=m_menu.facts.kind==CzmRichMenu::Facts::Profile?Q_min(height,(int)(H*.32f)):height;
   m_cardInfo=CZM_Rect(m_body.x+cpad,m_body.y+cpad,m_body.w-cpad*2,panel);
   context=panel+(m_menu.numCards?gap:0);
  }else if(m_menu.navigation&&m_menu.kind==CzmServerView::Cards&&m_menu.body[0]){
   int lines=0;for(const char*p=m_menu.body;*p;++p)if(*p=='\n')++lines;
   context=Q_min(7,lines)*Q_max((int)(H*.037f),CZM_FontHeight(CZM_Font(CZMF_UI_META))+2);
   m_cardInfo=CZM_Rect(m_body.x+cpad,m_body.y+cpad,m_body.w-cpad*2,context);
  }
  const int columns=m_body.w>=H*.88f?2:1,cardRows=Q_max(1,(m_menu.numCards+columns-1)/columns);
  const int cardW=(m_body.w-cpad*2-gap*(columns-1))/columns;
  const int cardH=Q_max(1,Q_min((int)(H*(m_menu.navigation?.154f:.125f)),(m_body.h-navigation-context-cpad*2-gap*(cardRows-1))/cardRows));
  for(int i=0;i<m_menu.numCards;i++)m_menu.cards[i].rect=CZM_Rect(m_body.x+cpad+(i%columns)*(cardW+gap),m_body.y+cpad+navigation+context+(i/columns)*(cardH+gap),cardW,cardH);
  m_content=CZM_Rect(m_body.x+cpad,m_body.y+cpad+navigation,m_body.w-cpad*2,m_body.h-cpad*2-navigation);
 }
 m_field=m_submit=m_prev=m_next=m_refresh=CZM_Rect(0,0,0,0);
 for(int i=0;i<6;i++)m_friendRows[i]=CZM_Rect(0,0,0,0);
 if(m_menu.kind!=CzmServerView::Cards){
  const int titleH=H*.067f,bottom=H*.067f;
  m_content.y+=titleH;m_content.h-=titleH;
  if(m_menu.kind==CzmServerView::Form){
   const int fieldH=H*(CzmServerView::ProfileCodeCommand(m_menu.command)?.085f:.125f);
   m_submit=CZM_Rect(m_content.x+m_content.w-H*.26f,m_body.y+m_body.h-cpad-bottom,H*.26f,bottom);
   m_field=CZM_Rect(m_content.x,m_submit.y-fieldH-gap,m_content.w,fieldH);
   m_content.h=Q_max(H/18,m_field.y-gap-m_content.y);
  }else if(m_menu.kind==CzmServerView::Account||m_menu.kind==CzmServerView::Friends){
   const int by=m_body.y+m_body.h-cpad-bottom;
   m_submit=CZM_Rect(m_content.x,by,Q_min((int)(H*.40f),m_content.w),bottom);
   if(m_menu.kind==CzmServerView::Friends){
    const int bW=H*.14f;
    m_prev=CZM_Rect(m_content.x+m_content.w-bW*2-gap,by,bW,bottom);
    m_next=CZM_Rect(m_content.x+m_content.w-bW,by,bW,bottom);
    m_refresh=CZM_Rect(m_content.x,by,H*.27f,bottom);
    const int rowH=Q_min((int)(H*.075f),(by-gap-m_content.y-gap*5)/6);
    for(int i=0;i<6;i++)m_friendRows[i]=CZM_Rect(m_content.x,m_content.y+i*(rowH+gap),m_content.w,rowH);
   }
   m_content.h=Q_max(1,by-gap-m_content.y);
  }
 }
}

int CCzmServerWindow::HitTest( void ) const
{
 int x=uiStatic.cursorX,y=uiStatic.cursorY;
 if(m_close.Grown(H*.012f).Contains(x,y))return HIT_CLOSE;
 if(m_return.w&&m_return.Contains(x,y))return HIT_RETURN;
 if(m_back.w&&m_back.Contains(x,y))return HIT_BACK;
 if(m_navPrev.w&&m_navPrev.Contains(x,y))return HIT_MENU_PREV;
 if(m_navNext.w&&m_navNext.Contains(x,y))return HIT_MENU_NEXT;
 if(m_tabsUp.w&&m_tabsUp.Contains(x,y))return HIT_TABS_UP;
 if(m_tabsDown.w&&m_tabsDown.Contains(x,y))return HIT_TABS_DOWN;
 for(int i=0;i<m_menu.numTabs;i++)if(m_menu.tabs[i].rect.w&&m_menu.tabs[i].rect.Contains(x,y))return HIT_TAB+i;
 if(m_menu.kind==CzmServerView::Form){if(m_field.Contains(x,y))return HIT_FIELD;if(m_submit.Contains(x,y))return HIT_SUBMIT;}
 else if(m_menu.kind==CzmServerView::Account){if(m_submit.Contains(x,y))return HIT_SUBMIT;}
 else if(m_menu.kind==CzmServerView::Friends){
  if(!CZM_OnlineAccount())return m_submit.Contains(x,y)?HIT_SUBMIT:HIT_NONE;
  if(m_prev.Contains(x,y))return HIT_PREV;if(m_next.Contains(x,y))return HIT_NEXT;if(m_refresh.Contains(x,y))return HIT_REFRESH;
  for(int i=0;m_friendPage>=0&&i<6&&m_friendPage*6+i<m_friendCount;i++)if(m_friendRows[i].Contains(x,y))return 200+i;
 }else if(m_menu.kind==CzmServerView::Cards)for(int i=0;i<m_menu.numCards;i++)if(m_menu.cards[i].rect.Contains(x,y))return HIT_CARD+i;
 return HIT_NONE;
}

void CCzmServerWindow::Activate( int hit )
{
	if( hit == HIT_FIELD && m_menu.kind == CzmServerView::Form )
	{
		m_typing = true;
		EngFuncs::SetTextInputRect( m_field.x, m_field.y, m_field.w, m_field.h );
		UI_EnableTextInput( true );
		return;
	}
	if( hit == HIT_SUBMIT ) { Submit(); return; }
	if( hit == HIT_REFRESH ) { FetchFriends( m_friendOffset ); return; }
	if( hit == HIT_PREV || hit == HIT_NEXT )
	{
		if( m_request ) return;
		if( hit == HIT_PREV )
		{
			if( m_friendPage > 0 ) m_friendPage--;
			else if( m_friendOffset > 0 ) FetchFriends( Q_max( 0, m_friendOffset - 40 ));
		}
		else if( ( m_friendPage + 1 ) * 6 < m_friendCount ) m_friendPage++;
		else if( m_nextOffset >= 0 ) FetchFriends( m_nextOffset );
		return;
	}
	if( hit == HIT_CLOSE || hit == HIT_RETURN )
	{
		CZM_PlayClick();
		Close( true );
		return;
	}
	if( hit == HIT_BACK && ( m_menu.navigation ? m_menu.canGoBack : m_menu.parent[0] != 0 ))
	{
		CZM_PlayClick();
		if( m_menu.navigation )
			EngFuncs::ClientCmd( false, "czm_menu_back\n" );
		else
			EngFuncs::ClientCmdF( false, "czm_menu_tab %s\n", m_menu.parent );
		return;
	}
	if( hit == HIT_MENU_PREV || hit == HIT_MENU_NEXT )
	{
		if( m_menu.Compact() && !m_menu.navigation ) return;
		const int slot = hit == HIT_MENU_PREV ? m_menu.prevSlot : m_menu.nextSlot;
		if( Waiting() || ( !slot && ( hit != HIT_MENU_PREV || m_menu.menuPage < 2 )))
			return;
		CZM_PlayClick();
		m_iPicked = SM_MAX_CARDS;
		m_iPickTime = uiStatic.realTime;
		if( slot )
			EngFuncs::ClientCmdF( false, "slot%d\n", slot );
		else
			EngFuncs::ClientCmd( false, "czm_menu_prev\n" );
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
		{
			Q_strncpy( m_notice, c.sub, sizeof( m_notice ));
			return;
		}
		CZM_PlayClick();
		if( m_menu.facts.kind == CzmRichMenu::Facts::Profile && m_menu.facts.profile.state == 0 && c.key == 1 &&
			CZM_OnSurvivalServer() )
		{
			CZM_AccountShow( CZM_OnlineKey(), EngFuncs::GetCvarString( "name" ));
			return;
		}
		m_iPicked = hit - HIT_CARD;
		m_iPickTime = uiStatic.realTime;
		if( !strcmp( m_menu.tab, "loadout" ))
			EngFuncs::ClientCmdF( false, "czm_shop_select %d %d\n", m_menu.serial, c.key );
		else
			EngFuncs::ClientCmdF( false, "slot%d\n", c.key );
	}
	else if( hit >= 200 && hit < 206 && m_menu.kind == CzmServerView::Friends )
		InviteFriend( m_friendPage * 6 + hit - 200 );
}

bool CCzmServerWindow::KeyDown( int key )
{
	if( m_typing )
	{
		if( UI::Key::IsEscape( key ) || UI::Key::IsEnter( key )) { EndInput(); return true; }
		if( UI::Key::IsBackspace( key )) { CzmServerView::Backspace( m_input ); return true; }
		if( !UI::Key::IsLeftMouse( key )) return true;
	}
	if( UI::Key::IsEscape( key ))
	{
		if( m_menu.navigation ? m_menu.canGoBack : m_menu.parent[0] != 0 ) Activate( HIT_BACK );
		else Close( true );
		return true;
	}
	if( key == K_MWHEELUP || key == K_MWHEELDOWN )
	{
		if( m_menu.Compact() )
		{
			const int step = Q_max( 1, (int)( H * .076f ));
			m_scroll = bound( 0, m_scroll + ( key == K_MWHEELUP ? -step : step ), m_scrollMax );
		}
		else if( m_menu.kind == CzmServerView::Text || m_menu.kind == CzmServerView::Form || m_menu.kind == CzmServerView::Account )
			m_scroll = bound( 0, m_scroll + ( key == K_MWHEELUP ? -1 : 1 ) * Q_max( 1, H / 14 ), m_scrollMax );
		else Activate( key == K_MWHEELUP ? HIT_TABS_UP : HIT_TABS_DOWN );
		return true;
	}

	if( UI::Key::IsLeftMouse( key ))
	{
		Layout( 0 );
		m_iPressed = HitTest();
		m_drag = ( m_menu.kind != CzmServerView::Cards || m_menu.Compact() ) && m_content.Contains( uiStatic.cursorX, uiStatic.cursorY );
		m_moved = false; m_downY = uiStatic.cursorY; m_downScroll = m_scroll;
		if( m_typing && m_iPressed != HIT_FIELD && m_iPressed != HIT_SUBMIT ) EndInput();
		return true;
	}

	// the keys of a keyboard still pick, like the text menu
	if( m_menu.navigation && key == '9' && m_menu.nextSlot )
	{
		Activate( HIT_MENU_NEXT );
		return true;
	}
	if( m_menu.navigation && key == '8' && ( m_menu.menuPages || m_menu.prevSlot == 8 ))
	{
		if( m_menu.menuPage > 1 || m_menu.prevSlot == 8 ) Activate( HIT_MENU_PREV );
		else if( m_menu.canGoBack ) Activate( HIT_BACK );
		return true;
	}
	if( key >= '1' && key <= '9' && m_menu.kind == CzmServerView::Cards )
	{
		for( int i = 0; i < m_menu.numCards; i++ )
		{
			if( m_menu.cards[i].key == key - '0' )
				Activate( HIT_CARD + i );
		}
		return true;
	}
	if( key == '0' )
	{
		// A foreign server may use 0 as Back rather than Exit. The separate
		// Return-to-game control always closes locally without selecting it.
		if( m_menu.plain ) for( int i = 0; i < m_menu.numCards; ++i )
			if( m_menu.cards[i].key == 10 ) { Activate( HIT_CARD + i ); return true; }
		Close( true );
	}
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
		m_drag = false;
		if( !m_moved && hit == pressed && hit != HIT_NONE )
			Activate( hit );
	}
	return true;
}

bool CCzmServerWindow::MouseMove( int x, int y )
{
	BaseClass::MouseMove( x, y );
	if( m_drag )
	{
		int delta = uiStatic.cursorY - m_downY;
		if( abs( delta ) > H / 60 ) m_moved = true;
		if( m_moved ) m_scroll = bound( 0, m_downScroll - delta, m_scrollMax );
	}
	return true;
}

void CCzmServerWindow::Char( int key )
{
	if( CzmServerView::ProfileCodeCommand( m_menu.command ) &&
		( key <= 0 || key > 127 || !strchr( "0123456789abcdefABCDEF", key ) || strlen( m_input ) >= 32 ))
		return;
	if( m_typing ) CzmServerView::Append( m_input, sizeof( m_input ), key );
}

void CCzmServerWindow::EndInput()
{
	if( m_typing ) UI_EnableTextInput( false );
	m_typing = false;
}

void CCzmServerWindow::ResetPage()
{
	EndInput();
	if( m_request ) m_abandoned.AddToTail( m_request );
	m_request = m_requestKind = m_friendCount = m_friendOffset = m_friendPage = m_successFriend = 0;
	m_nextOffset = -1; m_scroll = m_scrollMax = 0;
	m_friendsLoaded = m_formPending = false;
	m_input[0] = m_notice[0] = m_requestNonce[0] = 0;
	m_requestIdentity = CZM_OnlineIdentity();
}

void CCzmServerWindow::Submit()
{
	if( m_menu.kind == CzmServerView::Account || ( m_menu.kind == CzmServerView::Friends && !CZM_OnlineAccount() ))
	{
		EndInput(); CZM_AccountShow( CZM_OnlineKey(), EngFuncs::GetCvarString( "name" )); return;
	}
	const bool migration = CzmServerView::ProfileCodeCommand( m_menu.command );
	if( m_menu.kind != CzmServerView::Form || !( migration ? CZM_OnSurvivalServer() : CzmServerView::FormCommand( m_menu.command ))) return;
	if( m_formPending ) return;
	char *begin = m_input;
	while( *begin == ' ' ) ++begin;
	if( begin != m_input ) memmove( m_input, begin, strlen( begin ) + 1 );
	size_t length = strlen( m_input );
	while( length && m_input[length - 1] == ' ' ) m_input[--length] = 0;
	if( migration && !CzmServerView::ProfileCode( m_input ))
	{
		Q_strncpy( m_notice, CZM_IsRussian() ? "Введи код из 32 символов" : "Enter the 32-character code", sizeof( m_notice )); return;
	}
	if( CzmServerView::Characters( m_input ) < 3 )
	{
		Q_strncpy( m_notice, CZM_IsRussian() ? "Введите хотя бы 3 символа" : "Enter at least 3 characters", sizeof( m_notice )); return;
	}
	EndInput();
	m_formPending = true; m_formTime = uiStatic.realTime;
	EngFuncs::ClientCmdF( false, "%s \"%s\"\n", m_menu.command, m_input );
	Q_strncpy( m_notice, CZM_IsRussian() ? "Отправляем…" : "Sending…", sizeof( m_notice ));
	// A server reply replaces this form. A failed send keeps the text available for retry.
}

void CCzmServerWindow::FetchFriends( int offset )
{
	if( m_request || !CZM_OnlineReady() || !CZM_OnlineAccount() ) return;
	m_friendPage = offset < m_friendOffset ? -1 : 0;
	m_friendOffset = Q_max( 0, offset ); m_friendCount = 0; m_nextOffset = -1;
	m_friendsLoaded = false;
	char path[128]; snprintf( path, sizeof( path ), "/api/v1/social/people/friends?offset=%d", m_friendOffset );
	m_requestIdentity = CZM_OnlineIdentity(); m_requestKind = 1;
	m_request = CZM_NetRequest( "GET", CZM_OnlineUrl( path ), CZM_OnlineKey(), "" );
	Q_strncpy( m_notice, CZM_IsRussian() ? "Загружаем друзей…" : "Loading friends…", sizeof( m_notice ));
	if( !m_request ) Q_strncpy( m_notice, CZM_IsRussian() ? "Нет связи. Нажмите обновить" : "Connection failed. Refresh the list", sizeof( m_notice ));
}

void CCzmServerWindow::FriendsFrame()
{
	int status; CUtlString body;
	for( int i = m_abandoned.Count() - 1; i >= 0; --i )
		if( CZM_NetPoll( m_abandoned[i], &status, body )) m_abandoned.Remove( i );
	if( m_menu.kind != CzmServerView::Friends ) return;
	if( m_requestIdentity != CZM_OnlineIdentity() )
	{
		ResetPage();
		Q_strncpy( m_notice, CZM_IsRussian() ? "Профиль изменился. Обновите список" : "Profile changed. Refresh the list", sizeof( m_notice ));
		return;
	}
	if( m_request && CZM_NetPoll( m_request, &status, body ))
	{
		m_request = 0; CzmJson j; bool parsed = j.Parse( body.Get() );
		if( status == 200 && parsed )
		{
			if( m_requestKind == 1 )
			{
				m_friendsLoaded = true;
				int list = j.Get( 0, "people" ); m_friendCount = Q_min( 40, j.Count( list ));
				for( int i = 0; i < m_friendCount; i++ )
				{
					int item = j.At( list, i ); auto &f = m_friends[i];
					f.id = j.Int( j.Get( item, "id" )); f.online = j.Bool( j.Get( item, "online" ));
					Q_strncpy( f.nick, j.String( j.Get( item, "nick" )), sizeof( f.nick ));
				}
				if( m_friendPage < 0 ) m_friendPage = Q_max( 0, ( m_friendCount - 1 ) / 6 );
				m_nextOffset = j.Int( j.Get( 0, "next" ), -1 ); m_notice[0] = 0;
			}
			else
			{
				m_successFriend = m_sentFriend;
				Q_strncpy( m_notice, CZM_IsRussian() ? "Приглашение отправлено другу" : "Invitation sent to your friend", sizeof( m_notice ));
			}
		}
		else Q_strncpy( m_notice, status == 403 ? ( CZM_IsRussian() ? "Приглашение недоступно. Проверьте дружбу и ограничения профиля" : "Invite unavailable. Check friendship and profile restrictions" ) : ( CZM_IsRussian() ? "Нет связи. Нажмите обновить или повторите отправку" : "Connection failed. Refresh or retry" ), sizeof( m_notice ));
	}
	if( !m_request && !m_friendsLoaded && !m_notice[0] ) FetchFriends( m_friendOffset );
}

void CCzmServerWindow::InviteFriend( int index )
{
	if( m_request || index < 0 || index >= m_friendCount || m_friends[index].id <= 0 || m_friends[index].id == m_successFriend ) return;
	const char *address = EngFuncs::GetCvarString( "czm_connect_adr" );
	if( !CL_IsActive() || !address || !address[0] || CZM_ServerBlocked( address ))
	{
		Q_strncpy( m_notice, CZM_IsRussian() ? "Приглашение на этот сервер недоступно" : "Cannot invite to this server", sizeof( m_notice )); return;
	}
	if( m_sentFriend != m_friends[index].id || !m_requestNonce[0] ) CZM_NetNewKey( m_requestNonce, sizeof( m_requestNonce ));
	m_sentFriend = m_friends[index].id;
	CUtlString body; body.Append( "{\"server\":" ); CZM_JsonQuote( body, address );
	body.Append( ",\"proto\":\"gs\",\"name\":" ); CZM_JsonQuote( body, EngFuncs::GetCvarString( "czm_connect_name" ));
	body.Append( ",\"nonce\":" ); CZM_JsonQuote( body, m_requestNonce ); body.Append( "}" );
	char path[100]; snprintf( path, sizeof( path ), "/api/v1/social/invite/%d", m_sentFriend );
	m_requestKind = 2; m_requestIdentity = CZM_OnlineIdentity();
	m_request = CZM_NetRequest( "POST", CZM_OnlineUrl( path ), CZM_OnlineKey(), body.Get() );
	Q_strncpy( m_notice, CZM_IsRussian() ? "Отправляем приглашение…" : "Sending invitation…", sizeof( m_notice ));
	if( !m_request ) Q_strncpy( m_notice, CZM_IsRussian() ? "Нет связи. Повторите отправку" : "Connection failed. Retry sending", sizeof( m_notice ));
}

void CCzmServerWindow::DrawHeader( int a )
{
 if(m_menu.Compact()){
  const CzmRect&h=m_head;const int pad=H*.018f;
  const unsigned accent=PackRGBA(229,63,77,a),muted=PackRGBA(155,166,184,a);
  const HFont small=CZM_Font(CZMF_UI_META),title=CZM_Font(CZMF_UI_TITLE);
  int right=m_close.x-pad;
  const bool tokens=CZM_OnSurvivalServer()&&(m_menu.hasTokens||m_menu.facts.kind==CzmRichMenu::Facts::Profile);
  if(tokens){
   const int value=m_menu.hasTokens?m_menu.tokens:m_menu.facts.profile.tokens;
   char text[48];snprintf(text,sizeof(text),"CZM Token: %d",value);
   HFont font=small;const int chipW=Q_min((int)(h.w*.48f),(int)(H*.40f));
   if(CZM_TextWidth(font,text)+pad*2>chipW)font=CZM_Font(CZMF_TINY);
   CzmRect chip=CZM_Rect(right-chipW,h.y+pad,chipW,H*.052f);
   CzmStyle::Surface(chip,PackRGBA(28,35,45,a),PackRGBA(64,75,90,a),Q_max(4,H/100));
   CZM_DrawText(font,chip.x+pad/2,chip.y+(chip.h-CZM_FontHeight(font))/2,chip.w-pad,text,PackRGBA(231,187,96,a),QM_CENTER);
   right=chip.x-pad;
  }
  CZM_DrawText(small,h.x+pad,h.y+pad,right-h.x-pad,CZM_OnSurvivalServer()?"CZM | SURVIVAL":"CZM | SERVER",accent);
  const int titleY=h.y+h.h*.43f,x=h.x+pad+(m_back.w?m_back.w+pad:0);
  CZM_DrawText(title,x,titleY,h.x+h.w-pad-x,m_menu.head[0]?m_menu.head:(CZM_IsRussian()?"МЕНЮ СЕРВЕРА":"SERVER MENU"),CZM_White(a));
  if(m_back.w){
   CzmStyle::Surface(m_back,PackRGBA(27,34,44,a),IsPressed(HIT_BACK)?accent:PackRGBA(64,75,90,a),H/100);
   CzmStyle::Text(m_back,"‹",CZMF_UI_ACTION,CZM_White(a),QM_CENTER);
  }
  char path[196];const char*subtitle=m_menu.chip[0]?m_menu.chip:m_menu.sub;
  if(m_menu.navigation?m_menu.canGoBack:m_menu.parent[0]!=0){
   if(strchr(m_menu.sub,'/'))subtitle=m_menu.sub;
   else{snprintf(path,sizeof(path),CZM_IsRussian()?"Меню сервера / %s":"Server menu / %s",m_menu.head);subtitle=path;}
  }
  CZM_DrawText(small,h.x+pad,h.y+h.h*.77f,h.w-pad*2,subtitle,muted);
  CzmStyle::Surface(m_close,PackRGBA(27,34,44,a),IsPressed(HIT_CLOSE)?accent:PackRGBA(64,75,90,a),H/100);
  const int side=m_close.w*.42f;
  CZM_DrawImage(UI_DIR "icon_close.png",m_close.x+(m_close.w-side)/2,m_close.y+(m_close.h-side)/2,side,side,CZM_White(a));
  UI_FillRect(h.x+pad,h.y+h.h-2,h.w-pad*2,1,PackRGBA(51,62,78,a));
  UI_FillRect(h.x+pad,h.y+h.h-3,Q_max(16,(int)(h.w*.13f)),Q_max(2,H/400),accent);
  return;
 }

 const CzmRect &h=m_head;int pad=H*.025f,tile=H*.070f,x=h.x+pad;
 unsigned accent=PackRGBA(255,168,66,a);
 CzmStyle::Surface(CZM_Rect(x,h.y+(h.h-tile)/2,tile,tile),PackRGBA(38,32,25,a),PackRGBA(118,81,38,a),tile/5);
 const char *icon=m_menu.headerIcon[0]?MenuIcon(m_menu.headerIcon):UI_DIR "icon_star.png";
 for(int i=0;i<m_menu.numTabs;i++)if(!strcmp(m_menu.tabs[i].key,m_szTab))icon=MenuIcon(m_menu.tabs[i].icon);
 CZM_DrawImage(icon,x+tile/4,h.y+(h.h-tile)/2+tile/4,tile/2,tile/2,accent);
 x+=tile+pad;
 const HFont title=CZM_Font(CZMF_UI_TITLE),small=CZM_Font(CZMF_UI_META);
 int chipW=Q_min((int)(h.w*.36f),(int)(H*.65f)),right=m_close.x-pad;
 int textW=right-x-chipW-pad;
 if(textW<H*.32f){chipW=0;textW=right-x;}
 CZM_DrawText(small,x,h.y+H*.020f,textW,CZM_IsRussian()?"COUNTER ZOMBIE · СЕРВЕР":"COUNTER ZOMBIE · SERVER",accent);
 CZM_DrawText(title,x,h.y+H*.047f,textW,m_menu.head,CZM_White(a));
 if(chipW){
  int cy=h.y+H*.034f;
  char balance[48];const char*chip=m_menu.chip;
  if(CZM_OnSurvivalServer()&&(m_menu.hasTokens||m_menu.facts.kind==CzmRichMenu::Facts::Profile)){
   snprintf(balance,sizeof(balance),"CZM Token: %d",m_menu.hasTokens?m_menu.tokens:m_menu.facts.profile.tokens);chip=balance;
  }
  CZM_DrawText(small,right-chipW,cy,chipW,chip,PackRGBA(183,194,205,a),QM_RIGHT);
  CZM_DrawText(small,right-chipW,cy+CZM_FontHeight(small)+H*.008f,chipW,m_menu.sub,PackRGBA(133,146,164,a),QM_RIGHT);
 }
 CzmStyle::Surface(m_close,PackRGBA(27,32,40,a),IsPressed(HIT_CLOSE)?accent:PackRGBA(66,74,86,a),m_close.h/5);
 int ci=m_close.w*.38f;CZM_DrawImage(UI_DIR "icon_close.png",m_close.x+(m_close.w-ci)/2,m_close.y+(m_close.h-ci)/2,ci,ci,CZM_White(a));
 UI_FillRect(h.x,h.y+h.h-1,h.w,1,PackRGBA(62,69,80,a));
}

void CCzmServerWindow::DrawTabs( int a )
{
 if(!m_menu.numTabs)return;
 UI_FillRect(m_side.x,m_side.y,m_side.w,m_side.h,PackRGBA(12,16,22,a));
 UI_FillRect(m_side.x+m_side.w-1,m_side.y,1,m_side.h,PackRGBA(48,56,68,a));
 HFont font=CZM_Font(CZMF_UI_LABEL),small=CZM_Font(CZMF_UI_META);
 for(int i=0;i<m_menu.numTabs;i++){
  const CzmMenuTab&t=m_menu.tabs[i];const CzmRect&r=t.rect;if(r.w<=0)continue;
  bool on=!strcmp(t.key,m_szTab),pressed=IsPressed(HIT_TAB+i);unsigned accent=PackRGBA(229,63,77,a);
  if(on||pressed){CzmStyle::Surface(r,PackRGBA(on?47:29,on?28:37,on?35:48,a),PackRGBA(on?133:49,on?48:60,on?62:75,a),r.h/8);if(on)UI_FillRect(r.x,r.y+r.h/5,Q_max(2,H/300),r.h*3/5,accent);}
  int icon=r.h*.37f,ix=r.x+r.h*.18f,lx=ix+icon+r.h*.18f,lw=r.x+r.w-lx-r.h*.14f;
  CZM_DrawImage(MenuIcon(t.icon),ix,r.y+(r.h-icon)/2,icon,icon,on?accent:PackRGBA(149,163,179,a));
  if(t.badge[0]){
   int bw=Q_min((int)(r.w*.18f),Q_max(r.h/3,CZM_TextWidth(small,t.badge)+r.h/5));
   CZM_DrawText(small,r.x+r.w-bw-r.h*.1f,r.y+(r.h-CZM_FontHeight(small))/2,bw,t.badge,accent,QM_CENTER);lw-=bw+r.h*.1f;
  }
  CZM_DrawText(font,lx,r.y+(r.h-CZM_FontHeight(font))/2,lw,t.name,on?CZM_White(a):PackRGBA(184,195,208,a));
 }
 if(m_tabsUp.w){
  CzmStyle::Button(m_tabsUp,CZM_IsRussian()?"Выше":"Up",m_iTabFirst>0,false,IsPressed(HIT_TABS_UP));
  CzmStyle::Button(m_tabsDown,CZM_IsRussian()?"Ниже":"Down",m_iTabFirst+m_iTabRows<m_menu.numTabs,false,IsPressed(HIT_TABS_DOWN));
 }
}

static void FactDuration( int seconds, bool ru, char *text, size_t size )
{
	if( seconds >= 3600 )
		snprintf( text, size, ru ? "%d ч %d мин" : "%d h %d min", seconds / 3600, seconds / 60 % 60 );
	else if( seconds >= 60 )
		snprintf( text, size, ru ? "%d мин %d сек" : "%d min %d s", seconds / 60, seconds % 60 );
	else
		snprintf( text, size, ru ? "%d сек" : "%d s", seconds );
}

void CCzmServerWindow::DrawFacts( int a )
{
	const auto &facts = m_menu.facts;
	const CzmRect &r = m_cardInfo;
	const bool ru = facts.russian;
	const int pad = H * .025f, gap = H * .017f, badgeH = H * .058f;
	const unsigned gold = PackRGBA( 255, 176, 72, a );
	const unsigned green = PackRGBA( 110, 218, 172, a );
	const unsigned ink = CZM_White( a ), muted = PackRGBA( 172, 185, 202, a );
	const unsigned fill = PackRGBA( 25, 33, 44, a ), edge = PackRGBA( 54, 68, 84, a );
	auto status = [&]( int x, int y, int width, const char *text, bool saved )
	{
		const int w = Q_min( width, CZM_TextWidth( CZM_Font( CZMF_UI_LABEL ), text ) + pad * 2 );
		CzmRect pill = CZM_Rect( x, y, w, badgeH );
		CzmStyle::Round( pill, saved ? PackRGBA( 26, 59, 50, a ) : PackRGBA( 59, 46, 29, a ));
		CzmStyle::Text( pill, text, CZMF_UI_LABEL, saved ? green : gold, QM_CENTER );
	};
	auto tile = [&]( const CzmRect &box, const char *icon, const char *title, const char *value, unsigned accent )
	{
		CzmStyle::Surface( box, fill, edge );
		const int iconSize = H * .088f;
		CzmRect iconTile = CZM_Rect( box.x + pad, box.y + pad, iconSize, iconSize );
		CzmStyle::Round( iconTile, PackRGBA( 42, 49, 60, a ));
		CzmStyle::Icon( iconTile, MenuIcon( icon ), accent );
		const int tx = iconTile.x + iconSize + gap;
		const int tw = box.x + box.w - pad - tx;
		CzmStyle::Text( CZM_Rect( tx, box.y + pad, tw, H * .068f ), value, CZMF_UI_TITLE, ink );
		CzmStyle::TextLines( CZM_Rect( tx, box.y + pad + H * .074f, tw, H * .065f ), title, CZMF_UI_LABEL, muted );
	};
	if( facts.kind == CzmRichMenu::Facts::Statistics )
	{
		const auto &s = facts.stats;
		status( r.x, r.y, r.w, s.saved ? ( ru ? "Прогресс сохраняется" : "Progress is saved" )
			: ( ru ? "Только текущая сессия" : "Current session only" ), s.saved != 0 );
		const int top = r.y + badgeH + gap, w = ( r.w - gap ) / 2;
		const int h = ( r.h - badgeH - gap * 2 ) / 2;
		char value[4][48];
		snprintf( value[0], sizeof( value[0] ), "%d", s.kills );
		snprintf( value[1], sizeof( value[1] ), "%d", s.deaths );
		snprintf( value[2], sizeof( value[2] ), "%d / %d", s.wins, s.rounds );
		FactDuration( s.seconds, ru, value[3], sizeof( value[3] ));
		tile( CZM_Rect( r.x, top, w, h ), "target", ru ? "Убийства и заражения" : "Kills and infections", value[0], gold );
		tile( CZM_Rect( r.x + w + gap, top, w, h ), "shield", ru ? "Смерти и полученные заражения" : "Deaths and times infected", value[1], gold );
		tile( CZM_Rect( r.x, top + h + gap, w, h ), "trophy", ru ? "Победы / раунды" : "Wins / rounds", value[2], green );
		tile( CZM_Rect( r.x + w + gap, top + h + gap, w, h ), "clock", ru ? "Активное время" : "Active play time", value[3], green );
		return;
	}
	if( facts.kind == CzmRichMenu::Facts::Progress )
	{
		const auto &p = facts.progress;
		char level[80], time[48], kills[16];
		if( p.next > p.level ) snprintf( level, sizeof( level ), "LVL %d  →  LVL %d", p.level, p.next );
		else snprintf( level, sizeof( level ), ru ? "LVL %d  ·  Ближайшие этапы" : "LVL %d  ·  Next milestones", p.level );
		const int heroH = H * .112f, tipH = H * .082f;
		CzmRect hero = CZM_Rect( r.x, r.y, r.w, heroH );
		CzmStyle::Surface( hero, PackRGBA( 42, 35, 27, a ), PackRGBA( 113, 79, 40, a ));
		CzmStyle::Icon( CZM_Rect( hero.x + pad, hero.y, hero.h, hero.h ), MenuIcon( "crown" ), gold );
		CzmStyle::Text( CZM_Rect( hero.x + pad + hero.h, hero.y, hero.w - hero.h - pad * 2, hero.h ), level, CZMF_UI_TITLE, ink );
		const int w = ( r.w - gap ) / 2, h = r.h - heroH - tipH - gap * 2;
		CzmRect killTile = CZM_Rect( r.x, r.y + heroH + gap, w, h );
		CzmRect timeTile = CZM_Rect( r.x + w + gap, killTile.y, w, h );
		snprintf( kills, sizeof( kills ), "%d", p.killsLeft );
		FactDuration( p.timeLeft, ru, time, sizeof( time ));
		tile( killTile, "target", ru ? "Осталось убийств и заражений" : "Kills and infections remaining", kills, gold );
		tile( timeTile, "clock", ru ? "Осталось активного времени" : "Active time remaining", time, green );
		auto bar = [&]( const CzmRect &box, int left, int total, unsigned color )
		{
			CzmRect track = CZM_Rect( box.x + pad, box.y + box.h - pad - H * .014f, box.w - pad * 2, H * .014f );
			CzmStyle::Round( track, PackRGBA( 55, 68, 83, a ));
			track.w = (int)( track.w * ( 1.0 - double( left ) / total ));
			CzmStyle::Round( track, color );
		};
		bar( killTile, p.killsLeft, p.killGoal, gold );
		bar( timeTile, p.timeLeft, p.timeGoal, green );
		CzmStyle::TextLines( CZM_Rect( r.x + pad, killTile.y + h + gap, r.w - pad * 2, tipH ),
			ru ? "Время и убийства дают отдельные ступени прогресса." : "Time and kills each count toward your level.", CZMF_UI_LABEL, muted );
		return;
	}
	const auto &p = facts.profile;
	CzmStyle::Surface( r, fill, edge );
	const int side = H * .115f;
	CzmRect avatar = CZM_Rect( r.x + pad, r.y + pad, side, side );
	CzmStyle::Round( avatar, PackRGBA( 51, 45, 38, a ));
	CzmStyle::Icon( avatar, MenuIcon( "user" ), gold );
	const int x = avatar.x + side + gap, width = r.x + r.w - pad - x;
	const char *states[] = { ru ? "Гостевой профиль" : "Guest profile", "Steam",
		ru ? "Сохранённый профиль" : "Saved profile", ru ? "Аккаунт CZM подключён" : "CZM account linked" };
	status( x, r.y + pad, width, states[p.state], p.state != 0 );
	CzmStyle::Text( CZM_Rect( x, r.y + pad + badgeH, width, H * .063f ), p.name, CZMF_UI_TITLE, ink );
	char info[100];
	snprintf( info, sizeof( info ), ru ? "LVL %d    ·    Токены %d" : "LVL %d    ·    Tokens %d", p.level, p.tokens );
	CzmStyle::Text( CZM_Rect( x, r.y + pad + badgeH + H * .065f, width, H * .052f ), info, CZMF_UI_ACTION, gold );
	const char *help = p.state ? ( ru ? "Уровень, статистика и токены сохраняются автоматически." : "Your level, stats and tokens are saved automatically." )
		: ( ru ? "Войди в аккаунт CZM, чтобы сохранить прогресс." : "Sign in to CZM to save your progress." );
	CzmStyle::TextLines( CZM_Rect( x, r.y + pad + badgeH + H * .127f, width, H * .080f ), help, CZMF_UI_LABEL, muted );
}

void CCzmServerWindow::DrawCards( int a )
{
 if(!m_menu.Compact()&&m_back.w&&!m_menu.navigation)CzmStyle::Button(m_back,CZM_IsRussian()?"‹ Назад":"‹ Back",true,false,IsPressed(HIT_BACK),PackRGBA(255,168,66,a),CZMF_UI_META);
 if( m_menu.facts.kind!=CzmRichMenu::Facts::None ) DrawFacts(a);
 else if( m_cardInfo.h )
 {
  const HFont font=CZM_Font(CZMF_UI_META);
  const int lineH=Q_max(1,CZM_FontHeight(font));
  int starts[8];
  const int count=CZM_WrapText(font,m_menu.body,m_cardInfo.w,starts,Q_min(7,m_cardInfo.h/lineH));
  for( int i=0; i<count; ++i )
  {
   char line[256];
   CZM_WrapLine(m_menu.body,starts,i,line,sizeof(line));
   CZM_DrawText(font,m_cardInfo.x,m_cardInfo.y+i*lineH,m_cardInfo.w,line,PackRGBA(187,199,215,a));
  }
 }
 if(m_menu.Compact()){
  const HFont name=CZM_Font(CZMF_UI_LABEL),meta=CZM_Font(CZMF_UI_META);
  const unsigned muted=PackRGBA(155,166,184,a),accent=PackRGBA(229,63,77,a);
  auto icon=[](const CzmMenuCard&c)->const char*{
   if(c.icon[0]&&strcmp(c.icon,"star")&&strcmp(c.icon,"chevron_right"))return c.icon;
   const char*n=c.name;
   if(strstr(n,"Истор")||strstr(n,"History"))return "clock";
   if(strstr(n,"Боевой пропуск")||strstr(n,"Battle pass"))return "ticket";
   if(strstr(n,"Мой прогресс"))return "user";
   if(strstr(n,"Передать")||strstr(n,"Transfer")||strstr(n,"Токен")||strstr(n,"Token"))return "coins";
   if(strstr(n,"Прогресс")||strstr(n,"Статист")||strstr(n,"LVL")||strstr(n,"Progress")||strstr(n,"Level")||strstr(n,"Stats"))return "chart";
   if(strstr(n,"Магаз")||strstr(n,"Shop")||strstr(n,"Store"))return "cart";
   if(strstr(n,"Голос")||strstr(n,"Vote")||strstr(n,"Poll"))return "flag";
   if(strstr(n,"Настрой")||strstr(n,"Settings")||strstr(n,"Options"))return "gear";
   if(strstr(n,"Инвент")||strstr(n,"Inventory"))return "box";
   if(strstr(n,"Лавка")||strstr(n,"Market"))return "users";
   if(strstr(n,"Язык")||strstr(n,"Language"))return "globe";
   if(strstr(n,"Класс")||strstr(n,"Class"))return "users";
   if(strstr(n,"Назад")||strstr(n,"Back"))return "back";
   if(strstr(n,"Выход")||strstr(n,"Exit"))return "close";
   if(strstr(n,"Далее")||strstr(n,"Next")||strstr(n,"More"))return "chevron";
   return "info";
  };
  for(int i=0;i<m_menu.numCards;i++){
   const CzmMenuCard&c=m_menu.cards[i];const CzmRect&r=c.rect;if(r.w<=0||r.h<=0)continue;
   const bool selected=IsPressed(HIT_CARD+i)||m_iPicked==i;
   CzmStyle::Surface(r,selected?PackRGBA(47,28,35,a):PackRGBA(25,32,42,a),selected?accent:PackRGBA(51,62,78,a),Q_max(4,H/110));
   const int inset=Q_max(4,r.h/5),side=r.h*.52f;
   int tx=r.x+inset;
   if(m_menu.plain){
    char key[4];snprintf(key,sizeof(key),"%d",c.key%10);
    const int keyW=r.h*.40f;CZM_DrawText(meta,tx,r.y+(r.h-CZM_FontHeight(meta))/2,keyW,key,muted,QM_CENTER);tx+=keyW+inset/2;
   }
   CZM_DrawImage(MenuIcon(icon(c)),tx,r.y+(r.h-side)/2,side,side,c.enabled?(selected?accent:CZM_White(a)):PackRGBA(119,130,145,a));tx+=side+inset;
   const int arrow=r.h*.28f,right=r.x+r.w-inset-arrow;
   const char*status=!c.enabled?(c.sub[0]?c.sub:(CZM_IsRussian()?"Недоступно":"Unavailable")):(c.badge[0]?(c.badge[0]=='!'?c.badge+1:c.badge):c.sub);
   int statusW=status[0]?Q_min((int)(r.w*.35f),CZM_TextWidth(meta,status)+inset):0;
   CZM_DrawText(name,tx,r.y+(r.h-CZM_FontHeight(name))/2,Q_max(1,right-tx-inset-statusW),c.name,c.enabled?CZM_White(a):muted);
   if(statusW)CZM_DrawText(meta,right-inset-statusW,r.y+(r.h-CZM_FontHeight(meta))/2,statusW,status,c.enabled&&c.badge[0]?accent:muted,QM_RIGHT);
   CZM_DrawImage(c.enabled?UI_DIR "icon_chevron.png":UI_DIR "icon_block.png",right,r.y+(r.h-arrow)/2,arrow,arrow,c.enabled?CZM_White(a):muted);
  }
  if(m_scrollMax){
   const int track=m_content.h,thumb=Q_max(H/30,track*m_iCardRows/Q_max(m_iCardRows,m_menu.numCards));
   UI_FillRect(m_body.x+m_body.w-Q_max(2,H/300),m_content.y+m_scroll*(track-thumb)/m_scrollMax,Q_max(2,H/300),thumb,PackRGBA(109,125,145,a));
  }
  return;
 }
 HFont name=CZM_Font(CZMF_UI_LABEL),sub=CZM_Font(CZMF_UI_META);
 float t=Q_min(1.0f,(uiStatic.realTime-m_iChangeTime)/130.0f);int alpha=a*t;
 for(int i=0;i<m_menu.numCards;i++){
  const CzmMenuCard&c=m_menu.cards[i];CzmRect r=c.rect;bool selected=IsPressed(HIT_CARD+i)||m_iPicked==i;
  r.y+=(1-t)*H*.012f;unsigned accent=PackRGBA(255,168,66,alpha);
  CzmStyle::Surface(r,selected?PackRGBA(43,36,28,alpha):PackRGBA(25,31,40,alpha),selected?accent:PackRGBA(57,66,80,alpha),Q_max(4,H/90));
  int tile=r.h*.56f,ix=r.x+r.h*.20f,iy=r.y+(r.h-tile)/2;
  CzmStyle::Round(CZM_Rect(ix,iy,tile,tile),PackRGBA(39,43,50,alpha),tile/5);
  CZM_DrawImage(MenuIcon(c.icon),ix+tile/5,iy+tile/5,tile*3/5,tile*3/5,c.enabled?accent:PackRGBA(119,130,145,alpha));
  int tx=ix+tile+r.h*.20f,chev=r.h*.18f,tw=r.x+r.w-tx-chev-r.h*.32f;
  int nh=CZM_FontHeight(name),sh=c.sub[0]?CZM_FontHeight(sub):0,top=r.y+(r.h-nh-sh-(sh?r.h*.06f:0))/2;
  if(c.badge[0]){const char*b=c.badge[0]=='!'?c.badge+1:c.badge;int bw=Q_min(tw/3,CZM_TextWidth(sub,b)+(int)(H*.02f));CZM_DrawText(sub,r.x+r.w-bw-r.h*.3f,r.y+r.h*.10f,bw,b,accent,QM_RIGHT);}
  CZM_DrawText(name,tx,top,tw,c.name,c.enabled?CZM_White(alpha):PackRGBA(144,154,169,alpha));
  if(sh)CZM_DrawText(sub,tx,top+nh+r.h*.06f,tw,c.sub,PackRGBA(154,168,186,alpha));
  CZM_DrawImage(c.enabled?UI_DIR "icon_chevron.png":UI_DIR "icon_block.png",r.x+r.w-chev-r.h*.16f,r.y+(r.h-chev)/2,chev,chev,PackRGBA(126,140,157,alpha));
 }
}

void CCzmServerWindow::DrawFooter( int a )
{
 if(m_menu.Compact()){
  const bool ru=CZM_IsRussian();const unsigned accent=PackRGBA(229,63,77,a),muted=PackRGBA(130,143,161,a);
  const bool prev=m_menu.navigation&&(m_menu.prevSlot||m_menu.menuPage>1),next=m_menu.navigation&&m_menu.nextSlot;
  CzmRect nav=CZM_Rect(m_return.x,m_navPrev.y,m_return.w,m_navPrev.h);
  CzmStyle::Surface(nav,PackRGBA(25,32,42,a),PackRGBA(51,62,78,a),Q_max(4,H/110));
  CzmStyle::Text(m_navPrev,ru?"‹ Предыдущая":"‹ Previous",CZMF_UI_LABEL,prev?(IsPressed(HIT_MENU_PREV)?accent:CZM_White(a)):muted,QM_CENTER);
  CzmStyle::Text(m_navNext,ru?"Следующая ›":"Next ›",CZMF_UI_LABEL,next?accent:muted,QM_CENTER);
  char page[24];
  if(m_menu.navigation&&m_menu.menuPages)snprintf(page,sizeof(page),"%d / %d",m_menu.menuPage,m_menu.menuPages);
  else snprintf(page,sizeof(page),"%s",m_menu.plain?"—":"1 / 1");
  CzmStyle::Text(CZM_Rect(m_navPrev.x+m_navPrev.w,m_navPrev.y,m_navNext.x-m_navPrev.x-m_navPrev.w,m_navPrev.h),page,CZMF_UI_LABEL,CZM_White(a),QM_CENTER);
  if(m_notice[0]){
   const int y=nav.y+nav.h+H*.004f;
   CZM_DrawText(CZM_Font(CZMF_TINY),m_return.x,y,m_return.w,m_notice,PackRGBA(231,187,96,a),QM_CENTER);
  }
  const unsigned fill=IsPressed(HIT_RETURN)?PackRGBA(158,38,54,a):PackRGBA(190,43,60,a);
  CzmStyle::Surface(m_return,fill,accent,Q_max(4,H/110));
  const char*label=ru?"В игру":"Return to game";
  const HFont font=CZM_Font(CZMF_UI_ACTION);const int icon=m_return.h*.36f,gap=m_return.h*.25f,textW=CZM_TextWidth(font,label);
  const int left=m_return.x+(m_return.w-textW-icon-gap)/2;
  CZM_DrawImage(UI_DIR "icon_play.png",left,m_return.y+(m_return.h-icon)/2,icon,icon,CZM_White(a));
  CZM_DrawText(font,left+icon+gap,m_return.y+(m_return.h-CZM_FontHeight(font))/2,textW+2,label,CZM_White(a));
  return;
 }

 const CzmRect&f=m_foot;HFont font=CZM_Font(CZMF_UI_META);int pad=H*.025f,lineH=CZM_FontHeight(font),x=f.x+pad;
 UI_FillRect(f.x,f.y,f.w,1,PackRGBA(48,56,68,a));
 if( m_menu.navigation )
 {
  const bool ru=CZM_IsRussian();
  const unsigned amber=PackRGBA(255,175,66,a);
  if( m_back.w )
  {
   CzmStyle::Surface(m_back,PackRGBA(25,31,40,a),IsPressed(HIT_BACK)?amber:PackRGBA(142,154,170,a));
   CzmStyle::Text(m_back,ru?"← Назад":"← Back",CZMF_UI_LABEL,CZM_White(a),QM_CENTER);
  }
  if( m_navPrev.w )
  {
   CzmStyle::Surface(m_navPrev,PackRGBA(25,31,40,a),IsPressed(HIT_MENU_PREV)?amber:PackRGBA(63,73,87,a));
   CzmStyle::Text(m_navPrev,"‹",CZMF_UI_LABEL,CZM_White(a),QM_CENTER);
  }
  if( m_menu.menuPages>1 )
  {
   char page[24];
   snprintf(page,sizeof(page),"%d / %d",m_menu.menuPage,m_menu.menuPages);
   CzmStyle::Text(CZM_Rect(f.x+f.w*.462f,f.y,f.w*.076f,f.h),page,CZMF_UI_META,PackRGBA(155,166,184,a),QM_CENTER);
  }
  if( m_navNext.w )
  {
   const unsigned fill=IsPressed(HIT_MENU_NEXT)?PackRGBA(225,145,46,a):amber;
   CzmStyle::Surface(m_navNext,fill,amber);
   CzmStyle::Text(m_navNext,ru?"Далее →":"Next →",CZMF_UI_LABEL,PackRGBA(23,25,30,a),QM_CENTER);
  }
  return;
 }
 const char*right=m_notice[0]?m_notice:m_menu.foot;
 const char*brand="COUNTER ZOMBIE MOBILE";int brandW=CZM_TextWidth(font,brand),rightW=CZM_TextWidth(font,right);
 unsigned color=m_notice[0]?PackRGBA(255,184,94,a):PackRGBA(130,145,164,a);
 if(brandW+rightW+pad*3<=f.w){
  int y=f.y+(f.h-lineH)/2;CZM_DrawText(font,x,y,brandW+2,brand,PackRGBA(130,145,164,a));
  CZM_DrawText(font,x+brandW+pad,y,f.w-brandW-pad*3,right,color,QM_RIGHT);
 }else{
  HFont small=CZM_Font(CZMF_TINY);int sh=CZM_FontHeight(small),top=f.y+(f.h-lineH-sh-H*.003f)/2;
  CZM_DrawText(small,x,top,f.w-pad*2,brand,PackRGBA(115,129,148,a));
  CZM_DrawText(font,x,top+sh+H*.003f,f.w-pad*2,right,color);
 }
}

void CCzmServerWindow::DrawPage( int a )
{
	const bool ru = CZM_IsRussian();
	const bool migration = CzmServerView::ProfileCodeCommand( m_menu.command );
	const unsigned accent = PackRGBA( 255, 168, 66, a );
	if( m_back.w && !m_menu.navigation ) CzmStyle::Button( m_back, ru ? "‹ Назад" : "‹ Back", true, false, IsPressed( HIT_BACK ), accent, CZMF_UI_META );
	const int titleY = m_content.y - (int)( H * .067f );
	CZM_DrawText( CZM_Font( CZMF_UI_ACTION ), m_content.x, titleY, m_content.w, m_menu.pageTitle, CZM_White( a ));
	if( m_menu.kind == CzmServerView::Friends && CZM_OnlineAccount() )
	{
		for( int i = 0; m_friendPage >= 0 && i < 6 && m_friendPage * 6 + i < m_friendCount; ++i )
		{
			const Friend &f = m_friends[m_friendPage * 6 + i]; const CzmRect &r = m_friendRows[i];
			CzmStyle::Surface( r, PackRGBA( 26, 33, 43, a ), IsPressed( 200 + i ) ? accent : PackRGBA( 57, 67, 81, a ), H / 100 );
			const int dot = Q_max( 3, H / 100 ), x = r.x + (int)( H * .020f );
			CZM_DrawImage( UI_DIR "dot.png", x, r.y + ( r.h - dot ) / 2, dot, dot, f.online ? PackRGBA( 107, 218, 167, a ) : PackRGBA( 113, 125, 142, a ));
			const char *action = f.id == m_successFriend ? ( ru ? "Приглашён" : "Invited" ) : ( ru ? "Пригласить" : "Invite" );
			int right = Q_min( (int)( r.w * .35f ), (int)( H * .24f ));
			CZM_DrawText( CZM_Font( CZMF_UI_LABEL ), x + dot + H * .014f, r.y + ( r.h - CZM_FontHeight( CZM_Font( CZMF_UI_LABEL ))) / 2, r.w - right - dot - H * .07f, f.nick, CZM_White( a ));
			CZM_DrawText( CZM_Font( CZMF_UI_META ), r.x + r.w - right - H * .018f, r.y + ( r.h - CZM_FontHeight( CZM_Font( CZMF_UI_META ))) / 2, right, action, accent, QM_RIGHT );
		}
		if( !m_friendCount )
			CzmStyle::TextLines( m_content, m_friendsLoaded ? ( ru ? "В списке пока нет друзей. Добавьте друга через его профиль в игре, затем обновите список." : "No friends yet. Add a friend through their in-game profile, then refresh this list." ) : ( m_notice[0] ? m_notice : ( ru ? "Загружаем список…" : "Loading list…" )), CZMF_PANEL_TEXT );
		CzmStyle::Button( m_refresh, ru ? "Обновить" : "Refresh", !m_request, false, IsPressed( HIT_REFRESH ), accent, CZMF_UI_META );
		CzmStyle::Button( m_prev, "‹", m_friendPage > 0 || m_friendOffset > 0, false, IsPressed( HIT_PREV ), accent );
		CzmStyle::Button( m_next, "›", ( m_friendPage + 1 ) * 6 < m_friendCount || m_nextOffset >= 0, false, IsPressed( HIT_NEXT ), accent );
		return;
	}
	const char *text = m_menu.kind == CzmServerView::Friends && !CZM_OnlineAccount()
		? ( ru ? "Войдите в аккаунт CZM, чтобы увидеть друзей и отправить приглашение на этот сервер." : "Sign in to CZM to see your friends and invite them to this server." ) : m_menu.body;
	const HFont font = CZM_Font( CZMF_PANEL_TEXT ); int starts[129];
	int lineH = CZM_FontHeight( font ) + Q_max( 2, H / 160 ), lines = CZM_WrapText( font, text, m_content.w - H * .018f, starts, 128 );
	m_scrollMax = Q_max( 0, lines * lineH - m_content.h ); m_scroll = bound( 0, m_scroll, m_scrollMax );
	UI::Scissor::PushScissor( m_content.x, m_content.y, m_content.w, m_content.h );
	for( int i = 0; i < lines; ++i )
	{
		int y = m_content.y + i * lineH - m_scroll;
		if( y + lineH <= m_content.y || y >= m_content.y + m_content.h ) continue;
		char line[1024]; CZM_WrapLine( text, starts, i, line, sizeof( line ));
		CZM_DrawText( font, m_content.x, y, m_content.w - H * .018f, line, PackRGBA( 190, 202, 218, a ));
	}
	UI::Scissor::PopScissor();
	if( m_scrollMax )
	{
		int track = m_content.h, thumb = Q_max( H / 25, track * track / ( track + m_scrollMax ));
		UI_FillRect( m_content.x + m_content.w - Q_max( 2, H / 300 ), m_content.y + m_scroll * ( track - thumb ) / m_scrollMax, Q_max( 2, H / 300 ), thumb, accent );
	}
	if( m_menu.kind == CzmServerView::Account || m_menu.kind == CzmServerView::Friends )
		CzmStyle::Button( m_submit, ru ? "Войти в профиль" : "Sign in", true, false, IsPressed( HIT_SUBMIT ), accent );
	if( m_menu.kind == CzmServerView::Form )
	{
		if( m_formPending && uiStatic.realTime - m_formTime > 20000 )
		{
			m_formPending = false;
			Q_strncpy( m_notice, ru ? "Ответ не получен. Текст сохранён, можно повторить отправку" : "No response. Your text is kept for retry", sizeof( m_notice ));
		}
		CzmStyle::Surface( m_field, PackRGBA( 11, 16, 23, a ), m_typing ? accent : PackRGBA( 71, 84, 102, a ), H / 100 );
		CzmRect r = CZM_Rect( m_field.x + H * .018f, m_field.y + H * .012f, m_field.w - H * .036f, m_field.h - H * .024f );
		const int chars = CzmServerView::Characters( m_input );
		char masked[33] = {};
		if( migration ) memset( masked, '*', Q_min( chars, 32 ));
		const char *input = migration ? masked : m_input;
		CzmStyle::TextLines( r, input[0] ? input : ( m_menu.hint[0] ? m_menu.hint : ( ru ? "Нажмите и введите текст…" : "Tap to enter text…" )), CZMF_PANEL_TEXT, input[0] ? CZM_White( a ) : PackRGBA( 116, 133, 154, a ));
		char counter[48]; snprintf( counter, sizeof( counter ), "%d / %d", chars, migration ? 32 : 180 );
		const char *feedback = migration && m_notice[0] ? m_notice : counter;
		CZM_DrawText( CZM_Font( CZMF_UI_LABEL ), m_content.x, m_submit.y + ( m_submit.h - CZM_FontHeight( CZM_Font( CZMF_UI_LABEL ))) / 2, m_submit.x - m_content.x - H * .018f, feedback, PackRGBA( 157, 172, 190, a ));
		CzmStyle::Button( m_submit, m_formPending ? ( ru ? "Отправляем…" : "Sending…" )
			: migration ? ( ru ? "Перенести" : "Transfer" ) : ( ru ? "Отправить" : "Send" ), !m_formPending, false, IsPressed( HIT_SUBMIT ), accent );
	}
}

void CCzmServerWindow::Draw()
{
 if(m_bClosing)return;
 if(!CL_IsActive()){Close(false);return;}
 FriendsFrame();
 float t=Q_min(1.0f,(uiStatic.realTime-m_iOpenTime)/170.0f),ease=1-(1-t)*(1-t);int a=255*ease;
 Layout((1-ease)*H*.025f);
 UI_FillRect(0,0,ScreenWidth,ScreenHeight,PackRGBA(3,5,9,a*165/255));
 CzmStyle::Surface(m_win,PackRGBA(17,22,30,a),PackRGBA(69,77,90,a),Q_max(6,H/70));
 UI_FillRect(m_win.x+H*.025f,m_win.y,Q_max(1,(int)(m_win.w*.24f)),Q_max(2,H/400),PackRGBA(229,63,77,a));
 DrawHeader(a);DrawTabs(a);
 if(m_menu.kind==CzmServerView::Cards)DrawCards(a);else DrawPage(a);
 DrawFooter(a);
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
static bool OpenClassPreview( bool ct, bool conditionZero, int teamFlags );

class CCzmTeamCard : public CMenuBaseClientWindow
{
public:
	typedef CMenuBaseClientWindow BaseClass;
	CCzmTeamCard() : BaseClass( "CzmTeamCard" ), m_bSpectate( false ), m_bCancel( false ), m_bPlay( false ), m_iSlot( -1 ),
		m_iPressed( 0 ), m_iOpenTime( 0 ), m_bClosing( false ), W( 0 ), H( 0 ) { m_szMap[0] = m_szText[0] = 0; }

	void Open( int teamFlags, bool conditionZero );
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
	bool m_bSpectate, m_bCancel, m_bPlay;
	int m_iSlot;               // our server (CZM_OFFICIAL_*), -1 another
	int m_teamFlags = 0;
	bool m_conditionZero = false;
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

void CCzmTeamCard::Open( int teamFlags, bool conditionZero )
{
	const char *map = g_pClient ? g_pClient->GetLevelName() : NULL;
	const char *counts = EngFuncs::GetCvarString( "czm_team_counts" );

	Q_strncpy( m_szMap, map && map[0] ? map : "", sizeof( m_szMap ));
	ReadDescription();
	m_teamFlags = teamFlags;
	m_conditionZero = conditionZero;
	m_bSpectate = ( teamFlags & 1 ) != 0;
	m_bCancel = ( teamFlags & 4 ) != 0;
	m_iSlot = CZM_OfficialSlotNow();
	m_bPlay = m_iSlot >= 0 || CZM_PlayServer();
	m_iCounts[0] = m_iCounts[1] = 0;
	if( counts )
		sscanf( counts, "%d %d", &m_iCounts[0], &m_iCounts[1] );
	m_iPressed = 0;
	m_iOpenTime = uiStatic.realTime;
	m_bClosing = false;
	// our welcome is on the card: the MOTD box goes
	if( m_bPlay )
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
	// The capability or the official cache may arrive after the initial team window.
	m_iSlot = CZM_OfficialSlotNow();
	bool play = m_iSlot >= 0 || CZM_PlayServer();
	if( play != m_bPlay )
	{
		m_bPlay = play;
		m_iPressed = 0;
		if( play ) EngFuncs::CvarSetString( "czm_motd_off", "1" );
	}
	W = ScreenWidth;
	H = ScreenHeight;

	int cw = Q_min( (int)( W * 0.40f ), (int)( H * 0.80f ));
	int pad = H * 0.034f, mapH = cw * 0.27f, btnH = H * 0.088f, gap = H * 0.016f;
	HFont nameFont = CZM_Font( CZMF_MENU_TITLE ), textFont = CZM_Font( CZMF_PANEL_TEXT ), hintFont = CZM_Font( CZMF_UI_META );
	int starts[4], lines = m_szText[0] ? CZM_WrapText( textFont, m_szText, cw - pad * 2, starts, 3 ) : 0;
	int rows = m_bPlay ? 2 : ( m_bSpectate ? 2 : 1 );
	int ch = H * 0.014f + mapH + CZM_FontHeight( nameFont ) * 0.6f + lines * ( CZM_FontHeight( textFont ) + H * 0.004f ) + gap * 1.6f
		+ rows * btnH + ( rows - 1 ) * gap + ( m_bPlay ? CZM_FontHeight( hintFont ) + gap * 2 : 0 ) + pad;

	m_card = CZM_Rect(( W - cw ) / 2, ( H - ch ) / 2, cw, ch );
	m_map = CZM_Rect( m_card.x + H * 0.014f, m_card.y + H * 0.014f, cw - H * 0.028f, mapH );
	m_iTextY = m_map.y + mapH + CZM_FontHeight( nameFont ) * 0.6f;

	int y = m_iTextY + lines * ( CZM_FontHeight( textFont ) + H * 0.004f ) + gap * 1.6f;
	int x = m_card.x + pad, w = cw - pad * 2;

	for( int i = 0; i < BTN_COUNT; i++ )
		m_btn[i] = CZM_Rect( 0, 0, 0, 0 );

	if( m_bPlay )
	{
		int half = ( w - gap ) / 2;
		m_btn[BTN_PLAY] = CZM_Rect( x, y, half, btnH );
		m_btn[BTN_SPECTATE] = CZM_Rect( x + half + gap, y, w - half - gap, btnH );
		m_btn[BTN_CT] = CZM_Rect( x, y + btnH + gap, half, btnH );
		m_btn[BTN_T] = CZM_Rect( x + half + gap, y + btnH + gap, w - half - gap, btnH );
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
	if( ( m_iSlot >= 0 || CZM_PlayServer() ) && button != BTN_CLOSE )
	{
		const char *choice = button == BTN_SPECTATE ? "spectator" : button == BTN_T ? "zombie" : button == BTN_CT ? "human" : "auto";
		EngFuncs::ClientCmdF( false, "czm_join %s\n", choice );
	}
	else if( button == BTN_T || button == BTN_CT )
	{
		if( !OpenClassPreview( button == BTN_CT, m_conditionZero, m_teamFlags ))
			EngFuncs::ClientCmdF( false, "%s\n", commands[button] );
	}
	else if( commands[button] )
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
	if( key == '1' ) Press( BTN_T );
	else if( key == '2' ) Press( BTN_CT );
	else if( key == '5' ) Press( m_bPlay ? BTN_PLAY : BTN_AUTO );
	else if( key == '6' && ( m_bPlay || m_bSpectate )) Press( BTN_SPECTATE );
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

		if( m_bPlay )
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
			if( m_bPlay )
				snprintf( label, sizeof( label ), "%s", t ? ( ru ? "Зайти за Зомби" : "Join zombies" ) : ( ru ? "Зайти за людей" : "Join humans" ) );
			else snprintf( label, sizeof( label ), "%s · %d", t ? ( ru ? "Т" : "T" ) : ( ru ? "КТ" : "CT" ), m_iCounts[t ? 0 : 1] );
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
	if( m_bPlay )
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

class CCzmClassCard : public CMenuBaseClientWindow
{
public:
	CCzmClassCard() : CMenuBaseClientWindow( "CzmClassCard" ) {}
	void Open( bool ct, bool conditionZero, int teamFlags = -1 );
	bool AcceptServerClass( bool ct, bool conditionZero );
	void ClearPending() { m_pendingClass = 0; }
	void Draw() override;
	bool KeyDown( int key ) override;
	bool KeyUp( int key ) override;
	void Hide() override;

private:
	enum { Back = 7, Join };
	void Layout();
	int Hit() const;
	void Activate( int action );
	const char *Name( int index ) const;
	bool DrawModel();

	bool m_ct = false, m_closing = false;
	int m_count = 5, m_selected = 0, m_pressed = 0;
	int m_teamFlags = -1, m_pendingClass = 0;
	double m_pendingUntil = 0;
	int m_modelChoice = -1, m_modelWidth = 0, m_modelHeight = 0;
	CzmRect m_panel, m_preview, m_rows[6], m_back, m_join;
	CMenuPlayerModelView m_model;
};

void CCzmClassCard::Open( bool ct, bool conditionZero, int teamFlags )
{
	m_ct = ct;
	m_count = conditionZero ? 6 : 5;
	m_teamFlags = teamFlags;
	m_selected = m_pressed = 0;
	m_modelChoice = -1;
	m_closing = false;
	CZM_KeepClientMenu( this );
	EngFuncs::KEY_SetDest( KEY_MENU );
	EngFuncs::ClientCmd( true, "touch_setclientonly 1" );
	CMenuBaseClientWindow::Show();
}

bool CCzmClassCard::AcceptServerClass( bool ct, bool conditionZero )
{
	const int selected = m_pendingClass;
	ClearPending();
	if( !selected || EngFuncs::DoubleTime() > m_pendingUntil || ct != m_ct || conditionZero != ( m_count == 6 ))
		return false;
	EngFuncs::ClientCmdF( false, "joinclass %d\n", selected );
	return true;
}

void CCzmClassCard::Hide()
{
	if( m_closing ) return;
	m_closing = true;
	CZM_CloseClientMenuSoon( this );
}

void CCzmClassCard::Layout()
{
	const int w = ScreenWidth, h = ScreenHeight, pad = h * .036f, gap = h * .013f;
	const int width = Q_min( (int)( w * .90f ), (int)( h * 1.66f ));
	m_panel = CZM_Rect( ( w - width ) / 2, h * .064f, width, h * .872f );
	const int x = m_panel.x + pad, y = m_panel.y + h * .183f, body = h * .50f;
	const int rowWidth = ( width - 2 * pad - gap ) * .45f;
	const int rowHeight = ( body - gap * ( m_count - 1 )) / m_count;
	for( int i = 0; i < m_count; i++ )
		m_rows[i] = CZM_Rect( x, y + i * ( rowHeight + gap ), rowWidth, rowHeight );
	m_preview = CZM_Rect( x + rowWidth + gap, y, width - 2 * pad - rowWidth - gap, body );

	const int actionY = m_panel.y + m_panel.h - pad - h * .088f;
	const int actionWidth = ( width - 2 * pad - gap ) / 2;
	if( m_teamFlags >= 0 )
	{
		m_back = CZM_Rect( x, actionY, actionWidth, h * .088f );
		m_join = CZM_Rect( x + actionWidth + gap, actionY, actionWidth, m_back.h );
	}
	else
	{
		m_back = CZM_Rect( 0, 0, 0, 0 );
		m_join = CZM_Rect( x, actionY, width - 2 * pad, h * .088f );
	}
}

const char *CCzmClassCard::Name( int index ) const
{
	static const char *names[2][5] = {
		{ "Phoenix Connexion", "Elite Crew", "Arctic Avengers", "Guerrilla Warfare", "Midwest Militia" },
		{ "SEAL Team 6", "GSG-9", "SAS", "GIGN", "Spetsnaz" },
	};
	if( index == m_count - 1 ) return CZM_IsRussian() ? "Автовыбор" : "Auto-select";
	return names[m_ct][index];
}

bool CCzmClassCard::DrawModel()
{
	if( m_selected == m_count - 1 ) return false;
	static const char *models[2][5] = {
		{ "terror", "leet", "arctic", "guerilla", "militia" },
		{ "urban", "gsg9", "sas", "gign", "spetsnaz" },
	};
	const char *model = models[m_ct][m_selected];
	if( m_modelChoice != m_selected || m_modelWidth != ScreenWidth || m_modelHeight != ScreenHeight )
	{
		const int pad = ScreenHeight * .012f;
		m_model.iFlags |= QMF_DISABLESCAILING | QMF_INACTIVE;
		m_model.m_bCanCaptureFocus = false;
		m_model.SetRect( m_preview.x + pad, m_preview.y + pad, m_preview.w - 2 * pad, m_preview.h - pad - ScreenHeight * .053f );
		m_model.VidInit();
		m_model.backgroundColor.SetDefault( 0 );
		m_model.iStrokeWidth = 0;
		m_modelChoice = m_selected;
		m_modelWidth = ScreenWidth;
		m_modelHeight = ScreenHeight;
		char path[128];
		if( m_model.ent && CzmPlayerModel::Path( model, path, sizeof( path )) && EngFuncs::FileExists( path ))
			EngFuncs::SetModel( m_model.ent, path );
		snprintf( path, sizeof( path ), "gfx/vgui/%s.tga", model );
		const bool hasModel = m_model.ent && m_model.ent->model;
		m_model.hPlayerImage = hasModel ? 0 : EngFuncs::PIC_Load( path );
		m_model.eOverrideMode = hasModel ? CMenuPlayerModelView::PMV_SHOWMODEL : CMenuPlayerModelView::PMV_SHOWIMAGE;
	}
	if( !m_model.hPlayerImage && ( !m_model.ent || !m_model.ent->model )) return false;
	m_model.Draw();
	return true;
}

void CCzmClassCard::Draw()
{
	if( m_closing ) return;
	if( !CL_IsActive() ) { Hide(); return; }
	Layout();
	const bool ru = CZM_IsRussian();
	const int h = ScreenHeight, pad = h * .036f;
	UI_FillRect( 0, 0, ScreenWidth, h, PackRGBA( 4, 6, 10, 182 ));
	CZM_DrawSliced( UI_DIR "smenu_frame.png", m_panel.x, m_panel.y, m_panel.w, m_panel.h, 48, pad, CZM_White());
	CZM_DrawText( CZM_Font( CZMF_MENU_TITLE ), m_panel.x + pad, m_panel.y + pad, m_panel.w - 2 * pad,
		ru ? "Выбор персонажа" : "Choose a character", CZM_White());
	const HFont note = CZM_Font( CZMF_UI_LABEL );
	CZM_DrawText( note, m_panel.x + pad, m_panel.y + h * .124f, m_panel.w - 2 * pad,
		m_ct ? ( ru ? "Спецназ · КТ" : "Counter-Terrorists · CT" ) : ( ru ? "Террористы · Т" : "Terrorists · T" ),
		m_ct ? PackRGBA( 147, 196, 255, 255 ) : PackRGBA( 251, 171, 146, 255 ));
	for( int i = 0; i < m_count; i++ )
		CZM_DrawButton( i == m_selected ? UI_DIR "tab_on.png" : UI_DIR "button_secondary.png",
			m_rows[i], Name( i ), CZM_White(), m_pressed == i + 1, CZMF_UI_LABEL );
	CZM_DrawSliced( UI_DIR "card.png", m_preview.x, m_preview.y, m_preview.w, m_preview.h, 30, pad / 2, CZM_White());
	if( !DrawModel() )
	{
		const int icon = h * .115f;
		CZM_DrawImage( UI_DIR "icon_users.png", m_preview.x + ( m_preview.w - icon ) / 2,
			m_preview.y + ( m_preview.h - icon ) / 2, icon, icon, CZM_White( 120 ));
	}
	CZM_DrawText( note, m_preview.x + pad, m_preview.y + m_preview.h - h * .043f, m_preview.w - 2 * pad,
		Name( m_selected ), CZM_White(), QM_CENTER );
	if( m_teamFlags >= 0 )
		CZM_DrawButton( UI_DIR "button_secondary.png", m_back, ru ? "Назад" : "Back", CZM_White(), m_pressed == Back, CZMF_TILE_STATUS );
	CZM_DrawButton( UI_DIR "tab_on.png", m_join, ru ? "В бой" : "Join", CZM_White(), m_pressed == Join, CZMF_TILE_STATUS );
}

int CCzmClassCard::Hit() const
{
	if( m_teamFlags >= 0 && m_back.HasCursor() ) return Back;
	if( m_join.HasCursor() ) return Join;
	for( int i = 0; i < m_count; i++ )
		if( m_rows[i].HasCursor() ) return i + 1;
	return 0;
}

void CCzmClassCard::Activate( int action )
{
	if( m_closing || !action || ( action == Back && m_teamFlags < 0 )) return;
	CZM_PlayClick();
	if( action <= m_count )
	{
		m_selected = action - 1;
		return;
	}
	Hide();
	if( action == Back ) menu_czmteam->Open( m_teamFlags, m_count == 6 );
	else if( m_teamFlags >= 0 )
	{
		// Stock servers lock team changes while waiting for joinclass.
		// Send the team only after the player confirms the local preview.
		m_pendingClass = m_selected + 1;
		m_pendingUntil = EngFuncs::DoubleTime() + 5.0;
		EngFuncs::ClientCmdF( false, "jointeam %d\n", m_ct ? 2 : 1 );
	}
	else EngFuncs::ClientCmdF( false, "joinclass %d\n", m_selected + 1 );
}

bool CCzmClassCard::KeyDown( int key )
{
	if( UI::Key::IsEscape( key )) Activate( Back );
	else if( UI::Key::IsEnter( key )) Activate( Join );
	else if( UI::Key::IsLeftMouse( key )) { Layout(); m_pressed = Hit(); }
	else if( key >= '1' && key < '1' + m_count ) Activate( key - '0' );
	return true;
}

bool CCzmClassCard::KeyUp( int key )
{
	if( UI::Key::IsLeftMouse( key ))
	{
		Layout();
		const int pressed = m_pressed;
		m_pressed = 0;
		if( pressed == Hit() ) Activate( pressed );
	}
	return true;
}

ADD_MENU3( menu_czmclass, CCzmClassCard, UI_CzmClass_Menu );
void UI_CzmClass_Menu( void ) {}

static bool OpenClassPreview( bool ct, bool conditionZero, int teamFlags )
{
	if( !menu_czmclass ) return false;
	menu_czmclass->ClearPending();
	menu_czmclass->Open( ct, conditionZero, teamFlags );
	return true;
}

bool CZM_TeamShow( int menuType, int param1, int param2 )
{
	// our servers choose the model: no class menu after the team
	if(( menuType == CZM_MENU_CLASS_T || menuType == CZM_MENU_CLASS_CT ) && ( CZM_PlayServer() || CZM_OfficialSlotNow() >= 0 ))
	{
		EngFuncs::ClientCmd( false, "joinclass 5\n" );
		return true;
	}
	if( ( menuType == CZM_MENU_CLASS_T || menuType == CZM_MENU_CLASS_CT ) && menu_czmclass )
	{
		if( !menu_czmclass->AcceptServerClass( menuType == CZM_MENU_CLASS_CT, param1 != 0 ))
			menu_czmclass->Open( menuType == CZM_MENU_CLASS_CT, param1 != 0 );
		return true;
	}
	if( menuType != CZM_MENU_TEAM || !menu_czmteam )
		return false;
	if( menu_czmclass ) menu_czmclass->ClearPending();
	menu_czmteam->Open( param1, param2 != 0 );
	return true;
}

// Our menus get the window; returns true when the cards overlay must leave the menu alone.
static bool ServerWindowFrame( const char *value )
{
	bool rich = IsRichMenu( value );
	bool plain = !rich && value && value[0] && CL_IsActive() && EngFuncs::GetCvarFloat( "czm_menu_cards" ) != 0.0f && !CzmWeapons::Wire( value ) && !CZM_IsWeaponMenu( value );
	if( plain ) { ParseMenu( value ); plain = s_menu.numCards > 0; }
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
		EngFuncs::ClientCmdF( true, "touch_addbutton \"_czm_spec_exit\" \"\" \"czm_join auto\" %f %f %f %f 255 255 255 0 4\n",
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

	// The weapon window must close when the next ShowMenu is an equipment card.
	if( CZM_ShopWeaponFrame( value ) || ServerWindowFrame( value ))
	{
		RemoveButtons();
		return;
	}
	// A closing shop may still have its last packet until the server replies.
	if( CzmSurvivalShop::Wire( CzmWeapons::Text( value )))
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
