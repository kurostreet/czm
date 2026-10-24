/*
CzmMain.cpp - Counter Zombie Mobile main screen and in-game pause window
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
#include <time.h>
#include <math.h>

#include "extdll_menu.h"
#include "BaseMenu.h"
#include "Utils.h"
#include "Framework.h"
#include "keydefs.h"
#include "CzmMenu.h"
#include "CzmDesign.h"

#define UI_DIR "gfx/czm/ui/"
#define CZM_MAX_TILES 8
#define CZM_ABOUT_ROWS 7

#define CZM_CONTACT_URL "mailto:kuro.street.inc@gmail.com"
#define CZM_GROUP_URL "https://t.me/counter_zombie_mobile"
#define CZM_SITE_URL "https://counter-zombie.ru"
#define CZM_SOURCE_URL "https://github.com/kurostreet/czm"

namespace
{

// the bell counts unread news and an update waiting to be installed
int UnreadNotifications( void )
{
	return CZM_NewsUnread() + ( CZM_Update() ? 1 : 0 );
}

// the day this build was made, 11.10.2026
void BuildDate( char *out, size_t size )
{
	static const char *months = "JanFebMarAprMayJunJulAugSepOctNovDec";
	const char *date = __DATE__; // "Oct 11 2026"
	char month[4] = { date[0], date[1], date[2], 0 };
	const char *m = strstr( months, month );

	snprintf( out, size, "%02d.%02d.%s", atoi( date + 4 ), m ? (int)( m - months ) / 3 + 1 : 0, date + 7 );
}

} // namespace

/*
=================
CCzmMainMenu

Header (nick, bell, language), one big tile per game mode and the bottom navigation.
Everything is drawn by hand, the window has no stock items.
=================
*/
class CCzmMainMenu : public CMenuFramework
{
public:
	CCzmMainMenu();

	void Show() override;
	void Draw() override;
	void Think() override;
	bool KeyDown( int key ) override;
	bool KeyUp( int key ) override;
	void Char( int key ) override;

private:
	enum EOverlay
	{
		OV_NONE = 0,
		OV_QUIT,
		OV_BELL,
		OV_ABOUT,
		OV_CHAT,
		OV_SETUP, // first start: language and nickname
	};

	enum EHit
	{
		HIT_NONE = 0,
		HIT_PROFILE,
		HIT_BELL,
		HIT_LANG_RU,
		HIT_LANG_EN,
		HIT_BACKDROP,
		HIT_PANEL,
		HIT_CLOSE,
		HIT_QUIT_YES,
		HIT_QUIT_NO,
		HIT_VERSION,
		HIT_SETUP_RU,
		HIT_SETUP_EN,
		HIT_SETUP_NICK,
		HIT_SETUP_GO,
		HIT_SETUP_LOGIN, // played before: sign in, the account brings the settings back
		HIT_SETUP_REGISTER,
		HIT_ABOUT_TELEGRAM,
		HIT_ABOUT_GROUP,
		HIT_ABOUT_SITE,
		HIT_UPDATE,
		HIT_ABOUT_SOURCE,
		HIT_QUICK,                  // quick play under the logo
		HIT_LOBBY_CREATE,          // start a temporary team room
		HIT_LOBBY_SEARCH,          // browse public rooms
		HIT_NAV,                    // 5 navigation items
		HIT_TILE = HIT_NAV + 5,     // one per server
		HIT_RETIRE = HIT_TILE + CZM_MAX_TILES,
		HIT_LAST = HIT_RETIRE + 6
	};

	void Layout( void );
	int HitTest( void ) const;
	bool IsPressed( int hit ) const { return m_iPressed == hit && HitTest() == hit; }
	void Activate( int hit );

	void DrawTitle( void );
	void DrawHeader( void );
	void DrawTile( int index, CzmRect r );
	void DrawNav( void );
	void DrawOverlay( void );
	void DrawAbout( void );
	void DrawBell( void );
	void DrawSetup( void );
	void FinishSetup( void );
	void DrawQuick( void );
	void DrawRetired( void );

	int m_overlay;
	int m_iPressed;
	int m_iVersionTaps;
	double m_flVersionTapTime;

	// layout, recalculated every frame from the screen size
	int W, H, m_iMargin;
	char m_szNick[64];
	int m_iNickX, m_iNickW;
	int m_iTiles;
	int m_iPanelLineY;
	CzmRect m_avatar, m_profile, m_bell, m_lang;
	CzmRect m_tiles[CZM_MAX_TILES], m_nav[5];
	CzmRect m_panel, m_close, m_quitYes, m_quitNo, m_version;
	CzmRect m_aboutLogo, m_aboutRows[CZM_ABOUT_ROWS];
	CzmRect m_update, m_updateButton;
	CzmRect m_setupLang, m_setupNick, m_setupGo, m_setupLogin, m_setupRegister;
	CzmRect m_quick, m_lobbyCreate, m_lobbySearch;
	CzmRect m_retire[6];
	char m_szQuickNote[160];   // why the search found nothing, shown for a few seconds
	double m_flQuickNote;
	CzmTextEdit m_nick;
	bool m_bNickWarning;
};

CCzmMainMenu::CCzmMainMenu() : CMenuFramework( "CzmMain" )
{
	m_overlay = OV_NONE;
	m_iPressed = HIT_NONE;
	m_iVersionTaps = 0;
	m_flVersionTapTime = 0.0;
	m_szQuickNote[0] = 0;
	m_flQuickNote = 0.0;
	W = H = m_iMargin = 0;
	m_szNick[0] = 0;
	m_iNickX = m_iNickW = 0;
	m_iTiles = 0;
	m_iPanelLineY = 0;
	memset( &m_nick, 0, sizeof( m_nick ));
	m_bNickWarning = false;
}

void CCzmMainMenu::Show()
{
	m_overlay = OV_NONE;
	m_iPressed = HIT_NONE;
	CMenuFramework::Show();
	CZM_QueryServers( true );
	CZM_ApplyStartupSettings();

	if( CZM_FirstStart( ) && CZM_OnlinePlayAllowed( ))
	{
		m_overlay = OV_SETUP;
		m_bNickWarning = false;
		memset( &m_nick, 0, sizeof( m_nick ));
	}

	// the engine build string would sit on the navigation bar, the version is in About
	EngFuncs::CvarSetValue( "scr_drawversion", 0.0f );

	// a game started from the server list ended: back to the list
	if( m_overlay == OV_NONE && CZM_OnlinePlayAllowed() )
		CZM_ServerListReturn();
}

void CCzmMainMenu::Think()
{
	CMenuFramework::Think();

	// keep the tiles fresh while the player looks at them
	if( CZM_OnlinePlayAllowed() && m_pStack->Current() == this && !CL_IsActive() && EngFuncs::GetCvarFloat( "czm_loading" ) == 0.0f )
		CZM_QueryServers( false );
}

void CCzmMainMenu::Layout( void )
{
	HFont nickFont = CZM_Font( CZMF_NICK );
	HFont hintFont = CZM_Font( CZMF_SMALL );
	int avatar, top, chip, langW, pencil, right;
	int tileW, tileH, gap, areaTop, areaBottom, total, y;

	W = ScreenWidth;
	H = ScreenHeight;
	for( int i = 0; i < 6; ++i )
		m_retire[i] = CZM_Rect( W * ( i % 2 ? 0.51f : 0.14f ), H * ( 0.52f + ( i / 2 ) * 0.11f ), W * 0.35f, H * 0.078f );
	m_iMargin = W * 0.03f;

	// header: avatar, nick and the hint under it
	avatar = H * 0.078f;
	top = H * 0.022f;
	m_avatar = CZM_Rect( m_iMargin, top, avatar, avatar );

	CZM_CleanName( EngFuncs::GetCvarString( "name" ), m_szNick, sizeof( m_szNick ));
	if( !m_szNick[0] )
		Q_strncpy( m_szNick, "Player", sizeof( m_szNick ));

	m_iNickX = m_iMargin + avatar + H * 0.022f;
	m_iNickW = Q_min( CZM_TextWidth( nickFont, m_szNick ), (int)( W * 0.34f ));
	pencil = H * 0.028f;
	right = Q_max( m_iNickX + m_iNickW + (int)( H * 0.012f ) + pencil, m_iNickX + CZM_TextWidth( hintFont, CZM_T( "nick_hint" )));
	m_profile = CZM_Rect( m_iMargin, top, right - m_iMargin, avatar );

	// header right: bell and language switch
	chip = H * 0.066f;
	langW = H * 0.22f;
	m_lang = CZM_Rect( W - m_iMargin - langW, top, langW, chip );
	m_bell = CZM_Rect( m_lang.x - H * 0.025f - chip, top, chip, chip );

	// three home slots: pinned servers, the rest are "+ add" tiles
	m_iTiles = Q_min( CZM_HOME_MAX, CZM_MAX_TILES );
	tileH = H * 0.205f;
	tileW = tileH * 37 / 10;
	if( tileW > W * 0.42f )
	{
		tileW = W * 0.42f;
		tileH = tileW * 10 / 37;
	}

	gap = H * 0.03f;
	areaTop = H * 0.13f;
	areaBottom = H * 0.87f;
	total = m_iTiles * tileH + Q_max( 0, m_iTiles - 1 ) * gap;
	if( total > areaBottom - areaTop && m_iTiles > 0 )
	{
		tileH = ( areaBottom - areaTop - ( m_iTiles - 1 ) * gap ) / m_iTiles;
		tileW = tileH * 37 / 10;
		total = m_iTiles * tileH + ( m_iTiles - 1 ) * gap;
	}

	y = areaTop + ( areaBottom - areaTop - total ) / 2;
	for( int i = 0; i < m_iTiles; i++ )
		m_tiles[i] = CZM_Rect( W - m_iMargin - tileW, y + i * ( tileH + gap ), tileW, tileH );

	// quick play under the logo, left of the tiles
	{
		int qw = Q_min( (int)( H * 0.66f ), ( m_iTiles > 0 ? m_tiles[0].x : W ) - m_iMargin - (int)( H * 0.06f ));
		// Three equal full-width actions, aligned to the same left edge.
		// Shared geometry; colour identifies the action without a saturated pill.
		const int actionHeight = Q_max(48,(int)(H * 0.105f));
		// The touch rectangles grow by 1.5% of H on each side.
		// Leave >3% between rows so adjacent hit regions never overlap.
		const int actionGap = Q_max(12,(int)(H * 0.038f));
		m_quick = CZM_Rect( m_iMargin, H * 0.335f, qw, actionHeight );
		m_lobbyCreate = CZM_Rect(m_quick.x,m_quick.y+actionHeight+actionGap,
		                         m_quick.w,actionHeight);
		m_lobbySearch = CZM_Rect(m_quick.x,m_lobbyCreate.y+actionHeight+actionGap,
		                         m_quick.w,actionHeight);
	}

	// The visible cards are also their touch targets; the gaps stay empty.
	y = H * 0.898f;
	int navMargin = H * 0.022f, navGap = H * 0.014f;
	int navWidth = ( W - navMargin * 2 - navGap * 4 ) / 5;
	for( int i = 0; i < 5; i++ )
		m_nav[i] = CZM_Rect( navMargin + i * ( navWidth + navGap ), y, navWidth, H - y - H * 0.016f );

	// panels
	if( m_overlay == OV_SETUP )
	{
		int pad = H * 0.03f;
		int pw = H * 0.86f, ph = H * 0.72f;
		int lineH = H * 0.075f, loginH = H * 0.062f;

		m_panel = CZM_Rect(( W - pw ) / 2, ( H - ph ) / 2, pw, ph );
		m_setupLang = CZM_Rect( m_panel.x + ( pw - H * 0.30f ) / 2, m_panel.y + ph * 0.27f, H * 0.30f, lineH );
		m_setupNick = CZM_Rect( m_panel.x + pad, m_panel.y + ph * 0.43f, pw - pad * 2, lineH );
		m_setupLogin = CZM_Rect( m_panel.x + ( pw - H * 0.56f ) / 2, m_panel.y + ph - pad - loginH, H * 0.56f, loginH );
		m_setupRegister = CZM_Rect( m_setupLogin.x, m_setupLogin.y - H * 0.014f - loginH, m_setupLogin.w, loginH );
		m_setupGo = CZM_Rect( m_panel.x + ( pw - H * 0.40f ) / 2, m_setupRegister.y - H * 0.022f - H * 0.085f, H * 0.40f, H * 0.085f );
	}
	else if( m_overlay == OV_QUIT )
	{
		int pad = H * 0.03f;
		int bh = H * 0.07f;
		int pw = H * 0.70f, ph = H * 0.27f;
		int bw;

		m_panel = CZM_Rect(( W - pw ) / 2, ( H - ph ) / 2, pw, ph );
		bw = ( pw - pad * 3 ) / 2;
		m_quitNo = CZM_Rect( m_panel.x + pad, m_panel.y + ph - pad - bh, bw, bh );
		m_quitYes = CZM_Rect( m_panel.x + pad * 2 + bw, m_quitNo.y, bw, bh );
	}
	else
	{
		bool about = m_overlay == OV_ABOUT, bell = m_overlay == OV_BELL;
		int pw = about || bell ? Q_min( (int)( H * 1.16f ), (int)( W * 0.80f )) : Q_min( (int)( H * 1.0f ), (int)( W * 0.62f ));
		int ph = H * ( about ? 0.74f : bell ? ( CZM_NewsCount() ? 0.72f : CZM_Update() ? 0.48f : 0.38f ) : 0.62f );
		int pad = H * 0.03f;
		int closeSize = H * 0.075f;
		int rowH = H * 0.062f, y;

		m_panel = CZM_Rect(( W - pw ) / 2, ( H - ph ) / 2, pw, ph );
		m_close = CZM_Rect( m_panel.x + pw - closeSize - H * 0.015f, m_panel.y + H * 0.015f, closeSize, closeSize );
		m_iPanelLineY = m_panel.y + pad * 0.8f + CZM_FontHeight( CZM_Font( CZMF_PANEL_TITLE )) + H * 0.02f;

		// About: logo, then the developer, the group, website, source code, version (five taps open the console), last update
		m_aboutLogo = CZM_Rect( m_panel.x + pad, m_iPanelLineY + H * 0.025f, pw - pad * 2, H * 0.075f );
		y = m_aboutLogo.y + m_aboutLogo.h + H * 0.015f;
		for( int i = 0; i < CZM_ABOUT_ROWS; i++ )
			m_aboutRows[i] = CZM_Rect( m_panel.x + pad, y + i * rowH, pw - pad * 2, rowH );
		m_version = m_aboutRows[4];

		// bell: the update card on top, the news under it
		m_update = CZM_Rect( m_panel.x + pad, m_iPanelLineY + H * 0.025f, pw - pad * 2, CZM_Update() ? (int)( H * 0.25f ) : 0 );
		m_updateButton = CZM_Rect( m_update.x + m_update.w - H * 0.03f - H * 0.36f, m_update.y + m_update.h - H * 0.03f - H * 0.08f,
			H * 0.36f, H * 0.08f );
	}
}

int CCzmMainMenu::HitTest( void ) const
{
	const int grow = ScreenHeight * 0.015f;

	if( !CZM_OnlinePlayAllowed() )
	{
		if( m_lang.HasCursor() ) return uiStatic.cursorX < m_lang.x + m_lang.w / 2 ? HIT_LANG_RU : HIT_LANG_EN;
		for( int i = 0; i < 6; ++i ) if( m_retire[i].HasCursor() ) return HIT_RETIRE + i;
		return HIT_PANEL;
	}

	if( m_overlay == OV_SETUP )
	{
		if( m_setupLang.HasCursor( ))
			return uiStatic.cursorX < m_setupLang.x + m_setupLang.w / 2 ? HIT_SETUP_RU : HIT_SETUP_EN;
		if( m_setupNick.HasCursor( ))
			return HIT_SETUP_NICK;
		if( m_setupGo.HasCursor( ))
			return HIT_SETUP_GO;
		if( m_setupLogin.HasCursor( ))
			return HIT_SETUP_LOGIN;
		if( m_setupRegister.HasCursor( ))
			return HIT_SETUP_REGISTER;
		return HIT_PANEL; // the window stays until the player finishes it
	}

	if( m_overlay != OV_NONE )
	{
		if( m_overlay == OV_QUIT )
		{
			if( m_quitYes.HasCursor( ))
				return HIT_QUIT_YES;
			if( m_quitNo.HasCursor( ))
				return HIT_QUIT_NO;
		}
		else
		{
			if( m_close.HasCursor( ))
				return HIT_CLOSE;
			if( m_overlay == OV_ABOUT && m_version.HasCursor( ))
				return HIT_VERSION;
			if( m_overlay == OV_ABOUT && m_aboutRows[0].HasCursor( ))
				return HIT_ABOUT_TELEGRAM;
			if( m_overlay == OV_ABOUT && m_aboutRows[1].HasCursor( ))
				return HIT_ABOUT_GROUP;
			if( m_overlay == OV_ABOUT && m_aboutRows[2].HasCursor( ))
				return HIT_ABOUT_SITE;
			if( m_overlay == OV_ABOUT && m_aboutRows[3].HasCursor( ))
				return HIT_ABOUT_SOURCE;
			if( m_overlay == OV_BELL && CZM_Update() && m_updateButton.Grown( grow ).HasCursor( ))
				return HIT_UPDATE;
		}

		return m_panel.HasCursor() ? HIT_PANEL : HIT_BACKDROP;
	}

	if( m_profile.Grown( grow ).HasCursor( ))
		return HIT_PROFILE;
	if( m_bell.Grown( grow ).HasCursor( ))
		return HIT_BELL;
	if( m_lang.Grown( grow ).HasCursor( ))
		return uiStatic.cursorX < m_lang.x + m_lang.w / 2 ? HIT_LANG_RU : HIT_LANG_EN;

	if( m_quick.Grown( grow ).HasCursor( ))
		return HIT_QUICK;
	if( m_lobbyCreate.Grown( grow ).HasCursor( ))
		return HIT_LOBBY_CREATE;
	if( m_lobbySearch.Grown( grow ).HasCursor( ))
		return HIT_LOBBY_SEARCH;

	for( int i = 0; i < m_iTiles; i++ )
	{
		if( m_tiles[i].HasCursor( ))
			return HIT_TILE + i;
	}

	for( int i = 0; i < 5; i++ )
	{
		if( m_nav[i].HasCursor( ))
			return HIT_NAV + i;
	}

	return HIT_NONE;
}

void CCzmMainMenu::Activate( int hit )
{
	if( hit == HIT_PANEL || hit == HIT_NONE )
		return;

	if( hit != HIT_VERSION )
		CZM_PlayClick();

	if( !CZM_OnlinePlayAllowed() && hit != HIT_LANG_RU && hit != HIT_LANG_EN )
	{
		switch( hit - HIT_RETIRE )
		{
		case 0: EngFuncs::ShellExecute( "https://counter-zombie.ru/#beta", NULL, false ); break;
		case 1: CZM_DistributionHelp( CZM_OnlineKey(), m_szNick ); break;
		case 2: CZM_AccountShow( CZM_OnlineKey(), m_szNick ); break;
		case 3: CZM_LayoutsShow(); break;
		case 4: CZM_DistributionShow( CZM_OnlineKey(), m_szNick ); break;
		case 5: EngFuncs::ClientCmd( false, "quit\n" ); break;
		}
		return;
	}

	switch( hit )
	{
	case HIT_PROFILE:
		CZM_OpenProfile( CZM_OnlinePlayer() );
		break;
	case HIT_NAV + 0:
		CZM_OpenChat();
		break;
	case HIT_NAV + 1:
		CZM_OpenFriends();
		break;
	case HIT_NAV + 2:
		CZM_OpenServerList();
		break;
	case HIT_NAV + 3:
		CZM_OpenSettings( CZM_TAB_LAST );
		break;
	case HIT_ABOUT_TELEGRAM:
		EngFuncs::ShellExecute( CZM_CONTACT_URL, NULL, false );
		break;
	case HIT_ABOUT_GROUP:
		EngFuncs::ShellExecute( CZM_GROUP_URL, NULL, false );
		break;
	case HIT_ABOUT_SITE:
		EngFuncs::ShellExecute( CZM_SITE_URL, NULL, false );
		break;
	case HIT_ABOUT_SOURCE:
		EngFuncs::ShellExecute( CZM_SOURCE_URL, NULL, false );
		break;
	case HIT_SETUP_RU:
	case HIT_SETUP_EN:
		CZM_SetLanguage( hit == HIT_SETUP_RU );
		break;
	case HIT_SETUP_NICK:
		m_nick.Begin( m_nick.text, m_setupNick );
		break;
	case HIT_SETUP_GO:
		FinishSetup();
		break;
	case HIT_LOBBY_CREATE:
		CZM_OpenLobbyCreate();
		break;
	case HIT_LOBBY_SEARCH:
		CZM_OpenLobbySearch();
		break;
	case HIT_QUICK:
		m_szQuickNote[0] = 0;
		if( CZM_QuickPlayActive( ))
			CZM_QuickPlayCancel();
		else
			CZM_QuickPlayStart();
		break;
	case HIT_SETUP_LOGIN:
		// the window closes by itself once the account signs in (CzmOnline finishes the first start)
		m_nick.End();
		CZM_AccountShow( CZM_OnlineKey(), "" );
		break;
	case HIT_SETUP_REGISTER:
		m_nick.End();
		CZM_AccountRegister( CZM_OnlineKey(), m_nick.text );
		break;
	case HIT_NAV + 4:
		m_overlay = OV_ABOUT;
		m_iVersionTaps = 0;
		break;
	case HIT_BELL:
		m_overlay = OV_BELL;
		CZM_NewsOpen();
		break;
	case HIT_UPDATE:
	{
		const CzmUpdateInfo *update = CZM_Update();
		int state;
		double done, total;
		char error[32];

		if( !update )
			break;
		if( update->store )
		{
			CZM_NetStoreUpdateStart();
			break;
		}
		CZM_UpdateState( &state, &done, &total, error, sizeof( error ));
		if( state == CZM_UPDATE_DOWNLOADING )
			CZM_UpdateCancel();
		else if( state == CZM_UPDATE_READY || state == CZM_UPDATE_PERMISSION )
			CZM_UpdateInstall();
		else if( state == CZM_UPDATE_IDLE || state == CZM_UPDATE_ERROR )
			CZM_UpdateStart( *update );
		break;
	}
	case HIT_LANG_RU:
		CZM_SetLanguage( true );
		break;
	case HIT_LANG_EN:
		CZM_SetLanguage( false );
		break;
	case HIT_BACKDROP:
	case HIT_CLOSE:
	case HIT_QUIT_NO:
		// the news seen in the bell are read
		if( m_overlay == OV_BELL && !CZM_NewsLoading( ))
			CZM_NewsMarkRead();
		m_overlay = OV_NONE;
		break;
	case HIT_QUIT_YES:
		EngFuncs::ClientCmd( false, "quit\n" );
		break;
	case HIT_VERSION:
	{
		double now = EngFuncs::DoubleTime();

		if( now - m_flVersionTapTime > 2.0 )
			m_iVersionTaps = 0;

		m_flVersionTapTime = now;
		if( ++m_iVersionTaps >= 5 )
		{
			m_iVersionTaps = 0;
			m_overlay = OV_NONE;
			CZM_OpenConsole();
		}
		break;
	}
	default:
		if( hit >= HIT_TILE && hit < HIT_TILE + m_iTiles )
		{
			int index = hit - HIT_TILE;

			if( index < CZM_ServerCount( ))
				CZM_ConnectToServer( index );   // a pinned server
			else
				CZM_OpenServerList();           // an empty slot: choose a server
		}
		break;
	}
}

void CCzmMainMenu::FinishSetup( void )
{
	m_nick.End();

	if( !CZM_NickIsValid( m_nick.text ))
	{
		m_bNickWarning = true;
		return;
	}

	CZM_SetNick( m_nick.text );
	CZM_FinishFirstStart();
	m_overlay = OV_NONE;
}

void CCzmMainMenu::Char( int key )
{
	m_nick.Char( key );
	m_bNickWarning = false;
}

bool CCzmMainMenu::KeyDown( int key )
{
	Layout();

	if( m_nick.active && m_nick.KeyDown( key ))
	{
		m_bNickWarning = false;
		return true;
	}

	if( UI::Key::IsLeftMouse( key ))
	{
		m_iPressed = HitTest();

		// a tap outside the field hides the keyboard
		if( m_nick.active && m_iPressed != HIT_SETUP_NICK )
			m_nick.End();
		return true;
	}

	if( !CZM_OnlinePlayAllowed() && UI::Key::IsEscape( key ) )
	{
		Activate( HIT_RETIRE + 5 );
		return true;
	}

	// the first start window stays until the player finishes it
	if( UI::Key::IsEscape( key ) && m_overlay == OV_SETUP )
	{
		m_nick.End();
		return true;
	}

	// Back on the phone: close a panel or ask before quitting
	if( UI::Key::IsEscape( key ))
	{
		m_overlay = ( m_overlay == OV_NONE ) ? OV_QUIT : OV_NONE;
		m_iPressed = HIT_NONE;
		EngFuncs::PlayLocalSound( uiStatic.sounds[SND_OUT] );
		return true;
	}

	return CMenuFramework::KeyDown( key );
}

bool CCzmMainMenu::KeyUp( int key )
{
	if( UI::Key::IsLeftMouse( key ))
	{
		int pressed = m_iPressed;
		int hit;

		Layout();
		hit = HitTest();
		m_iPressed = HIT_NONE;

		// act on release over the same element, a slide away cancels the tap
		if( hit != HIT_NONE && hit == pressed )
			Activate( hit );

		return true;
	}

	return CMenuFramework::KeyUp( key );
}

/*
Quick play: one tap and the game picks the best open zombie server (CzmServers.cpp).
A slow red glow breathes behind the button; while it searches, the play icon becomes a spinner.
*/
void CCzmMainMenu::DrawQuick( void )
{
    const CzmRect &r=m_quick;
    const double now=EngFuncs::DoubleTime();
    bool searching=CZM_QuickPlayActive();
    if(r.w<=r.h*2)return;
    if(searching){
        char name[64];
        if(CZM_QuickPlayFrame(name,sizeof(name))<0){
            Q_strncpy(m_szQuickNote,CZM_T("quick_none"),sizeof(m_szQuickNote));
            m_flQuickNote=now+6.0;
        }
        searching=CZM_QuickPlayActive();
    }
    CzmStyle::HomeAction(r,
        searching?(CZM_IsRussian()?"Ищем сервер…":"Finding a server…"):
                  (CZM_IsRussian()?"Быстрая игра":"Quick play"),
        searching?(CZM_IsRussian()?"Нажми, чтобы отменить":"Tap to cancel"):
                  (CZM_IsRussian()?"Подобрать сервер с игроками":"Find a server with players"),
        searching?UI_DIR "icon_refresh.png":UI_DIR "icon_play.png",
        CzmStyle::AccentRed(),true,IsPressed(HIT_QUICK));
    if(m_szQuickNote[0]&&now<m_flQuickNote)
        CZM_DrawText(CZM_Font(CZMF_SMALL),m_lobbySearch.x,
            m_lobbySearch.y+m_lobbySearch.h+H*.010f,m_lobbySearch.w,
            m_szQuickNote,PackRGBA(255,193,185,255));
}

void CCzmMainMenu::DrawTitle( void )
{
	int aspect = CZM_ImageAspect1000( "gfx/czm/title.png" );
	int h = H * 0.12f;
	int maxW = ( m_iTiles > 0 ? m_tiles[0].x : W ) - m_iMargin - H * 0.03f;

	if( aspect <= 0 || maxW <= 0 )
		return;

	if( h * aspect / 1000 > maxW )
		h = maxW * 1000 / aspect;

	CZM_DrawImage( "gfx/czm/title.png", m_iMargin, H * 0.165f, h * aspect / 1000, h );
}

void CCzmMainMenu::DrawHeader( void )
{
	HFont nickFont = CZM_Font( CZMF_NICK );
	HFont hintFont = CZM_Font( CZMF_SMALL );
	HFont langFont = CZM_Font( CZMF_LANG );
	bool profilePressed = IsPressed( HIT_PROFILE );
	int nickY, pencil, iconSize, unread, inset, segment, textY;
	bool russian = CZM_IsRussian();

	// avatar, nick, hint
	CZM_AvatarPending(); // a photo from the gallery may have just arrived
	CZM_DrawImage( CZM_CurrentAvatarImage(), m_avatar.x, m_avatar.y, m_avatar.w, m_avatar.h, profilePressed ? PackRGBA( 190, 190, 190, 255 ) : CZM_White());
	nickY = m_avatar.y + m_avatar.h * 0.04f;
	CZM_DrawText( nickFont, m_iNickX, nickY, m_iNickW, m_szNick, profilePressed ? CZM_Grey() : CZM_White());
	pencil = H * 0.028f;
	CZM_DrawImage( UI_DIR "icon_pencil.png", m_iNickX + m_iNickW + H * 0.012f, nickY + ( CZM_FontHeight( nickFont ) - pencil ) / 2,
		pencil, pencil, PackRGBA( 200, 205, 215, 255 ));
	CZM_DrawText( hintFont, m_iNickX, m_avatar.y + m_avatar.h * 0.62f, W * 0.4f, CZM_T( "nick_hint" ), CZM_Grey());

	// bell with the unread counter
	CZM_DrawImage( UI_DIR "chip_round.png", m_bell.x, m_bell.y, m_bell.w, m_bell.h, IsPressed( HIT_BELL ) ? PackRGBA( 170, 170, 170, 255 ) : CZM_White());
	iconSize = m_bell.h * 0.58f;
	CZM_DrawImage( UI_DIR "icon_bell.png", m_bell.x + ( m_bell.w - iconSize ) / 2, m_bell.y + ( m_bell.h - iconSize ) / 2, iconSize, iconSize );

	unread = UnreadNotifications();
	if( unread > 0 )
	{
		HFont badgeFont = CZM_Font( CZMF_SMALL );
		int d = m_bell.h * 0.44f;
		int bx = m_bell.x + m_bell.w - d * 3 / 4;
		int by = m_bell.y - d / 4;
		char count[8];

		snprintf( count, sizeof( count ), unread > 9 ? "9+" : "%d", unread );
		CZM_DrawImage( UI_DIR "dot.png", bx, by, d, d, PackRGBA( 239, 68, 68, 255 ));
		CZM_DrawText( badgeFont, bx, by + ( d - CZM_FontHeight( badgeFont )) / 2, d, count, CZM_White(), QM_CENTER );
	}

	// RU | EN
	CZM_DrawPill( UI_DIR "chip_lang.png", m_lang.x, m_lang.y, m_lang.w, m_lang.h );
	inset = m_lang.h * 0.09f;
	segment = m_lang.w / 2 - inset;
	CZM_DrawPill( UI_DIR "pill_lang_on.png", russian ? m_lang.x + inset : m_lang.x + m_lang.w / 2, m_lang.y + inset, segment, m_lang.h - inset * 2 );
	textY = m_lang.y + ( m_lang.h - CZM_FontHeight( langFont )) / 2;
	CZM_DrawText( langFont, m_lang.x + inset, textY, segment, "RU", russian ? CZM_White() : CZM_Grey(), QM_CENTER );
	CZM_DrawText( langFont, m_lang.x + m_lang.w / 2, textY, segment, "EN", russian ? CZM_Grey() : CZM_White(), QM_CENTER );
}

// a point on the rounded-rectangle border, s in [0, perim)
static void CZM_RoundRectPoint( const CzmRect &r, float rad, float s, float perim, float *ox, float *oy )
{
	const float HALF_PI = 1.5707963f, PI = 3.1415927f;
	float straightH = r.w - 2 * rad; // top and bottom
	float straightV = r.h - 2 * rad; // the sides
	float arc = HALF_PI * rad;       // a quarter circle
	float a;

	s = fmodf( s, perim );
	if( s < 0 )
		s += perim;

	if( s < straightH ) { *ox = r.x + rad + s; *oy = r.y; return; }
	s -= straightH;
	if( s < arc ) { a = -HALF_PI + ( s / arc ) * HALF_PI; *ox = r.x + r.w - rad + cosf( a ) * rad; *oy = r.y + rad + sinf( a ) * rad; return; }
	s -= arc;
	if( s < straightV ) { *ox = r.x + r.w; *oy = r.y + rad + s; return; }
	s -= straightV;
	if( s < arc ) { a = ( s / arc ) * HALF_PI; *ox = r.x + r.w - rad + cosf( a ) * rad; *oy = r.y + r.h - rad + sinf( a ) * rad; return; }
	s -= arc;
	if( s < straightH ) { *ox = r.x + r.w - rad - s; *oy = r.y + r.h; return; }
	s -= straightH;
	if( s < arc ) { a = HALF_PI + ( s / arc ) * HALF_PI; *ox = r.x + rad + cosf( a ) * rad; *oy = r.y + r.h - rad + sinf( a ) * rad; return; }
	s -= arc;
	if( s < straightV ) { *ox = r.x; *oy = r.y + r.h - rad - s; return; }
	s -= straightV;
	a = PI + ( s / arc ) * HALF_PI; *ox = r.x + rad + cosf( a ) * rad; *oy = r.y + rad + sinf( a ) * rad;
}

// a golden comet running along the tile border, so the tile asks to be tapped:
// a continuous fading trail (samples closer than their size never look like beads)
// and a soft glow around a white-hot head
static void CZM_TileLightning( const CzmRect &r, int index )
{
	const float TWO_PI = 6.2831853f;
	float rad = r.h * 0.16f;
	float perim = 2.0f * ( r.w + r.h ) - 8.0f * rad + TWO_PI * rad;
	float t = (float)EngFuncs::DoubleTime();
	float offset = index * perim * 0.41f;              // the three tiles are out of step
	float head = t * ( perim / 3.2f ) + offset;        // one loop every ~3.2 s
	float length = perim * 0.17f;                      // the tail
	float core = Q_max( 2.0f, r.h * 0.022f );          // line thickness at the head
	int samples = (int)( length / Q_max( 1.0f, core * 0.45f ));
	float x = 0, y = 0;

	samples = bound( 24, samples, 160 );

	// glow first, so the line stays crisp on top
	for( int k = samples; k >= 0; k -= 4 )
	{
		float f = 1.0f - (float)k / samples;           // 0 at the end of the tail, 1 at the head
		int g = (int)( core * ( 2.5f + 4.0f * f ));

		CZM_RoundRectPoint( r, rad, head - length * k / samples, perim, &x, &y );
		CZM_DrawImage( UI_DIR "glow.png", (int)x - g, (int)y - g, g * 2, g * 2, PackRGBA( 255, 170, 40, (int)( 70 * f * f )));
	}

	for( int k = samples; k >= 0; k-- )
	{
		float f = 1.0f - (float)k / samples;
		int sz = (int)( core * ( 0.35f + 0.85f * f ));
		int a = (int)( 250 * f * sqrtf( f ));

		if( sz < 2 )
			sz = 2;
		CZM_RoundRectPoint( r, rad, head - length * k / samples, perim, &x, &y );
		CZM_DrawImage( UI_DIR "dot.png", (int)x - sz / 2, (int)y - sz / 2, sz, sz,
			f > 0.92f ? PackRGBA( 255, 250, 228, a ) : PackRGBA( 255, 200, 70, a ));
	}

	// the head: a bright core in a wide warm halo
	CZM_RoundRectPoint( r, rad, head, perim, &x, &y );
	{
		int halo = (int)( core * 9.0f ), spark = (int)( core * 3.2f );

		CZM_DrawImage( UI_DIR "glow.png", (int)x - halo, (int)y - halo, halo * 2, halo * 2, PackRGBA( 255, 176, 50, 120 ));
		CZM_DrawImage( UI_DIR "glow.png", (int)x - spark, (int)y - spark, spark * 2, spark * 2, PackRGBA( 255, 252, 235, 255 ));
	}
}

void CCzmMainMenu::DrawTile( int index, CzmRect r )
{
	bool add = index >= CZM_ServerCount();
	CzmServer *server = add ? NULL : CZM_Server( index );
	HFont statusFont = CZM_Font( CZMF_TILE_STATUS );
	int margin = r.h / 10, rad = Q_max(5,(int)(H*.012f));
	char text[128];

	// pressed tiles sink a little
	if( IsPressed( HIT_TILE + index ))
	{
		int dx = r.w * 0.02f, dy = r.h * 0.02f;
		r = CZM_Rect( r.x + dx, r.y + dy, r.w - dx * 2, r.h - dy * 2 );
		rad = Q_max(5,(int)(H*.012f));
	}

	CzmStyle::Surface(r,PackRGBA(20,27,38,250));

	if( add )
	{
		// an empty slot: a soft card with a plus, taps into the server list
		bool pressed = IsPressed( HIT_TILE + index );
		int ps = r.h * 0.26f, cx = r.x + r.w / 2, cy = r.y + r.h * 0.40f;
		unsigned int tint = pressed ? CZM_White() : PackRGBA( 150, 200, 255, 255 );

		CzmStyle::Surface(r,PackRGBA(20,27,38,245));
		CZM_DrawImage( UI_DIR "chip_round.png", cx - ps / 2, cy - ps / 2, ps, ps );
		CZM_DrawImage( UI_DIR "icon_plus.png", cx - ps * 0.27f, cy - ps * 0.27f, ps * 0.54f, ps * 0.54f, tint );
		CZM_DrawText( CZM_Font( CZMF_TILE_TEXT ), r.x, r.y + r.h * 0.66f, r.w, CZM_T( "tile_add" ), PackRGBA( 220, 224, 232, 255 ), QM_CENTER );
		CZM_DrawText( CZM_Font( CZMF_SMALL ), r.x, r.y + r.h * 0.82f, r.w, CZM_T( "tile_add_hint" ), PackRGBA( 140, 146, 156, 255 ), QM_CENTER );
		return;
	}

	unsigned int accent = server->accent ? server->accent : PackRGBA( 124, 58, 237, 255 );

	// base card
	CzmStyle::Surface(r,PackRGBA(20,27,38,250));

	// the map picture as a thumbnail on the right, well inside the rounded corners
	{
		int coverH = r.h - rad * 2, coverW = coverH;
		int coverX = r.x + r.w - coverW - rad, coverY = r.y + rad;
		CzmStyle::MapPreview(CZM_Rect(coverX,coverY,coverW,coverH),server->map,server->name);

		// accent spine on the left edge
		UI_FillRect( r.x + rad * 0.6f, r.y + rad * 0.7f, Q_max( 3, (int)( r.w * 0.010f )), r.h - rad * 1.4f, accent );

		int textX = r.x + rad * 1.0f;
		int textW = coverX - textX - r.h * 0.08f;
		int statusY = r.y + r.h * 0.78f, dot = r.h * 0.07f, x, right = textX + textW;
		unsigned int dotColor;
		char name[128];

		CZM_CleanName( server->name, name, sizeof( name ));
		// Straight type and two measured lines keep actual server names readable.
		HFont titleFont = CZM_Font( CZMF_UI_ACTION );
		if( CZM_FontHeight( titleFont ) * 2 > r.h * 0.48f ) titleFont = CZM_Font( CZMF_SHOP_NAME );
		const char *title = name[0] ? name : server->address;
		char first[128];
		size_t best = 0, space = 0;
		for( size_t i = 0; title[i] && i < sizeof( first ) - 1; )
		{
			size_t next = i + 1;
			while( title[next] && ((unsigned char)title[next] & 0xc0) == 0x80 ) next++;
			if( next >= sizeof( first )) break;
			memcpy( first, title, next ); first[next] = 0;
			if( CZM_TextWidth( titleFont, first ) > textW ) break;
			best = next;
			if( title[i] == ' ' ) space = i;
			i = next;
		}
		if( title[best] && space ) best = space;
		memcpy( first, title, best ); first[best] = 0;
		int titleY = r.y + r.h * 0.07f, lineH = CZM_FontHeight( titleFont ) * 96 / 100;
		CZM_DrawText( titleFont, textX, titleY, textW, first, CZM_White());
		const char *second = title + best;
		while( *second == ' ' ) second++;
		if( *second ) CZM_DrawText( titleFont, textX, titleY + lineH, textW, second, PackRGBA( 232, 236, 242, 255 ));

		if( server->map[0] )
		{
			snprintf( text, sizeof( text ), "%s  %s", CZM_T( "lbl_map" ), server->map );
			CZM_DrawText( CZM_Font( CZMF_SMALL ), textX, r.y + r.h * 0.57f, textW, text, PackRGBA( 215, 220, 228, 255 ));
		}

		x = textX + dot + r.h * 0.05f;
		if( server->answerTime <= 0.0 && server->misses == 0 )
		{
			dotColor = PackRGBA( 150, 156, 166, 255 );
			CZM_DrawText( statusFont, x, statusY, right - x, CZM_T( "querying" ), CZM_Grey());
		}
		else if( server->answerTime <= 0.0 || server->misses >= 2 )
		{
			dotColor = PackRGBA( 248, 113, 113, 255 );
			CZM_DrawText( statusFont, x, statusY, right - x, CZM_T( "offline" ), PackRGBA( 248, 113, 113, 255 ));
		}
		else
		{
			bool full = server->maxplayers > 0 && server->players >= server->maxplayers;

			dotColor = full ? PackRGBA( 250, 204, 21, 255 ) : PackRGBA( 74, 222, 128, 255 );
			snprintf( text, sizeof( text ), "%d/%d %s", server->players, server->maxplayers, CZM_T( "in_game" ));
			CZM_DrawText( statusFont, x, statusY, right - x, text, CZM_White());
			x += CZM_TextWidth( statusFont, text );

			if( server->ping >= 0 && x < right )
			{
				CZM_DrawText( statusFont, x, statusY, right - x, "  ·  ", CZM_Grey());
				x += CZM_TextWidth( statusFont, "  ·  " );
				snprintf( text, sizeof( text ), "%d %s", server->ping, CZM_T( "ms" ));
				CZM_DrawText( statusFont, x, statusY, right - x, text, CZM_PingColor( server->ping ));
			}
		}
		CZM_DrawImage( UI_DIR "dot.png", textX, statusY + ( CZM_FontHeight( statusFont ) - dot ) / 2, dot, dot, dotColor );
	}

	// pinned heart in the top-right corner
	{
		int hs = r.h * 0.20f;

		CZM_DrawImage( UI_DIR "icon_heart_on.png", r.x + r.w - hs - rad * 0.5f, r.y + rad * 0.4f, hs, hs, PackRGBA( 244, 63, 94, 255 ));
	}

}

// Two clipped corners give the dock a clear silhouette without a stretched bitmap.
static void CZM_NavCard( const CzmRect &r, int cut, unsigned int color )
{
	UI_FillRect( r.x, r.y + cut, r.w, r.h - cut * 2, color );
	for( int n = 0; n < cut; n++ )
	{
		UI_FillRect( r.x, r.y + n, r.w - cut + n, 1, color );
		UI_FillRect( r.x + cut - n, r.y + r.h - n - 1, r.w - cut + n, 1, color );
	}
}

void CCzmMainMenu::DrawNav( void )
{
	static const char *icons[5] = { UI_DIR "icon_chat.png", UI_DIR "icon_users.png", UI_DIR "icon_globe.png", UI_DIR "icon_gear.png", UI_DIR "icon_info.png" };
	static const char *labels[5] = { "nav_chat", "nav_friends", "nav_servers", "nav_settings", "nav_about" };
	static const char *hints[5] = { "nav_chat_hint", "nav_friends_hint", "nav_servers_hint", "nav_settings_hint", "nav_about_hint" };
	HFont font = CZM_Font( CZMF_LANG ), small = CZM_Font( CZMF_SMALL );
	int edge = CZM_LineWidth(), pad = H * 0.018f, cut = Q_max( 3, (int)( H * 0.010f ));
	int badge = H * 0.062f, iconSize = H * 0.036f, chevron = H * 0.021f;
	int top = m_nav[0].y - H * 0.014f;
	int widest = 0;
	for( int i = 0; i < 5; i++ )
	{
		widest = Q_max( widest, CZM_TextWidth( font, CZM_T( labels[i] )));
		widest = Q_max( widest, CZM_TextWidth( small, CZM_T( hints[i] )));
	}
	bool horizontal = m_nav[0].w >= pad * 4 + badge + chevron + widest;

	CZM_DrawImage( UI_DIR "fade_top.png", 0, top, W, H - top, PackRGBA( 4, 7, 11, 230 ));

	for( int i = 0; i < 5; i++ )
	{
		const CzmRect &r = m_nav[i];
		bool pressed = IsPressed( HIT_NAV + i );
		unsigned int accent = PackRGBA( 239, 52, 67, 255 );
		unsigned int textColor = pressed ? CZM_White() : PackRGBA( 235, 239, 246, 255 );
		CZM_NavCard( CZM_Rect( r.x, r.y + edge * 3, r.w, r.h ), cut, PackRGBA( 0, 0, 0, 110 ));
		CZM_NavCard( r, cut, pressed ? accent : PackRGBA( 66, 76, 90, 230 ));
		CZM_NavCard( CZM_Rect( r.x + edge, r.y + edge, r.w - edge * 2, r.h - edge * 2 ), cut - edge,
			pressed ? PackRGBA( 47, 27, 35, 250 ) : PackRGBA( 15, 23, 33, 245 ));
		UI_FillRect( r.x + pad, r.y, r.w * 0.28f, edge * 2, accent );

		if( horizontal )
		{
			int badgeX = r.x + pad, badgeY = r.y + ( r.h - badge ) / 2;
			int textX = badgeX + badge + pad, textW = r.x + r.w - pad * 2 - chevron - textX;
			int textY = r.y + ( r.h - CZM_FontHeight( font ) - CZM_FontHeight( small ) - edge * 3 ) / 2;
			UI_FillRect( badgeX, badgeY, badge, badge, pressed ? PackRGBA( 144, 34, 49, 180 ) : PackRGBA( 38, 49, 64, 225 ));
			CZM_DrawImage( icons[i], badgeX + ( badge - iconSize ) / 2, badgeY + ( badge - iconSize ) / 2, iconSize, iconSize, textColor );
			CZM_DrawText( font, textX, textY, textW, CZM_T( labels[i] ), textColor );
			// the chat button shows how many players have the game open right now
			int online = i == 0 ? CZM_OnlineCount() : -1;
			if( online > 0 )
			{
				char text[48];
				int dot = CZM_FontHeight( small ) * 45 / 100, hy = textY + CZM_FontHeight( font ) + edge * 3;

				snprintf( text, sizeof( text ), CZM_T( "nav_chat_online" ), online );
				CZM_DrawImage( UI_DIR "glow.png", textX - dot / 2, hy + CZM_FontHeight( small ) / 2 - dot, dot * 2, dot * 2, PackRGBA( 74, 222, 128, 140 ));
				CZM_DrawImage( UI_DIR "dot.png", textX, hy + ( CZM_FontHeight( small ) - dot ) / 2, dot, dot, PackRGBA( 74, 222, 128, 255 ));
				CZM_DrawText( small, textX + dot * 2, hy, textW - dot * 2, text, PackRGBA( 134, 239, 172, 255 ));
			}
			else
				CZM_DrawText( small, textX, textY + CZM_FontHeight( font ) + edge * 3, textW, CZM_T( hints[i] ), PackRGBA( 147, 160, 180, 255 ));
			CZM_DrawImage( UI_DIR "icon_chevron.png", r.x + r.w - pad - chevron, r.y + ( r.h - chevron ) / 2,
				chevron, chevron, pressed ? accent : PackRGBA( 113, 128, 148, 255 ));
		}
		else
		{
			int compactIcon = H * 0.028f;
			HFont compactFont = CZM_Font( CZMF_NAV );
			int groupH = compactIcon + edge * 4 + CZM_FontHeight( compactFont );
			int iconY = r.y + ( r.h - groupH ) / 2;
			CZM_DrawImage( icons[i], r.x + ( r.w - compactIcon ) / 2, iconY, compactIcon, compactIcon, textColor );
			CZM_DrawText( compactFont, r.x + pad, iconY + compactIcon + edge * 4, r.w - pad * 2, CZM_T( labels[i] ), textColor, QM_CENTER );
		}
		if( i == 1 && CZM_SocialUnread() + CZM_SocialRequests() > 0 )
		{
			char count[16]; int n = CZM_SocialUnread() + CZM_SocialRequests();
			snprintf( count, sizeof( count ), n > 99 ? "99+" : "%d", n );
			int bw = H * 0.06f, bh = H * 0.029f;
			CZM_DrawPill( UI_DIR "button_primary.png", r.x + r.w - bw - pad, r.y + edge * 2, bw, bh );
			CZM_DrawText( small, r.x + r.w - bw - pad, r.y + edge * 2, bw, count, CZM_White(), QM_CENTER );
		}
	}
}

void CCzmMainMenu::DrawAbout( void )
{
	static const char *icons[CZM_ABOUT_ROWS] = { UI_DIR "icon_send.png", UI_DIR "icon_users.png", UI_DIR "icon_globe.png", UI_DIR "icon_code.png",
		UI_DIR "icon_tag.png", UI_DIR "icon_calendar.png", UI_DIR "icon_gear.png" };
	static const char *labels[CZM_ABOUT_ROWS] = { "about_tg", "about_group", "about_site", "about_source", "about_version", "about_updated", "about_engine" };
	HFont labelFont = CZM_Font( CZMF_PANEL_TEXT );
	HFont valueFont = CZM_Font( CZMF_TILE_STATUS );
	const CzmRect &logoRow = m_aboutLogo;
	int logo = logoRow.h;
	int textX = logoRow.x + logo + H * 0.03f;
	char date[32];

	CZM_DrawImage( UI_DIR "avatar.png", logoRow.x, logoRow.y, logo, logo );
	CZM_DrawText( CZM_Font( CZMF_NICK ), textX, logoRow.y + logo * 0.10f, logoRow.x + logoRow.w - textX, "Counter Zombie Mobile", CZM_White());
	CZM_DrawText( CZM_Font( CZMF_SMALL ), textX, logoRow.y + logo * 0.58f, logoRow.x + logoRow.w - textX, "32 players", CZM_Grey());

	BuildDate( date, sizeof( date ));

	for( int i = 0; i < CZM_ABOUT_ROWS; i++ )
	{
		const CzmRect &r = m_aboutRows[i];
		bool link = i <= 3;
		bool pressed = ( i == 0 && IsPressed( HIT_ABOUT_TELEGRAM )) || ( i == 1 && IsPressed( HIT_ABOUT_GROUP ))
			|| ( i == 2 && IsPressed( HIT_ABOUT_SITE )) || ( i == 3 && IsPressed( HIT_ABOUT_SOURCE ));
		int chip = r.h * 0.62f, icon = chip * 0.52f, chevron = r.h * 0.30f;
		int labelX = r.x + chip + H * 0.022f, valueRight = r.x + r.w - ( link ? chevron + H * 0.012f : 0 );
		const char *value;
		unsigned int valueColor = CZM_White();
		int valueW;

		switch( i )
		{
		case 0: value = "kuro.street.inc@gmail.com"; valueColor = PackRGBA( 125, 196, 255, 255 ); break;
		case 1: value = "t.me/counter_zombie_mobile"; valueColor = PackRGBA( 125, 196, 255, 255 ); break;
		case 2: value = "counter-zombie.ru"; valueColor = PackRGBA( 125, 196, 255, 255 ); break;
		case 3: value = "github.com/kurostreet/czm"; valueColor = PackRGBA( 125, 196, 255, 255 ); break;
		case 4: value = CZM_Version(); break;
		case 5: value = date; break;
		default: value = "Xash3D FWGS (GPL)"; break;
		}

		if( pressed )
			CZM_DrawSliced( UI_DIR "card.png", r.x - H * 0.012f, r.y + H * 0.004f, r.w + H * 0.024f, r.h - H * 0.008f, 30, (int)( H * 0.02f ));
		if( i > 0 )
			UI_FillRect( labelX, r.y, r.x + r.w - labelX, CZM_LineWidth(), CZM_White( 24 ));

		CZM_DrawImage( UI_DIR "chip_round.png", r.x, r.y + ( r.h - chip ) / 2, chip, chip );
		CZM_DrawImage( icons[i], r.x + ( chip - icon ) / 2, r.y + ( r.h - icon ) / 2, icon, icon, PackRGBA( 220, 224, 232, 255 ));

		// the value keeps its full width, the label gives way
		valueW = Q_min( CZM_TextWidth( valueFont, value ), ( valueRight - labelX ) * 3 / 5 );
		CZM_DrawText( labelFont, labelX, r.y + ( r.h - CZM_FontHeight( labelFont )) / 2, valueRight - valueW - H * 0.02f - labelX,
			CZM_T( labels[i] ), PackRGBA( 165, 172, 182, 255 ));
		CZM_DrawText( valueFont, valueRight - valueW, r.y + ( r.h - CZM_FontHeight( valueFont )) / 2, valueW + 2, value, valueColor, QM_RIGHT );

		if( link )
			CZM_DrawImage( UI_DIR "icon_chevron.png", r.x + r.w - chevron, r.y + ( r.h - chevron ) / 2, chevron, chevron, PackRGBA( 150, 156, 166, 255 ));
	}

	{
		const CzmRect &last = m_aboutRows[CZM_ABOUT_ROWS - 1];
		HFont small = CZM_Font( CZMF_SMALL );

		CZM_DrawText( small, m_panel.x, last.y + last.h + H * 0.022f, m_panel.w, CZM_T( "about_more" ), PackRGBA( 120, 126, 136, 255 ), QM_CENTER );
	}
}

void CCzmMainMenu::DrawBell( void )
{
	HFont textFont = CZM_Font( CZMF_PANEL_TEXT );
	HFont smallFont = CZM_Font( CZMF_SMALL );
	const unsigned int dim = PackRGBA( 165, 172, 182, 255 );
	const CzmUpdateInfo *update = CZM_Update();
	int pad = H * 0.03f, x = m_panel.x + pad, w = m_panel.w - pad * 2;
	int y = m_iPanelLineY + H * 0.025f, bottom = m_panel.y + m_panel.h - pad * 0.7f;
	int seen = (int)EngFuncs::GetCvarFloat( "czm_news_seen" );

	if( update )
	{
		const CzmRect &c = m_update;
		HFont nameFont = CZM_Font( CZMF_NICK );
		int state;
		double done, total;
		char error[32], text[160], size[32];
		const char *label;
		int starts[4], lines, ty;

		CZM_UpdateState( &state, &done, &total, error, sizeof( error ));
		CZM_DrawSliced( UI_DIR "card_on.png", c.x, c.y, c.w, c.h, 30, (int)( H * 0.022f ));

		double downloadSize = update->patchSize > 0 ? update->patchSize : update->size;
		if( state != CZM_UPDATE_IDLE && total > 0 )
			downloadSize = total;
		snprintf( size, sizeof( size ), "%.1f %s", downloadSize / 1048576.0, CZM_T( "mb" ));
		if( update->store && downloadSize <= 0 )
			size[0] = 0;	// Play did not say the size
		if( update->store )
			Q_strncpy( text, CZM_T( "upd_store_title" ), sizeof( text ));
		else
			snprintf( text, sizeof( text ), "%s %s", CZM_T( "upd_title" ), update->version );
		CZM_DrawText( nameFont, c.x + H * 0.03f, c.y + H * 0.022f, c.w - H * 0.06f - CZM_TextWidth( smallFont, size ) - H * 0.02f, text, CZM_White());
		CZM_DrawText( smallFont, c.x + c.w - H * 0.03f - CZM_TextWidth( smallFont, size ), c.y + H * 0.03f, CZM_TextWidth( smallFont, size ) + 2, size, dim );

		// what is new, up to three lines
		ty = c.y + H * 0.022f + CZM_FontHeight( nameFont ) + H * 0.01f;
		const char *notes = update->store ? CZM_T( "upd_store_notes" ) : update->notes;	// follows the language switch
		lines = CZM_WrapText( textFont, notes, c.w - H * 0.06f, starts, 3 );
		for( int l = 0; l < lines && ty + CZM_FontHeight( textFont ) < m_updateButton.y; l++ )
		{
			char line[512];

			CZM_WrapLine( notes, starts, l, line, sizeof( line ));
			CZM_DrawText( textFont, c.x + H * 0.03f, ty, c.w - H * 0.06f, line, PackRGBA( 220, 224, 232, 255 ));
			ty += CZM_FontHeight( textFont ) * 115 / 100;
		}

		// the button follows the download
		switch( state )
		{
		case CZM_UPDATE_DOWNLOADING:
		{
			int barX = c.x + H * 0.03f, barW = m_updateButton.x - H * 0.03f - barX;
			int barY = m_updateButton.y + m_updateButton.h / 2, barH = Q_max( 4, (int)( H * 0.01f ));
			int percent = total > 0 ? (int)( done * 100.0 / total ) : 0;

			UI_FillRect( barX, barY, barW, barH, CZM_White( 40 ));
			UI_FillRect( barX, barY, (int)( barW * bound( 0.0, total > 0 ? done / total : 0.0, 1.0 )), barH, PackRGBA( 239, 68, 68, 255 ));
			snprintf( text, sizeof( text ), CZM_T( "upd_downloading" ), percent );
			CZM_DrawText( smallFont, barX, barY - CZM_FontHeight( smallFont ) - H * 0.008f, barW, text, CZM_White());
			label = CZM_T( "upd_cancel" );
			break;
		}
		case CZM_UPDATE_VERIFYING:
			label = CZM_T( "upd_verifying" );
			break;
		case CZM_UPDATE_READY:
			label = CZM_T( "upd_install" );
			break;
		case CZM_UPDATE_INSTALLING:
			label = CZM_T( "upd_installing" );
			break;
		case CZM_UPDATE_PERMISSION:
			CZM_DrawText( smallFont, c.x + H * 0.03f, m_updateButton.y + ( m_updateButton.h - CZM_FontHeight( smallFont )) / 2,
				m_updateButton.x - c.x - H * 0.05f, CZM_T( "upd_permission" ), PackRGBA( 250, 204, 21, 255 ));
			label = CZM_T( "upd_install" );
			break;
		case CZM_UPDATE_ERROR:
			snprintf( text, sizeof( text ), "upd_error_%s", error[0] ? error : "network" );
			CZM_DrawText( smallFont, c.x + H * 0.03f, m_updateButton.y + ( m_updateButton.h - CZM_FontHeight( smallFont )) / 2,
				m_updateButton.x - c.x - H * 0.05f, CZM_T( text ), PackRGBA( 248, 113, 113, 255 ));
			label = CZM_T( "upd_download" );
			break;
		default:
			label = CZM_T( "upd_download" );
			break;
		}
		if( update->store )
			label = CZM_T( "upd_store_button" );

		CZM_DrawButton( state == CZM_UPDATE_DOWNLOADING ? UI_DIR "button_secondary.png" : UI_DIR "button_primary.png", m_updateButton, label,
			CZM_White(), IsPressed( HIT_UPDATE ));
		y = c.y + c.h + H * 0.03f;
	}

	// news, newest first
	if( !CZM_NewsCount( ))
	{
		const char *text = CZM_NewsLoading() ? CZM_T( "news_loading" ) : update ? "" : CZM_T( "bell_empty" );
		int iconSize = H * 0.10f;
		int middle = ( y + bottom ) / 2;

		if( !update )
			CZM_DrawImage( UI_DIR "icon_bell.png", m_panel.x + ( m_panel.w - iconSize ) / 2, middle - iconSize, iconSize, iconSize, CZM_White( 60 ));
		CZM_DrawText( textFont, x, update ? y : middle + H * 0.025f, w, text, dim, QM_CENTER );
		return;
	}

	for( int i = 0; i < CZM_NewsCount() && y < bottom; i++ )
	{
		const CzmNews *n = CZM_NewsItem( i );
		char date[32], line[1024];
		int starts[11], lines;
		time_t t = n->time;

		strftime( date, sizeof( date ), "%d.%m.%Y", localtime( &t ));
		if( n->id > seen )
			CZM_DrawImage( UI_DIR "dot.png", x, y + ( CZM_FontHeight( smallFont ) - H * 0.014f ) / 2, H * 0.014f, H * 0.014f, PackRGBA( 239, 68, 68, 255 ));
		CZM_DrawText( smallFont, x + ( n->id > seen ? H * 0.025f : 0 ), y, w, date, dim );
		y += CZM_FontHeight( smallFont ) + H * 0.006f;

		lines = CZM_WrapText( textFont, n->text, w, starts, 10 );
		for( int l = 0; l < lines && y + CZM_FontHeight( textFont ) <= bottom; l++ )
		{
			CZM_WrapLine( n->text, starts, l, line, sizeof( line ));
			CZM_DrawText( textFont, x, y, w, line, CZM_White());
			y += CZM_FontHeight( textFont ) * 115 / 100;
		}
		y += H * 0.025f;
	}
}

void CCzmMainMenu::DrawSetup( void )
{
	HFont titleFont = CZM_Font( CZMF_PANEL_TITLE );
	HFont textFont = CZM_Font( CZMF_PANEL_TEXT );
	HFont langFont = CZM_Font( CZMF_LANG );
	bool russian = CZM_IsRussian();
	int inset = m_setupLang.h * 0.09f;
	int segment = m_setupLang.w / 2 - inset;
	int textY;

	UI_FillRect( 0, 0, W, H, PackRGBA( 0, 0, 0, 190 ));
	CZM_DrawPanel( m_panel );

	CZM_DrawText( titleFont, m_panel.x, m_panel.y + m_panel.h * 0.10f, m_panel.w, CZM_T( "setup_title" ), CZM_White(), QM_CENTER );
	CZM_DrawText( textFont, m_panel.x, m_panel.y + m_panel.h * 0.10f + CZM_FontHeight( titleFont ) + H * 0.015f, m_panel.w,
		CZM_T( "setup_text" ), PackRGBA( 165, 172, 182, 255 ), QM_CENTER );

	// RU | EN, the same switch as in the header
	CZM_DrawPill( UI_DIR "chip_lang.png", m_setupLang.x, m_setupLang.y, m_setupLang.w, m_setupLang.h );
	CZM_DrawPill( UI_DIR "pill_lang_on.png", russian ? m_setupLang.x + inset : m_setupLang.x + m_setupLang.w / 2, m_setupLang.y + inset,
		segment, m_setupLang.h - inset * 2 );
	textY = m_setupLang.y + ( m_setupLang.h - CZM_FontHeight( langFont )) / 2;
	CZM_DrawText( langFont, m_setupLang.x + inset, textY, segment, "RU", russian ? CZM_White() : CZM_Grey(), QM_CENTER );
	CZM_DrawText( langFont, m_setupLang.x + m_setupLang.w / 2, textY, segment, "EN", russian ? CZM_Grey() : CZM_White(), QM_CENTER );

	CZM_DrawField( m_setupNick, m_nick, m_nick.text, CZM_T( "nick_placeholder" ), IsPressed( HIT_SETUP_NICK ));
	if( m_bNickWarning )
		CZM_DrawText( CZM_Font( CZMF_SMALL ), m_setupNick.x, m_setupNick.y + m_setupNick.h + H * 0.015f, m_setupNick.w,
			CZM_T( "nick_bad" ), PackRGBA( 248, 113, 113, 255 ), QM_CENTER );

	CZM_DrawButton( UI_DIR "button_primary.png", m_setupGo, CZM_T( "setup_go" ), CZM_White(), IsPressed( HIT_SETUP_GO ));
	CZM_DrawButton( UI_DIR "button_secondary.png", m_setupRegister, CZM_T( "setup_register" ), PackRGBA( 220, 224, 232, 255 ),
		IsPressed( HIT_SETUP_REGISTER ), CZMF_TILE_STATUS );
	CZM_DrawButton( UI_DIR "button_secondary.png", m_setupLogin, CZM_T( "setup_login" ), PackRGBA( 220, 224, 232, 255 ),
		IsPressed( HIT_SETUP_LOGIN ), CZMF_TILE_STATUS );
}

void CCzmMainMenu::DrawOverlay( void )
{
	HFont titleFont = CZM_Font( CZMF_PANEL_TITLE );
	int pad = H * 0.03f;
	int closeIcon;

	// signed in from the first window: the account already brought the nickname and settings
	if( m_overlay == OV_SETUP && !CZM_FirstStart( ))
	{
		m_nick.End();
		m_overlay = OV_NONE;
		return;
	}

	if( m_overlay == OV_SETUP )
	{
		DrawSetup();
		return;
	}

	UI_FillRect( 0, 0, W, H, PackRGBA( 0, 0, 0, 170 ));
	CZM_DrawPanel( m_panel );

	if( m_overlay == OV_QUIT )
	{
		int titleY = m_panel.y + ( m_quitNo.y - m_panel.y - CZM_FontHeight( titleFont )) / 2;

		CZM_DrawText( titleFont, m_panel.x + pad, titleY, m_panel.w - pad * 2, CZM_T( "quit_title" ), CZM_White(), QM_CENTER );
		CZM_DrawButton( UI_DIR "button_secondary.png", m_quitNo, CZM_T( "cancel" ), CZM_White(), IsPressed( HIT_QUIT_NO ));
		CZM_DrawButton( UI_DIR "button_primary.png", m_quitYes, CZM_T( "quit_yes" ), CZM_White(), IsPressed( HIT_QUIT_YES ));
		return;
	}

	// title, close button and a thin line under them
	CZM_DrawText( titleFont, m_panel.x + pad, m_panel.y + pad * 0.8f, m_close.x - m_panel.x - pad,
		CZM_T( m_overlay == OV_BELL ? "bell_title" : m_overlay == OV_CHAT ? "chat_title" : "about_title" ), CZM_White());
	closeIcon = m_close.h * 0.42f;
	CZM_DrawImage( UI_DIR "icon_close.png", m_close.x + ( m_close.w - closeIcon ) / 2, m_close.y + ( m_close.h - closeIcon ) / 2,
		closeIcon, closeIcon, IsPressed( HIT_CLOSE ) ? CZM_White() : PackRGBA( 190, 196, 206, 255 ));
	UI_FillRect( m_panel.x + pad, m_iPanelLineY, m_panel.w - pad * 2, CZM_LineWidth(), CZM_White( 30 ));

	if( m_overlay == OV_BELL )
	{
		DrawBell();
		return;
	}

	DrawAbout();
}

void CCzmMainMenu::DrawRetired( void )
{
	UI_FillRect( 0, 0, W, H, PackRGBA( 0, 0, 0, 165 ) );
	CZM_DrawPanel( CZM_Rect( W * 0.09f, H * 0.075f, W * 0.82f, H * 0.84f ) );
	HFont title = CZM_Font( CZMF_PANEL_TITLE ), text = CZM_Font( CZMF_PANEL_TEXT ), small = CZM_Font( CZMF_SMALL );
	CZM_DrawText( title, W * 0.13f, H * 0.12f, W * 0.74f, CZM_T( "retired_title" ), CZM_White(), QM_CENTER );
	const char *keys[] = { "retired_intro", "retired_step1", "retired_step2" };
	for( int i = 0; i < 3; ++i )
	{
		const char *value = CZM_T( keys[i] ); int starts[3];
		int lines = CZM_WrapText( text, value, W * 0.72f, starts, 2 );
		for( int l = 0; l < lines; ++l )
		{
			char line[512]; CZM_WrapLine( value, starts, l, line, sizeof( line ) );
			CZM_DrawText( text, W * 0.14f, H * ( 0.225f + i * 0.095f ) + l * CZM_FontHeight( text ), W * 0.72f,
				line, PackRGBA( 220, 225, 234, 255 ), i == 0 ? QM_CENTER : 0 );
		}
	}
	static const char *labels[] = { "retired_beta", "retired_help", "retired_account", "retired_layout", "retired_testing", "retired_exit" };
	for( int i = 0; i < 6; ++i )
		CZM_DrawButton( i == 0 ? UI_DIR "button_primary.png" : UI_DIR "button_secondary.png", m_retire[i], CZM_T( labels[i] ),
			CZM_White(), IsPressed( HIT_RETIRE + i ), CZMF_TILE_STATUS );
	CZM_DrawText( small, W * 0.13f, H * 0.86f, W * 0.74f, CZM_T( "retired_keep" ), CZM_Grey(), QM_CENTER );
	CzmRect ru = CZM_Rect( m_lang.x, m_lang.y, m_lang.w / 2, m_lang.h );
	CzmRect en = CZM_Rect( ru.x + ru.w, ru.y, ru.w, ru.h );
	CZM_DrawButton( UI_DIR "button_secondary.png", ru, "RU", CZM_IsRussian() ? CZM_White() : CZM_Grey(), IsPressed( HIT_LANG_RU ), CZMF_SMALL );
	CZM_DrawButton( UI_DIR "button_secondary.png", en, "EN", CZM_IsRussian() ? CZM_Grey() : CZM_White(), IsPressed( HIT_LANG_EN ), CZMF_SMALL );
}

void CCzmMainMenu::Draw()
{
	Layout();
	if( !CZM_OnlinePlayAllowed() )
	{
		DrawRetired();
		CZM_StartupReady();
		return;
	}

	// darker top edge so the header reads on any art
	CZM_DrawImage( UI_DIR "fade_top.png", 0, 0, W, H * 0.22f, CZM_White( 200 ));

	// Quiet the artwork under the actions while preserving the central character.
	CZM_DrawImage("gfx/czm/fade_left.png",0,0,W*.58f,H,CZM_White(185));
	DrawTitle();
	DrawQuick();
    CzmStyle::HomeAction(m_lobbyCreate,
        CZM_IsRussian()?"Создать лобби":"Create lobby",
        CZM_IsRussian()?"Собрать свою команду":"Bring your team together",
        UI_DIR "icon_users.png",CzmStyle::AccentBlue(),false,IsPressed(HIT_LOBBY_CREATE));
    CzmStyle::HomeAction(m_lobbySearch,
        CZM_IsRussian()?"Поиск лобби":"Find lobby",
        CZM_IsRussian()?"Присоединиться к команде":"Join an open team",
        UI_DIR "icon_search.png",CzmStyle::AccentGold(),false,IsPressed(HIT_LOBBY_SEARCH));

	for( int i = 0; i < m_iTiles; i++ )
		DrawTile( i, m_tiles[i] );
	DrawNav();
	DrawHeader();

	if( m_overlay != OV_NONE )
		DrawOverlay();
	CZM_StartupReady();
}

/*
=================
CCzmPauseMenu

Small window over the game: resume, settings, leave to the main screen.
=================
*/
class CCzmPauseMenu : public CMenuFramework
{
public:
	CCzmPauseMenu();

	void Show() override;
	void Draw() override;
	bool KeyDown( int key ) override;
	bool KeyUp( int key ) override;

private:
	enum EHit
	{
		HIT_NONE = 0,
		HIT_RESUME,
		HIT_SETTINGS,
		HIT_LEAVE,
	};

	void Layout( void );
	int HitTest( void ) const;
	bool IsPressed( int hit ) const { return m_iPressed == hit && HitTest() == hit; }
	void Activate( int hit );

	int m_iPressed;
	CzmRect m_panel, m_resume, m_settings, m_leave;
};

CCzmPauseMenu::CCzmPauseMenu() : CMenuFramework( "CzmPause" )
{
	m_iPressed = HIT_NONE;
}

void CCzmPauseMenu::Show()
{
	m_iPressed = HIT_NONE;
	CMenuFramework::Show();
}

void CCzmPauseMenu::Layout( void )
{
	const int W = ScreenWidth, H = ScreenHeight;
	int pw = H * 0.66f, ph = H * 0.48f;
	int bw, bh, y, gap;

	m_panel = CZM_Rect(( W - pw ) / 2, ( H - ph ) / 2, pw, ph );
	bw = pw * 0.78f;
	bh = ph * 0.15f;
	gap = ph * 0.05f;
	y = m_panel.y + ph * 0.34f;

	m_resume = CZM_Rect(( W - bw ) / 2, y, bw, bh );
	m_settings = CZM_Rect( m_resume.x, y + bh + gap, bw, bh );
	m_leave = CZM_Rect( m_resume.x, y + ( bh + gap ) * 2, bw, bh );
}

int CCzmPauseMenu::HitTest( void ) const
{
	if( m_resume.HasCursor( ))
		return HIT_RESUME;
	if( m_settings.HasCursor( ))
		return HIT_SETTINGS;
	if( m_leave.HasCursor( ))
		return HIT_LEAVE;
	return HIT_NONE;
}

bool CCzmPauseMenu::KeyDown( int key )
{
	Layout();

	if( UI::Key::IsLeftMouse( key ))
	{
		m_iPressed = HitTest();
		return true;
	}

	// Back again returns to the game
	if( UI::Key::IsEscape( key ))
	{
		m_iPressed = HIT_NONE;
		UI_CloseMenu();
		return true;
	}

	return CMenuFramework::KeyDown( key );
}

bool CCzmPauseMenu::KeyUp( int key )
{
	if( UI::Key::IsLeftMouse( key ))
	{
		int pressed = m_iPressed;
		int hit;

		Layout();
		hit = HitTest();
		m_iPressed = HIT_NONE;

		if( hit != HIT_NONE && hit == pressed )
			Activate( hit );

		return true;
	}

	return CMenuFramework::KeyUp( key );
}

void CCzmPauseMenu::Draw()
{
	const int H = ScreenHeight;
	HFont titleFont = CZM_Font( CZMF_PANEL_TITLE );
	HFont textFont = CZM_Font( CZMF_PANEL_TEXT );
	const char *mode = EngFuncs::GetCvarString( "czm_connect_name" );
	const char *map = EngFuncs::GetCvarString( "czm_loading_map" );
	char subtitle[160];

	Layout();
	CZM_DrawPanel( m_panel );

	CZM_DrawText( titleFont, m_panel.x, m_panel.y + m_panel.h * 0.13f - CZM_FontHeight( titleFont ) / 2, m_panel.w,
		CZM_T( "pause" ), CZM_White(), QM_CENTER );

	// mode and map
	if( !mode || !mode[0] )
		mode = EngFuncs::GetCvarString( "czm_loading_host" );
	if( !map || !map[0] )
		map = gpGlobals->maptitle;

	if( mode && mode[0] && map && map[0] )
		snprintf( subtitle, sizeof( subtitle ), "%s  ·  %s", mode, map );
	else
		snprintf( subtitle, sizeof( subtitle ), "%s", ( mode && mode[0] ) ? mode : ( map ? map : "" ));

	CZM_DrawText( textFont, m_panel.x + H * 0.03f, m_panel.y + m_panel.h * 0.24f - CZM_FontHeight( textFont ) / 2,
		m_panel.w - H * 0.06f, subtitle, PackRGBA( 165, 172, 182, 255 ), QM_CENTER );

	CZM_DrawButton( UI_DIR "button_primary.png", m_resume, CZM_T( "resume" ), CZM_White(), IsPressed( HIT_RESUME ));
	CZM_DrawButton( UI_DIR "button_secondary.png", m_settings, CZM_T( "settings" ), CZM_White(), IsPressed( HIT_SETTINGS ));
	CZM_DrawButton( UI_DIR "button_danger.png", m_leave, CZM_T( "to_menu" ), PackRGBA( 255, 150, 150, 255 ), IsPressed( HIT_LEAVE ));
}

/*
=================
registration

UI_Main_Menu is what the engine opens: the pause window in the game, the main screen otherwise.
=================
*/
ADD_MENU( menu_czmmain, CCzmMainMenu, UI_CzmMain_Menu );
ADD_MENU( menu_czmpause, CCzmPauseMenu, UI_CzmPause_Menu );
ADD_MENU4( menu_main, NULL, UI_Main_Menu, NULL );

void UI_Main_Menu( void )
{
	if( CL_IsActive( ))
		UI_CzmPause_Menu();
	else
		UI_CzmMain_Menu();
}

void CCzmPauseMenu::Activate( int hit )
{
	CZM_PlayClick();

	switch( hit )
	{
	case HIT_RESUME:
		UI_CloseMenu();
		break;
	case HIT_SETTINGS:
		CZM_OpenSettings( CZM_TAB_LAST );
		break;
	case HIT_LEAVE:
		EngFuncs::ClientCmd( false, "disconnect\n" );
		// the disconnect runs on the next frame, open the main screen directly
		UI_CzmMain_Menu();
		break;
	}
}
