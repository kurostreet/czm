/*
CzmShop.cpp - Counter Zombie Mobile shop: the buy menu as a wheel or as a grid of cards
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

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "extdll_menu.h"
#include "BaseMenu.h"
#include "BaseClientWindow.h"
#include "PlayerModelView.h"
#include "Utils.h"
#include "keydefs.h"
#include "CzmMenu.h"
#include "../../common/czm_player_model.h"
#include "../../common/czm_weapon_menu.h"

#define UI_DIR "gfx/czm/ui/"
#define SHOP_DIR "gfx/czm/shop/"

// buy menus the client asks for (dlls/cdll_dll.h)
#define CZM_MENU_BUY       28
#define CZM_MENU_BUY_ITEM  34

#define TEAM_T  1
#define TEAM_CT 2

/*
=================
what the shop sells

Prices are the standard Counter-Strike 1.6 ones. Pictures are the game's own buy
menu pictures (gfx/vgui), turned into white silhouettes when the shop opens.
=================
*/
enum
{
	CAT_PISTOLS = 0,
	CAT_SHOTGUNS,
	CAT_SMG,
	CAT_RIFLES,
	CAT_MG,
	CAT_EQUIPMENT,
	CAT_COUNT
};

static const struct
{
	const char *ru, *en, *image;
} s_categories[CAT_COUNT] =
{
	{ "Пистолеты", "Pistols", "deserteagle" },
	{ "Дробовики", "Shotguns", "m3" },
	{ "Пист.-пулемёты", "SMGs", "mp5" },
	{ "Винтовки", "Rifles", "ak47" },
	{ "Пулемёты", "Machine guns", "m249" },
	{ "Снаряжение", "Equipment", "hegrenade" },
};

struct CzmShopItem
{
	const char *name;     // weapon name, the same in both languages
	const char *ru, *en;  // equipment name (NULL for weapons)
	const char *image;    // gfx/vgui/<image>.tga
	const char *command;  // buy command
	int price;
	int team;             // 0 both, TEAM_T, TEAM_CT
	int category;
	int weapon;           // weapon id for "owned", 0 none
	int damage, pellets, clip, ammo, speed;
};

static const CzmShopItem s_items[] =
{
	// pistols
	{ "Glock-18", NULL, NULL, "glock18", "glock", 400, 0, CAT_PISTOLS, 17, 25, 1, 20, 120, 250 },
	{ "USP", NULL, NULL, "usp45", "usp", 500, 0, CAT_PISTOLS, 16, 34, 1, 12, 100, 250 },
	{ "P228", NULL, NULL, "p228", "p228", 600, 0, CAT_PISTOLS, 1, 32, 1, 13, 52, 250 },
	{ "Desert Eagle", NULL, NULL, "deserteagle", "deagle", 650, 0, CAT_PISTOLS, 26, 54, 1, 7, 35, 250 },
	{ "Five-SeveN", NULL, NULL, "fiveseven", "fiveseven", 750, TEAM_CT, CAT_PISTOLS, 11, 20, 1, 20, 100, 250 },
	{ "Dual Elites", NULL, NULL, "elites", "elites", 800, TEAM_T, CAT_PISTOLS, 10, 36, 1, 30, 120, 250 },
	// shotguns
	{ "M3", NULL, NULL, "m3", "m3", 1700, 0, CAT_SHOTGUNS, 21, 20, 9, 8, 32, 230 },
	{ "XM1014", NULL, NULL, "xm1014", "xm1014", 3000, 0, CAT_SHOTGUNS, 5, 20, 6, 7, 32, 240 },
	// submachine guns
	{ "TMP", NULL, NULL, "tmp", "tmp", 1250, TEAM_CT, CAT_SMG, 23, 20, 1, 30, 120, 250 },
	{ "MAC-10", NULL, NULL, "mac10", "mac10", 1400, TEAM_T, CAT_SMG, 7, 29, 1, 30, 100, 250 },
	{ "MP5", NULL, NULL, "mp5", "mp5", 1500, 0, CAT_SMG, 19, 26, 1, 30, 120, 250 },
	{ "UMP45", NULL, NULL, "ump45", "ump45", 1700, 0, CAT_SMG, 12, 30, 1, 25, 100, 250 },
	{ "P90", NULL, NULL, "p90", "p90", 2350, 0, CAT_SMG, 30, 21, 1, 50, 100, 245 },
	// rifles
	{ "Galil", NULL, NULL, "galil", "galil", 2000, TEAM_T, CAT_RIFLES, 14, 30, 1, 35, 90, 240 },
	{ "FAMAS", NULL, NULL, "famas", "famas", 2250, TEAM_CT, CAT_RIFLES, 15, 30, 1, 25, 90, 240 },
	{ "AK-47", NULL, NULL, "ak47", "ak47", 2500, TEAM_T, CAT_RIFLES, 28, 36, 1, 30, 90, 221 },
	{ "Scout", NULL, NULL, "scout", "scout", 2750, 0, CAT_RIFLES, 3, 75, 1, 10, 90, 260 },
	{ "M4A1", NULL, NULL, "m4a1", "m4a1", 3100, TEAM_CT, CAT_RIFLES, 22, 32, 1, 30, 90, 230 },
	{ "SG 552", NULL, NULL, "sg552", "sg552", 3500, TEAM_T, CAT_RIFLES, 27, 33, 1, 30, 90, 235 },
	{ "AUG", NULL, NULL, "aug", "aug", 3500, TEAM_CT, CAT_RIFLES, 8, 32, 1, 30, 90, 240 },
	{ "SG 550", NULL, NULL, "sg550", "sg550", 4200, TEAM_CT, CAT_RIFLES, 13, 70, 1, 30, 90, 210 },
	{ "AWP", NULL, NULL, "awp", "awp", 4750, 0, CAT_RIFLES, 18, 115, 1, 10, 30, 210 },
	{ "G3SG1", NULL, NULL, "g3sg1", "g3sg1", 5000, TEAM_T, CAT_RIFLES, 24, 80, 1, 20, 90, 210 },
	// machine guns
	{ "M249", NULL, NULL, "m249", "m249", 5750, 0, CAT_MG, 20, 32, 1, 100, 200, 220 },
	// equipment
	{ NULL, "Броня", "Kevlar", "kevlar", "vest", 650, 0, CAT_EQUIPMENT, 0, 0, 0, 0, 0, 0 },
	{ NULL, "Броня + шлем", "Kevlar + helmet", "kevlar_helmet", "vesthelm", 1000, 0, CAT_EQUIPMENT, 0, 0, 0, 0, 0, 0 },
	{ NULL, "Световая", "Flashbang", "flashbang", "flash", 200, 0, CAT_EQUIPMENT, 25, 0, 0, 0, 0, 0 },
	{ NULL, "Осколочная", "HE grenade", "hegrenade", "hegren", 300, 0, CAT_EQUIPMENT, 4, 0, 0, 0, 0, 0 },
	{ NULL, "Дымовая", "Smoke grenade", "smokegrenade", "sgren", 300, 0, CAT_EQUIPMENT, 9, 0, 0, 0, 0, 0 },
	{ NULL, "Набор сапёра", "Defuse kit", "defuser", "defuser", 200, TEAM_CT, CAT_EQUIPMENT, 0, 0, 0, 0, 0, 0 },
	{ NULL, "Ночное видение", "Night vision", "nightvision", "nvgs", 1250, 0, CAT_EQUIPMENT, 0, 0, 0, 0, 0, 0 },
	{ NULL, "Щит", "Tactical shield", "shield", "shield", 2200, TEAM_CT, CAT_EQUIPMENT, 0, 0, 0, 0, 0, 0 },
};

#define CZM_SHOP_ITEMS ( (int)( sizeof( s_items ) / sizeof( s_items[0] )))
#define CZM_MAX_SECTORS 8

static const struct
{
	const char *ru, *en; // two lines: title and what it buys
	const char *ru2, *en2;
	const char *command;
} s_quick[] =
{
	{ "Повторить закупку", "Rebuy", "как в прошлом раунде", "like last round", "rebuy" },
	{ "Автозакупка", "Auto buy", "оружие и снаряжение", "weapons and gear", "autobuy" },
	{ "Броня + шлем", "Kevlar + helmet", "$ 1 000", "$ 1 000", "vesthelm" },
	{ "Патроны", "Ammo", "основное и пистолет", "primary and pistol", "primammo; secammo" },
	{ "Гранаты", "Grenades", "осколочная, свет, дым", "HE, flash, smoke", "hegren; flash; sgren" },
};

#define CZM_QUICK ( (int)( sizeof( s_quick ) / sizeof( s_quick[0] )))

static const char *ItemName( const CzmShopItem &item )
{
	if( item.name )
		return item.name;
	return CZM_IsRussian() ? item.ru : item.en;
}

static void FormatMoney( int value, char *buf, size_t size )
{
	// 16000 -> "$ 16 000"
	if( value >= 1000 )
		snprintf( buf, size, "$ %d %03d", value / 1000, value % 1000 );
	else
		snprintf( buf, size, "$ %d", value );
}

/*
=================
silhouettes

The game's buy menu pictures, white with the original transparency, cropped to
the picture. Built once in memory and handed to the engine as a TGA file.
=================
*/
struct CzmSilhouette
{
	char image[32];
	HIMAGE handle;
	int w, h;
};

static CzmSilhouette s_silhouettes[48];
static int s_numSilhouettes;

static bool DecodeTGA( const byte *data, int length, int *width, int *height, byte **rgba )
{
	int idlen, cmtype, type, w, h, bpp, desc, pos, px;
	byte *out;

	if( length < 18 )
		return false;

	idlen = data[0];
	cmtype = data[1];
	type = data[2];
	w = data[12] | data[13] << 8;
	h = data[14] | data[15] << 8;
	bpp = data[16];
	desc = data[17];
	px = bpp / 8;

	if( cmtype != 0 || ( type != 2 && type != 10 ) || ( bpp != 24 && bpp != 32 ) || w <= 0 || h <= 0 || w > 1024 || h > 1024 )
		return false;

	pos = 18 + idlen;
	out = (byte *)malloc( w * h * 4 );
	if( !out )
		return false;

	for( int i = 0; i < w * h; )
	{
		int count = 1;
		bool rle = false;

		if( type == 10 )
		{
			if( pos >= length )
				break;
			rle = ( data[pos] & 0x80 ) != 0;
			count = ( data[pos] & 0x7F ) + 1;
			pos++;
		}

		for( int k = 0; k < count && i < w * h; k++, i++ )
		{
			const byte *p = data + pos;

			if( pos + px > length )
			{
				free( out );
				return false;
			}

			// TGA stores BGR(A); rows go up unless the top-left bit is set
			int x = i % w, y = i / w;
			int row = ( desc & 0x20 ) ? y : h - 1 - y;
			byte *o = out + ( row * w + x ) * 4;
			o[0] = p[2];
			o[1] = p[1];
			o[2] = p[0];
			o[3] = px == 4 ? p[3] : 255;

			if( !rle || k == count - 1 )
				pos += px;
		}
	}

	*width = w;
	*height = h;
	*rgba = out;
	return true;
}

static CzmSilhouette *Silhouette( const char *image )
{
	char path[64], name[64];
	byte *data, *rgba = NULL, *tga;
	int length = 0, w = 0, h = 0, x0, y0, x1, y1, cw, ch;
	bool hasAlpha = false;
	CzmSilhouette *s;

	for( int i = 0; i < s_numSilhouettes; i++ )
	{
		if( !strcmp( s_silhouettes[i].image, image ))
			return s_silhouettes[i].handle ? &s_silhouettes[i] : NULL;
	}

	if( s_numSilhouettes >= (int)( sizeof( s_silhouettes ) / sizeof( s_silhouettes[0] )))
		return NULL;

	s = &s_silhouettes[s_numSilhouettes++];
	memset( s, 0, sizeof( *s ));
	Q_strncpy( s->image, image, sizeof( s->image ));

	snprintf( path, sizeof( path ), "gfx/vgui/%s.tga", image );
	data = (byte *)EngFuncs::COM_LoadFile( path, &length );
	if( !data )
		return NULL;

	if( !DecodeTGA( data, length, &w, &h, &rgba ))
	{
		EngFuncs::COM_FreeFile( data );
		return NULL;
	}
	EngFuncs::COM_FreeFile( data );

	for( int i = 0; i < w * h; i++ )
	{
		if( rgba[i * 4 + 3] < 250 )
		{
			hasAlpha = true;
			break;
		}
	}

	// pictures without transparency: whatever differs from the corner colour is the weapon
	if( !hasAlpha )
	{
		const byte *bg = rgba;
		for( int i = 0; i < w * h; i++ )
		{
			byte *p = rgba + i * 4;
			int d = Q_max( abs( p[0] - bg[0] ), Q_max( abs( p[1] - bg[1] ), abs( p[2] - bg[2] )));
			p[3] = (byte)bound( 0, ( d - 12 ) * 6, 255 );
		}
	}

	// crop to what is visible
	x0 = w; y0 = h; x1 = -1; y1 = -1;
	for( int y = 0; y < h; y++ )
	{
		for( int x = 0; x < w; x++ )
		{
			if( rgba[( y * w + x ) * 4 + 3] > 24 )
			{
				x0 = Q_min( x0, x ); x1 = Q_max( x1, x );
				y0 = Q_min( y0, y ); y1 = Q_max( y1, y );
			}
		}
	}

	if( x1 < x0 || y1 < y0 )
	{
		free( rgba );
		return NULL;
	}

	cw = x1 - x0 + 1;
	ch = y1 - y0 + 1;
	tga = (byte *)calloc( 1, 18 + cw * ch * 4 );
	if( !tga )
	{
		free( rgba );
		return NULL;
	}

	tga[2] = 2;
	tga[12] = cw & 0xFF; tga[13] = cw >> 8;
	tga[14] = ch & 0xFF; tga[15] = ch >> 8;
	tga[16] = 32;
	tga[17] = 0x28; // 8 alpha bits, top-left origin
	for( int y = 0; y < ch; y++ )
	{
		for( int x = 0; x < cw; x++ )
		{
			byte *o = tga + 18 + ( y * cw + x ) * 4;
			o[0] = o[1] = o[2] = 255;
			o[3] = rgba[(( y + y0 ) * w + ( x + x0 )) * 4 + 3];
		}
	}
	free( rgba );

	snprintf( name, sizeof( name ), "#czm_sil_%s.tga", image );
	s->handle = EngFuncs::PIC_Load( name, tga, 18 + cw * ch * 4 );
	s->w = cw;
	s->h = ch;
	free( tga );

	return s->handle ? s : NULL;
}

// draws the silhouette as large as fits into the box, centred
static void DrawSilhouette( const char *image, int x, int y, int w, int h, unsigned int color )
{
	CzmSilhouette *s = Silhouette( image );
	float scale;
	int dw, dh, r, g, b, a;

	if( !s || w <= 0 || h <= 0 )
		return;

	scale = Q_min( (float)w / s->w, (float)h / s->h );
	dw = s->w * scale;
	dh = s->h * scale;
	UnpackRGBA( r, g, b, a, color );
	EngFuncs::PIC_Set( s->handle, r, g, b, a );
	EngFuncs::PIC_DrawTrans( x + ( w - dw ) / 2, y + ( h - dh ) / 2, dw, dh );
}

/*
=================
the weapon wheel (CzmWheels.cpp): what the player carries, as the shop draws it
=================
*/
bool CZM_ShopCarried( unsigned int weaponBits, int slot, const char **name, const char **image, int *weapon )
{
	// the grenade slot shows the strongest grenade carried
	static const int grenades[] = { 4, 25, 9 }; // HE, flashbang, smoke (weapon ids)

	for( int k = 0; slot == 2 && k < 3; k++ )
	{
		for( int i = 0; i < CZM_SHOP_ITEMS; i++ )
		{
			if( s_items[i].weapon == grenades[k] && ( weaponBits & ( 1u << grenades[k] )))
			{
				*name = ItemName( s_items[i] );
				*image = s_items[i].image;
				*weapon = grenades[k];
				return true;
			}
		}
	}

	for( int i = 0; slot != 2 && i < CZM_SHOP_ITEMS; i++ )
	{
		const CzmShopItem &item = s_items[i];
		const bool pistol = item.category == CAT_PISTOLS;

		if( !item.weapon || item.category == CAT_EQUIPMENT || pistol != ( slot == 1 ))
			continue;
		if( weaponBits & ( 1u << item.weapon ))
		{
			*name = ItemName( item );
			*image = item.image;
			*weapon = item.weapon;
			return true;
		}
	}
	return false;
}

void CZM_ShopDrawSilhouette( const char *image, int x, int y, int w, int h, unsigned int color )
{
	DrawSilhouette( image, x, y, w, h, color );
}

/*
=================
CCzmShop
=================
*/
/*
=================
weapon menus of servers

Zombie Plague and similar mods give weapons with a text menu ("Primary Weapon [1-7]": "1. IMI Galil",
..., "8. Remember Selection [Off]", "9. Next/Back", "0. Exit"). When most items are weapons the
game shows the menu in the shop: the wheel or the grid of the "Shop" setting, the weapons'
pictures and numbers; a pick sends the menu's key like the digit would.
=================
*/
#define CZM_WEAPON_EXTRA 3

static void DrawWeapon( const CzmShopItem &item, int x, int y, int w, int h, unsigned int color )
{
	char path[96];
	snprintf( path, sizeof( path ), SHOP_DIR "weapons/weapon_%d.png", item.weapon );
	if( item.name && CZM_Image( path ) )
	{
		int iw = Q_min( w, h * 2 ), ih = iw / 2;
		CZM_DrawImage( path, x + ( w - iw ) / 2, y + ( h - ih ) / 2, iw, ih, color );
	}
	else DrawSilhouette( item.image, x, y, w, h, color );
}

struct CzmWeaponMenu
{
	int serial;
	CzmWeapons::Meta meta;
	CzmSurvivalShop::View shop;
	char title[64];
	int keys[CZM_MAX_SECTORS];              // menu key of each weapon slot
	const CzmShopItem *items[CZM_MAX_SECTORS];
	int count;
	int toggleKey;                          // "remember the choice", 0 none
	char toggleText[48];
	bool toggleOn;
	int extraKeys[CZM_WEAPON_EXTRA];        // next/back and anything else, on the bottom bar
	char extraText[CZM_WEAPON_EXTRA][40];
	int extras;
};

// the menu line without colour codes (\y \r \w \d \R)
static void PlainLine( const char *line, char *out, size_t size )
{
	size_t n = 0;

	for( const char *p = line; *p && *p != '\n' && n < size - 1; p++ )
	{
		if( p[0] == '\\' && p[1] && strchr( "yrwdR", p[1] ))
		{
			p++;
			continue;
		}
		out[n++] = *p;
	}
	while( n && ( out[n - 1] == ' ' || out[n - 1] == '\r' ))
		n--;
	out[n] = 0;
}

static const CzmShopItem *FindWeapon( const char *text )
{
	// the order matters: "xm1014" before "m3", "sg552" before "sg550" does not
	static const struct { const char *key, *image; } names[] =
	{
		{ "m4a1", "m4a1" }, { "ak47", "ak47" }, { "galil", "galil" }, { "famas", "famas" }, { "sg552", "sg552" },
		{ "sg550", "sg550" }, { "aug", "aug" }, { "scout", "scout" }, { "awp", "awp" }, { "g3sg1", "g3sg1" },
		{ "m249", "m249" }, { "mp5", "mp5" }, { "p90", "p90" }, { "ump", "ump45" }, { "mac10", "mac10" },
		{ "tmp", "tmp" }, { "xm1014", "xm1014" }, { "m3", "m3" }, { "glock", "glock18" }, { "usp", "usp45" },
		{ "p228", "p228" }, { "deagle", "deserteagle" }, { "deserteagle", "deserteagle" }, { "fiveseven", "fiveseven" },
		{ "elite", "elites" },
	};
	char low[64];
	size_t n = 0;

	for( const char *p = text; *p && n < sizeof( low ) - 1; p++ )
	{
		char c = *p;
		if( c >= 'A' && c <= 'Z' )
			c += 'a' - 'A';
		if(( c >= 'a' && c <= 'z' ) || ( c >= '0' && c <= '9' ))
			low[n++] = c;
	}
	low[n] = 0;

	for( size_t k = 0; k < sizeof( names ) / sizeof( names[0] ); k++ )
	{
		if( !strstr( low, names[k].key ))
			continue;
		for( int i = 0; i < CZM_SHOP_ITEMS; i++ )
		{
			if( s_items[i].name && !strcmp( s_items[i].image, names[k].image ))
				return &s_items[i];
		}
	}
	return NULL;
}

static bool Contains( const char *text, const char *word )
{
	return V_stristr( text, word ) != NULL;
}

static const CzmShopItem *ShopWeapon( int weapon )
{
	for( const CzmShopItem &item : s_items )
	{
		if( weapon ? item.weapon == weapon : !strcmp( item.command, "vesthelm" ))
			return &item;
	}
	return NULL;
}

// "serial validslots\ntext" of the cards; true when it is a weapon menu
static bool ParseWeaponMenu( const char *value, CzmWeaponMenu &m )
{
	const char *line = value ? strchr( value, '\n' ) : NULL;
	int validSlots = 0, unknown = 0;

	memset( &m, 0, sizeof( m ));
	if( !line || !strncmp( line + 1, "#czm1", 5 ))
		return false;
	sscanf( value, "%d %d", &m.serial, &validSlots );
	if( CzmSurvivalShop::Wire( line + 1 ))
	{
		if( !CzmSurvivalShop::Parse( line + 1, m.shop )) return false;
		for( int i = 0; i < m.shop.count; ++i )
		{
			const auto &row = m.shop.rows[i];
			if( !row.weapon && m.shop.tab != CzmSurvivalShop::Equipment ) continue;
			const CzmShopItem *item = ShopWeapon( row.weapon );
			if( !item ) continue;
			m.keys[m.count] = row.index;
			m.items[m.count++] = item;
		}
		return true;
	}
	m.meta = CzmWeapons::Parse( value );

	for( line++; *line; )
	{
		const char *end = strchr( line, '\n' );
		char text[160];

		PlainLine( line, text, sizeof( text ));
		line = end ? end + 1 : line + strlen( line );
		if( !text[0] || !strncmp( text, "#czmw1\t", 7 ))
			continue;

		if( text[0] >= '0' && text[0] <= '9' && ( text[1] == '.' || text[1] == ')' ))
		{
			int key = text[0] == '0' ? 10 : text[0] - '0';
			const char *name = text + 2;
			const CzmShopItem *item;

			while( *name == ' ' )
				name++;
			if( key == 10 || !( validSlots & ( 1 << ( key - 1 ))))
				continue;
			item = FindWeapon( name );
			if( item && m.count < CZM_MAX_SECTORS )
			{
				m.keys[m.count] = key;
				m.items[m.count++] = item;
			}
			else if( strchr( name, '[' ) && !m.toggleKey )
			{
				// "Remember Selection [Off]": a switch
				const char *open = strchr( name, '[' );
				m.toggleKey = key;
				Q_strncpy( m.toggleText, name, Q_min( sizeof( m.toggleText ), (size_t)( open - name ) + 1 ));
				for( int n = strlen( m.toggleText ); n > 0 && m.toggleText[n - 1] == ' '; n-- )
					m.toggleText[n - 1] = 0;
				// [On] [Off], [Вкл] [Выкл] (Cyrillic has no case folding here: "ыкл" is both off words)
				bool off = Contains( open, "off" ) || Contains( open, "disabled" ) || strstr( open, "ыкл" );
				m.toggleOn = !off && ( Contains( open, "on" ) || Contains( open, "enabled" ) || strstr( open, "Вкл" ) || strstr( open, "вкл" ));
			}
			else if( m.meta.purchase && key == 9 && m.meta.pages > 1 )
				continue; // separate previous/next controls use the page command
			else if( m.extras < CZM_WEAPON_EXTRA )
			{
				m.extraKeys[m.extras] = key;
				Q_strncpy( m.extraText[m.extras++], name, sizeof( m.extraText[0] ));
				unknown++;
			}
			continue;
		}

		// the title, without "[1-7]"
		if( !m.title[0] )
		{
			char *bracket;
			Q_strncpy( m.title, text, sizeof( m.title ));
			if(( bracket = strchr( m.title, '[' )) != NULL )
				*bracket = 0;
			for( int n = strlen( m.title ); n > 0 && m.title[n - 1] == ' '; n-- )
				m.title[n - 1] = 0;
		}
	}

	// Explicit metadata also supports a server with a single permitted weapon.
	if( m.meta.valid ) m.toggleOn = m.meta.remember != 0;
	return m.count >= ( m.meta.valid ? 1 : 2 ) && unknown <= 2;
}

bool CZM_IsWeaponMenu( const char *value )
{
	CzmWeaponMenu menu;
	return ParseWeaponMenu( value, menu );
}

class CCzmShop : public CMenuBaseClientWindow
{
public:
	typedef CMenuBaseClientWindow BaseClass;
	CCzmShop();

	void Open( int team );
	void OpenServerMenu( const CzmWeaponMenu &menu );
	bool ServerMode( void ) const { return m_bServerMenu; }
	int Serial( void ) const { return m_wmenu.serial; }
	// a weapon was picked: the next menu (pistols) may come
	bool Waiting( void ) const { return m_iPickTime && uiStatic.realTime - m_iPickTime < 700; }
	void CloseServerMenu( bool exitMenu );

	void Init() override;
	void VidInit() override;
	void Show() override;
	void Hide() override;
	void Draw() override;
	bool KeyDown( int key ) override;
	bool KeyUp( int key ) override;
	bool MouseMove( int x, int y ) override;

private:
	enum
	{
		HIT_NONE = 0,
		HIT_CLOSE,
		HIT_HUB,
		HIT_SELECT,
		HIT_CANCEL,
		HIT_TAB = 10,     // + category
		HIT_QUICK = 30,   // + quick button
		HIT_ITEM = 100,   // + slot in the current category
	};

	void ReadState( void );
	void SelectCategory( int category );
	void Layout( void );
	void LayoutSurvival();
	void DrawSurvivalTop();
	void DrawSurvivalFooter();
	void DrawSurvivalGear();
	void ActivateSurvival( int hit );
	void SendSurvival( int action, int value );
	bool Survival() const { return m_bServerMenu && m_wmenu.shop.token != 0; }
	bool RoundShop() const { return Survival() && m_wmenu.shop.roundPurchase; }
	bool Gear() const { return Survival() && m_wmenu.shop.tab == CzmSurvivalShop::Equipment; }
	bool RowEnabled( int row ) const { return !Survival() || m_wmenu.shop.rows[m_wmenu.keys[row]].enabled; }
	int SelectedWeapon() const
	{
		return Survival() ? ( m_wmenu.shop.tab == CzmSurvivalShop::Primary ? m_wmenu.shop.primary : m_wmenu.shop.pistol )
			: m_wmenu.meta.selected;
	}
	int HitTest( void ) const;
	int WheelSlot( int x, int y ) const;
	int QuickCount( void ) const;
	int QuickKey( int i, const char **text ) const;
	bool IsPressed( int hit ) const { return m_iPressed == hit && HitTest() == hit; }
	void Activate( int hit );
	void Buy( const CzmShopItem &item );
	void Toast( const char *text );
	bool Owned( const CzmShopItem &item ) const;
	bool ShowPrice() const { return !m_bServerMenu || m_wmenu.meta.purchase || Survival(); }
	int Price( int row ) const
	{
		if( Survival() ) return m_wmenu.shop.rows[m_wmenu.keys[row]].price;
		return m_wmenu.meta.purchase && m_bServerMenu ? m_wmenu.meta.price : m_slots[row]->price;
	}

	void DrawTop( void );
	void DrawTabs( void );
	void DrawQuick( void );
	void DrawWheel( void );
	void DrawInfo( const CzmShopItem *item );
	bool DrawPlayerSkin( const CzmRect &rect );
	void DrawGrid( void );

	int m_iTeam;
	int m_iMoney;
	unsigned int m_iWeaponBits;
	int m_iArmor;
	bool m_bHelmet;
	bool m_bAlive;

	int m_iCategory;
	const CzmShopItem *m_slots[CZM_MAX_SECTORS];
	int m_iSlots;
	int m_iPressed;
	int m_iHover;      // wheel: slot under the finger, -1 none
	int m_iInfo;       // slot shown in the info panel
	char m_szToast[96];
	int m_iToastTime;
	bool m_bGrid;
	bool m_bClosing;
	bool m_bServerMenu;      // a weapon menu of the server, not the CS shop
	CzmWeaponMenu m_wmenu;
	int m_iPickTime, m_iOpenTime, m_iPacketTime;

	// layout, recalculated every frame
	int W, H;
	CzmRect m_top, m_close, m_tabs[CAT_COUNT], m_quick[CZM_QUICK], m_info, m_buy, m_cancel, m_cards[CZM_MAX_SECTORS];
	int m_iWheelX, m_iWheelY, m_iWheelR;
	CMenuPlayerModelView m_skinView;
	char m_szSkinPath[128];
	CzmRect m_skinRect;
};

static int s_iLastCategory = CAT_RIFLES;

CCzmShop::CCzmShop() : BaseClass( "CzmShop" )
{
	m_iTeam = TEAM_T;
	m_iMoney = 0;
	m_iWeaponBits = 0;
	m_iArmor = 0;
	m_bHelmet = false;
	m_bAlive = true;
	m_iCategory = CAT_RIFLES;
	m_iSlots = 0;
	m_iPressed = HIT_NONE;
	m_iHover = m_iInfo = -1;
	m_szToast[0] = 0;
	m_iToastTime = 0;
	m_bGrid = false;
	m_bClosing = false;
	m_bServerMenu = false;
	memset( &m_wmenu, 0, sizeof( m_wmenu ));
	m_iPickTime = m_iOpenTime = 0;
	W = H = 0;
	m_iWheelX = m_iWheelY = m_iWheelR = 0;
	memset( m_slots, 0, sizeof( m_slots ));
	m_szSkinPath[0] = 0;
	m_skinRect = CZM_Rect( 0, 0, 0, 0 );
}

void CCzmShop::Init()
{
	BaseClass::Init();
	pos.x = uiStatic.xOffset;
	pos.y = uiStatic.yOffset;
	size.w = uiStatic.width;
	size.h = 768;
}

void CCzmShop::VidInit()
{
	pos.x = uiStatic.xOffset;
	pos.y = uiStatic.yOffset;
	size.w = uiStatic.width;
	size.h = 768;
	BaseClass::VidInit();
}

void CCzmShop::ReadState( void )
{
	int money = 0, team = 0, armor = 0, helmet = 0, alive = 1;
	unsigned int bits = 0;
	const char *state = EngFuncs::GetCvarString( "czm_buy_state" );

	if( state && sscanf( state, "%d %d %u %d %d %d", &money, &team, &bits, &armor, &helmet, &alive ) == 6 )
	{
		m_iMoney = money;
		if( team == TEAM_T || team == TEAM_CT )
			m_iTeam = team;
		m_iWeaponBits = bits;
		m_iArmor = armor;
		m_bHelmet = helmet != 0;
		m_bAlive = alive != 0;
	}
	if( Survival() ) m_iMoney = m_wmenu.shop.balance;
	else if( m_bServerMenu && m_wmenu.meta.purchase ) m_iMoney = m_wmenu.meta.balance;
}

void CCzmShop::SelectCategory( int category )
{
	m_iCategory = s_iLastCategory = bound( 0, category, CAT_COUNT - 1 );
	m_iSlots = 0;

	for( int i = 0; i < CZM_SHOP_ITEMS && m_iSlots < CZM_MAX_SECTORS; i++ )
	{
		const CzmShopItem &item = s_items[i];
		if( item.category == m_iCategory && ( !item.team || item.team == m_iTeam ))
			m_slots[m_iSlots++] = &item;
	}

	m_iHover = -1;
	m_iInfo = m_iSlots > 0 ? 0 : -1;

	// show what the player holds, or the best weapon he can afford
	for( int i = 0; i < m_iSlots; i++ )
	{
		if( Owned( *m_slots[i] ))
		{
			m_iInfo = i;
			return;
		}
	}
	for( int i = 0; i < m_iSlots; i++ )
	{
		if( m_slots[i]->price <= m_iMoney )
			m_iInfo = i;
	}
}

static int s_iWeaponClosed = -1;

void CCzmShop::OpenServerMenu( const CzmWeaponMenu &menu )
{
	bool open = m_bServerMenu && CZM_ClientMenuOpen( this );
	if( !open || !menu.shop.roundPurchase || m_wmenu.shop.tab != menu.shop.tab || m_wmenu.shop.page != menu.shop.page )
		m_iOpenTime = uiStatic.realTime;

	m_bServerMenu = true;
	m_wmenu = menu;
	m_iPickTime = 0;
	m_iPacketTime = uiStatic.realTime;
	ReadState();
	m_bGrid = Gear() || EngFuncs::GetCvarFloat( "czm_shop" ) == 2.0f;
	m_iSlots = menu.count;
	for( int i = 0; i < m_iSlots; i++ )
		m_slots[i] = menu.items[i];
	m_iHover = -1;
	m_iInfo = m_iSlots > 0 ? 0 : -1;
	if( Survival() && !Gear() )
	{
		const int preview = RoundShop() ? m_wmenu.shop.preview : SelectedWeapon();
		for( int i = 0; i < m_iSlots; ++i )
			if( m_slots[i]->weapon == preview ) m_iInfo = i;
	}
	m_iPressed = HIT_NONE;
	m_szToast[0] = 0;
	if( open )
		return;
	m_bClosing = false;
	CZM_KeepClientMenu( this );
	Show();
}

void CCzmShop::CloseServerMenu( bool exitMenu )
{
	if( exitMenu )
	{
		s_iWeaponClosed = m_wmenu.serial;
		if( Survival() ) SendSurvival( CzmSurvivalShop::Close, 0 );
		else EngFuncs::ClientCmdF( false, "czm_shop_select %d 10\n", m_wmenu.serial );
	}
	Hide();
}

void CCzmShop::Open( int team )
{
	if( team == TEAM_T || team == TEAM_CT )
		m_iTeam = team;
	m_bServerMenu = false;
	m_iPickTime = 0;
	m_iOpenTime = uiStatic.realTime;
	ReadState();
	m_bGrid = EngFuncs::GetCvarFloat( "czm_shop" ) == 2.0f;
	SelectCategory( s_iLastCategory );
	m_iPressed = HIT_NONE;
	m_szToast[0] = 0;
	m_bClosing = false;
	CZM_KeepClientMenu( this );
	Show();
}

void CCzmShop::Show()
{
	m_szSkinPath[0] = 0; // other menu previews share the engine's preview entity
	EngFuncs::KEY_SetDest( KEY_MENU );
	EngFuncs::ClientCmd( true, "touch_setclientonly 1" );
	BaseClass::Show();
}

// the stock way, on the next frame (Hide() on the only client window would leave it in the stack)
void CCzmShop::Hide()
{
	if( m_bClosing )
		return;
	m_bClosing = true;
	CZM_CloseClientMenuSoon( this );
}

bool CCzmShop::Owned( const CzmShopItem &item ) const
{
	if( m_bServerMenu )
		return false;
	if( item.weapon )
		return ( m_iWeaponBits & ( 1u << item.weapon )) != 0;
	if( !strcmp( item.command, "vesthelm" ))
		return m_iArmor >= 100 && m_bHelmet;
	if( !strcmp( item.command, "vest" ))
		return m_iArmor >= 100;
	return false;
}

void CCzmShop::Toast( const char *text )
{
	Q_strncpy( m_szToast, text, sizeof( m_szToast ));
	m_iToastTime = uiStatic.realTime;
}

void CCzmShop::Buy( const CzmShopItem &item )
{
	char text[96], money[32];

	if( item.price > m_iMoney )
	{
		FormatMoney( item.price - m_iMoney, money, sizeof( money ));
		snprintf( text, sizeof( text ), CZM_IsRussian() ? "Не хватает %s" : "%s short", money );
		Toast( text );
		return;
	}

	CZM_PlayClick();
	EngFuncs::ClientCmdF( false, "%s\n", item.command );
	snprintf( text, sizeof( text ), CZM_IsRussian() ? "Куплено: %s" : "Bought: %s", ItemName( item ));
	Toast( text );
}

/*
=================
layout
=================
*/
void CCzmShop::Layout( void )
{
	int tabX, tabY, tabW, tabH, tabGap, quickX, quickY, quickH, gap;

	W = ScreenWidth;
	H = ScreenHeight;
	if( Survival() )
	{
		LayoutSurvival();
		return;
	}
	gap = H * 0.017f;

	m_top = CZM_Rect( 0, 0, W, H * 0.103f );
	m_close = CZM_Rect( W - H * 0.037f - H * 0.073f, ( m_top.h - H * 0.073f ) / 2, H * 0.073f, H * 0.073f );

	// categories on the left (a weapon menu of the server has none)
	tabX = W * 0.018f;
	tabY = H * 0.137f;
	tabW = m_bServerMenu ? 0 : Q_max( (int)( W * 0.135f ), (int)( H * 0.29f ));
	tabH = H * 0.105f;
	tabGap = H * 0.013f;
	for( int i = 0; i < CAT_COUNT; i++ )
		m_tabs[i] = m_bServerMenu ? CZM_Rect( 0, 0, 0, 0 ) : CZM_Rect( tabX, tabY + i * ( tabH + tabGap ), tabW, tabH );

	// quick buttons along the bottom; a server menu puts its switch and other items there
	quickX = m_bServerMenu ? W * 0.05f : tabX + tabW + gap * 2;
	quickY = H * 0.878f;
	quickH = H * 0.09f;
	{
		int count = QuickCount();
		int total = W - quickX - W * 0.02f - gap * ( CZM_QUICK - 1 );
		int each = total / CZM_QUICK;
		if( m_bServerMenu )
			each = Q_min( (int)( W * .29f ), ( W - quickX * 2 - gap * ( count - 1 ) ) / Q_max( 1, count ) );
		for( int i = 0; i < CZM_QUICK; i++ )
			m_quick[i] = i < count ? CZM_Rect( quickX + i * ( each + gap ), quickY, each, quickH ) : CZM_Rect( 0, 0, 0, 0 );
	}

	if( !m_bGrid )
	{
		int area = W - quickX;
		int infoW = Q_min( (int)( area * 0.47f ), (int)( H * 0.83f ));

		m_info = CZM_Rect( W - W * 0.02f - infoW, tabY, infoW, H * 0.655f );
		m_iWheelR = Q_min( (int)( H * 0.33f ), ( m_info.x - quickX - gap * 2 ) / 2 );
		m_iWheelX = quickX + ( m_info.x - quickX ) / 2;
		m_iWheelY = tabY + ( m_info.h ) / 2 + H * 0.01f;
		m_buy = CZM_Rect( m_info.x + H * 0.04f, m_info.y + m_info.h - H * 0.04f - H * 0.09f, m_info.w - H * 0.08f, H * 0.09f );
	}
	else
	{
		int columns = m_iSlots > 6 ? 4 : ( m_iSlots > 2 ? 3 : Q_max( 1, m_iSlots ));
		int areaX = quickX, areaW = W - W * 0.05f - areaX;
		int areaY = m_bServerMenu ? H * 0.18f : tabY, areaH = quickY - gap * 4 - areaY;
		int cardW = ( areaW - gap * ( columns - 1 )) / columns;
		int cardH = ( areaH - gap ) / 2;

		for( int i = 0; i < m_iSlots; i++ )
		{
			int row = i / columns, inRow = Q_min( columns, m_iSlots - row * columns );
			int center = ( areaW - inRow * cardW - ( inRow - 1 ) * gap ) / 2;
			m_cards[i] = CZM_Rect( areaX + center + ( i % columns ) * ( cardW + gap ), areaY + row * ( cardH + gap ), cardW, cardH );
		}
	}
}

int CCzmShop::QuickCount( void ) const
{
	if( !m_bServerMenu )
		return CZM_QUICK;
	const int pages = m_wmenu.meta.valid && m_wmenu.meta.pages > 1 ? 2 : 0;
	const int extras = !m_wmenu.meta.valid || m_wmenu.meta.purchase ? m_wmenu.extras : 0;
	return Q_min( CZM_QUICK, ( m_wmenu.toggleKey ? 1 : 0 ) + pages + extras );
}

// the menu key of a bottom button of a server menu: the switch first, then the rest
int CCzmShop::QuickKey( int i, const char **text ) const
{
	if( m_wmenu.toggleKey )
	{
		if( i == 0 )
		{
			*text = CZM_IsRussian() ? "ЗАПОМНИТЬ ВЫБОР" : "REMEMBER CHOICE";
			return m_wmenu.toggleKey;
		}
		i--;
	}
	if( m_wmenu.meta.valid && m_wmenu.meta.pages > 1 )
	{
		if( i < 2 )
		{
			*text = i == 0 ? ( CZM_IsRussian() ? "‹ НАЗАД" : "‹ PREVIOUS" ) : ( CZM_IsRussian() ? "ДАЛЕЕ ›" : "NEXT ›" );
			return i == 0 ? -1 : -2;
		}
		i -= 2;
	}
	if( i < m_wmenu.extras )
	{
		*text = m_wmenu.extraText[i];
		return m_wmenu.extraKeys[i];
	}
	*text = "";
	return 0;
}

int CCzmShop::WheelSlot( int x, int y ) const
{
	float dx = x - m_iWheelX, dy = y - m_iWheelY;
	float dist = sqrtf( dx * dx + dy * dy );
	float angle, step;

	if( m_iSlots <= 0 || dist > m_iWheelR * 1.05f || dist < m_iWheelR * ( 88.0f / 300.0f ))
		return -1;

	// angle from the top, clockwise; slot 0 is centred at the top
	step = 360.0f / m_iSlots;
	angle = atan2f( dy, dx ) * 180.0f / M_PI + 90.0f + step / 2.0f;
	while( angle < 0.0f )
		angle += 360.0f;
	while( angle >= 360.0f )
		angle -= 360.0f;

	return bound( 0, (int)( angle / step ), m_iSlots - 1 );
}

int CCzmShop::HitTest( void ) const
{
	int x = uiStatic.cursorX, y = uiStatic.cursorY;

	if( m_close.Grown( H / 60 ).Contains( x, y ))
		return HIT_CLOSE;

	for( int i = 0; i < CAT_COUNT; i++ )
	{
		if( m_tabs[i].Contains( x, y ))
			return HIT_TAB + i;
	}

	for( int i = 0; i < CZM_QUICK; i++ )
	{
		if( m_quick[i].Contains( x, y ))
			return HIT_QUICK + i;
	}
	if( RoundShop() )
	{
		if( m_cancel.Contains( x, y )) return HIT_CANCEL;
		if( !Gear() && m_iInfo >= 0 && m_buy.Contains( x, y )) return HIT_SELECT;
	}

	if( m_bGrid )
	{
		for( int i = 0; i < m_iSlots; i++ )
		{
			if( m_cards[i].Contains( x, y ))
				return HIT_ITEM + i;
		}
		return HIT_NONE;
	}

	if( m_info.Contains( x, y ))
		return m_buy.Contains( x, y ) && m_iInfo >= 0 ? HIT_ITEM + m_iInfo : HIT_NONE;

	{
		int slot = WheelSlot( x, y );
		float dx = x - m_iWheelX, dy = y - m_iWheelY;

		if( slot >= 0 )
			return HIT_ITEM + slot;
		if( dx * dx + dy * dy < (float)m_iWheelR * m_iWheelR * 0.09f )
			return HIT_HUB;
	}

	return HIT_NONE;
}

/*
=================
input
=================
*/
void CCzmShop::Activate( int hit )
{
	if( Survival() )
	{
		ActivateSurvival( hit );
		return;
	}
	if( m_bServerMenu )
	{
		// the keys of the server's menu
		const char *text;
		int key = 0;

		if( hit == HIT_CLOSE )
		{
			CZM_PlayClick();
			CloseServerMenu( true );
			return;
		}
		if( hit >= HIT_QUICK && hit < HIT_QUICK + QuickCount( ))
			key = QuickKey( hit - HIT_QUICK, &text );
		else if( hit >= HIT_ITEM && hit < HIT_ITEM + m_iSlots )
			key = m_wmenu.keys[hit - HIT_ITEM];
		if( key && !Waiting( ))
		{
			CZM_PlayClick();
			m_iPickTime = uiStatic.realTime;
			if( key < 0 && m_wmenu.meta.valid )
			{
				int page = m_wmenu.meta.page + ( key == -1 ? -1 : 1 );
				page = ( page + m_wmenu.meta.pages ) % m_wmenu.meta.pages;
				EngFuncs::ClientCmdF( false, "czm_weapon_page %d\n", page );
			}
			else EngFuncs::ClientCmdF( false, "czm_shop_select %d %d\n", m_wmenu.serial, key );
		}
		return;
	}

	if( hit == HIT_CLOSE )
	{
		CZM_PlayClick();
		UI_CloseClientMenu();
		return;
	}

	if( hit >= HIT_TAB && hit < HIT_TAB + CAT_COUNT )
	{
		CZM_PlayClick();
		SelectCategory( hit - HIT_TAB );
		return;
	}

	if( hit >= HIT_QUICK && hit < HIT_QUICK + CZM_QUICK )
	{
		const char *label = CZM_IsRussian() ? s_quick[hit - HIT_QUICK].ru : s_quick[hit - HIT_QUICK].en;
		char text[96];

		CZM_PlayClick();
		EngFuncs::ClientCmdF( false, "%s\n", s_quick[hit - HIT_QUICK].command );
		snprintf( text, sizeof( text ), "%s", label );
		Toast( text );
		return;
	}

	if( hit >= HIT_ITEM && hit < HIT_ITEM + m_iSlots )
		Buy( *m_slots[hit - HIT_ITEM] );
}

bool CCzmShop::KeyDown( int key )
{
	if( UI::Key::IsEscape( key ))
	{
		if( m_bServerMenu )
			CloseServerMenu( true );
		else
			UI_CloseClientMenu();
		return true;
	}

	if( UI::Key::IsLeftMouse( key ))
	{
		Layout();
		m_iPressed = HitTest();

		// The slot under the finger is shown while moving around the wheel.
		if( !m_bGrid && m_iPressed >= HIT_ITEM && !m_info.HasCursor( ))
			m_iHover = m_iInfo = m_iPressed - HIT_ITEM;
		return true;
	}

	// keys 1..8 pick categories, like the old menu
	if( !m_bServerMenu && key >= '1' && key < '1' + CAT_COUNT )
	{
		SelectCategory( key - '1' );
		return true;
	}

	return true;
}

bool CCzmShop::KeyUp( int key )
{
	if( UI::Key::IsLeftMouse( key ))
	{
		int pressed = m_iPressed, hit;

		Layout();
		hit = HitTest();
		m_iPressed = HIT_NONE;
		m_iHover = -1;

		if( hit == pressed && hit != HIT_NONE )
			Activate( hit );
		return true;
	}

	return true;
}

bool CCzmShop::MouseMove( int x, int y )
{
	if( !m_bGrid && m_iPressed >= HIT_ITEM && !m_info.HasCursor( ))
	{
		int slot;

		Layout();
		slot = WheelSlot( uiStatic.cursorX, uiStatic.cursorY );
		m_iHover = slot;
		if( slot >= 0 )
		{
			m_iInfo = slot;
			m_iPressed = HIT_ITEM + slot; // slide to another slot and release there
		}
	}

	return true;
}

/*
=================
drawing
=================
*/
void CCzmShop::DrawTop( void )
{
	HFont titleFont = CZM_Font( CZMF_PANEL_TITLE );
	HFont teamFont = CZM_Font( CZMF_TILE_STATUS );
	HFont moneyFont = CZM_Font( CZMF_SHOP_MONEY );
	const char *team;
	char money[32];
	int x, tw, pillH, closeIcon;
	bool ru = CZM_IsRussian();
	if( Survival() )
	{
		DrawSurvivalTop();
		return;
	}

	UI_FillRect( m_top.x, m_top.y, m_top.w, m_top.h, PackRGBA( 10, 12, 16, 220 ));
	UI_FillRect( m_top.x, m_top.y + m_top.h - CZM_LineWidth(), m_top.w, CZM_LineWidth(), CZM_White( 25 ));

	x = W * 0.018f;
	if( m_bServerMenu )
	{
		const char *title = m_wmenu.meta.valid ? ( m_wmenu.meta.primary ? ( ru ? "ГЛАВНОЕ ОРУЖИЕ" : "PRIMARY WEAPON" ) :
			( ru ? "ПИСТОЛЕТЫ" : "PISTOLS" ) ) : m_wmenu.title;
		x = W * .05f;
		CZM_DrawText( titleFont, x, H * .025f, m_close.x - x - H * .03f, title, CZM_White());
		const char *subtitle = m_wmenu.meta.purchase ? ( m_wmenu.meta.primary
			? ( ru ? "ШАГ 1 ИЗ 4 · ОСНОВНОЕ ОРУЖИЕ" : "STEP 1 OF 4 · PRIMARY WEAPON" )
			: ( ru ? "ШАГ 2 ИЗ 4 · ПИСТОЛЕТ" : "STEP 2 OF 4 · PISTOL" ))
			: ( ru ? "ВЫБЕРИ СНАРЯЖЕНИЕ ДЛЯ БОЯ" : "CHOOSE YOUR LOADOUT" );
		CZM_DrawText( teamFont, x, H * .096f, W * .8f, subtitle, PackRGBA( 206, 160, 110, 255 ));
		if( m_wmenu.meta.valid )
		{
			char page[32]; snprintf( page, sizeof( page ), "%d / %d", m_wmenu.meta.page + 1, m_wmenu.meta.pages );
			CZM_DrawText( teamFont, m_close.x - H * .2f, H * .04f, H * .16f, page, PackRGBA( 255, 175, 85, 255 ), QM_RIGHT );
		}
		if( m_wmenu.meta.purchase )
		{
			FormatMoney( m_iMoney, money, sizeof( money ));
			CZM_DrawText( moneyFont, W * .52f, H * .081f, m_close.x - W * .53f, money, PackRGBA( 74, 222, 128, 255 ), QM_RIGHT );
		}
		closeIcon = m_close.h * .42f;
		CZM_DrawImage( SHOP_DIR "arsenal_button.png", m_close.x, m_close.y, m_close.w, m_close.h );
		CZM_DrawImage( UI_DIR "icon_close.png", m_close.x + ( m_close.w - closeIcon ) / 2, m_close.y + ( m_close.h - closeIcon ) / 2, closeIcon, closeIcon );
		return;
	}
	CZM_DrawText( titleFont, x, ( m_top.h - CZM_FontHeight( titleFont )) / 2, W * 0.3f, ru ? "МАГАЗИН" : "SHOP", CZM_White());
	x += CZM_TextWidth( titleFont, ru ? "МАГАЗИН" : "SHOP" ) + H * 0.025f;

	team = m_iTeam == TEAM_CT ? ( ru ? "СПЕЦНАЗ" : "COUNTER-TERRORISTS" ) : ( ru ? "ТЕРРОРИСТЫ" : "TERRORISTS" );
	tw = CZM_TextWidth( teamFont, team ) + H * 0.045f;
	pillH = H * 0.048f;
	CZM_DrawPill( UI_DIR "button_secondary.png", x, ( m_top.h - pillH ) / 2, tw, pillH,
		m_iTeam == TEAM_CT ? PackRGBA( 120, 170, 255, 255 ) : PackRGBA( 255, 140, 140, 255 ));
	CZM_DrawText( teamFont, x, ( m_top.h - CZM_FontHeight( teamFont )) / 2, tw, team,
		m_iTeam == TEAM_CT ? PackRGBA( 191, 219, 254, 255 ) : PackRGBA( 252, 165, 165, 255 ), QM_CENTER );

	FormatMoney( m_iMoney, money, sizeof( money ));
	CZM_DrawText( moneyFont, m_close.x - H * 0.03f - W * 0.3f, ( m_top.h - CZM_FontHeight( moneyFont )) / 2, W * 0.3f, money,
		PackRGBA( 74, 222, 128, 255 ), QM_RIGHT );

	closeIcon = m_close.h * 0.42f;
	CZM_DrawImage( UI_DIR "chip_round.png", m_close.x, m_close.y, m_close.w, m_close.h, IsPressed( HIT_CLOSE ) ? CZM_Grey() : CZM_White());
	CZM_DrawImage( UI_DIR "icon_close.png", m_close.x + ( m_close.w - closeIcon ) / 2, m_close.y + ( m_close.h - closeIcon ) / 2, closeIcon, closeIcon );
}

void CCzmShop::DrawTabs( void )
{
	HFont font = CZM_Font( CZMF_TILE_STATUS );
	int corner = H * 0.022f;

	for( int i = 0; i < CAT_COUNT; i++ )
	{
		const CzmRect &r = m_tabs[i];
		bool active = i == m_iCategory;
		int iconW = r.h * 0.95f, iconH = r.h * 0.5f, pad = r.h * 0.16f;

		CZM_DrawSliced( active ? UI_DIR "tab_on.png" : UI_DIR "card.png", r.x, r.y, r.w, r.h, 30, corner,
			IsPressed( HIT_TAB + i ) ? CZM_Grey() : CZM_White( active ? 255 : 230 ));
		DrawSilhouette( s_categories[i].image, r.x + pad, r.y + ( r.h - iconH ) / 2, iconW, iconH, CZM_White( active ? 255 : 200 ));
		CZM_DrawText( font, r.x + pad * 2 + iconW, r.y + ( r.h - CZM_FontHeight( font )) / 2, r.w - pad * 3 - iconW,
			CZM_IsRussian() ? s_categories[i].ru : s_categories[i].en, active ? CZM_White() : PackRGBA( 203, 210, 220, 255 ));
	}
}

void CCzmShop::DrawQuick( void )
{
	HFont font = CZM_Font( CZMF_TILE_STATUS );
	HFont small = CZM_Font( CZMF_SMALL );
	int corner = H * 0.02f;
	bool ru = CZM_IsRussian();

	if( m_bServerMenu )
	{
		for( int i = 0, count = QuickCount(); i < count; i++ )
		{
			const CzmRect &r = m_quick[i];
			const char *text;
			bool toggle = QuickKey( i, &text ) == m_wmenu.toggleKey && m_wmenu.toggleKey;
			bool on = toggle && m_wmenu.toggleOn;
			int pad = r.h * 0.28f;

			CZM_DrawImage( on || !toggle ? SHOP_DIR "arsenal_button_on.png" : SHOP_DIR "arsenal_button.png", r.x, r.y, r.w, r.h,
				IsPressed( HIT_QUICK + i ) ? CZM_Grey() : CZM_White());
			if( toggle )
			{
				// a switch: the knob right when on
				int sw = r.h * 0.84f, sh = r.h * 0.46f, sx = r.x + r.w - pad - sw, sy = r.y + ( r.h - sh ) / 2;
				int knob = sh - sh / 4;
				CZM_DrawPill( UI_DIR "button_secondary.png", sx, sy, sw, sh, on ? PackRGBA( 255, 255, 255, 120 ) : CZM_White());
				CZM_DrawImage( UI_DIR "dot.png", on ? sx + sw - knob - sh / 8 : sx + sh / 8, sy + sh / 8, knob, knob, CZM_White());
				CZM_DrawText( font, r.x + pad, r.y + ( r.h - CZM_FontHeight( font )) / 2, r.w - pad * 3 - sw, text, CZM_White());
			}
			else
				CZM_DrawText( font, r.x + pad, r.y + ( r.h - CZM_FontHeight( font )) / 2, r.w - pad * 2, text, CZM_White(), QM_CENTER );
		}
		return;
	}

	for( int i = 0; i < CZM_QUICK; i++ )
	{
		const CzmRect &r = m_quick[i];
		int pad = r.h * 0.28f;
		int textH = CZM_FontHeight( font ) + CZM_FontHeight( small ) + H * 0.004f;
		int y = r.y + ( r.h - textH ) / 2;

		CZM_DrawSliced( i == 0 ? UI_DIR "tab_on.png" : UI_DIR "card.png", r.x, r.y, r.w, r.h, 30, corner,
			IsPressed( HIT_QUICK + i ) ? CZM_Grey() : CZM_White());
		CZM_DrawText( font, r.x + pad, y, r.w - pad * 2, ru ? s_quick[i].ru : s_quick[i].en, CZM_White());
		CZM_DrawText( small, r.x + pad, y + CZM_FontHeight( font ) + H * 0.004f, r.w - pad * 2, ru ? s_quick[i].ru2 : s_quick[i].en2,
			i == 0 ? PackRGBA( 254, 226, 226, 255 ) : PackRGBA( 74, 222, 128, 255 ));
	}
}

void CCzmShop::DrawWheel( void )
{
	HFont nameFont = CZM_Font( CZMF_SHOP_NAME );
	HFont priceFont = CZM_Font( CZMF_SHOP_PRICE );
	HFont hubFont = CZM_Font( CZMF_TILE_STATUS );
	char path[64], money[32];
	int n = m_iSlots, size, selected;

	if( n <= 0 )
		return;

	// the images are 640 pixels for a wheel of radius 300
	size = m_iWheelR * 640 / 300;
	snprintf( path, sizeof( path ), SHOP_DIR "wheel%d.png", n );
	CZM_DrawImage( path, m_iWheelX - size / 2, m_iWheelY - size / 2, size, size );

	selected = m_iHover >= 0 ? m_iHover : m_iInfo;
	if( selected >= 0 && selected < n )
	{
		snprintf( path, sizeof( path ), SHOP_DIR "wheel%d_%d.png", n, selected );
		CZM_DrawImage( path, m_iWheelX - size / 2, m_iWheelY - size / 2, size, size );
	}

	for( int i = 0; i < n; i++ )
	{
		const CzmShopItem &item = *m_slots[i];
		const int price = Price( i );
		bool afford = !ShowPrice() || price <= m_iMoney;
		float angle = ( -90.0f + i * 360.0f / n ) * M_PI / 180.0f;
		float radius = n == 1 ? 0.0f : m_iWheelR * 0.64f;
		int cx = m_iWheelX + cosf( angle ) * radius;
		int cy = m_iWheelY + sinf( angle ) * radius;
		// silhouettes of neighbouring slots must not touch
		int boxW = n <= 2 ? m_iWheelR * 0.62f : Q_min( (int)( m_iWheelR * 0.62f ), (int)( m_iWheelR * 1.25f * sinf( M_PI / n )));
		int textW = Q_max( boxW * 13 / 10, (int)( m_iWheelR * 0.5f ));
		int imgH = m_iWheelR * 0.19f;
		int nameH = CZM_FontHeight( nameFont ), priceH = ShowPrice() ? CZM_FontHeight( priceFont ) : 0;
		int top = cy - ( imgH + nameH + priceH + H * 0.012f ) / 2;

		if( n == 1 )
			top = m_iWheelY - m_iWheelR * 0.72f;

		DrawWeapon( item, cx - boxW / 2, top, boxW, imgH, CZM_White( afford ? 255 : 100 ));
		CZM_DrawText( nameFont, cx - textW / 2, top + imgH + H * 0.008f, textW, ItemName( item ), CZM_White( afford ? 255 : 110 ), QM_CENTER );
		if( ShowPrice() )
		{
			FormatMoney( price, money, sizeof( money ));
			CZM_DrawText( priceFont, cx - textW / 2, top + imgH + H * 0.012f + nameH, textW, money,
				afford ? PackRGBA( 74, 222, 128, 255 ) : PackRGBA( 248, 113, 113, 255 ), QM_CENTER );
		}

		if( Owned( item ) || ( RoundShop() && item.weapon == SelectedWeapon() ))
		{
			int d = H * 0.032f;
			CZM_DrawImage( UI_DIR "dot.png", cx + boxW / 2 - d, top - d / 3, d, d, PackRGBA( 255, 255, 255, 255 ));
			CZM_DrawImage( UI_DIR "icon_check.png", cx + boxW / 2 - d + d / 5, top - d / 3 + d / 5, d * 3 / 5, d * 3 / 5, PackRGBA( 185, 28, 28, 255 ));
		}
	}

	// the hub tells the category
	{
		const char *label = CZM_IsRussian() ? s_categories[m_iCategory].ru : s_categories[m_iCategory].en;
		int hub = m_iWheelR * 80 / 300;
		if( m_bServerMenu )
			label = CZM_IsRussian() ? "Оружие" : "Weapons";
		CZM_DrawText( hubFont, m_iWheelX - hub, m_iWheelY - CZM_FontHeight( hubFont ) / 2, hub * 2, label, CZM_White(), QM_CENTER );
	}
}

bool CCzmShop::DrawPlayerSkin( const CzmRect &rect )
{
	char path[128];
	if( !CzmPlayerModel::Path( EngFuncs::GetCvarString( "czm_player_model" ), path, sizeof( path ))
		|| !EngFuncs::FileExists( path ))
		return false;

	if( strcmp( path, m_szSkinPath ) || rect.x != m_skinRect.x || rect.y != m_skinRect.y
		|| rect.w != m_skinRect.w || rect.h != m_skinRect.h || !m_skinView.ent )
	{
		m_skinView.iFlags |= QMF_DISABLESCAILING | QMF_INACTIVE;
		m_skinView.m_bCanCaptureFocus = false;
		m_skinView.eOverrideMode = CMenuPlayerModelView::PMV_SHOWMODEL;
		m_skinView.SetRect( rect.x, rect.y, rect.w, rect.h );
		m_skinView.VidInit();
		m_skinView.backgroundColor.SetDefault( 0 );
		m_skinView.colorStroke.SetDefault( 0 );
		m_skinView.iStrokeWidth = 0;
		if( !m_skinView.ent )
			return false;
		EngFuncs::SetModel( m_skinView.ent, path );
		Q_strncpy( m_szSkinPath, path, sizeof( m_szSkinPath ));
		m_skinRect = rect;
	}
	if( !m_skinView.ent->model )
		return false;
	m_skinView.Draw();
	return true;
}

void CCzmShop::DrawInfo( const CzmShopItem *item )
{
	HFont bigFont = CZM_Font( CZMF_SHOP_BIG );
	HFont priceFont = CZM_Font( CZMF_SHOP_CARD_PRICE );
	HFont textFont = CZM_Font( CZMF_PANEL_TEXT );
	HFont valueFont = CZM_Font( CZMF_TILE_STATUS );
	HFont buyFont = CZM_Font( CZMF_SHOP_CARD );
	int pad = H * 0.04f, x, y, w;
	char money[32];
	bool ru = CZM_IsRussian();

	CZM_DrawPanel( m_info );
	if( !item )
		return;

	x = m_info.x + pad;
	w = m_info.w - pad * 2;
	y = m_info.y + pad * 0.8f;

	CZM_DrawText( bigFont, x, y, m_bServerMenu ? w : w * 0.62f, ItemName( *item ), CZM_White());
	if( !m_bServerMenu )
	{
		FormatMoney( item->price, money, sizeof( money ));
		CZM_DrawText( priceFont, x, y + ( CZM_FontHeight( bigFont ) - CZM_FontHeight( priceFont )) / 2, w, money,
			item->price <= m_iMoney ? PackRGBA( 74, 222, 128, 255 ) : PackRGBA( 248, 113, 113, 255 ), QM_RIGHT );
	}
	y += CZM_FontHeight( bigFont ) + H * 0.02f;

	const int skinW = w * 0.30f, skinGap = H * 0.018f;
	CzmRect skin = CZM_Rect( x + w - skinW, y, skinW, H * ( Survival() ? .20f : .31f ));
	if( DrawPlayerSkin( skin ))
	{
		CZM_DrawText( CZM_Font( CZMF_UI_META ), skin.x, skin.y + skin.h + H * 0.008f, skin.w,
			ru ? "Ваш скин" : "Your skin", PackRGBA( 155, 166, 184, 255 ), QM_CENTER );
		w -= skinW + skinGap;
		textFont = CZM_Font( CZMF_UI_META );
	}

	DrawWeapon( *item, x + w * 0.08f, y, w * 0.84f, H * ( Survival() ? .105f : .15f ), CZM_White());
	y += H * ( Survival() ? .115f : .17f );

	if( item->clip )
	{
		// bars: damage, magazine, speed
		struct { const char *label; float t; char value[32]; } rows[3];

		rows[0].label = ru ? "Урон" : "Damage";
		rows[0].t = item->damage * item->pellets / 180.0f;
		if( item->pellets > 1 )
			snprintf( rows[0].value, sizeof( rows[0].value ), "%d × %d", item->damage, item->pellets );
		else
			snprintf( rows[0].value, sizeof( rows[0].value ), "%d", item->damage );
		rows[1].label = ru ? "Патроны" : "Ammo";
		rows[1].t = item->clip / 100.0f;
		snprintf( rows[1].value, sizeof( rows[1].value ), "%d / %d", item->clip, item->ammo );
		rows[2].label = ru ? "Подвижность" : "Mobility";
		rows[2].t = ( item->speed - 180.0f ) / 80.0f;
		snprintf( rows[2].value, sizeof( rows[2].value ), "%d", item->speed );

		for( int i = 0; i < 3; i++ )
		{
			int labelW = w * 0.34f, valueW = w * 0.22f;
			int barX = x + labelW, barW = w - labelW - valueW - H * 0.02f;
			int barH = Q_max( 4, (int)( H * 0.012f ));
			int rowH = H * ( Survival() ? .036f : .05f );
			int cy = y + rowH / 2;

			CZM_DrawText( textFont, x, cy - CZM_FontHeight( textFont ) / 2, labelW, rows[i].label, PackRGBA( 203, 210, 220, 255 ));
			UI_FillRect( barX, cy - barH / 2, barW, barH, CZM_White( 30 ));
			UI_FillRect( barX, cy - barH / 2, (int)( barW * bound( 0.05f, rows[i].t, 1.0f )), barH, PackRGBA( 239, 68, 68, 255 ));
			CZM_DrawText( valueFont, x + w - valueW, cy - CZM_FontHeight( valueFont ) / 2, valueW, rows[i].value, CZM_White(), QM_RIGHT );
			y += rowH;
		}
	}
	else
	{
		const char *text;

		if( !strcmp( item->command, "vest" )) text = ru ? "Броня 100. Держит пули в корпус." : "Armor 100, stops body shots.";
		else if( !strcmp( item->command, "vesthelm" )) text = ru ? "Броня 100 и шлем: защищает и голову." : "Armor 100 and a helmet for the head.";
		else if( !strcmp( item->command, "flash" )) text = ru ? "Ослепляет. Можно взять две." : "Blinds. You can carry two.";
		else if( !strcmp( item->command, "hegren" )) text = ru ? "Взрыв: урон всем рядом." : "Explodes, damages everyone near.";
		else if( !strcmp( item->command, "sgren" )) text = ru ? "Дымовая завеса закрывает обзор." : "A smoke screen blocks the view.";
		else if( !strcmp( item->command, "defuser" )) text = ru ? "Разминирует бомбу вдвое быстрее." : "Defuses the bomb twice as fast.";
		else if( !strcmp( item->command, "nvgs" )) text = ru ? "Видно в темноте." : "See in the dark.";
		else text = ru ? "Защищает спереди, только пистолет." : "Covers your front, pistol only.";

		CZM_DrawText( textFont, x, y + H * 0.02f, w, text, PackRGBA( 203, 210, 220, 255 ));
	}

	// the buy button
	CZM_DrawSliced( UI_DIR "tab_on.png", m_buy.x, m_buy.y, m_buy.w, m_buy.h, 30, (int)( H * 0.02f ),
		RoundShop() ? ( RowEnabled( m_iInfo ) && !IsPressed( HIT_SELECT ) ? CZM_White() : CZM_Grey() ) :
		IsPressed( HIT_ITEM + m_iInfo ) && m_info.HasCursor() ? CZM_Grey() : CZM_White());
	const char *label = ru ? "КУПИТЬ" : "BUY";
	char action[80];
	if( Survival() )
	{
		if( RowEnabled( m_iInfo ))
			label = m_wmenu.shop.equipmentSelection && item->weapon == SelectedWeapon() ?
				( ru ? "СНЯТЬ ВЫБОР" : "REMOVE SELECTION" ) : ( ru ? "ВЫБРАТЬ" : "SELECT" );
		else if( item->weapon == SelectedWeapon() ) label = ru ? "В КОМПЛЕКТЕ" : "IN LOADOUT";
		else label = ru ? "ПРОСМОТР" : "PREVIEW";
	}
	else if( m_bServerMenu && m_wmenu.meta.purchase )
	{
		FormatMoney( m_wmenu.meta.price, money, sizeof( money ));
		snprintf( action, sizeof( action ), "%s · %s", label, money );
		label = action;
	}
	else if( m_bServerMenu )
		label = m_wmenu.meta.queued ? ( ru ? "НА СЛЕДУЮЩИЙ РАУНД" : "FOR NEXT ROUND" ) : ( ru ? "ВЗЯТЬ" : "TAKE" );
	else if( Owned( *item ))
		label = ru ? "КУПИТЬ ЕЩЁ" : "BUY AGAIN";
	CZM_DrawText( buyFont, m_buy.x, m_buy.y + ( m_buy.h - CZM_FontHeight( buyFont )) / 2, m_buy.w, label, CZM_White(), QM_CENTER );
}

void CCzmShop::DrawGrid( void )
{
	HFont nameFont = CZM_Font( CZMF_SHOP_CARD );
	HFont priceFont = CZM_Font( CZMF_SHOP_CARD_PRICE );
	int mode = bound( 0, (int)EngFuncs::GetCvarFloat( "czm_shop_anim" ), 2 );
	int age = uiStatic.realTime - m_iOpenTime;
	for( int i = 0; i < m_iSlots; i++ )
	{
		const CzmShopItem &item = *m_slots[i];
		CzmRect r = m_cards[i];
		const int price = Price( i );
		bool afford = !ShowPrice() || price <= m_iMoney;
		bool selected = m_bServerMenu && ( m_wmenu.meta.valid || Survival() ) ? item.weapon == SelectedWeapon() : Owned( item );
		bool active = IsPressed( HIT_ITEM + i ) || ( RoundShop() ? m_iInfo == i : r.HasCursor() );
		float t = mode ? bound( 0.0f, ( age - i * 14 ) / 180.0f, 1.0f ) : 1;
		t = 1 - ( 1 - t ) * ( 1 - t );
		int alpha = mode == 1 ? (int)( 255 * t ) : 255;
		int slide = mode == 2 ? (int)( H * .035f * ( 1 - t )) : 0;
		int pad = r.h * .09f;
		int textY = r.y + r.h - pad - CZM_FontHeight( nameFont );
		CZM_DrawImage( selected || active ? SHOP_DIR "arsenal_selected.png" : SHOP_DIR "arsenal_card.png", r.x, r.y, r.w, r.h, CZM_White( alpha ));
		DrawWeapon( item, r.x + r.w * .055f, r.y + pad * .8f + slide, r.w * .89f, textY - r.y - pad - slide, CZM_White( afford ? alpha : alpha * .4f ));
		CZM_DrawText( nameFont, r.x + pad * 2.5f, textY, r.w - pad * 3.5f, ItemName( item ), CZM_White( alpha ));
		if( ShowPrice() )
		{
			char money[32]; FormatMoney( price, money, sizeof( money ));
			CZM_DrawText( priceFont, r.x + pad, r.y + pad, r.w - pad * 2, money,
				afford ? PackRGBA( 255, 179, 93, alpha ) : PackRGBA( 248, 113, 113, alpha ), QM_RIGHT );
		}
		if( selected )
		{
			int d = H * .034f;
			CZM_DrawImage( UI_DIR "icon_check.png", r.x + r.w - pad - d, r.y + pad, d, d, PackRGBA( 255, 177, 63, alpha ));
		}
	}
}

void CCzmShop::Draw()
{
	ReadState();

	// dead, spectating or out of the game: the shop is not for now
	if( m_bClosing || ( !m_bAlive && !m_bServerMenu ) || !CL_IsActive( ))
	{
		Hide();
		return;
	}

	Layout();

	CZM_DrawCover( CZM_Image( "gfx/czm/loading_3.png" ), 0, 0, W, H );
	UI_FillRect( 0, 0, W, H, PackRGBA( 6, 8, 12, 180 ));
	DrawTop();
	if( !m_bServerMenu )
		DrawTabs();

	if( Gear() )
		DrawSurvivalGear();
	else if( m_bGrid )
	{
		DrawGrid();
		if( RoundShop() ) DrawInfo( m_iInfo >= 0 && m_iInfo < m_iSlots ? m_slots[m_iInfo] : NULL );
	}
	else
	{
		DrawWheel();
		DrawInfo( m_iInfo >= 0 && m_iInfo < m_iSlots ? m_slots[m_iInfo] : NULL );
	}

	if( Survival() )
		DrawSurvivalFooter();
	else
		DrawQuick();
	if( m_bServerMenu && m_wmenu.meta.valid )
	{
		const bool ru = CZM_IsRussian();
		const char *hint = m_wmenu.meta.queued ? ( ru ? "Выдача со следующего раунда" : "Issued from the next round" ) :
			( ru ? "Одна закупка за матч · Нажми на оружие" : "One purchase per match · Tap a weapon" );
		if( m_wmenu.meta.purchase )
		{
			switch( m_wmenu.meta.notice )
			{
			case 1: hint = ru ? "Не хватает кредитов" : "Not enough credits"; break;
			case 2: hint = ru ? "Сохрани профиль в разделе «Мой прогресс»" : "Save your profile under My progress"; break;
			case 3: hint = ru ? "Оружие уже куплено на этот матч" : "Weapon already bought for this match"; break;
			case 4: hint = ru ? "Не удалось сохранить покупку" : "The purchase could not be saved"; break;
			}
		}
		CZM_DrawText( CZM_Font( CZMF_UI_META ), W * .05f, H * .824f, W * .9f, hint, PackRGBA( 205, 184, 161, 255 ));
	}

	if( m_szToast[0] && uiStatic.realTime - m_iToastTime < 1800 )
	{
		HFont font = CZM_Font( CZMF_TILE_STATUS );
		int tw = CZM_TextWidth( font, m_szToast ) + H * 0.08f;
		CzmRect r = CZM_Rect(( W - tw ) / 2, ( m_top.h - H * 0.065f ) / 2, tw, H * 0.065f );

		CZM_DrawPill( UI_DIR "button_secondary.png", r.x, r.y, r.w, r.h );
		CZM_DrawText( font, r.x, r.y + ( r.h - CZM_FontHeight( font )) / 2, r.w, m_szToast, CZM_White(), QM_CENTER );
	}
}

void CCzmShop::LayoutSurvival()
{
	const bool grid = Gear() || EngFuncs::GetCvarFloat( "czm_shop" ) == 2.0f;
	if( grid != m_bGrid )
	{
		m_bGrid = grid;
		m_iPressed = HIT_NONE;
		m_iHover = -1;
	}

	const auto &shop = m_wmenu.shop;
	const int x = W * .035f, gap = H * .014f, width = W - 2 * x;
	const bool round = RoundShop();
	const int y = H * .216f, end = H * ( round ? .695f : .731f );
	const CzmRect empty = CZM_Rect( 0, 0, 0, 0 );
	m_top = CZM_Rect( 0, 0, W, H * .198f );
	m_close = CZM_Rect( W - x - H * .069f, H * .016f, H * .069f, H * .069f );
	for( auto &tab : m_tabs ) tab = empty;
	const int tabW = ( width - 2 * gap ) / 3;
	for( int i = 0; i < 3; ++i )
		m_tabs[i] = CZM_Rect( x + i * ( tabW + gap ), H * .104f, tabW, H * .077f );

	const int by = H * .886f, bh = H * .085f;
	m_quick[0] = CZM_Rect( x, by, width * .30f, bh );
	m_quick[1] = shop.page > 0 ? CZM_Rect( x + width * .324f, by, width * .05f, bh ) : empty;
	m_quick[2] = shop.page + 1 < shop.pages ? CZM_Rect( x + width * .385f, by, width * .05f, bh ) : empty;
	m_quick[3] = Gear() ? empty : CZM_Rect( x + width * .45f, by, width * .187f, bh );
	m_quick[4] = CZM_Rect( x + width * .658f, by, width * .342f, bh );
	m_cancel = empty;
	if( round )
	{
		m_quick[0].w = width * .258f;
		if( m_quick[1].w ) m_quick[1].x = x + width * .271f;
		if( m_quick[2].w ) m_quick[2].x = x + width * .329f;
		if( m_quick[3].w ) m_quick[3] = CZM_Rect( x + width * .39f, by, width * .117f, bh );
		if( shop.status == CzmSurvivalShop::Pending ) m_cancel = CZM_Rect( x + width * .516f, by, width * .145f, bh );
		m_quick[4] = CZM_Rect( x + width * .671f, by, width * .329f, bh );
	}

	if( !Gear() && ( round || !m_bGrid ))
	{
		const int infoW = Q_min( (int)( width * .49f ), (int)( H * .86f ));
		m_info = CZM_Rect( W - x - infoW, y, infoW, end - y );
		m_buy = CZM_Rect( m_info.x + gap, end - H * .092f, infoW - 2 * gap, H * .077f );
	}

	if( Gear() )
	{
		const int top = y + H * .050f, left = width * .57f, h = ( end - top - 2 * gap ) / 3;
		for( int i = 0; i < 3; ++i )
			m_cards[i] = CZM_Rect( x, top + i * ( h + gap ), left, h );
		m_cards[3] = CZM_Rect( x + left + gap, top, width - left - gap, end - top );
	}
	else if( m_bGrid )
	{
		const int gridW = round ? m_info.x - x - gap : width;
		const int columns = round && gridW < H * .95f ? 2 : 3;
		const int rows = Q_max( 1, ( m_iSlots + columns - 1 ) / columns );
		const int cardW = ( gridW - gap * ( columns - 1 )) / columns;
		const int cardH = ( end - y - gap * ( rows - 1 )) / rows;
		for( int i = 0; i < m_iSlots; ++i )
		{
			const int row = i / columns, cells = Q_min( columns, m_iSlots - row * columns );
			const int offset = ( gridW - cells * cardW - ( cells - 1 ) * gap ) / 2;
			m_cards[i] = CZM_Rect( x + offset + ( i % columns ) * ( cardW + gap ), y + row * ( cardH + gap ), cardW, cardH );
		}
	}
	else
	{
		m_iWheelX = ( x + m_info.x ) / 2;
		m_iWheelY = ( y + end ) / 2;
		m_iWheelR = Q_min( (int)( H * ( round ? .222f : .237f )), ( m_info.x - x - 2 * gap ) / 2 );
	}
}

static void DrawSurvivalButton( const CzmRect &r, const char *label, bool accent, bool enabled, bool pressed, bool primary = false )
{
	const HFont font = CZM_Font( CZMF_UI_LABEL );
	unsigned tint = accent ? PackRGBA( 220, 58, 54, 255 ) : PackRGBA( 57, 64, 76, 255 );
	if( !enabled ) tint = PackRGBA( 43, 47, 54, 235 );
	else if( pressed ) tint = accent ? PackRGBA( 166, 45, 39, 255 ) : PackRGBA( 83, 94, 110, 255 );
	if( primary && enabled ) tint = pressed ? CZM_Grey() : CZM_White();
	CZM_DrawSliced( primary && enabled ? UI_DIR "tab_on.png" : UI_DIR "button_secondary.png",
		r.x, r.y, r.w, r.h, 24, Q_max( 4, r.h / 6 ), tint );
	CZM_DrawText( font, r.x + r.h / 7, r.y + ( r.h - CZM_FontHeight( font )) / 2, r.w - r.h * 2 / 7,
		label, enabled ? CZM_White() : PackRGBA( 150, 158, 170, 255 ), QM_CENTER );
}

void CCzmShop::DrawSurvivalTop()
{
	const bool ru = CZM_IsRussian();
	const HFont title = CZM_Font( CZMF_PANEL_TITLE );
	const HFont money = CZM_Font( CZMF_SHOP_MONEY );
	char balance[32];
	FormatMoney( m_iMoney, balance, sizeof( balance ));
	UI_FillRect( m_top.x, m_top.y, m_top.w, m_top.h, PackRGBA( 10, 14, 20, 241 ));
	CZM_DrawText( title, m_tabs[0].x, H * .022f, W * .6f, ru ? "МАГАЗИН" : "SHOP", CZM_White() );
	CZM_DrawText( money, W * .64f, H * .035f, m_close.x - W * .66f, balance, PackRGBA( 100, 223, 160, 255 ), QM_RIGHT );
	DrawSurvivalButton( m_close, "×", false, true, IsPressed( HIT_CLOSE ));
	const char *labels[] = { ru ? "Основное оружие" : "Primary weapon", ru ? "Пистолеты" : "Pistols",
		ru ? "Снаряжение" : "Equipment" };
	for( int i = 0; i < 3; ++i )
		DrawSurvivalButton( m_tabs[i], labels[i], i == m_wmenu.shop.tab, true, IsPressed( HIT_TAB + i ));
}

static void FormatShopLoadout( char *out, size_t size, int primary, int pistol, int gear, bool legacy, bool ru )
{
	const CzmShopItem *a = primary ? ShopWeapon( primary ) : NULL;
	const CzmShopItem *b = pistol ? ShopWeapon( pistol ) : NULL;
	const char *empty = legacy ? ( ru ? "Штатное" : "Starter" ) : "—";
	int len = snprintf( out, size, "%s + %s", a ? ItemName( *a ) : empty, b ? ItemName( *b ) : empty );
	if( gear && len >= 0 && (size_t)len < size )
	{
		int count = 0;
		for( int i = 0; i < 4; i++ )
			if( gear & ( 1 << i )) ++count;
		snprintf( out + len, size - len, ru ? " + %d снаряж." : " + %d gear", count );
	}
}

void CCzmShop::DrawSurvivalFooter()
{
	using namespace CzmSurvivalShop;
	const bool ru = CZM_IsRussian();
	const auto &shop = m_wmenu.shop;
	const int x = m_tabs[0].x, width = W - 2 * x;
	const HFont title = CZM_Font( CZMF_UI_LABEL );
	const HFont noteFont = CZM_Font( CZMF_UI_META );
	char summary[96];
	FormatShopLoadout( summary, sizeof( summary ), shop.primary, shop.pistol, shop.equipment, !shop.equipmentSelection, ru );
	const bool round = RoundShop(), pending = shop.status == Pending, ready = ( shop.flags & CanConfirm ) != 0;
	const char *status = ru ? "Комплект оружия" : "Weapon loadout";
	const char *hint = ru ? "Купленное оружие выдаётся со следующего раунда" : "Purchased weapons are issued from the next round";
	char timer[96];
	if( round )
	{
		const int left = Q_max( 0, shop.windowMs - ( uiStatic.realTime - m_iPacketTime ));
		if( pending ) hint = ru ? "Заказ можно заменить или отменить до выдачи" : "You can replace or cancel your order before delivery";
		else if( shop.mode == BuyNow && left > 0 )
		{
			snprintf( timer, sizeof( timer ), ru ? "Закупка без лимита · %d с" : "Unlimited purchases · %d s", ( left + 999 ) / 1000 );
			hint = timer;
		}
		else if( shop.mode == BuyNow ) hint = ru ? "Доступна одна покупка с выдачей сразу" : "One purchase can be equipped now";
		else if( shop.mode == BuyNext ) hint = ru ? "Следующая покупка будет выдана в новом раунде" : "Your next purchase will be delivered next round";
		else hint = ru ? "Покупка сейчас доступна за живого человека" : "You can buy now while alive as a human";
	}
	else if( pending )
	{
		status = ru ? "Ожидает следующего раунда" : "Waiting for the next round";
		hint = ru ? "До начала раунда покупку можно отменить" : "Cancel before the round starts for a full refund";
	}
	else if( shop.status == Purchased )
	{
		status = ru ? "Куплено на эту карту" : "Purchased for this map";
		hint = ru ? "Купленное оружие отмечено галочкой" : "Your purchased weapons are marked";
	}
	if( shop.status == Guest )
		hint = ru ? "Войди в профиль, чтобы купить оружие" : "Sign in to buy weapons";
	const char *noticesRu[] = { "", "Не хватает кредитов", "Войди в профиль, чтобы купить оружие", "Покупка сейчас недоступна",
		"Не удалось выполнить действие", "Цена или раунд изменились. Проверь комплект", "Покупка отменена. Кредиты возвращены",
		"Снаряжение выдано", "Уже получено в этой жизни", "Комплект выдан", "Заказ на следующий раунд оплачен", "Заказ заменён", "Заказ отменён" };
	const char *noticesEn[] = { "", "Not enough credits", "Sign in to buy weapons", "Purchase unavailable right now",
		"Could not complete the action", "The price or round changed. Check the loadout", "Purchase cancelled. Credits returned",
		"Equipment received", "Already received this life", "Loadout equipped", "Next round's order paid", "Order replaced", "Order cancelled" };
	if( shop.notice ) hint = ( ru ? noticesRu : noticesEn )[shop.notice];

	const int top = H * ( round ? .710f : .750f );
	UI_FillRect( 0, top, W, H - top, PackRGBA( 10, 14, 20, 249 ));
	UI_FillRect( x, top, width, CZM_LineWidth(), PackRGBA( 255, 177, 83, 135 ));
	if( round )
	{
		char pair[96], line[144];
		FormatShopLoadout( pair, sizeof( pair ), shop.currentPrimary, shop.currentPistol, shop.currentEquipment, !shop.equipmentSelection, ru );
		snprintf( line, sizeof( line ), ru ? "Этот раунд · %s" : "This round · %s",
			shop.currentPrimary || shop.currentPistol || shop.currentEquipment ? pair : ( ru ? "нет покупки" : "no purchase" ));
		CZM_DrawText( noteFont, x, H * .726f, width * .49f, line, CZM_White() );
		FormatShopLoadout( pair, sizeof( pair ), shop.nextPrimary, shop.nextPistol, shop.nextEquipment, !shop.equipmentSelection, ru );
		snprintf( line, sizeof( line ), ru ? "Следующий · %s" : "Next round · %s", pending ? pair : ( ru ? "нет заказа" : "no order" ));
		CZM_DrawText( noteFont, x + width * .51f, H * .726f, width * .49f, line, PackRGBA( 245, 180, 99, 255 ));
		snprintf( line, sizeof( line ), ru ? "Выбрано · %s" : "Selected · %s", shop.primary || shop.pistol || shop.equipment ? summary : "—" );
		CZM_DrawText( title, x, H * .776f, width, line, CZM_White() );
	}
	else
	{
		CZM_DrawText( title, x, H * .764f, width * .53f, summary, CZM_White() );
		CZM_DrawText( noteFont, x + width * .535f, H * .771f, width * .465f, status, PackRGBA( 245, 180, 99, 255 ), QM_RIGHT );
	}
	CZM_DrawText( noteFont, x, H * .827f, width, hint, PackRGBA( 196, 207, 222, 255 ));

	const CzmRect &remember = m_quick[0];
	const bool canRemember = ( shop.flags & CanRemember ) != 0;
	const HFont small = CZM_Font( CZMF_UI_META );
	const unsigned track = shop.remember ? PackRGBA( 231, 67, 58, 255 ) : PackRGBA( 84, 92, 108, 255 );
	const int sh = remember.h * .37f, sw = sh * 17 / 10;
	const int sx = remember.x + remember.w - sw - remember.h / 6, sy = remember.y + ( remember.h - sh ) / 2;
	CZM_DrawSliced( UI_DIR "button_secondary.png", remember.x, remember.y, remember.w, remember.h, 24, 6, PackRGBA( 44, 53, 68, 245 ));
	CZM_DrawPill( UI_DIR "button_secondary.png", sx, sy, sw, sh, track );
	CZM_DrawImage( UI_DIR "dot.png", sx + ( shop.remember ? sw - sh : 0 ), sy, sh, sh, CZM_White( canRemember ? 255 : 110 ));
	CZM_DrawText( small, remember.x + remember.h / 7, remember.y + ( remember.h - CZM_FontHeight( small )) / 2,
		sx - remember.x - remember.h / 5, ru ? "Запомнить комплект" : "Remember loadout", CZM_White( canRemember ? 255 : 110 ));

	if( m_quick[1].w ) DrawSurvivalButton( m_quick[1], "‹", false, true, IsPressed( HIT_QUICK + 1 ));
	if( m_quick[2].w ) DrawSurvivalButton( m_quick[2], "›", false, true, IsPressed( HIT_QUICK + 2 ));
	if( m_quick[3].w )
	{
		const bool advance = shop.equipmentSelection || ( !round && ( pending || ( shop.locked & ( 1 << shop.tab ))));
		DrawSurvivalButton( m_quick[3], advance ? ( ru ? "Далее" : "Next" ) : ( ru ? "Пропустить" : "Skip" ),
			false, true, IsPressed( HIT_QUICK + 3 ));
	}

	char action[96], price[32];
	FormatMoney( shop.total, price, sizeof( price ));
	if( shop.equipmentSelection )
	{
		if( m_cancel.w ) DrawSurvivalButton( m_cancel, ru ? "Отменить" : "Cancel", false, true, IsPressed( HIT_CANCEL ));
		const char *confirm = ru ? "Подтвердить" : "Confirm";
		const int delta = shop.total - shop.reserved;
		Q_strncpy( action, confirm, sizeof( action ));
		if( ready && delta != 0 )
		{
			FormatMoney( delta < 0 ? -delta : delta, price, sizeof( price ));
			snprintf( action, sizeof( action ), "%s · %s%s", confirm, delta < 0 ? "+" : "", price );
			if( CZM_TextWidth( title, action ) > m_quick[4].w - m_quick[4].h * 2 / 7 )
				Q_strncpy( action, confirm, sizeof( action ));
		}
	}
	else if( round )
	{
		if( m_cancel.w ) DrawSurvivalButton( m_cancel, ru ? "Отменить" : "Cancel", false, true, IsPressed( HIT_CANCEL ));
		if( !ready ) Q_strncpy( action, pending ? ( ru ? "Заказ оплачен" : "Order paid" ) :
			( ru ? "Выбери оружие" : "Select weapons" ), sizeof( action ));
		else if( pending )
		{
			const int delta = shop.total - shop.reserved;
			if( delta > 0 ) snprintf( action, sizeof( action ), ru ? "Заменить · доплата $%d" : "Replace · pay $%d", delta );
			else if( delta < 0 ) snprintf( action, sizeof( action ), ru ? "Заменить · возврат $%d" : "Replace · refund $%d", -delta );
			else Q_strncpy( action, ru ? "Заменить заказ" : "Replace order", sizeof( action ));
		}
		else if( shop.mode == BuyNow ) snprintf( action, sizeof( action ), ru ? "Купить сейчас · %s" : "Buy now · %s", price );
		else
		{
			snprintf( action, sizeof( action ), ru ? "Купить на следующий раунд · %s" : "Buy for next round · %s", price );
			if( CZM_TextWidth( title, action ) > m_quick[4].w - m_quick[4].h * 2 / 7 )
				snprintf( action, sizeof( action ), ru ? "На след. раунд · %s" : "Next round · %s", price );
		}
	}
	else if( pending ) snprintf( action, sizeof( action ), ru ? "Отменить · +%s" : "Cancel · +%s", price );
	else if( ready ) snprintf( action, sizeof( action ), ru ? "Купить комплект · %s" : "Buy loadout · %s", price );
	else Q_strncpy( action, shop.status == Purchased ? ( ru ? "Куплено" : "Purchased" ) :
		( ru ? "Выбери оружие" : "Select weapons" ), sizeof( action ));
	DrawSurvivalButton( m_quick[4], action, ready, ready || ( !round && pending ), IsPressed( HIT_QUICK + 4 ), round );
}

void CCzmShop::DrawSurvivalGear()
{
	const bool ru = CZM_IsRussian();
	const auto &shop = m_wmenu.shop;
	const HFont title = CZM_Font( CZMF_UI_LABEL ), note = CZM_Font( CZMF_UI_META );
	const char *ruNames[] = { "Огненная граната", "Замораживающая граната", "Осветительная граната", "Броня + шлем" };
	const char *enNames[] = { "Fire grenade", "Frost grenade", "Flare grenade", "Armor + helmet" };
	CZM_DrawText( title, m_cards[0].x, H * .218f, m_cards[0].w, ru ? "ГРАНАТЫ" : "GRENADES", CZM_White() );
	CZM_DrawText( title, m_cards[3].x, H * .218f, m_cards[3].w, ru ? "БРОНЯ" : "ARMOR", CZM_White() );
	for( int i = 0; i < m_iSlots; ++i )
	{
		const CzmRect &r = m_cards[i];
		const int key = m_wmenu.keys[i], price = Price( i );
		const bool armor = key == 3, enabled = RowEnabled( i );
		const bool selected = ( shop.equipment & ( 1 << key )) != 0;
		const unsigned color = selected ? CZM_White() : !enabled ? PackRGBA( 120, 201, 158, 255 ) :
			price <= m_iMoney ? PackRGBA( 250, 183, 94, 255 ) : PackRGBA( 244, 122, 118, 255 );
		const int pad = H * .018f, icon = H * ( armor ? .17f : .083f );
		DrawSurvivalButton( r, "", selected, enabled, IsPressed( HIT_ITEM + i ));
		DrawWeapon( *m_slots[i], armor ? r.x + ( r.w - icon ) / 2 : r.x + pad,
			armor ? r.y + H * .040f : r.y + ( r.h - icon ) / 2, icon, icon, CZM_White( enabled ? 255 : 140 ));
		const int x = armor ? r.x + pad : r.x + pad * 2 + icon;
		const int y = armor ? r.y + H * .235f : r.y + r.h * .19f;
		const int w = r.x + r.w - pad - x, align = armor ? QM_CENTER : QM_LEFT;
		CZM_DrawText( title, x, y, w, ( ru ? ruNames : enNames )[key], CZM_White(), align );
		char action[64];
		if( selected ) snprintf( action, sizeof( action ), ru ? "✓ Выбрано · $%d" : "✓ Selected · $%d", price );
		else if( enabled && shop.equipmentSelection ) snprintf( action, sizeof( action ), ru ? "Выбрать · $%d" : "Select · $%d", price );
		else if( enabled ) snprintf( action, sizeof( action ), ru ? "Купить сейчас · $%d" : "Buy now · $%d", price );
		else Q_strncpy( action, RoundShop() && !( m_wmenu.shop.flags & CzmSurvivalShop::CanBuyGear ) ?
			( ru ? "Доступно за людей" : "Available as a human" ) : ( ru ? "Получено" : "Owned" ), sizeof( action ));
		CZM_DrawText( note, x, y + H * .050f, w, action, color, align );
	}
}

void CCzmShop::SendSurvival( int action, int value )
{
	EngFuncs::ClientCmdF( false, "czm_loadout %d %d %d\n", m_wmenu.shop.token, action, value );
}

void CCzmShop::ActivateSurvival( int hit )
{
	using namespace CzmSurvivalShop;
	if( hit == HIT_CLOSE )
	{
		CZM_PlayClick();
		CloseServerMenu( true );
		return;
	}
	if( Waiting() ) return;

	const auto &shop = m_wmenu.shop;
	int action = 0, value = 0;
	if( hit >= HIT_TAB && hit < HIT_TAB + 3 )
	{
		value = hit - HIT_TAB;
		if( value != shop.tab ) action = Section;
	}
	else if( hit >= HIT_ITEM && hit < HIT_ITEM + m_iSlots )
	{
		const int row = hit - HIT_ITEM;
		if( RoundShop() && !Gear() )
		{
			m_iInfo = row;
			if( m_slots[row]->weapon != shop.preview ) { action = Item; value = m_wmenu.keys[row]; }
		}
		else if( RowEnabled( row ))
		{
			action = Item;
			value = m_wmenu.keys[row];
		}
	}
	else if( hit == HIT_SELECT && RoundShop() && !Gear() && m_iInfo >= 0 && m_iInfo < m_iSlots && RowEnabled( m_iInfo ))
	{
		value = m_slots[m_iInfo]->weapon;
		if( value == shop.preview ) action = Select;
	}
	else if( hit == HIT_CANCEL && RoundShop() && shop.status == Pending ) action = Cancel;
	else if( hit == HIT_QUICK && ( shop.flags & CanRemember )) action = Remember;
	else if( hit == HIT_QUICK + 1 && shop.page > 0 ) { action = Page; value = shop.page - 1; }
	else if( hit == HIT_QUICK + 2 && shop.page + 1 < shop.pages ) { action = Page; value = shop.page + 1; }
	else if( hit == HIT_QUICK + 3 && !Gear() ) action = Skip;
	else if( hit == HIT_QUICK + 4 )
	{
		if( !RoundShop() && shop.status == Pending ) action = Cancel;
		else if( shop.flags & CanConfirm ) action = Confirm;
	}
	if( !action ) return;
	CZM_PlayClick();
	m_iPickTime = uiStatic.realTime;
	SendSurvival( action, value );
}

ADD_MENU3( menu_czmshop, CCzmShop, UI_CzmShop_Menu );

// console command menu_czmshop, for testing
void UI_CzmShop_Menu( void )
{
	if( menu_czmshop && CL_IsActive( ))
		menu_czmshop->Open( 0 );
}

// A weapon menu of the server goes to the shop window; true while the window has it.
bool CZM_ShopWeaponFrame( const char *value )
{
	bool open = menu_czmshop && menu_czmshop->ServerMode() && CZM_ClientMenuOpen( menu_czmshop );
	int serial = -1;
	CzmWeaponMenu menu;

	if( value && value[0] )
		sscanf( value, "%d", &serial );

	if( open && ( EngFuncs::GetCvarFloat( "czm_shop" ) == 0 || EngFuncs::GetCvarFloat( "_vgui_menus" ) == 0 ))
	{
		menu_czmshop->CloseServerMenu( false );
		return false;
	}
	if( open )
	{
		if( !value || !value[0] )
		{
			// after a pick the next menu (pistols, the switch again) comes in a moment
			if( !menu_czmshop->Waiting( ))
				menu_czmshop->CloseServerMenu( false );
			return true;
		}
		if( serial == menu_czmshop->Serial( ))
			return true;
		if( ParseWeaponMenu( value, menu ))
		{
			menu_czmshop->OpenServerMenu( menu );
			return true;
		}
		menu_czmshop->CloseServerMenu( false );
		return false;
	}

	if( !value || !value[0] || serial == s_iWeaponClosed || EngFuncs::GetCvarFloat( "czm_shop" ) == 0.0f || EngFuncs::GetCvarFloat( "_vgui_menus" ) == 0.0f || !menu_czmshop
		|| !CL_IsActive() || uiStatic.menu.IsActive() || uiStatic.client.IsActive( ))
		return false;
	if( !ParseWeaponMenu( value, menu ))
		return false;
	menu_czmshop->OpenServerMenu( menu );
	return true;
}

bool CZM_ShopShow( int menuType, int team )
{
	// 0: the stock menus, the classic text menu is chosen by _vgui_menus
	if( menuType < CZM_MENU_BUY || menuType > CZM_MENU_BUY_ITEM || EngFuncs::GetCvarFloat( "czm_shop" ) == 0.0f )
		return false;

	if( !menu_czmshop )
		return false;

	// the server sends the buy menu again after a purchase: keep the open shop as it is
	if( CZM_ClientMenuOpen( menu_czmshop ))
		return true;

	menu_czmshop->Open( team );
	return true;
}
