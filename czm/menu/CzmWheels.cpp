/*
CzmWheels.cpp - Counter Zombie Mobile wheels: the weapon wheel and the radio wheel
Copyright (C) 2026 Counter Zombie Mobile authors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

On a touch button ("_czmwheel weapons", "_czmwheel radio" and the stock radio button
"showvguimenu 38") the engine follows the finger and keeps the game going: other fingers walk
and look meanwhile (patch czm-touch-press-and-wheels). It says where the wheel is in the cvar
czm_wheel, this file draws it over the game and runs what the engine picks ("czm_wheel_pick").
Held: slide from the button towards a choice and let go. A quick tap on the weapon wheel switches
to the last weapon, a tap on the radio wheel leaves it open for a tap on a phrase.

"showvguimenu 38" typed in the console (no finger, no touch button) opens the radio wheel as a
menu window instead: tap a phrase, the hub or outside closes it.
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

#define CZM_MENU_RADIOSELECTOR 38 // dlls/cdll_dll.h
#define CZM_RADIO_IDLE 6000       // ms without a touch: the window closes by itself

// the same as in the engine (patch czm-touch-press-and-wheels)
#define CZM_WHEEL_HUB 0.30f  // of the radius
#define CZM_WHEEL_EDGE 1.12f // of the radius
enum { WHEEL_NONE, WHEEL_HELD, WHEEL_OPEN };

enum { KIND_RADIO, KIND_CHAT, KIND_SPRAY, KIND_WEAPON, KIND_ICON };

struct CzmWheelSlot
{
	const char *icon;    // gfx/czm/ui/<icon>.png; KIND_WEAPON: the buy menu picture when nothing is carried
	const char *ru, *en;
	const char *command; // KIND_CHAT: no command, the label goes to the chat
	int kind;
	int carry;           // KIND_WEAPON: 0 primary, 1 pistol, 2 grenade
};

// clockwise from the top
static const CzmWheelSlot s_radio[] =
{
	{ "icon_target", "Враг замечен", "Enemy spotted", "enemyspot", KIND_RADIO, 0 },
	{ "icon_plus", "Нужна помощь", "Need backup", "needbackup", KIND_RADIO, 0 },
	{ "icon_users", "За мной", "Follow me", "followme", KIND_RADIO, 0 },
	{ "icon_shield", "Прикрой", "Cover me", "coverme", KIND_RADIO, 0 },
	{ "icon_spray", "Спрей", "Spray", "impulse 201", KIND_SPRAY, 0 },
	{ "icon_heart", "Спасибо!", "Thanks!", NULL, KIND_CHAT, 0 },
	{ "icon_check", "Понял", "Roger", "roger", KIND_RADIO, 0 },
	{ "icon_flag", "Держим позицию", "Hold position", "holdpos", KIND_RADIO, 0 },
};

// the three stock radio menus (radio1..radio3), in their order, clockwise from the top
static const CzmWheelSlot s_radioCommands[] =
{
	{ "icon_shield", "Прикрой меня", "Cover me", "coverme", KIND_RADIO, 0 },
	{ "icon_go", "Иди первым", "Take the point", "takepoint", KIND_RADIO, 0 },
	{ "icon_flag", "Держи позицию", "Hold position", "holdpos", KIND_RADIO, 0 },
	{ "icon_refresh", "Сбор", "Regroup", "regroup", KIND_RADIO, 0 },
	{ "icon_users", "За мной", "Follow me", "followme", KIND_RADIO, 0 },
	{ "icon_plus", "Под огнём!", "Taking fire", "takingfire", KIND_RADIO, 0 },
};

static const CzmWheelSlot s_radioGroup[] =
{
	{ "icon_go", "Вперёд!", "Go, go, go", "go", KIND_RADIO, 0 },
	{ "icon_back", "Отходим", "Fall back", "fallback", KIND_RADIO, 0 },
	{ "icon_users", "Держимся вместе", "Stick together", "sticktog", KIND_RADIO, 0 },
	{ "icon_flag", "По позициям", "Get in position", "getinpos", KIND_RADIO, 0 },
	{ "icon_target", "Штурмуем", "Storm the front", "stormfront", KIND_RADIO, 0 },
	{ "icon_info", "Доложите", "Report in", "report", KIND_RADIO, 0 },
};

static const CzmWheelSlot s_radioReplies[] =
{
	{ "icon_check", "Так точно", "Affirmative", "roger", KIND_RADIO, 0 },
	{ "icon_target", "Враг замечен", "Enemy spotted", "enemyspot", KIND_RADIO, 0 },
	{ "icon_plus", "Нужна помощь", "Need backup", "needbackup", KIND_RADIO, 0 },
	{ "icon_shield", "Чисто", "Sector clear", "sectorclear", KIND_RADIO, 0 },
	{ "icon_flag", "На позиции", "In position", "inposition", KIND_RADIO, 0 },
	{ "icon_info", "Докладываю", "Reporting in", "reportingin", KIND_RADIO, 0 },
	{ "icon_bomb", "Рванёт!", "Gonna blow!", "getout", KIND_RADIO, 0 },
	{ "icon_close", "Никак нет", "Negative", "negative", KIND_RADIO, 0 },
	{ "icon_skull", "Враг убит", "Enemy down", "enemydown", KIND_RADIO, 0 },
};

static const CzmWheelSlot s_weapons[] =
{
	{ "ak47", "Основное", "Primary", "slot1", KIND_WEAPON, 0 },
	{ "deserteagle", "Пистолет", "Pistol", "slot2", KIND_WEAPON, 1 },
	{ "hegrenade", "Гранаты", "Grenades", "slot4", KIND_WEAPON, 2 },
	{ "icon_cart", "Магазин", "Shop", "buy", KIND_ICON, 0 },
	{ "icon_knife", "Нож", "Knife", "weapon_knife", KIND_ICON, 0 },
};

struct CzmWheel
{
	const char *name;
	const CzmWheelSlot *slots;
	int count;
	const char *tap; // a tap on the button without a slide; NULL: the wheel stays open
	const char *hub; // the picture in the middle
};

static const CzmWheel s_wheels[] =
{
	{ "weapons", s_weapons, sizeof( s_weapons ) / sizeof( s_weapons[0] ), "lastinv", "icon_refresh" },
	{ "radio", s_radio, sizeof( s_radio ) / sizeof( s_radio[0] ), NULL, "icon_close" },
	{ "radio1", s_radioCommands, sizeof( s_radioCommands ) / sizeof( s_radioCommands[0] ), NULL, "icon_close" },
	{ "radio2", s_radioGroup, sizeof( s_radioGroup ) / sizeof( s_radioGroup[0] ), NULL, "icon_close" },
	{ "radio3", s_radioReplies, sizeof( s_radioReplies ) / sizeof( s_radioReplies[0] ), NULL, "icon_close" },
};

static const CzmWheel *FindWheel( const char *name )
{
	for( size_t i = 0; i < sizeof( s_wheels ) / sizeof( s_wheels[0] ); i++ )
	{
		if( !strcmp( s_wheels[i].name, name ))
			return &s_wheels[i];
	}
	return NULL;
}

static const char *SlotLabel( const CzmWheelSlot &slot )
{
	return CZM_IsRussian() ? slot.ru : slot.en;
}

// the small line under a choice
static const char *SlotWhere( const CzmWheelSlot &slot )
{
	bool ru = CZM_IsRussian();

	switch( slot.kind )
	{
	case KIND_CHAT: return ru ? "в чат" : "to chat";
	case KIND_SPRAY: return ru ? "на стену" : "on a wall";
	case KIND_RADIO: return ru ? "рация" : "radio";
	}
	return NULL;
}

// the choice in a direction, clockwise from the top
static int SectorOf( int count, float dx, float dy )
{
	const float step = 360.0f / count;
	float angle = atan2f( dy, dx ) * 180.0f / M_PI + 90.0f + step / 2.0f;

	while( angle < 0.0f )
		angle += 360.0f;
	while( angle >= 360.0f )
		angle -= 360.0f;
	return bound( 0, (int)( angle / step ), count - 1 );
}

// what a finger points at: held, the direction of the slide; open, the place on the wheel; -1 none
static int WheelChoice( const CzmWheel &wheel, int mode, float dx, float dy, float radius )
{
	if( mode == WHEEL_OPEN )
	{
		const float d = sqrtf( dx * dx + dy * dy );
		if( d < radius * CZM_WHEEL_HUB || d > radius * CZM_WHEEL_EDGE )
			return -1;
	}
	else if( dx == 0.0f && dy == 0.0f )
		return -1; // a tap
	return SectorOf( wheel.count, dx, dy );
}

static unsigned int CarriedWeapons( void );

// the class names of the weapons by id: "weapon_ak47" takes it in hand at once, "slot1" would only
// open the weapon list unless hud_fastswitch is on
static const char *s_weaponNames[31] =
{
	NULL, "p228", NULL, "scout", "hegrenade", "xm1014", "c4", "mac10", "aug", "smokegrenade", "elite",
	"fiveseven", "ump45", "sg550", "galil", "famas", "usp", "glock18", "awp", "mp5navy", "m249",
	"m3", "m4a1", "tmp", "g3sg1", "flashbang", "deagle", "sg552", "ak47", "knife", "p90",
};

static void RunSlot( const CzmWheelSlot &slot )
{
	const char *name, *image;
	int weapon = 0;

	if( slot.kind == KIND_CHAT )
		EngFuncs::ClientCmdF( false, "say \"%s\"\n", SlotLabel( slot ));
	else if( slot.kind == KIND_WEAPON && CZM_ShopCarried( CarriedWeapons(), slot.carry, &name, &image, &weapon )
		&& weapon > 0 && weapon < 31 && s_weaponNames[weapon] )
		EngFuncs::ClientCmdF( false, "weapon_%s\n", s_weaponNames[weapon] );
	else
		EngFuncs::ClientCmdF( false, "%s\n", slot.command );
}

static unsigned int CarriedWeapons( void )
{
	const char *state = EngFuncs::GetCvarString( "czm_buy_state" );
	int money, team;
	unsigned int bits = 0;

	if( !state || sscanf( state, "%d %d %u", &money, &team, &bits ) != 3 )
		return 0;
	return bits;
}

/*
=================
drawing, shared by the touch wheels and the radio window
=================
*/
static void DrawWheel( const CzmWheel &wheel, int cx, int cy, int r, int hover, bool hubLit, int alpha )
{
	HFont nameFont = CZM_Font( CZMF_SHOP_NAME );
	HFont whereFont = CZM_Font( CZMF_SMALL );
	const int H = ScreenHeight;
	const unsigned int carried = CarriedWeapons();
	char path[64];
	int size, hub;

	// the wheel art is 640 pixels for a radius of 300
	size = r * 640 / 300;
	snprintf( path, sizeof( path ), SHOP_DIR "wheel%d.png", wheel.count );
	CZM_DrawImage( path, cx - size / 2, cy - size / 2, size, size, CZM_White( alpha ));
	if( hover >= 0 )
	{
		snprintf( path, sizeof( path ), SHOP_DIR "wheel%d_%d.png", wheel.count, hover );
		CZM_DrawImage( path, cx - size / 2, cy - size / 2, size, size, CZM_White( alpha ));
	}

	for( int i = 0; i < wheel.count; i++ )
	{
		const CzmWheelSlot &slot = wheel.slots[i];
		const float angle = ( -90.0f + i * 360.0f / wheel.count ) * M_PI / 180.0f;
		const int sx = cx + cosf( angle ) * r * 0.64f;
		const int sy = cy + sinf( angle ) * r * 0.64f;
		const int picH = r * 0.17f, picW = slot.kind == KIND_WEAPON ? r * 0.44f : picH;
		const int textW = r * ( wheel.count > 8 ? 0.46f : wheel.count > 6 ? 0.52f : 0.6f );
		const int nameH = CZM_FontHeight( nameFont ), whereH = CZM_FontHeight( whereFont );
		const int top = sy - ( picH + nameH + whereH + H * 0.012f ) / 2;
		const char *label = SlotLabel( slot ), *where = SlotWhere( slot );
		bool lit = true;
		int labelH = nameH, labelW;

		if( slot.kind == KIND_WEAPON )
		{
			const char *name = NULL, *image = NULL;
			int weapon = 0;

			// the gun carried in this slot, or a pale picture of the slot when there is none
			lit = CZM_ShopCarried( carried, slot.carry, &name, &image, &weapon );
			if( lit )
			{
				where = label;
				label = name;
			}
			else
			{
				image = slot.icon;
				where = CZM_IsRussian() ? "нет" : "none";
			}
			CZM_ShopDrawSilhouette( image, sx - picW / 2, top, picW, picH, CZM_White( lit ? alpha : alpha * 70 / 255 ));
		}
		else
		{
			snprintf( path, sizeof( path ), UI_DIR "%s.png", slot.icon );
			CZM_DrawImage( path, sx - picW / 2, top, picW, picH, CZM_White( alpha ));
		}

		// a long phrase gets smaller letters rather than leaving its slot
		labelW = CZM_TextWidth( nameFont, label );
		if( labelW > textW && labelW > 0 )
			labelH = Q_max( 1, labelH * textW / labelW );
		UI_DrawString( nameFont, sx - textW / 2, top + picH + H * 0.008f + ( nameH - labelH ) / 2, textW, labelH, label,
			CZM_White( lit ? alpha : alpha * 120 / 255 ), labelH, QM_CENTER | QM_TOP, ETF_NO_WRAP | ETF_FORCECOL );
		if( where )
			CZM_DrawText( whereFont, sx - textW / 2, top + picH + H * 0.012f + nameH, textW, where,
				i == hover ? PackRGBA( 254, 226, 226, alpha ) : PackRGBA( 150, 158, 172, alpha ), QM_CENTER );
	}

	hub = r * 0.13f;
	snprintf( path, sizeof( path ), UI_DIR "%s.png", wheel.hub );
	CZM_DrawImage( path, cx - hub / 2, cy - hub / 2, hub, hub, hubLit ? PackRGBA( 255, 120, 128, alpha ) : CZM_White( alpha ));
}

/*
=================
the touch wheels over the game
=================
*/
static struct
{
	bool shown;
	int shownAt; // ms, for the way the wheel opens
} s_touch;

void CZM_DrawTouchWheel( void )
{
	const char *value = EngFuncs::GetCvarString( "czm_wheel" );
	char name[16];
	int mode, cx, cy, r, dx, dy, pointing, shown, hover, alpha;
	const CzmWheel *wheel;
	float grow;

	if( !value || sscanf( value, "%15s %d %d %d %d %d %d %d %d", name, &mode, &cx, &cy, &r, &dx, &dy, &pointing, &shown ) != 9
		|| !shown || !CL_IsActive() || uiStatic.menu.IsActive() || uiStatic.client.IsActive() || !( wheel = FindWheel( name )) || r <= 0 )
	{
		s_touch.shown = false;
		return;
	}

	if( !s_touch.shown )
	{
		s_touch.shown = true;
		s_touch.shownAt = uiStatic.realTime;
	}

	// it opens in a tenth of a second, growing a little
	grow = bound( 0.0f, ( uiStatic.realTime - s_touch.shownAt ) / 120.0f, 1.0f );
	grow = grow * grow * ( 3.0f - 2.0f * grow );
	alpha = 255 * grow;
	r = r * ( 0.9f + 0.1f * grow );

	hover = pointing ? WheelChoice( *wheel, mode, dx, dy, r ) : -1;
	DrawWheel( *wheel, cx, cy, r, hover, false, alpha );

	// open after a tap: say how to choose
	if( mode == WHEEL_OPEN )
	{
		HFont font = CZM_Font( CZMF_TILE_STATUS );
		const char *hint = CZM_IsRussian() ? "Нажми на фразу. Мимо колеса — закрыть" : "Tap a phrase. Tap outside to close";
		int y = cy + r * CZM_WHEEL_EDGE + ScreenHeight * 0.02f;

		if( y + CZM_FontHeight( font ) > ScreenHeight )
			y = cy - r * CZM_WHEEL_EDGE - ScreenHeight * 0.02f - CZM_FontHeight( font );
		CZM_DrawText( font, 0, y, ScreenWidth, hint, PackRGBA( 220, 224, 232, alpha ), QM_CENTER );
	}
}

// "czm_wheel_pick <kind> <mode> <dx> <dy> <radius>" from the engine
static void UI_CzmWheelPick_f( void )
{
	const CzmWheel *wheel;
	int choice;

	if( EngFuncs::CmdArgc() < 6 || !( wheel = FindWheel( EngFuncs::CmdArgv( 1 ))))
		return;

	choice = WheelChoice( *wheel, atoi( EngFuncs::CmdArgv( 2 )), atof( EngFuncs::CmdArgv( 3 )), atof( EngFuncs::CmdArgv( 4 )),
		atof( EngFuncs::CmdArgv( 5 )));
	if( choice >= 0 )
		RunSlot( wheel->slots[choice] );
	else if( wheel->tap )
		EngFuncs::ClientCmdF( false, "%s\n", wheel->tap );
}

ADD_COMMAND( czm_wheel_pick, UI_CzmWheelPick_f );

/*
=================
the radio wheel as a menu window, for "showvguimenu 38" without a touch button
=================
*/
static const CzmWheel &RadioWheel( void )
{
	return s_wheels[1];
}

class CCzmRadio : public CMenuBaseClientWindow
{
public:
	typedef CMenuBaseClientWindow BaseClass;
	CCzmRadio();

	void Open( void );

	void Init() override;
	void VidInit() override;
	void Show() override;
	void Hide() override;
	void Draw() override;
	bool KeyDown( int key ) override;
	bool KeyUp( int key ) override;
	bool MouseMove( int x, int y ) override;

	enum
	{
		HIT_NONE = 0,
		HIT_HUB,
		HIT_OUTSIDE,
		HIT_SLOT = 100, // + slot
	};

	void Layout( void );
	int Slot( int x, int y ) const;
	int HitTest( void ) const;
	void Send( int slot );
	void Close( void );

	int m_iPressed;   // what the finger went down on
	int m_iHover;     // the slot under the finger, -1 none
	int m_iActive;    // last touch, for closing by itself
	bool m_bClosing;
	int W, H, m_iX, m_iY, m_iR;
};

CCzmRadio::CCzmRadio() : BaseClass( "CzmRadio" )
{
	m_iPressed = HIT_NONE;
	m_iHover = -1;
	m_iActive = 0;
	m_bClosing = false;
	W = H = m_iX = m_iY = m_iR = 0;
}

void CCzmRadio::Init()
{
	BaseClass::Init();
	pos.x = uiStatic.xOffset;
	pos.y = uiStatic.yOffset;
	size.w = uiStatic.width;
	size.h = 768;
}

void CCzmRadio::VidInit()
{
	pos.x = uiStatic.xOffset;
	pos.y = uiStatic.yOffset;
	size.w = uiStatic.width;
	size.h = 768;
	BaseClass::VidInit();
}

void CCzmRadio::Open( void )
{
	m_iPressed = HIT_NONE;
	m_iHover = -1;
	m_iActive = uiStatic.realTime;
	m_bClosing = false;
	CZM_KeepClientMenu( this );
	Show();
}

void CCzmRadio::Show()
{
	EngFuncs::KEY_SetDest( KEY_MENU );
	EngFuncs::ClientCmd( true, "touch_setclientonly 1" );
	BaseClass::Show();
}

void CCzmRadio::Hide()
{
	Close();
}

// the stock way, on the next frame (Hide() on the only client window would leave it in the stack)
void CCzmRadio::Close( void )
{
	if( m_bClosing )
		return;
	m_bClosing = true;
	CZM_CloseClientMenuSoon( this );
}

void CCzmRadio::Layout( void )
{
	W = ScreenWidth;
	H = ScreenHeight;
	m_iR = Q_min( (int)( H * 0.38f ), (int)( W * 0.24f ));
	m_iX = W / 2;
	m_iY = H / 2 - H * 0.02f;
}

int CCzmRadio::Slot( int x, int y ) const
{
	return WheelChoice( RadioWheel(), WHEEL_OPEN, x - m_iX, y - m_iY, m_iR );
}

int CCzmRadio::HitTest( void ) const
{
	int x = uiStatic.cursorX, y = uiStatic.cursorY;
	int slot = Slot( x, y );
	float dx = x - m_iX, dy = y - m_iY;

	if( slot >= 0 )
		return HIT_SLOT + slot;
	if( dx * dx + dy * dy < (float)m_iR * m_iR * CZM_WHEEL_HUB * CZM_WHEEL_HUB )
		return HIT_HUB;
	return HIT_OUTSIDE;
}

void CCzmRadio::Send( int slot )
{
	if( slot < 0 || slot >= RadioWheel().count )
		return;

	CZM_PlayClick();
	RunSlot( RadioWheel().slots[slot] );
	Close();
}

bool CCzmRadio::KeyDown( int key )
{
	if( UI::Key::IsEscape( key ))
	{
		Close();
		return true;
	}

	if( UI::Key::IsLeftMouse( key ))
	{
		Layout();
		m_iActive = uiStatic.realTime;
		m_iPressed = HitTest();
		m_iHover = m_iPressed >= HIT_SLOT ? m_iPressed - HIT_SLOT : -1;
		return true;
	}

	// keys 1..8 send the phrases in order
	if( key >= '1' && key < '1' + RadioWheel().count )
	{
		Send( key - '1' );
		return true;
	}

	return true;
}

bool CCzmRadio::KeyUp( int key )
{
	if( !UI::Key::IsLeftMouse( key ))
		return true;

	int hit, pressed = m_iPressed;

	Layout();
	hit = HitTest();
	m_iPressed = HIT_NONE;
	m_iHover = -1;
	m_iActive = uiStatic.realTime;

	if( hit >= HIT_SLOT && pressed >= HIT_SLOT )
		Send( hit - HIT_SLOT ); // pressed on the wheel and let go on a phrase
	else if( hit == pressed && ( hit == HIT_HUB || hit == HIT_OUTSIDE ))
		Close();
	return true;
}

bool CCzmRadio::MouseMove( int x, int y )
{
	Layout();
	m_iActive = uiStatic.realTime;
	if( m_iPressed != HIT_NONE )
		m_iHover = Slot( uiStatic.cursorX, uiStatic.cursorY );
	return true;
}

void CCzmRadio::Draw()
{
	HFont hintFont = CZM_Font( CZMF_TILE_STATUS );

	// out of the match or idle: close
	if( m_bClosing || !CL_IsActive() || uiStatic.realTime - m_iActive > CZM_RADIO_IDLE )
	{
		Close();
		return;
	}

	Layout();
	UI_FillRect( 0, 0, W, H, PackRGBA( 4, 6, 10, 120 ));
	DrawWheel( RadioWheel(), m_iX, m_iY, m_iR, m_iHover, m_iPressed == HIT_HUB, 255 );
	CZM_DrawText( hintFont, 0, m_iY + m_iR + H * 0.035f, W,
		CZM_IsRussian() ? "Нажми на фразу или проведи к ней и отпусти" : "Tap a phrase, or slide to it and let go",
		PackRGBA( 190, 196, 206, 255 ), QM_CENTER );
}

ADD_MENU3( menu_czmradio, CCzmRadio, UI_CzmRadio_Menu );

// console command menu_czmradio
void UI_CzmRadio_Menu( void )
{
	if( menu_czmradio && CL_IsActive( ))
		menu_czmradio->Open();
}

bool CZM_RadioShow( int menuType )
{
	if( menuType != CZM_MENU_RADIOSELECTOR || !menu_czmradio )
		return false;

	if( CZM_ClientMenuOpen( menu_czmradio ))
		return true; // already open

	menu_czmradio->Open();
	return true;
}
