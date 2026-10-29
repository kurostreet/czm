/*
CzmRadio.cpp - Counter Zombie Mobile radio wheel: radio commands, a thank-you and the spray on one wheel
Copyright (C) 2026 Counter Zombie Mobile authors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

Every "Radio" touch button (showvguimenu 38) opens it. It opens while the finger is still on the
button: slide to a phrase and let go to send it, or let go and tap a phrase. The hub, a tap
outside, Escape or a few quiet seconds close it. Radio commands are the game's own (any server
knows them), the thank-you goes to the chat in the menu language.
*/

#include <math.h>
#include <stdio.h>
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
#define CZM_RADIO_SLOTS 8
#define CZM_RADIO_IDLE 6000 // ms without a touch: the wheel closes by itself

enum { KIND_RADIO, KIND_CHAT, KIND_SPRAY };

// clockwise from the top
static const struct
{
	const char *icon;
	const char *ru, *en;
	const char *command; // KIND_CHAT: the text itself
	int kind;
} s_slots[CZM_RADIO_SLOTS] =
{
	{ "icon_target", "Враг замечен", "Enemy spotted", "enemyspot", KIND_RADIO },
	{ "icon_plus", "Нужна помощь", "Need backup", "needbackup", KIND_RADIO },
	{ "icon_users", "За мной", "Follow me", "followme", KIND_RADIO },
	{ "icon_shield", "Прикрой", "Cover me", "coverme", KIND_RADIO },
	{ "icon_spray", "Спрей", "Spray", "impulse 201", KIND_SPRAY },
	{ "icon_heart", "Спасибо!", "Thanks!", NULL, KIND_CHAT },
	{ "icon_check", "Понял", "Roger", "roger", KIND_RADIO },
	{ "icon_flag", "Держим позицию", "Hold position", "holdpos", KIND_RADIO },
};

static const char *SlotLabel( int i )
{
	return CZM_IsRussian() ? s_slots[i].ru : s_slots[i].en;
}

static const char *SlotWhere( int i )
{
	bool ru = CZM_IsRussian();

	switch( s_slots[i].kind )
	{
	case KIND_CHAT: return ru ? "в чат" : "to chat";
	case KIND_SPRAY: return ru ? "на стену" : "on a wall";
	}
	return ru ? "рация" : "radio";
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
	bool m_bFresh;    // opened by a finger still on the touch button
	bool m_bSlid;     // that finger has moved since: letting go sends
	int m_iMoveX, m_iMoveY;
	int m_iActive;    // last touch, for closing by itself
	bool m_bClosing;
	int W, H, m_iX, m_iY, m_iR;
};

CCzmRadio::CCzmRadio() : BaseClass( "CzmRadio" )
{
	m_iPressed = HIT_NONE;
	m_iHover = -1;
	m_bFresh = m_bSlid = false;
	m_iMoveX = m_iMoveY = -1;
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
	m_bFresh = true;
	m_bSlid = false;
	m_iMoveX = m_iMoveY = -1;
	m_iActive = uiStatic.realTime;
	m_bClosing = false;
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
	BaseClass::Hide();
	if( m_pStack->Count() <= 1 )
	{
		EngFuncs::KEY_ClearStates();
		EngFuncs::KEY_SetDest( KEY_GAME );
		EngFuncs::ClientCmd( false, "touch_setclientonly 0" );
	}
}

void CCzmRadio::Close( void )
{
	if( m_bClosing )
		return;
	m_bClosing = true;
	Hide();
}

void CCzmRadio::Layout( void )
{
	W = ScreenWidth;
	H = ScreenHeight;
	m_iR = Q_min( (int)( H * 0.38f ), (int)( W * 0.24f ));
	m_iX = W / 2;
	m_iY = H / 2 - H * 0.02f;
}

// the slot under a point; the wheel art is 640 pixels for a radius of 300 with a hub of 88
int CCzmRadio::Slot( int x, int y ) const
{
	float dx = x - m_iX, dy = y - m_iY;
	float dist = sqrtf( dx * dx + dy * dy );
	const float step = 360.0f / CZM_RADIO_SLOTS;
	float angle;

	if( dist > m_iR * 1.12f || dist < m_iR * ( 88.0f / 300.0f ))
		return -1;

	angle = atan2f( dy, dx ) * 180.0f / M_PI + 90.0f + step / 2.0f;
	while( angle < 0.0f )
		angle += 360.0f;
	while( angle >= 360.0f )
		angle -= 360.0f;
	return bound( 0, (int)( angle / step ), CZM_RADIO_SLOTS - 1 );
}

int CCzmRadio::HitTest( void ) const
{
	int x = uiStatic.cursorX, y = uiStatic.cursorY;
	int slot = Slot( x, y );
	float dx = x - m_iX, dy = y - m_iY;

	if( slot >= 0 )
		return HIT_SLOT + slot;
	if( dx * dx + dy * dy < (float)m_iR * m_iR * 0.09f )
		return HIT_HUB;
	return HIT_OUTSIDE;
}

void CCzmRadio::Send( int slot )
{
	if( slot < 0 || slot >= CZM_RADIO_SLOTS )
		return;

	CZM_PlayClick();
	if( s_slots[slot].kind == KIND_CHAT )
		EngFuncs::ClientCmdF( false, "say \"%s\"\n", SlotLabel( slot ));
	else
		EngFuncs::ClientCmdF( false, "%s\n", s_slots[slot].command );
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
		m_bFresh = false;
		m_iActive = uiStatic.realTime;
		m_iPressed = HitTest();
		m_iHover = m_iPressed >= HIT_SLOT ? m_iPressed - HIT_SLOT : -1;
		return true;
	}

	// keys 1..8 send the phrases in order
	if( key >= '1' && key < '1' + CZM_RADIO_SLOTS )
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
	m_iActive = uiStatic.realTime;

	if( m_bFresh )
	{
		// the finger that opened the wheel: a slide to a phrase sends it, a plain tap leaves the wheel open
		m_bFresh = false;
		if( m_bSlid && hit >= HIT_SLOT )
			Send( hit - HIT_SLOT );
		m_iHover = -1;
		return true;
	}

	m_iHover = -1;
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

	if( m_bFresh )
	{
		// a slide counts once the finger has gone a little way from where it was first seen
		if( m_iMoveX < 0 )
		{
			m_iMoveX = uiStatic.cursorX;
			m_iMoveY = uiStatic.cursorY;
		}
		else
		{
			float dx = uiStatic.cursorX - m_iMoveX, dy = uiStatic.cursorY - m_iMoveY;
			if( dx * dx + dy * dy > H * 0.05f * H * 0.05f )
				m_bSlid = true;
		}
		if( m_bSlid )
			m_iHover = Slot( uiStatic.cursorX, uiStatic.cursorY );
	}
	else if( m_iPressed != HIT_NONE )
		m_iHover = Slot( uiStatic.cursorX, uiStatic.cursorY );

	return true;
}

void CCzmRadio::Draw()
{
	HFont nameFont = CZM_Font( CZMF_SHOP_NAME );
	HFont whereFont = CZM_Font( CZMF_SMALL );
	HFont hintFont = CZM_Font( CZMF_TILE_STATUS );
	char path[64];
	int size, hub;

	// out of the match or idle: close (Hide only marks the window, the stack removes it after drawing)
	if( !CL_IsActive() || uiStatic.realTime - m_iActive > CZM_RADIO_IDLE )
	{
		Close();
		return;
	}

	Layout();
	UI_FillRect( 0, 0, W, H, PackRGBA( 4, 6, 10, 120 ));

	size = m_iR * 640 / 300;
	CZM_DrawImage( SHOP_DIR "wheel8.png", m_iX - size / 2, m_iY - size / 2, size, size );
	if( m_iHover >= 0 )
	{
		snprintf( path, sizeof( path ), SHOP_DIR "wheel8_%d.png", m_iHover );
		CZM_DrawImage( path, m_iX - size / 2, m_iY - size / 2, size, size );
	}

	for( int i = 0; i < CZM_RADIO_SLOTS; i++ )
	{
		const float angle = ( -90.0f + i * 360.0f / CZM_RADIO_SLOTS ) * M_PI / 180.0f;
		const int cx = m_iX + cosf( angle ) * m_iR * 0.64f;
		const int cy = m_iY + sinf( angle ) * m_iR * 0.64f;
		const int icon = m_iR * 0.17f;
		const int textW = m_iR * 0.52f;
		const int nameH = CZM_FontHeight( nameFont ), whereH = CZM_FontHeight( whereFont );
		const int top = cy - ( icon + nameH + whereH + H * 0.012f ) / 2;
		const bool on = i == m_iHover;
		const char *label = SlotLabel( i );
		int labelH = nameH, labelW = CZM_TextWidth( nameFont, label );

		snprintf( path, sizeof( path ), UI_DIR "%s.png", s_slots[i].icon );
		CZM_DrawImage( path, cx - icon / 2, top, icon, icon, CZM_White());

		// a long phrase gets smaller letters rather than leaving its slot
		if( labelW > textW && labelW > 0 )
			labelH = Q_max( 1, labelH * textW / labelW );
		UI_DrawString( nameFont, cx - textW / 2, top + icon + H * 0.008f + ( nameH - labelH ) / 2, textW, labelH, label,
			CZM_White(), labelH, QM_CENTER | QM_TOP, ETF_NO_WRAP | ETF_FORCECOL );
		CZM_DrawText( whereFont, cx - textW / 2, top + icon + H * 0.012f + nameH, textW, SlotWhere( i ),
			on ? PackRGBA( 254, 226, 226, 255 ) : PackRGBA( 150, 158, 172, 255 ), QM_CENTER );
	}

	// the hub closes
	hub = m_iR * 0.13f;
	CZM_DrawImage( UI_DIR "icon_close.png", m_iX - hub / 2, m_iY - hub / 2, hub, hub,
		m_iPressed == HIT_HUB ? CZM_Grey() : CZM_White());

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

	if( uiStatic.client.IsActive() && uiStatic.client.Current() == menu_czmradio )
		return true; // already open

	menu_czmradio->Open();
	return true;
}
