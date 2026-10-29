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
#include "Utils.h"
#include "keydefs.h"
#include "CzmMenu.h"

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
class CCzmShop : public CMenuBaseClientWindow
{
public:
	typedef CMenuBaseClientWindow BaseClass;
	CCzmShop();

	void Open( int team );

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
		HIT_TAB = 10,     // + category
		HIT_QUICK = 30,   // + quick button
		HIT_ITEM = 100,   // + slot in the current category
	};

	void ReadState( void );
	void SelectCategory( int category );
	void Layout( void );
	int HitTest( void ) const;
	int WheelSlot( int x, int y ) const;
	bool IsPressed( int hit ) const { return m_iPressed == hit && HitTest() == hit; }
	void Activate( int hit );
	void Buy( const CzmShopItem &item );
	void Toast( const char *text );
	bool Owned( const CzmShopItem &item ) const;

	void DrawTop( void );
	void DrawTabs( void );
	void DrawQuick( void );
	void DrawWheel( void );
	void DrawInfo( const CzmShopItem *item );
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
	int m_iInfo;       // wheel: slot shown in the info panel
	char m_szToast[96];
	int m_iToastTime;
	bool m_bGrid;
	bool m_bClosing;

	// layout, recalculated every frame
	int W, H;
	CzmRect m_top, m_close, m_tabs[CAT_COUNT], m_quick[CZM_QUICK], m_info, m_buy, m_cards[CZM_MAX_SECTORS];
	int m_iWheelX, m_iWheelY, m_iWheelR;
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
	W = H = 0;
	m_iWheelX = m_iWheelY = m_iWheelR = 0;
	memset( m_slots, 0, sizeof( m_slots ));
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

void CCzmShop::Open( int team )
{
	if( team == TEAM_T || team == TEAM_CT )
		m_iTeam = team;
	ReadState();
	m_bGrid = EngFuncs::GetCvarFloat( "czm_shop" ) == 2.0f;
	SelectCategory( s_iLastCategory );
	m_iPressed = HIT_NONE;
	m_szToast[0] = 0;
	m_bClosing = false;
	Show();
}

void CCzmShop::Show()
{
	EngFuncs::KEY_SetDest( KEY_MENU );
	EngFuncs::ClientCmd( true, "touch_setclientonly 1" );
	BaseClass::Show();
}

void CCzmShop::Hide()
{
	BaseClass::Hide();
	if( m_pStack->Count() <= 1 )
	{
		EngFuncs::KEY_ClearStates();
		EngFuncs::KEY_SetDest( KEY_GAME );
		EngFuncs::ClientCmd( false, "touch_setclientonly 0" );
	}
}

bool CCzmShop::Owned( const CzmShopItem &item ) const
{
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
	gap = H * 0.017f;

	m_top = CZM_Rect( 0, 0, W, H * 0.103f );
	m_close = CZM_Rect( W - H * 0.037f - H * 0.073f, ( m_top.h - H * 0.073f ) / 2, H * 0.073f, H * 0.073f );

	// categories on the left
	tabX = W * 0.018f;
	tabY = H * 0.137f;
	tabW = Q_max( (int)( W * 0.135f ), (int)( H * 0.29f ));
	tabH = H * 0.105f;
	tabGap = H * 0.013f;
	for( int i = 0; i < CAT_COUNT; i++ )
		m_tabs[i] = CZM_Rect( tabX, tabY + i * ( tabH + tabGap ), tabW, tabH );

	// quick buttons along the bottom
	quickX = tabX + tabW + gap * 2;
	quickY = H * 0.878f;
	quickH = H * 0.09f;
	{
		int total = W - quickX - W * 0.02f - gap * ( CZM_QUICK - 1 );
		for( int i = 0; i < CZM_QUICK; i++ )
			m_quick[i] = CZM_Rect( quickX + i * ( total / CZM_QUICK + gap ), quickY, total / CZM_QUICK, quickH );
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
		int columns = m_iSlots > 6 ? 4 : 3;
		int areaX = quickX, areaW = W - W * 0.02f - areaX;
		int areaY = tabY, areaH = quickY - gap * 2 - areaY;
		int cardW = ( areaW - gap * ( columns - 1 )) / columns;
		int cardH = ( areaH - gap ) / 2;

		for( int i = 0; i < m_iSlots; i++ )
			m_cards[i] = CZM_Rect( areaX + ( i % columns ) * ( cardW + gap ), areaY + ( i / columns ) * ( cardH + gap ), cardW, cardH );
	}
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
		UI_CloseClientMenu();
		return true;
	}

	if( UI::Key::IsLeftMouse( key ))
	{
		Layout();
		m_iPressed = HitTest();

		// the wheel works like in shooters: the slot under the finger is shown, release buys
		if( !m_bGrid && m_iPressed >= HIT_ITEM && !m_info.HasCursor( ))
			m_iHover = m_iInfo = m_iPressed - HIT_ITEM;
		return true;
	}

	// keys 1..8 pick categories, like the old menu
	if( key >= '1' && key < '1' + CAT_COUNT )
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

	UI_FillRect( m_top.x, m_top.y, m_top.w, m_top.h, PackRGBA( 10, 12, 16, 220 ));
	UI_FillRect( m_top.x, m_top.y + m_top.h - CZM_LineWidth(), m_top.w, CZM_LineWidth(), CZM_White( 25 ));

	x = W * 0.018f;
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
		bool afford = item.price <= m_iMoney;
		float angle = ( -90.0f + i * 360.0f / n ) * M_PI / 180.0f;
		float radius = n == 1 ? 0.0f : m_iWheelR * 0.64f;
		int cx = m_iWheelX + cosf( angle ) * radius;
		int cy = m_iWheelY + sinf( angle ) * radius;
		// silhouettes of neighbouring slots must not touch
		int boxW = n <= 2 ? m_iWheelR * 0.62f : Q_min( (int)( m_iWheelR * 0.62f ), (int)( m_iWheelR * 1.25f * sinf( M_PI / n )));
		int textW = Q_max( boxW * 13 / 10, (int)( m_iWheelR * 0.5f ));
		int imgH = m_iWheelR * 0.19f;
		int nameH = CZM_FontHeight( nameFont ), priceH = CZM_FontHeight( priceFont );
		int top = cy - ( imgH + nameH + priceH + H * 0.012f ) / 2;

		if( n == 1 )
			top = m_iWheelY - m_iWheelR * 0.72f;

		DrawSilhouette( item.image, cx - boxW / 2, top, boxW, imgH, CZM_White( afford ? 255 : 100 ));
		CZM_DrawText( nameFont, cx - textW / 2, top + imgH + H * 0.008f, textW, ItemName( item ), CZM_White( afford ? 255 : 110 ), QM_CENTER );
		FormatMoney( item.price, money, sizeof( money ));
		CZM_DrawText( priceFont, cx - textW / 2, top + imgH + H * 0.012f + nameH, textW, money,
			afford ? PackRGBA( 74, 222, 128, 255 ) : PackRGBA( 248, 113, 113, 255 ), QM_CENTER );

		if( Owned( item ))
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
		CZM_DrawText( hubFont, m_iWheelX - hub, m_iWheelY - CZM_FontHeight( hubFont ) / 2, hub * 2, label, CZM_White(), QM_CENTER );
	}
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

	CZM_DrawText( bigFont, x, y, w * 0.62f, ItemName( *item ), CZM_White());
	FormatMoney( item->price, money, sizeof( money ));
	CZM_DrawText( priceFont, x, y + ( CZM_FontHeight( bigFont ) - CZM_FontHeight( priceFont )) / 2, w, money,
		item->price <= m_iMoney ? PackRGBA( 74, 222, 128, 255 ) : PackRGBA( 248, 113, 113, 255 ), QM_RIGHT );
	y += CZM_FontHeight( bigFont ) + H * 0.02f;

	DrawSilhouette( item->image, x + w * 0.08f, y, w * 0.84f, H * 0.15f, CZM_White());
	y += H * 0.17f;

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
			int rowH = H * 0.05f;
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
		IsPressed( HIT_ITEM + m_iInfo ) && m_info.HasCursor() ? CZM_Grey() : CZM_White());
	CZM_DrawText( buyFont, m_buy.x, m_buy.y + ( m_buy.h - CZM_FontHeight( buyFont )) / 2, m_buy.w,
		Owned( *item ) ? ( ru ? "КУПИТЬ ЕЩЁ" : "BUY AGAIN" ) : ( ru ? "КУПИТЬ" : "BUY" ), CZM_White(), QM_CENTER );
}

void CCzmShop::DrawGrid( void )
{
	HFont nameFont = CZM_Font( CZMF_SHOP_CARD );
	HFont priceFont = CZM_Font( CZMF_SHOP_CARD_PRICE );
	HFont badgeFont = CZM_Font( CZMF_SHOP_PRICE );
	int corner = H * 0.03f;
	char money[32];

	for( int i = 0; i < m_iSlots; i++ )
	{
		const CzmShopItem &item = *m_slots[i];
		const CzmRect &r = m_cards[i];
		bool afford = item.price <= m_iMoney;
		bool owned = Owned( item );
		int pad = r.h * 0.09f;
		int textY = r.y + r.h - pad - CZM_FontHeight( nameFont );

		CZM_DrawSliced( owned ? UI_DIR "tab_on.png" : UI_DIR "card.png", r.x, r.y, r.w, r.h, 30, corner,
			IsPressed( HIT_ITEM + i ) ? CZM_Grey() : CZM_White());
		DrawSilhouette( item.image, r.x + r.w * 0.1f, r.y + pad * 1.4f, r.w * 0.8f, textY - r.y - pad * 2.4f, CZM_White( afford ? 255 : 95 ));

		CZM_DrawText( nameFont, r.x + pad * 1.2f, textY, r.w * 0.58f, ItemName( item ), CZM_White( afford ? 255 : 110 ));
		FormatMoney( item.price, money, sizeof( money ));
		CZM_DrawText( priceFont, r.x, textY + ( CZM_FontHeight( nameFont ) - CZM_FontHeight( priceFont )) / 2, r.w - pad * 1.2f, money,
			afford ? PackRGBA( 74, 222, 128, 255 ) : PackRGBA( 248, 113, 113, 255 ), QM_RIGHT );

		if( owned )
		{
			const char *badge = CZM_IsRussian() ? "ЕСТЬ" : "OWNED";
			int bw = CZM_TextWidth( badgeFont, badge ) + H * 0.03f, bh = H * 0.04f;
			CZM_DrawPill( UI_DIR "button_secondary.png", r.x + r.w - pad - bw, r.y + pad, bw, bh, CZM_White());
			CZM_DrawText( badgeFont, r.x + r.w - pad - bw, r.y + pad + ( bh - CZM_FontHeight( badgeFont )) / 2, bw, badge, CZM_White(), QM_CENTER );
		}
	}
}

void CCzmShop::Draw()
{
	ReadState();

	// dead, spectating or out of the game: the shop is not for now
	// (Hide only marks the window, the stack removes it after drawing)
	if( !m_bAlive || !CL_IsActive( ))
	{
		if( !m_bClosing )
		{
			m_bClosing = true;
			Hide();
		}
		return;
	}

	Layout();

	UI_FillRect( 0, 0, W, H, PackRGBA( 6, 8, 12, 150 ));
	DrawTop();
	DrawTabs();

	if( m_bGrid )
		DrawGrid();
	else
	{
		DrawWheel();
		DrawInfo( m_iInfo >= 0 && m_iInfo < m_iSlots ? m_slots[m_iInfo] : NULL );
	}

	DrawQuick();

	if( m_szToast[0] && uiStatic.realTime - m_iToastTime < 1800 )
	{
		HFont font = CZM_Font( CZMF_TILE_STATUS );
		int tw = CZM_TextWidth( font, m_szToast ) + H * 0.08f;
		CzmRect r = CZM_Rect(( W - tw ) / 2, ( m_top.h - H * 0.065f ) / 2, tw, H * 0.065f );

		CZM_DrawPill( UI_DIR "button_secondary.png", r.x, r.y, r.w, r.h );
		CZM_DrawText( font, r.x, r.y + ( r.h - CZM_FontHeight( font )) / 2, r.w, m_szToast, CZM_White(), QM_CENTER );
	}
}

ADD_MENU3( menu_czmshop, CCzmShop, UI_CzmShop_Menu );

// console command menu_czmshop, for testing
void UI_CzmShop_Menu( void )
{
	if( menu_czmshop && CL_IsActive( ))
		menu_czmshop->Open( 0 );
}

bool CZM_ShopShow( int menuType, int team )
{
	// 0: the stock menus, the classic text menu is chosen by _vgui_menus
	if( menuType < CZM_MENU_BUY || menuType > CZM_MENU_BUY_ITEM || EngFuncs::GetCvarFloat( "czm_shop" ) == 0.0f )
		return false;

	if( !menu_czmshop )
		return false;

	// the server sends the buy menu again after a purchase: keep the open shop as it is
	if( uiStatic.client.IsActive() && uiStatic.client.Current() == menu_czmshop )
		return true;

	menu_czmshop->Open( team );
	return true;
}
