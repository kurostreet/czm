/*
CzmTouch.cpp - Counter Zombie Mobile touch button layouts and the layout editor
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
#include "Utils.h"
#include "Framework.h"
#include "Scissor.h"
#include "keydefs.h"
#include "CzmMenu.h"
#include "../../common/czm_hud_paint.h"
#include "../../common/czm_hud_overlay.h"

#define UI_DIR "gfx/czm/ui/"
#define TOUCH_DIR "gfx/czm/touch/"
#define CZM_SCHEMES 3
#define CZM_MAX_BUTTONS 80
#define TOUCH_FLAG_HIDE     ( 1 << 0 )
#define TOUCH_FLAG_NOEDIT   ( 1 << 1 )
#define TOUCH_FLAG_DEF_HIDE ( 1 << 6 ) // saved hidden even after "More" showed it

/*
=================
actions a player can put on a button
=================
*/
enum
{
	GROUP_COMBAT = 0,
	GROUP_MOVE,
	GROUP_BUY,
	GROUP_TALK,
	GROUP_SERVER,
	GROUP_MENU,
	GROUP_CUSTOM,
	GROUP_COUNT
};

static const struct
{
	const char *ru, *en;
} s_groups[GROUP_COUNT] =
{
	{ "Бой", "Combat" },
	{ "Движение", "Movement" },
	{ "Покупка", "Buying" },
	{ "Общение", "Talk" },
	{ "Сервер", "Server" },
	{ "Меню", "Menus" },
	{ "Своё", "Custom" },
};

struct CzmAction
{
	const char *icon;
	const char *ru, *en;
	const char *command;
	int group;
};

static const CzmAction s_actions[] =
{
	// combat
	{ "fire", "Огонь", "Fire", "+attack", GROUP_COMBAT },
	{ "scope", "Прицел", "Aim", "+attack2", GROUP_COMBAT },
	{ "reload", "Перезарядка", "Reload", "+reload", GROUP_COMBAT },
	{ "use", "Использовать", "Use", "+use", GROUP_COMBAT },
	{ "rifle", "Основное", "Primary", "slot1", GROUP_COMBAT },
	{ "pistol", "Пистолет", "Pistol", "slot2", GROUP_COMBAT },
	{ "knife", "Нож", "Knife", "slot3", GROUP_COMBAT },
	{ "grenade", "Граната", "Grenade", "slot4", GROUP_COMBAT },
	{ "lastinv", "Прошлое оружие", "Last weapon", "lastinv", GROUP_COMBAT },
	{ "wheel", "Колесо оружия", "Weapon wheel", "_czmwheel weapons", GROUP_COMBAT },
	{ "invnext", "Следующее оружие", "Next weapon", "invnext", GROUP_COMBAT },
	{ "invprev", "Предыдущее оружие", "Previous weapon", "invprev", GROUP_COMBAT },
	{ "drop", "Выбросить", "Drop", "drop", GROUP_COMBAT },
	{ "flashlight", "Фонарик", "Flashlight", "impulse 100", GROUP_COMBAT },
	{ "nightvision", "Ночное видение", "Night vision", "nightvision", GROUP_COMBAT },
	{ "spray", "Спрей", "Spray", "impulse 201", GROUP_COMBAT },
	// movement
	{ "jump", "Прыжок", "Jump", "+jump", GROUP_MOVE },
	{ "duck", "Присесть", "Crouch", "+duck", GROUP_MOVE },
	{ "duck_toggle", "Присесть (вкл/выкл)", "Crouch toggle", "crouchtoggle", GROUP_MOVE },
	{ "duckjump", "Прыжок с приседом", "Crouch jump", "+czm_duckjump", GROUP_MOVE },
	{ "walk", "Тихий шаг", "Walk", "+speed", GROUP_MOVE },
	{ "autorun", "Автобег", "Auto run", "czm_autorun", GROUP_MOVE },
	{ "forward", "Вперёд (держать)", "Forward (hold)", "+forward", GROUP_MOVE },
	{ "back", "Назад (держать)", "Back (hold)", "+back", GROUP_MOVE },
	{ "left", "Влево (держать)", "Left (hold)", "+moveleft", GROUP_MOVE },
	{ "right", "Вправо (держать)", "Right (hold)", "+moveright", GROUP_MOVE },
	{ "ddrun", "Двойной присед (свайп)", "Double duck (swipe)", "_wheel czm_dd czm_dd", GROUP_MOVE },
	// buying
	{ "buy", "Покупка", "Buy menu", "buy", GROUP_BUY },
	{ "ammo1", "Патроны к основному", "Primary ammo", "buyammo1", GROUP_BUY },
	{ "ammo2", "Патроны к пистолету", "Pistol ammo", "buyammo2", GROUP_BUY },
	{ "armor", "Броня с каской", "Armor and helmet", "vesthelm", GROUP_BUY },
	{ "autobuy", "Автозакупка", "Auto buy", "autobuy", GROUP_BUY },
	{ "rebuy", "Повторить закупку", "Rebuy", "rebuy", GROUP_BUY },
	// talk
	{ "chat", "Чат", "Chat", "messagemode", GROUP_TALK },
	{ "teamchat", "Командный чат", "Team chat", "messagemode2", GROUP_TALK },
	{ "voice", "Голос", "Voice", "+voicerecord", GROUP_TALK },
	{ "radio", "Колесо рации", "Radio wheel", "showvguimenu 38", GROUP_TALK },
	{ "radio1", "Рация: команды", "Radio: commands", "radio1", GROUP_TALK },
	{ "radio2", "Рация: группа", "Radio: group", "radio2", GROUP_TALK },
	{ "radio3", "Рация: ответы", "Radio: replies", "radio3", GROUP_TALK },
	{ "score", "Счёт", "Score", "+showscores", GROUP_TALK },
	// server chat commands, the usual ones on zombie servers
	{ "zpmenu", "Меню зомби", "Zombie menu", "say /zpmenu", GROUP_SERVER },
	{ "servermenu", "Меню сервера", "Server menu", "say /menu", GROUP_SERVER },
	{ "unstuck", "Застрял", "Unstuck", "say /unstuck", GROUP_SERVER },
	{ "rs", "Сброс счёта", "Reset score", "say /rs", GROUP_SERVER },
	{ "rtv", "Голосовать за карту", "Rock the vote", "say rtv", GROUP_SERVER },
	{ "top", "Топ игроков", "Top players", "say /top15", GROUP_SERVER },
	{ "rank", "Мой ранг", "My rank", "say /rank", GROUP_SERVER },
	{ "vip", "VIP", "VIP", "say /vip", GROUP_SERVER },
	{ "timeleft", "Сколько осталось", "Time left", "say timeleft", GROUP_SERVER },
	{ "nextmap", "Следующая карта", "Next map", "say nextmap", GROUP_SERVER },
	{ "kill", "Kill (если застрял)", "Kill (if stuck)", "kill", GROUP_SERVER },
	// menus
	{ "more", "Ещё", "More", "czm_more", GROUP_MENU },
	{ "numbers", "Цифры меню", "Menu digits", "exec touch_default/numbers.cfg", GROUP_MENU },
	{ "num1", "1", "1", "slot1", GROUP_MENU },
	{ "num2", "2", "2", "slot2", GROUP_MENU },
	{ "num3", "3", "3", "slot3", GROUP_MENU },
	{ "num4", "4", "4", "slot4", GROUP_MENU },
	{ "num5", "5", "5", "slot5", GROUP_MENU },
	{ "num6", "6", "6", "slot6", GROUP_MENU },
	{ "num7", "7", "7", "slot7", GROUP_MENU },
	{ "num8", "8", "8", "slot8", GROUP_MENU },
	{ "num9", "9", "9", "slot9", GROUP_MENU },
	{ "num0", "0", "0", "slot10", GROUP_MENU },
	{ "cancel", "Меню / закрыть", "Menu / close", "cancelselect", GROUP_MENU },
	{ "team", "Сменить команду", "Change team", "chooseteam", GROUP_MENU },
	{ "screenshot", "Скриншот", "Screenshot", "snapshot", GROUP_MENU },
	{ "edit", "Настроить кнопки", "Edit buttons", "menu_czmtouch", GROUP_MENU },
};

#define CZM_ACTIONS ( (int)( sizeof( s_actions ) / sizeof( s_actions[0] )))

// all icons, for the icon picker
static const char *s_icons[] =
{
	"fire", "scope", "reload", "use", "rifle", "pistol", "knife", "grenade", "lastinv", "invnext", "invprev", "drop",
	"flashlight", "nightvision", "spray", "jump", "duck", "duck_toggle", "duckjump", "walk", "autorun", "forward", "back",
	"left", "right", "buy", "ammo1", "ammo2", "armor", "autobuy", "rebuy", "chat", "teamchat", "voice", "radio",
	"radio1", "radio2", "radio3", "score", "zpmenu", "servermenu", "unstuck", "rs", "rtv", "top", "rank", "vip",
	"timeleft", "nextmap", "more", "numbers", "num1", "num2", "num3", "num4", "num5", "num6", "num7", "num8", "num9",
	"num0", "cancel", "team", "screenshot", "edit", "custom", "ddrun", "kill", "wheel",
};

#define CZM_ICONS ( (int)( sizeof( s_icons ) / sizeof( s_icons[0] )))

static const char *ActionLabel( const CzmAction &action )
{
	return CZM_IsRussian() ? action.ru : action.en;
}

static const char *IconPath( const char *icon )
{
	static char path[96];

	snprintf( path, sizeof( path ), TOUCH_DIR "%s.png", icon );
	return path;
}

/*
=================
schemes
=================
*/
static void SchemePath( int scheme, char *buf, size_t size )
{
	snprintf( buf, size, "touch_profiles/czm_scheme%d.cfg", scheme );
}

// writes the buttons as they are now into the current touch config;
// touch_writeconfig only writes after the stock editor was opened, export always does
void CZM_SaveTouchConfig( void )
{
	char path[128];

	Q_strncpy( path, EngFuncs::GetCvarString( "touch_config_file" ), sizeof( path ));
	if( !path[0] || strchr( path, '"' ))
		return;

	EngFuncs::ClientCmdF( true, "touch_exportconfig \"%s\"\n", path );
}

int CZM_TouchScheme( void )
{
	int scheme = (int)EngFuncs::GetCvarFloat( "czm_touch_scheme" );
	return bound( 1, scheme, CZM_SCHEMES );
}

// makes the scheme the active touch config; the default layout if the player never saved it or asked to reset
void CZM_SetTouchScheme( int scheme, bool fromPreset )
{
	char path[64];

	scheme = bound( 1, scheme, CZM_SCHEMES );
	SchemePath( scheme, path, sizeof( path ));

	if( fromPreset || !EngFuncs::FileExists( path, true ))
	{
		EngFuncs::ClientCmdF( true, "exec touch_presets/czm_scheme%d.cfg\n", scheme );
		EngFuncs::CvarSetString( "touch_config_file", path );
		CZM_SaveTouchConfig();
	}
	else
	{
		EngFuncs::CvarSetString( "touch_config_file", path );
		EngFuncs::ClientCmdF( true, "exec \"%s\"\n", path );
	}

	// "More" starts closed on the new buttons
	EngFuncs::ClientCmd( true, "alias czm_more czm_more_show\n" );

	EngFuncs::CvarSetValue( "czm_touch_scheme", scheme );
}

void CZM_TouchStartup( void )
{
	// the first start with these layouts replaces the old stock buttons
	if( EngFuncs::GetCvarFloat( "czm_touch_version" ) < 1.0f )
	{
		CZM_SetTouchScheme( 1, true );
		EngFuncs::CvarSetValue( "czm_touch_version", 1.0f );
		EngFuncs::ClientCmd( false, "host_writeconfig\n" );
	}
}

/*
=================
layout data
=================
*/
struct CzmTouchButton
{
	char name[32];
	char texture[64];
	char command[128];
	float x1, y1, x2, y2;
	int color[4];
	int flags;
};

static bool ButtonEditable( const CzmTouchButton &b )
{
	// _move and _look are the walk and look zones; _wheel is a swipe button and _czmwheel a wheel of
	// choices, both the player's own
	if( b.command[0] == '_' && strncmp( b.command, "_wheel ", 7 ) && strncmp( b.command, "_hwheel ", 8 )
		&& strncmp( b.command, "_czmwheel ", 10 ))
		return false;
	return b.texture[0] && b.texture[0] != '#' && !( b.flags & TOUCH_FLAG_NOEDIT );
}

// the action a button runs, NULL for commands we do not know
static const CzmAction *FindAction( const CzmTouchButton &b )
{
	const char *icon = strrchr( b.texture, '/' );

	icon = icon ? icon + 1 : b.texture;

	// digits share commands with weapon slots, the icon tells them apart
	for( int i = 0; i < CZM_ACTIONS; i++ )
	{
		if( !stricmp( s_actions[i].command, b.command ) && !stricmp( s_actions[i].icon, icon ))
			return &s_actions[i];
	}

	for( int i = 0; i < CZM_ACTIONS; i++ )
	{
		if( !stricmp( s_actions[i].command, b.command ))
			return &s_actions[i];
	}

	return NULL;
}

static const char *ButtonLabel( const CzmTouchButton &b )
{
	const CzmAction *action = FindAction( b );

	if( action )
		return ActionLabel( *action );

	if( !strncmp( b.command, "say ", 4 ))
		return b.command + 4;

	return b.command;
}

/*
=================
match HUD

The HUD blocks are edited on the same screen as the buttons, so the player sees what
covers what. The HUD is one for all button schemes and lives in the czm_hud_* cvars.
=================
*/
#define HUD_ATLAS "gfx/czm/hud_glyphs.tga"
#define HUD_STYLES 3
#define HUD_BLOCKS CzmHud::BLOCKS // the text blocks and the radar
static_assert( HUD_STYLES == CzmHud::RADAR_STYLES && HUD_STYLES == CzmHud::MSG_STYLES, "one row of style buttons serves every block" );

struct CzmHudBlock
{
	float x, y;          // centre, share of the screen
	float scale, opacity;
	bool hidden;         // taken off the screen; "Hidden" in the bar shows it again
};

static const struct
{
	const char *ru, *en;
} s_hudNames[HUD_BLOCKS] =
{
	{ "Жизни", "Health" },
	{ "Броня", "Armor" },
	{ "Время", "Round time" },
	{ "Деньги", "Money" },
	{ "Патроны", "Ammo" },
	{ "Радар", "Radar" },
	{ "Чат", "Chat" },
	{ "Сообщения сервера", "Server messages" },
	{ "Загрузка файлов", "Downloads" },
}, s_hudStyles[HUD_STYLES] =
{
	{ "Классический", "Classic" },
	{ "Компактный", "Compact" },
	{ "CZM", "CZM" },
}, s_radarStyles[CzmHud::RADAR_STYLES] =
{
	{ "Классический", "Classic" },
	{ "Тактический", "Tactical" },
	{ "Минимал", "Minimal" },
}, s_msgStyles[CzmHud::MSG_STYLES] =
{
	{ "Классический", "Classic" },
	{ "CZM", "CZM" },
	{ "Контур", "Outline" },
}, s_specStyles[CzmHud::SPEC_STYLES] =
{
	{ "Минимал", "Minimal" },
	{ "Карточка", "Card" },
	{ "Кино", "Cinema" },
};

const char *CZM_SpectatorStyleName( int style )
{
	style = bound( 0, style, CzmHud::SPEC_STYLES - 1 );
	return CZM_IsRussian() ? s_specStyles[style].ru : s_specStyles[style].en;
}

const char *CZM_MessageStyleName( int style )
{
	style = bound( 0, style, CzmHud::MSG_STYLES - 1 );
	return CZM_IsRussian() ? s_msgStyles[style].ru : s_msgStyles[style].en;
}

static const char *HudName( int kind )
{
	return CZM_IsRussian() ? s_hudNames[kind].ru : s_hudNames[kind].en;
}

const char *CZM_RadarStyleName( int style )
{
	style = bound( 0, style, CzmHud::RADAR_STYLES - 1 );
	return CZM_IsRussian() ? s_radarStyles[style].ru : s_radarStyles[style].en;
}

static float HudField( const CzmHudBlock &block, int field )
{
	switch( field )
	{
	case 0: return block.x;
	case 1: return block.y;
	case 2: return block.scale;
	case 3: return block.opacity;
	default: return block.hidden ? 1.0f : 0.0f;
	}
}

static float HudMinScale( int kind )
{
	return kind == CzmHud::RADAR ? CzmHud::radarMinScale : kind == CzmHud::CHAT || kind == CzmHud::MESSAGES || kind == CzmHud::DOWNLOADS ? 0.6f : 0.65f;
}
static float HudMaxScale( int kind )
{
	return kind == CzmHud::RADAR ? CzmHud::radarMaxScale : kind == CzmHud::MESSAGES ? 1.0f : 1.6f;
}

// the chat line as the match draws it with the console font: its height follows "Text size"
static float ChatLineHeight( int screenHeight )
{
	float scale = EngFuncs::GetCvarFloat( "con_fontscale" );
	return screenHeight * 0.0168f * bound( 1.0f, scale, 3.0f );
}

// the same limits as the game HUD uses when it draws
static CzmHudBlock HudClamp( int kind, CzmHudBlock b )
{
	b.x = CzmHud::Clamp( b.x, 0.01f, 0.99f, CzmHud::defaults[kind][0] );
	b.y = CzmHud::Clamp( b.y, 0.01f, 0.99f, CzmHud::defaults[kind][1] );
	b.scale = CzmHud::Clamp( b.scale, HudMinScale( kind ), HudMaxScale( kind ), CzmHud::defaultScale[kind] );
	b.opacity = CzmHud::Clamp( b.opacity, 0.25f, 1.0f, 1.0f );
	return b;
}

static CzmHudBlock HudDefault( int kind )
{
	CzmHudBlock b = { CzmHud::defaults[kind][0], CzmHud::defaults[kind][1], CzmHud::defaultScale[kind], 1.0f, CzmHud::defaultHidden[kind] };
	return b;
}

static void ReadHud( CzmHudBlock *blocks, int *style, int *radarStyle, int *msgStyle )
{
	*style = (int)CzmHud::Clamp( EngFuncs::GetCvarFloat( "czm_hud_style" ), 0, HUD_STYLES - 1, 0 );
	*radarStyle = (int)CzmHud::Clamp( EngFuncs::GetCvarFloat( "czm_hud_radar_style" ), 0, CzmHud::RADAR_STYLES - 1, CzmHud::defaultRadarStyle );
	*msgStyle = (int)CzmHud::Clamp( EngFuncs::GetCvarFloat( "czm_hud_msg_style" ), 0, CzmHud::MSG_STYLES - 1, 1 );
	for( int i = 0; i < HUD_BLOCKS; i++ )
	{
		char key[64];
		float values[5];

		for( int k = 0; k < 5; k++ )
		{
			CzmHud::Key( key, sizeof( key ), i, CzmHud::fields[k] );
			values[k] = EngFuncs::GetCvarFloat( key );
		}
		CzmHudBlock b = { values[0], values[1], values[2], values[3], values[4] > 0.5f };
		blocks[i] = HudClamp( i, b );
	}
}

static void WriteHud( const CzmHudBlock *blocks, int style, int radarStyle, int msgStyle )
{
	EngFuncs::CvarSetValue( "czm_hud_style", style );
	EngFuncs::CvarSetValue( "czm_hud_radar_style", radarStyle );
	EngFuncs::CvarSetValue( "czm_hud_msg_style", msgStyle );
	for( int i = 0; i < HUD_BLOCKS; i++ )
	{
		for( int k = 0; k < 5; k++ )
		{
			char key[64];

			CzmHud::Key( key, sizeof( key ), i, CzmHud::fields[k] );
			EngFuncs::CvarSetValue( key, HudField( blocks[i], k ));
		}
	}
	EngFuncs::ClientCmd( false, "host_writeconfig\n" );
}

// places, sizes and opacity back to the defaults, hidden blocks come back; the chosen styles stay
void CZM_TouchResetHud( void )
{
	CzmHudBlock blocks[HUD_BLOCKS];

	for( int i = 0; i < HUD_BLOCKS; i++ )
		blocks[i] = HudDefault( i );
	WriteHud( blocks, (int)CzmHud::Clamp( EngFuncs::GetCvarFloat( "czm_hud_style" ), 0, HUD_STYLES - 1, 0 ),
		(int)CzmHud::Clamp( EngFuncs::GetCvarFloat( "czm_hud_radar_style" ), 0, CzmHud::RADAR_STYLES - 1, CzmHud::defaultRadarStyle ),
		(int)CzmHud::Clamp( EngFuncs::GetCvarFloat( "czm_hud_msg_style" ), 0, CzmHud::MSG_STYLES - 1, 1 ));
}

// the shared HUD painter drawing with menu calls: the preview is the HUD of the match
struct CzmMenuHudPainter : CzmHud::Painter
{
	void Fill( int x, int y, int w, int h, int r, int g, int b, int a ) override
	{
		if( w > 0 && h > 0 )
			UI_FillRect( x, y, w, h, PackRGBA( r, g, b, bound( 0, a, 255 )));
	}
	void Blend( int x, int y, int w, int h, int r, int g, int b, int a ) override
	{
		Fill( x, y, w, h, r, g, b, a );
	}
	void Text( float x, float y, float height, const char *s, int r, int g, int b, float alpha ) override
	{
		HIMAGE atlas = CZM_Image( HUD_ATLAS );
		int iw = atlas ? EngFuncs::PIC_Width( atlas ) : 0, ih = atlas ? EngFuncs::PIC_Height( atlas ) : 0;
		float width = height * 0.65f;
		int top = (int)( y + 0.5f ), bottom = (int)( y + height + 0.5f );

		if( iw <= 0 || ih <= 0 || bottom <= top )
			return;

		for( ; *s; s++, x += width )
		{
			unsigned c = (unsigned char)*s;
			int left = (int)( x + 0.5f ), right = (int)( x + width + 0.5f );
			wrect_t rc;

			if( c < 32 || c > 95 )
				c = '?';
			c -= 32;
			rc.left = ( c % 16 ) * iw / 16;
			rc.right = rc.left + iw / 16;
			rc.top = ( c / 16 ) * ih / 4;
			rc.bottom = rc.top + ih / 4;
			// the engine resets the colour after every picture
			EngFuncs::PIC_Set( atlas, r, g, b, bound( 0, (int)( alpha * 255.0f ), 255 ));
			EngFuncs::PIC_DrawTrans( left, top, right - left, bottom - top, &rc );
		}
	}
};

// thin frame inside the rectangle
static void DrawFrame( const CzmRect &r, int t, unsigned int color )
{
	UI_FillRect( r.x, r.y, r.w, t, color );
	UI_FillRect( r.x, r.y + r.h - t, r.w, t, color );
	UI_FillRect( r.x, r.y + t, t, r.h - t * 2, color );
	UI_FillRect( r.x + r.w - t, r.y + t, t, r.h - t * 2, color );
}

// overlapping controls pulse in amber, the selection stays red
static unsigned int ConflictColor( int alpha )
{
	float pulse = 0.65f + 0.35f * sinf( uiStatic.realTime * 0.006f );
	return PackRGBA( 255, 176, 32, (int)( alpha * pulse ));
}

// The radar as the match draws it (cl_dll/hud/czm_radar.cpp): the plate of the style,
// a few team marks and, on the tactical one, the compass. Used by the editor and the settings.
void CZM_DrawRadarPreview( int style, int x, int y, int size, float opacity )
{
	static const char *const plates[CzmHud::RADAR_STYLES] = { "classic", "tactical", "minimal" };
	static const char *const marks[3] = { "dot", "up", "down" };
	static const struct { float x, y; int kind; int r, g, b; } team[] =
	{
		{ 0.35f, -0.50f, 0, 236, 241, 248 },
		{ -0.45f, 0.20f, 0, 236, 241, 248 },
		{ 0.10f, 0.55f, 2, 236, 241, 248 },
		{ -0.20f, -0.75f, 0, 255, 72, 72 },
		{ 0.62f, 0.15f, 1, 236, 241, 248 },
	};
	char path[64];
	float cx = x + size * 0.5f, cy = y + size * 0.5f;
	float inner;
	int m;

	style = bound( 0, style, CzmHud::RADAR_STYLES - 1 );
	inner = size * 0.5f * CzmHud::RadarInner( style );
	snprintf( path, sizeof( path ), "gfx/czm/radar/radar_%s.png", plates[style] );
	CZM_DrawImage( path, x, y, size, size, CZM_White( bound( 0, (int)( 255 * opacity ), 255 )));

	if( style == CzmHud::RADAR_TACTICAL )
	{
		static const char *const letters[4] = { "N", "E", "S", "W" };
		CzmMenuHudPainter painter;
		float h = size * 0.07f, radius = inner * 0.93f;

		for( int i = 0; i < 4; i++ )
		{
			float a = ( 20.0f - i * 90.0f ) * 0.0174532925f; // as if the player looked a little to the left of north
			bool north = i == 0;
			painter.Text( cx + radius * sinf( a ) - h * 0.325f, cy - radius * cosf( a ) - h * 0.5f, h, letters[i],
				north ? 224 : 147, north ? 37 : 159, north ? 50 : 180, 1.0f );
		}
	}

	m = Q_max( 6, (int)( size * 0.085f ));
	for( size_t i = 0; i < sizeof( team ) / sizeof( team[0] ); i++ )
	{
		snprintf( path, sizeof( path ), "gfx/czm/radar/mark_%s.png", marks[team[i].kind] );
		CZM_DrawImage( path, (int)( cx + team[i].x * inner ) - m / 2, (int)( cy + team[i].y * inner ) - m / 2, m, m,
			PackRGBA( team[i].r, team[i].g, team[i].b, 255 ));
	}
}

// a rounded plate: two halves of the dot picture and a fill between them
static void DrawPill( float x, float y, float w, float h, unsigned int color )
{
	HIMAGE dot = CZM_Image( UI_DIR "dot.png" );
	int iw = dot ? EngFuncs::PIC_Width( dot ) : 0, ih = dot ? EngFuncs::PIC_Height( dot ) : 0;
	int r, g, b, a, cap = (int)( h * 0.5f + 0.5f );
	wrect_t rc;

	if( iw <= 0 || ih <= 0 || h < 2 )
		return;
	if( w < h )
		w = h;
	UnpackRGBA( r, g, b, a, color );
	rc.top = 0;
	rc.bottom = ih;
	rc.left = 0;
	rc.right = iw / 2;
	EngFuncs::PIC_Set( dot, r, g, b, a );
	EngFuncs::PIC_DrawTrans( (int)x, (int)y, cap, (int)h, &rc );
	UI_FillRect( (int)x + cap, (int)y, (int)w - cap * 2, (int)h, color );
	rc.left = iw / 2;
	rc.right = iw;
	EngFuncs::PIC_Set( dot, r, g, b, a );
	EngFuncs::PIC_DrawTrans( (int)( x + w ) - cap, (int)y, cap, (int)h, &rc );
}

/*
=================
chat and server messages as the match draws them (cl_dll/saytext.cpp, cl_dll/message.cpp):
classic CS text, CZM dark plates with a coloured edge, or a dark outline
=================
*/
struct CzmTextPart { const char *text; int r, g, b; };

static int MessageLineWidth( HFont font, const CzmTextPart *parts, int count )
{
	int w = 0;
	for( int i = 0; i < count; i++ )
		w += CZM_TextWidth( font, parts[i].text );
	return w;
}

// one line at x, y of height h: the plate or the outline by the style, then the coloured parts
static void DrawMessageLine( int style, HFont font, int x, int y, int h, const CzmTextPart *parts, int count,
	int edgeR, int edgeG, int edgeB, float opacity, int pad )
{
	int textY = y + ( h - CZM_FontHeight( font )) / 2, w = MessageLineWidth( font, parts, count );

	if( style == CzmHud::MSG_CZM )
	{
		UI_FillRect( x - pad, y, w + pad * 2, h, PackRGBA( 10, 14, 22, (int)( 175 * opacity )));
		UI_FillRect( x - pad, y, Q_max( 2, h / 10 ), h, PackRGBA( edgeR, edgeG, edgeB, (int)( 255 * opacity )));
	}
	else if( style == CzmHud::MSG_OUTLINE )
	{
		// a dark outline: the text four times around its place, as the match draws it
		const int o = h > 32 ? 2 : 1;
		const int dx[4] = { o, -o, o, -o }, dy[4] = { o, o, -o, -o };
		int tx = x;

		for( int i = 0; i < count; i++ )
		{
			for( int k = 0; k < 4; k++ )
				CZM_DrawText( font, tx + dx[k], textY + dy[k], 9999, parts[i].text, PackRGBA( 0, 0, 0, 255 ));
			tx += CZM_TextWidth( font, parts[i].text );
		}
	}
	for( int i = 0; i < count; i++ )
	{
		CZM_DrawText( font, x, textY, 9999, parts[i].text, PackRGBA( parts[i].r, parts[i].g, parts[i].b, 255 ));
		x += CZM_TextWidth( font, parts[i].text );
	}
}

// three chat lines growing up from the bottom of the area, the newest at the bottom
static void DrawChatSample( int style, int x, int bottom, int lineH, float opacity, HFont font )
{
	const bool ru = CZM_IsRussian();
	const CzmTextPart one[] = { { "Kuro", 153, 204, 255 }, { ru ? " :  всем привет!" : " :  hi all!", 255, 178, 0 } };
	const CzmTextPart two[] = { { "Zombie", 255, 63, 63 }, { ru ? " :  бегите на крышу" : " :  run to the roof", 255, 178, 0 } };
	const CzmTextPart three[] = { { ru ? "* Новый раунд, удачи!" : "* New round, good luck!", 153, 255, 153 } };
	int pad = lineH / 3;

	DrawMessageLine( style, font, x + pad, bottom - lineH * 3, lineH, one, 2, 224, 37, 50, opacity, pad );
	DrawMessageLine( style, font, x + pad, bottom - lineH * 2, lineH, two, 2, 224, 37, 50, opacity, pad );
	DrawMessageLine( style, font, x + pad, bottom - lineH, lineH, three, 1, 224, 37, 50, opacity, pad );
}

// two typical server texts where servers put them: the title at the top, the zombie status at the bottom left
static void DrawServerSample( int style, const CzmRect &frame, int lineH, float opacity, HFont font )
{
	const CzmTextPart title[] = { { "ZS.SERVER  •  zm_dust  •  12/32", 80, 230, 120 } };
	const CzmTextPart status[] = { { "HP: 1750  ·  Light Zombie  ·  Ammo packs: 35", 200, 230, 60 } };
	int pad = lineH / 3;
	int w = MessageLineWidth( font, title, 1 );

	DrawMessageLine( style, font, frame.x + ( frame.w - w ) / 2, frame.y + frame.h * 0.02f, lineH, title, 1, 80, 230, 120, opacity, pad );
	DrawMessageLine( style, font, frame.x + frame.w * 0.02f + pad, frame.y + frame.h * 0.88f, lineH, status, 1, 200, 230, 60, opacity, pad );
}

// a small picture of the three looks for the settings: a game shot with the chat and a server text
void CZM_DrawMessagePreview( int style, int x, int y, int w, int h )
{
	HFont font = CZM_Font( CZMF_SMALL );
	int lineH = CZM_FontHeight( font ) + 6;
	CzmRect frame = CZM_Rect( x, y, w, h );
	HIMAGE shot = CZM_Image( UI_DIR "editor_bg.png" );

	style = bound( 0, style, CzmHud::MSG_STYLES - 1 );
	if( shot )
	{
		// a bright part of the match screenshot, so the difference in readability shows
		int iw = EngFuncs::PIC_Width( shot ), ih = EngFuncs::PIC_Height( shot );
		wrect_t rc;
		rc.left = iw * 0.38f; rc.right = iw * 0.98f; rc.top = ih * 0.05f; rc.bottom = ih * 0.05f + ( rc.right - rc.left ) * h / Q_max( 1, w );
		if( rc.bottom > ih ) rc.bottom = ih;
		EngFuncs::PIC_Set( shot, 255, 255, 255, 255 );
		EngFuncs::PIC_DrawTrans( x, y, w, h, &rc );
	}
	DrawServerSample( style, CZM_Rect( frame.x, frame.y + lineH / 2, frame.w, frame.h - lineH ), lineH, 1.0f, font );
	DrawChatSample( style, x + w / 30, y + h * 0.80f, lineH, 1.0f, font );
}

// The spectator overlay and the download indicator drawn with menu calls: the same painting
// as the match (common/czm_hud_overlay.h), moved to an origin, words in a menu font.
struct CzmMenuCanvas : CzmHud::Canvas
{
	int ox, oy;
	HFont font;
	CzmMenuHudPainter atlas;

	CzmMenuCanvas( int x, int y, HFont f ) : ox( x ), oy( y ), font( f ) {}
	void Blend( int x, int y, int w, int h, int r, int g, int b, int a ) override
	{
		if( w > 0 && h > 0 && a > 0 )
			UI_FillRect( ox + x, oy + y, w, h, PackRGBA( r, g, b, bound( 0, a, 255 )));
	}
	void Glyphs( float x, float y, float height, const char *s, int r, int g, int b, float alpha ) override
	{
		atlas.Text( ox + x, oy + y, height, s, r, g, b, alpha );
	}
	int LabelWidth( const char *s ) override { return CZM_TextWidth( font, s ); }
	int LabelHeight() override { return CZM_FontHeight( font ); }
	void Label( int x, int y, const char *s, int r, int g, int b ) override
	{
		if( s && *s )
			CZM_DrawText( font, ox + x, oy + y, CZM_TextWidth( font, s ) + 4, s, PackRGBA( r, g, b, 255 ));
	}
	bool Avatar( int x, int y, int size ) override
	{
		CZM_DrawImage( UI_DIR "avatar.png", ox + x, oy + y, size, size );
		return true;
	}
};

// a dark part of the match screenshot under the previews
static void DrawMatchShot( int x, int y, int w, int h, float left )
{
	HIMAGE shot = CZM_Image( UI_DIR "editor_bg.png" );

	UI_FillRect( x, y, w, h, PackRGBA( 30, 36, 44, 255 ));
	if( !shot )
		return;
	int iw = EngFuncs::PIC_Width( shot ), ih = EngFuncs::PIC_Height( shot );
	wrect_t rc;
	rc.left = iw * left; rc.right = rc.left + iw * 0.6f; rc.top = ih * 0.2f; rc.bottom = rc.top + ( rc.right - rc.left ) * h / Q_max( 1, w );
	if( rc.right > iw ) rc.right = iw;
	if( rc.bottom > ih ) rc.bottom = ih;
	EngFuncs::PIC_Set( shot, 255, 255, 255, 255 );
	EngFuncs::PIC_DrawTrans( x, y, w, h, &rc );
}

// the spectator overlay of a style over a match picture, as in Settings → HUD
void CZM_DrawSpectatorPreview( int style, int x, int y, int w, int h )
{
	CzmMenuCanvas canvas( x, y, CZM_Font( CZMF_TINY ));
	CzmHud::SpecInfo info;

	DrawMatchShot( x, y, w, h, 0.2f );
	info.name = "Big-Show";
	info.team = 2;
	info.health = 73;
	info.scoreCT = 3;
	info.scoreT = 5;
	info.timer = "1:45";
	info.watching = CZM_IsRussian() ? "Наблюдение" : "Spectating";
	info.status = true;
	// the overlay of a phone screen of this shape, drawn at the card's size
	CzmHud::PaintSpectator( canvas, bound( 0, style, CzmHud::SPEC_STYLES - 1 ), w, h, info );
}

// the indicator with sample numbers, where the editor shows the block
static void DrawDownloadSample( const CzmHud::Rect &p, int ox = 0, int oy = 0 )
{
	CzmMenuCanvas canvas( ox, oy, CZM_Font( CZMF_SMALL ));
	CzmHud::PaintDownload( canvas, p, CZM_IsRussian() ? "Файлы сервера: 2" : "Server files: 2", 64.0f );
}

// The clip on the reload button as the match shows it (engine patch czm-reload-ammo): a full clip here.
static void DrawReloadPreview( const CzmRect &r )
{
	const unsigned int green = PackRGBA( 70, 215, 120, 245 );
	const int total = 30;
	float radius = Q_min( r.w, r.h ) * 0.5f, cx = r.x + r.w * 0.5f, cy = r.y + r.h * 0.5f;
	float ring = radius * 1.115f, thick = radius * 0.11f;
	float ph = radius * 0.62f, bigH = ph * 0.70f, smallH = ph * 0.46f, pw, px, py, border;
	CzmMenuHudPainter painter;

	// the ticks: the game draws short arcs, three small dots make each one here
	for( int i = 0; i < total; i++ )
	{
		float step = 6.2831853f / total, a0 = -1.5707963f + i * step + step * 0.17f;
		int d = Q_max( 2, (int)( thick + 0.5f ));

		for( int k = 0; k < 3; k++ )
		{
			float a = a0 + step * 0.66f * k / 2.0f;
			CZM_DrawImage( UI_DIR "dot.png", (int)( cx + cosf( a ) * ring ) - d / 2, (int)( cy + sinf( a ) * ring ) - d / 2, d, d, green );
		}
	}

	pw = 2 * bigH * 0.65f + 3 * smallH * 0.65f + ph * 0.6f;
	px = cx - pw * 0.5f;
	py = r.y + r.h - ph * 0.62f;
	border = Q_max( 1.0f, ph * 0.07f );
	DrawPill( px - border, py - border, pw + border * 2, ph + border * 2, green );
	DrawPill( px, py, pw, ph, PackRGBA( 12, 16, 24, 240 ));
	painter.Text( px + ph * 0.3f, py + ( ph - bigH ) * 0.5f, bigH, "30", 70, 215, 120, 1.0f );
	painter.Text( px + ph * 0.3f + 2 * bigH * 0.65f, py + ( ph - bigH ) * 0.5f + ( bigH - smallH ) * 0.82f, smallH, "/90", 190, 198, 210, 1.0f );
}

/*
=================
CCzmTouchEditor

The layout over the game: drag buttons, change size, opacity, icon and action,
hide, add and delete them; three layouts ("schemes") like in PUBG.
=================
*/
class CCzmTouchEditor : public CMenuFramework
{
public:
	CCzmTouchEditor();

	void Show() override;
	void Hide() override;
	void Draw() override;
	bool KeyDown( int key ) override;
	bool KeyUp( int key ) override;
	bool MouseMove( int x, int y ) override;
	void Char( int key ) override;

private:
	enum EOverlay
	{
		OV_NONE = 0,
		OV_ADD,      // pick an action for a new button
		OV_COMMAND,  // pick an action for the selected button
		OV_ICON,     // pick an icon for the selected button
		OV_CONFIRM_EXIT,
		OV_CONFIRM_RESET,
		OV_CONFIRM_SCHEME,
	};

	enum
	{
		HIT_NONE = 0,
		HIT_BAR,          // the bar itself, no action
		HIT_SCHEME,       // + scheme index (1..3)
		HIT_ADD = HIT_SCHEME + 4,
		HIT_HIDDEN,
		HIT_RESET,
		HIT_SAVE,
		HIT_EXIT,
		HIT_COLLAPSE,
		HIT_EXPAND,
		HIT_PANEL,        // selected button panel
		HIT_SIZE,
		HIT_OPACITY,
		HIT_HIDE,
		HIT_ICON,
		HIT_COMMAND,
		HIT_DELETE,
		HIT_OV_PANEL,     // picker and confirm windows
		HIT_OV_CLOSE,
		HIT_OV_BACKDROP,
		HIT_OV_YES,
		HIT_OV_NO,
		HIT_OV_SAY_FIELD,
		HIT_OV_SAY_ADD,
		HIT_OV_CMD_FIELD,
		HIT_OV_CMD_ADD,
		HIT_HUD_STYLE,    // + style, panel of a HUD block
		HIT_HUD_RESET = HIT_HUD_STYLE + HUD_STYLES,
		HIT_HUD_HIDE,
		HIT_GROUP = 100,  // + group
		HIT_ITEM = 200,   // + action or icon index
		HIT_HUD = 900,    // + HUD block
		HIT_BUTTON = 1000 // + layout button index
	};

	void Load( int scheme, bool fromPreset );
	bool Parse( const char *path );
	void Apply( void );
	void Exit( void );
	void Toast( const char *ru, const char *en );

	void Layout( void );
	int HitTest( void ) const;
	bool IsPressed( int hit ) const { return m_iPressed == hit && HitTest() == hit; }
	void Activate( int hit );
	void SetSlider( int which );
	void AddButton( const char *icon, const char *command );
	void SetAction( const char *icon, const char *command );
	void FinishCustom( bool chat );

	CzmRect ButtonRect( int i ) const;
	int ButtonAt( int x, int y ) const;
	CzmHud::Rect HudLayout( int kind ) const;
	CzmRect HudRect( int kind ) const;
	CzmRect HudGrab( int kind ) const; // where a finger takes the block: the frame of server messages by its label
	int HudAt( int x, int y ) const;
	void FindConflicts( void );
	const char *ItemName( int item ) const;
	float ButtonSize( int i ) const; // diameter, share of the screen width
	void SetButtonSize( int i, float size );

	void DrawHud( void );
	void DrawMessageFrame( const CzmRect &r, float opacity, bool selected );
	void DrawButtons( void );
	void DrawGuides( void );
	void DrawBar( void );
	void DrawPanel( void );
	void DrawHudPanel( void );
	void DrawConflictChip( void );
	void DrawPicker( void );
	void DrawConfirm( void );
	void DrawSlider( const CzmRect &r, float t, const char *label, const char *value );

	CzmTouchButton m_buttons[CZM_MAX_BUTTONS];
	int m_iButtons;
	CzmHudBlock m_hud[HUD_BLOCKS];
	int m_iHudStyle;    // the text blocks
	int m_iRadarStyle;
	int m_iMsgStyle;    // the chat and server messages
	int m_iHudSelected; // HUD block with the open panel, -1 when a button or nothing is selected
	int m_iDragHud;
	bool m_bSnapX;      // the dragged HUD block sits on the centre line
	float m_flSnapY;    // ...or on the row of another block, -1 if not

	// overlapping controls: items are the HUD blocks, then the buttons (HUD_BLOCKS + button)
	int m_conflict[HUD_BLOCKS + CZM_MAX_BUTTONS]; // one item it overlaps, -1 for none
	int m_iConflicts, m_iConflictA, m_iConflictB;
	int m_iScheme;
	int m_iSelected;
	bool m_bDirty;
	bool m_bShowHidden;
	bool m_bCollapsed;
	int m_overlay;
	int m_iPendingScheme;
	int m_iGroup;
	int m_iPressed;
	int m_iDragButton;
	float m_flGrabX, m_flGrabY;
	bool m_bMoved;
	int m_iDownX, m_iDownY;
	int m_iSlider;      // 0, HIT_SIZE or HIT_OPACITY while dragging
	int m_iPickerScroll, m_iPickerMaxScroll, m_iScrollAtDown;
	bool m_bPickerScrolling, m_bPickerMaybeScroll;
	CzmTextEdit m_say, m_cmd;
	const char *m_szToast;
	int m_iToastTime;
	int m_iShowTime;    // the hint at the bottom is shown for a few seconds

	// layout, recalculated every frame
	int W, H;
	CzmRect m_bar, m_schemes[CZM_SCHEMES], m_add, m_hidden, m_reset, m_save, m_exit, m_collapse, m_expand;
	CzmRect m_panel, m_size, m_opacity, m_hide, m_icon, m_command, m_delete;
	CzmRect m_hudStyles[HUD_STYLES], m_hudHide, m_hudReset; // panel of a HUD block
	CzmRect m_ovPanel, m_ovClose, m_ovYes, m_ovNo, m_ovClip, m_groups[GROUP_COUNT];
	CzmRect m_sayField, m_sayAdd, m_cmdField, m_cmdAdd;
	CzmRect m_items[CZM_ICONS > CZM_ACTIONS ? CZM_ICONS : CZM_ACTIONS];
	int m_itemIndex[CZM_ICONS > CZM_ACTIONS ? CZM_ICONS : CZM_ACTIONS];
	int m_iItems;
};

CCzmTouchEditor::CCzmTouchEditor() : CMenuFramework( "CzmTouchEditor" )
{
	m_iButtons = 0;
	for( int i = 0; i < HUD_BLOCKS; i++ )
		m_hud[i] = HudDefault( i );
	m_iHudStyle = m_iRadarStyle = 0;
	m_iMsgStyle = CzmHud::MSG_CZM;
	m_iHudSelected = m_iDragHud = -1;
	m_bSnapX = false;
	m_flSnapY = -1.0f;
	for( int i = 0; i < HUD_BLOCKS + CZM_MAX_BUTTONS; i++ )
		m_conflict[i] = -1;
	m_iConflicts = 0;
	m_iConflictA = m_iConflictB = -1;
	m_iScheme = 1;
	m_iSelected = -1;
	m_bDirty = m_bShowHidden = m_bCollapsed = false;
	m_overlay = OV_NONE;
	m_iPendingScheme = 1;
	m_iGroup = GROUP_COMBAT;
	m_iPressed = HIT_NONE;
	m_iDragButton = -1;
	m_flGrabX = m_flGrabY = 0.0f;
	m_bMoved = false;
	m_iDownX = m_iDownY = 0;
	m_iSlider = 0;
	m_iPickerScroll = m_iPickerMaxScroll = m_iScrollAtDown = 0;
	m_bPickerScrolling = m_bPickerMaybeScroll = false;
	memset( &m_say, 0, sizeof( m_say ));
	memset( &m_cmd, 0, sizeof( m_cmd ));
	m_szToast = NULL;
	m_iToastTime = 0;
	m_iShowTime = 0;
	m_iItems = 0;
	W = H = 0;
}

/*
=================
loading and saving
=================
*/
bool CCzmTouchEditor::Parse( const char *path )
{
	int length = 0;
	char *data = (char *)EngFuncs::COM_LoadFile( path, &length );
	char *line, *next;

	m_iButtons = 0;
	if( !data )
		return false;

	for( line = data; line && *line; line = next )
	{
		char token[256], *p;
		char args[14][128];
		int count = 0;

		next = strchr( line, '\n' );
		if( next )
			*next++ = 0;

		while( *line == ' ' || *line == '\t' )
			line++;

		if( strncmp( line, "touch_addbutton", 15 ))
			continue;

		p = line;
		while( count < 14 && ( p = EngFuncs::COM_ParseFile( p, token, sizeof( token ))) != NULL )
			Q_strncpy( args[count++], token, sizeof( args[0] ));

		if( count < 12 || m_iButtons >= CZM_MAX_BUTTONS )
			continue;

		CzmTouchButton &b = m_buttons[m_iButtons++];
		Q_strncpy( b.name, args[1], sizeof( b.name ));
		Q_strncpy( b.texture, args[2], sizeof( b.texture ));
		Q_strncpy( b.command, args[3], sizeof( b.command ));
		b.x1 = atof( args[4] );
		b.y1 = atof( args[5] );
		b.x2 = atof( args[6] );
		b.y2 = atof( args[7] );
		for( int k = 0; k < 4; k++ )
			b.color[k] = atoi( args[8 + k] );
		b.flags = count > 12 ? atoi( args[12] ) : 0;

		// "aspect" after the flags: the engine keeps such a button round on any screen,
		// the default layout and exported configs rely on it; the editor does the same
		if( count > 13 && atof( args[13] ) > 0.0f && b.texture[0] && b.texture[0] != '#' && ScreenHeight > 0 )
			b.y2 = b.y1 + ( b.x2 - b.x1 ) * ScreenWidth / ScreenHeight * atof( args[13] );
	}

	EngFuncs::COM_FreeFile( data );
	return true;
}

void CCzmTouchEditor::Load( int scheme, bool fromPreset )
{
	char path[64];

	CZM_SetTouchScheme( scheme, fromPreset );
	m_iScheme = CZM_TouchScheme();
	SchemePath( m_iScheme, path, sizeof( path ));
	Parse( path );

	// the default layout brings the default HUD places; otherwise unsaved HUD changes go too
	if( fromPreset )
		CZM_TouchResetHud();
	ReadHud( m_hud, &m_iHudStyle, &m_iRadarStyle, &m_iMsgStyle );

	m_iSelected = m_iHudSelected = -1;
	m_bDirty = false;
}

void CCzmTouchEditor::Apply( void )
{
	char path[64];

	SchemePath( m_iScheme, path, sizeof( path ));
	EngFuncs::CvarSetString( "touch_config_file", path );
	EngFuncs::ClientCmd( false, "touch_removeall\n" );

	for( int i = 0; i < m_iButtons; i++ )
	{
		const CzmTouchButton &b = m_buttons[i];

		EngFuncs::ClientCmdF( false, "touch_addbutton \"%s\" \"%s\" \"%s\" %f %f %f %f %d %d %d %d %d\n",
			b.name, b.texture, b.command, b.x1, b.y1, b.x2, b.y2,
			b.color[0], b.color[1], b.color[2], b.color[3], b.flags );
	}

	EngFuncs::ClientCmd( true, "alias czm_more czm_more_show\n" );
	CZM_SaveTouchConfig();
	WriteHud( m_hud, m_iHudStyle, m_iRadarStyle, m_iMsgStyle );
	m_bDirty = false;
	Toast( "Сохранено", "Saved" );
}

void CCzmTouchEditor::Toast( const char *ru, const char *en )
{
	m_szToast = CZM_IsRussian() ? ru : en;
	m_iToastTime = uiStatic.realTime;
}

void CCzmTouchEditor::Show()
{
	m_overlay = OV_NONE;
	m_iPressed = HIT_NONE;
	m_iDragButton = m_iDragHud = -1;
	m_bSnapX = false;
	m_flSnapY = -1.0f;
	m_iSlider = 0;
	m_szToast = NULL;
	m_iShowTime = uiStatic.realTime;
	m_bCollapsed = false;
	Load( CZM_TouchScheme(), false );
	CZM_SetGameVisible( true );
	CMenuFramework::Show();
}

void CCzmTouchEditor::Hide()
{
	m_say.End();
	m_cmd.End();
	CZM_SetGameVisible( false );
	CMenuFramework::Hide();

	// opened from a button in the match: go straight back to the game
	if( CL_IsActive() && !uiStatic.menu.IsActive( ))
		UI_CloseMenu();
}

void CCzmTouchEditor::Exit( void )
{
	if( m_bDirty )
		m_overlay = OV_CONFIRM_EXIT;
	else
		Hide();
}

/*
=================
buttons
=================
*/
CzmRect CCzmTouchEditor::ButtonRect( int i ) const
{
	const CzmTouchButton &b = m_buttons[i];
	return CZM_Rect( b.x1 * W, b.y1 * H, ( b.x2 - b.x1 ) * W, ( b.y2 - b.y1 ) * H );
}

int CCzmTouchEditor::ButtonAt( int x, int y ) const
{
	// the last drawn button is on top
	for( int i = m_iButtons - 1; i >= 0; i-- )
	{
		if( !ButtonEditable( m_buttons[i] ))
			continue;
		if(( m_buttons[i].flags & TOUCH_FLAG_HIDE ) && !m_bShowHidden )
			continue;
		if( ButtonRect( i ).Contains( x, y ))
			return i;
	}
	return -1;
}

CzmHud::Rect CCzmTouchEditor::HudLayout( int kind ) const
{
	const CzmHudBlock &b = m_hud[kind];

	if( kind == CzmHud::RADAR )
		return CzmHud::RadarLayout( W, H, b.x, b.y, b.scale, b.opacity );
	if( kind == CzmHud::CHAT )
		return CzmHud::ChatLayout( W, H, b.x, b.y, b.scale, b.opacity, ChatLineHeight( H ));
	if( kind == CzmHud::MESSAGES )
		return CzmHud::MessageFrame( W, H, b.x, b.y, b.scale, b.opacity );
	if( kind == CzmHud::DOWNLOADS )
		return CzmHud::DownloadLayout( W, H, b.x, b.y, b.scale, b.opacity, CZM_FontHeight( CZM_Font( CZMF_SMALL )));
	return CzmHud::Layout( kind, m_iHudStyle, W, H, b.x, b.y, b.scale, b.opacity, (int)strlen( CzmHud::samples[kind] ));
}

CzmRect CCzmTouchEditor::HudRect( int kind ) const
{
	CzmHud::Rect p = HudLayout( kind );
	return CZM_Rect( p.x, p.y, p.w, p.h );
}

CzmRect CCzmTouchEditor::HudGrab( int kind ) const
{
	CzmRect r = HudRect( kind );

	if( kind == CzmHud::MESSAGES )
	{
		int w = H * 0.56f, h = H * 0.08f;
		return CZM_Rect( r.x + ( r.w - w ) / 2, r.y + ( r.h - h ) / 2, w, h );
	}
	return r;
}

int CCzmTouchEditor::HudAt( int x, int y ) const
{
	// the selected block first, it is drawn with a frame on top
	if( m_iHudSelected >= 0 && ( !m_hud[m_iHudSelected].hidden || m_bShowHidden ) && HudGrab( m_iHudSelected ).Grown( H / 100 ).Contains( x, y ))
		return m_iHudSelected;
	for( int i = HUD_BLOCKS - 1; i >= 0; i-- )
	{
		if( m_hud[i].hidden && !m_bShowHidden )
			continue;
		if( HudGrab( i ).Grown( H / 100 ).Contains( x, y ))
			return i;
	}
	return -1;
}

const char *CCzmTouchEditor::ItemName( int item ) const
{
	if( item < 0 )
		return "";
	return item < HUD_BLOCKS ? HudName( item ) : ButtonLabel( m_buttons[item - HUD_BLOCKS] );
}

// What covers what in the match: HUD blocks are rectangles, buttons are round.
// Only what the player sees counts: hidden buttons and the move/look zones do not.
void CCzmTouchEditor::FindConflicts( void )
{
	struct Shape
	{
		bool round;
		float x, y, w, h; // rectangle, or centre and radius in x, y, w
		int item;
	} shapes[HUD_BLOCKS + CZM_MAX_BUTTONS];
	int count = 0;

	for( int i = 0; i < HUD_BLOCKS; i++ )
	{
		CzmHud::Rect p = HudLayout( i );

		// the frame of server messages is an area, not a control: it may cover buttons
		if( m_hud[i].hidden || i == CzmHud::MESSAGES )
			continue;
		// the round radars are circles, the tactical one is a square
		if( i == CzmHud::RADAR && m_iRadarStyle != CzmHud::RADAR_TACTICAL )
		{
			Shape shape = { true, p.x + p.w * 0.5f, p.y + p.h * 0.5f, p.w * 0.485f, 0.0f, i };
			shapes[count++] = shape;
		}
		else
		{
			Shape shape = { false, p.x, p.y, p.w, p.h, i };
			shapes[count++] = shape;
		}
	}

	for( int i = 0; i < m_iButtons; i++ )
	{
		const CzmTouchButton &b = m_buttons[i];
		CzmRect r;

		if( !ButtonEditable( b ) || ( b.flags & TOUCH_FLAG_HIDE ))
			continue;
		r = ButtonRect( i );
		// the round icon, a little inside its square so that touching edges do not count
		Shape shape = { true, r.x + r.w * 0.5f, r.y + r.h * 0.5f, Q_min( r.w, r.h ) * 0.45f, 0.0f, HUD_BLOCKS + i };
		shapes[count++] = shape;
	}

	for( int i = 0; i < HUD_BLOCKS + CZM_MAX_BUTTONS; i++ )
		m_conflict[i] = -1;
	m_iConflicts = 0;
	m_iConflictA = m_iConflictB = -1;

	for( int a = 0; a < count; a++ )
	{
		for( int b = a + 1; b < count; b++ )
		{
			const Shape &p = shapes[a], &q = shapes[b];
			bool overlap;

			if( p.round && q.round )
			{
				float dx = p.x - q.x, dy = p.y - q.y, r = p.w + q.w;
				overlap = dx * dx + dy * dy < r * r;
			}
			else if( p.round || q.round )
			{
				const Shape &c = p.round ? p : q, &box = p.round ? q : p;
				float nx = bound( box.x, c.x, box.x + box.w ), ny = bound( box.y, c.y, box.y + box.h );
				float dx = c.x - nx, dy = c.y - ny;
				overlap = dx * dx + dy * dy < c.w * c.w;
			}
			else
			{
				overlap = p.x < q.x + q.w - 1 && q.x < p.x + p.w - 1 && p.y < q.y + q.h - 1 && q.y < p.y + p.h - 1;
			}

			if( !overlap )
				continue;
			if( m_conflict[p.item] < 0 )
				m_conflict[p.item] = q.item;
			if( m_conflict[q.item] < 0 )
				m_conflict[q.item] = p.item;
			if( !m_iConflicts )
			{
				m_iConflictA = p.item;
				m_iConflictB = q.item;
			}
			m_iConflicts++;
		}
	}
}

float CCzmTouchEditor::ButtonSize( int i ) const
{
	return m_buttons[i].x2 - m_buttons[i].x1;
}

void CCzmTouchEditor::SetButtonSize( int i, float size )
{
	CzmTouchButton &b = m_buttons[i];
	float cx = ( b.x1 + b.x2 ) * 0.5f, cy = ( b.y1 + b.y2 ) * 0.5f;
	float h = size * W / H; // round on screen

	b.x1 = cx - size * 0.5f;
	b.x2 = cx + size * 0.5f;
	b.y1 = cy - h * 0.5f;
	b.y2 = cy + h * 0.5f;
}

void CCzmTouchEditor::AddButton( const char *icon, const char *command )
{
	CzmTouchButton *b;
	float size = 0.06f;

	if( m_iButtons >= CZM_MAX_BUTTONS )
	{
		Toast( "Слишком много кнопок", "Too many buttons" );
		return;
	}

	b = &m_buttons[m_iButtons];
	memset( b, 0, sizeof( *b ));
	snprintf( b->name, sizeof( b->name ), "czm_%d_%d", m_iButtons, uiStatic.realTime % 10000 );
	snprintf( b->texture, sizeof( b->texture ), TOUCH_DIR "%s", icon );
	Q_strncpy( b->command, command, sizeof( b->command ));
	b->x1 = b->x2 = 0.5f;
	b->y1 = b->y2 = 0.5f;
	b->color[0] = b->color[1] = b->color[2] = b->color[3] = 255;
	m_iSelected = m_iButtons++;
	SetButtonSize( m_iSelected, size );
	m_bDirty = true;
}

void CCzmTouchEditor::SetAction( const char *icon, const char *command )
{
	CzmTouchButton &b = m_buttons[m_iSelected];

	Q_strncpy( b.command, command, sizeof( b.command ));
	snprintf( b.texture, sizeof( b.texture ), TOUCH_DIR "%s", icon );
	m_bDirty = true;
}

void CCzmTouchEditor::FinishCustom( bool chat )
{
	CzmTextEdit &edit = chat ? m_say : m_cmd;
	char command[128];

	edit.End();
	if( !edit.text[0] )
		return;

	if( chat )
		snprintf( command, sizeof( command ), "say %s", edit.text );
	else
		Q_strncpy( command, edit.text, sizeof( command ));

	// the command is saved inside quotes
	for( char *c = command; *c; c++ )
	{
		if( *c == '"' )
			*c = '\'';
	}

	if( m_overlay == OV_ADD )
		AddButton( chat ? "chat" : "custom", command );
	else if( m_iSelected >= 0 )
		SetAction( chat ? "chat" : "custom", command );

	edit.text[0] = 0;
	m_overlay = OV_NONE;
}

/*
=================
layout
=================
*/
void CCzmTouchEditor::Layout( void )
{
	int pillH, gap, x, barW, segW;

	W = ScreenWidth;
	H = ScreenHeight;
	pillH = H * 0.07f;
	gap = H * 0.018f;

	// top bar: schemes, add, hidden, reset, save, exit
	barW = Q_min( (int)( W * 0.94f ), (int)( H * 1.72f ));
	m_bar = CZM_Rect(( W - barW ) / 2, H * 0.015f, barW, H * 0.105f );
	x = m_bar.x + H * 0.03f;
	segW = H * 0.33f;
	for( int i = 0; i < CZM_SCHEMES; i++ )
		m_schemes[i] = CZM_Rect( x + segW * i / CZM_SCHEMES, m_bar.y + ( m_bar.h - pillH ) / 2, segW / CZM_SCHEMES, pillH );
	x += segW + gap * 2;

	{
		int right = m_bar.x + m_bar.w - H * 0.03f - pillH; // collapse arrow on the far right
		int count = 5;
		int w = ( right - gap - x - gap * ( count - 1 )) / count;
		CzmRect *rects[] = { &m_add, &m_hidden, &m_reset, &m_save, &m_exit };

		for( int i = 0; i < count; i++ )
			*rects[i] = CZM_Rect( x + i * ( w + gap ), m_bar.y + ( m_bar.h - pillH ) / 2, w, pillH );
		m_collapse = CZM_Rect( right, m_bar.y + ( m_bar.h - pillH ) / 2, pillH, pillH );
	}
	m_expand = CZM_Rect(( W - H * 0.16f ) / 2, 0, H * 0.16f, H * 0.06f );

	// panel of the selected button, away from the button itself
	{
		int pw = Q_min( (int)( W * 0.66f ), (int)( H * 1.40f )), ph = H * 0.30f;
		int py = H - ph - H * 0.03f;
		int pad = H * 0.035f, rowH = H * 0.065f;
		int bw;

		float selected = m_iSelected >= 0 ? ( m_buttons[m_iSelected].y1 + m_buttons[m_iSelected].y2 ) * 0.5f
			: m_iHudSelected >= 0 ? m_hud[m_iHudSelected].y : 0.0f;

		if( selected > 0.55f )
			py = m_bCollapsed ? H * 0.07f : m_bar.y + m_bar.h + H * 0.02f;

		m_panel = CZM_Rect(( W - pw ) / 2, py, pw, ph );
		m_size = CZM_Rect( m_panel.x + pad, m_panel.y + H * 0.105f, ( pw - pad * 3 ) / 2, rowH );
		m_opacity = CZM_Rect( m_size.x + m_size.w + pad, m_size.y, m_size.w, rowH );
		bw = ( pw - pad * 2 - gap * 3 ) / 4;
		m_hide = CZM_Rect( m_panel.x + pad, m_panel.y + ph - pad - pillH, bw, pillH );
		m_icon = CZM_Rect( m_hide.x + bw + gap, m_hide.y, bw, pillH );
		m_command = CZM_Rect( m_icon.x + bw + gap, m_hide.y, bw, pillH );
		m_delete = CZM_Rect( m_command.x + bw + gap, m_hide.y, bw, pillH );

		// panel of a HUD block: three styles in the bottom row, "Hide" and "Default" in the top right corner
		bw = ( pw - pad * 2 - gap * ( HUD_STYLES - 1 )) / HUD_STYLES;
		for( int i = 0; i < HUD_STYLES; i++ )
			m_hudStyles[i] = CZM_Rect( m_panel.x + pad + i * ( bw + gap ), m_hide.y, bw, pillH );
		{
			int chipH = pillH * 0.82f, chipW = H * 0.25f;

			m_hudReset = CZM_Rect( m_panel.x + pw - pad - chipW, m_panel.y + H * 0.022f, chipW, chipH );
			m_hudHide = CZM_Rect( m_hudReset.x - gap - chipW, m_hudReset.y, chipW, chipH );
		}
	}

	// pickers and confirm windows
	if( m_overlay == OV_ADD || m_overlay == OV_COMMAND || m_overlay == OV_ICON )
	{
		int pw = W * 0.86f, ph = H * 0.84f;
		int pad = H * 0.04f, card = H * 0.20f, cardGap = H * 0.02f;
		int listX, listW, columns, y0, tabsW;
		bool groups = m_overlay != OV_ICON;

		m_ovPanel = CZM_Rect(( W - pw ) / 2, ( H - ph ) / 2, pw, ph );
		m_ovClose = CZM_Rect( m_ovPanel.x + pw - H * 0.09f - H * 0.015f, m_ovPanel.y + H * 0.015f, H * 0.09f, H * 0.09f );
		tabsW = groups ? H * 0.40f : 0;
		y0 = m_ovPanel.y + H * 0.12f;

		for( int i = 0; i < GROUP_COUNT; i++ )
			m_groups[i] = CZM_Rect( m_ovPanel.x + pad, y0 + i * ( H * 0.085f ), tabsW, H * 0.075f );

		listX = m_ovPanel.x + pad + ( groups ? tabsW + pad : 0 );
		listW = m_ovPanel.x + pw - pad - listX;
		m_ovClip = CZM_Rect( listX, y0, listW, m_ovPanel.y + ph - pad - y0 );

		m_iItems = 0;
		if( groups && m_iGroup == GROUP_CUSTOM )
		{
			int fieldH = H * 0.075f, addW = H * 0.30f;

			m_sayField = CZM_Rect( listX, y0 + H * 0.07f, listW - addW - cardGap, fieldH );
			m_sayAdd = CZM_Rect( m_sayField.x + m_sayField.w + cardGap, m_sayField.y, addW, fieldH );
			m_cmdField = CZM_Rect( listX, y0 + H * 0.27f, listW - addW - cardGap, fieldH );
			m_cmdAdd = CZM_Rect( m_cmdField.x + m_cmdField.w + cardGap, m_cmdField.y, addW, fieldH );
			m_iPickerMaxScroll = 0;
		}
		else
		{
			int total = groups ? 0 : CZM_ICONS;
			int lines;

			columns = Q_max( 1, ( listW + cardGap ) / ( card + cardGap ));
			if( groups )
			{
				for( int i = 0; i < CZM_ACTIONS; i++ )
				{
					if( s_actions[i].group == m_iGroup )
						m_itemIndex[total++] = i;
				}
			}
			else
			{
				card = H * 0.15f;
				columns = Q_max( 1, ( listW + cardGap ) / ( card + cardGap ));
				for( int i = 0; i < CZM_ICONS; i++ )
					m_itemIndex[i] = i;
			}

			for( int i = 0; i < total; i++ )
				m_items[i] = CZM_Rect( listX + ( i % columns ) * ( card + cardGap ),
					y0 + ( i / columns ) * ( card + cardGap ) - m_iPickerScroll, card, card );
			m_iItems = total;
			lines = ( total + columns - 1 ) / columns;
			m_iPickerMaxScroll = Q_max( 0, lines * ( card + cardGap ) - m_ovClip.h );
		}
	}
	else if( m_overlay != OV_NONE )
	{
		int pw = H * 0.86f, ph = H * 0.38f, pad = H * 0.04f, bh = H * 0.085f;
		int bw = ( pw - pad * 3 ) / 2;

		m_ovPanel = CZM_Rect(( W - pw ) / 2, ( H - ph ) / 2, pw, ph );
		m_ovNo = CZM_Rect( m_ovPanel.x + pad, m_ovPanel.y + ph - pad - bh, bw, bh );
		m_ovYes = CZM_Rect( m_ovPanel.x + pad * 2 + bw, m_ovNo.y, bw, bh );
	}
}

/*
=================
input
=================
*/
int CCzmTouchEditor::HitTest( void ) const
{
	int x = uiStatic.cursorX, y = uiStatic.cursorY;
	int button;

	if( m_overlay == OV_ADD || m_overlay == OV_COMMAND || m_overlay == OV_ICON )
	{
		if( m_ovClose.Grown( H / 80 ).Contains( x, y ))
			return HIT_OV_CLOSE;
		if( !m_ovPanel.Contains( x, y ))
			return HIT_OV_BACKDROP;

		if( m_overlay != OV_ICON )
		{
			for( int i = 0; i < GROUP_COUNT; i++ )
			{
				if( m_groups[i].Contains( x, y ))
					return HIT_GROUP + i;
			}

			if( m_iGroup == GROUP_CUSTOM )
			{
				if( m_sayField.Contains( x, y ))
					return HIT_OV_SAY_FIELD;
				if( m_sayAdd.Contains( x, y ))
					return HIT_OV_SAY_ADD;
				if( m_cmdField.Contains( x, y ))
					return HIT_OV_CMD_FIELD;
				if( m_cmdAdd.Contains( x, y ))
					return HIT_OV_CMD_ADD;
			}
		}

		if( m_ovClip.Contains( x, y ))
		{
			for( int i = 0; i < m_iItems; i++ )
			{
				if( m_items[i].Contains( x, y ))
					return HIT_ITEM + m_itemIndex[i];
			}
		}

		return HIT_OV_PANEL;
	}

	if( m_overlay != OV_NONE )
	{
		if( m_ovYes.Contains( x, y ))
			return HIT_OV_YES;
		if( m_ovNo.Contains( x, y ))
			return HIT_OV_NO;
		return m_ovPanel.Contains( x, y ) ? HIT_OV_PANEL : HIT_OV_BACKDROP;
	}

	if( m_bCollapsed )
	{
		if( m_expand.Grown( H / 60 ).Contains( x, y ))
			return HIT_EXPAND;
	}
	else
	{
		for( int i = 0; i < CZM_SCHEMES; i++ )
		{
			if( m_schemes[i].Contains( x, y ))
				return HIT_SCHEME + i + 1;
		}
		if( m_add.Contains( x, y ))
			return HIT_ADD;
		if( m_hidden.Contains( x, y ))
			return HIT_HIDDEN;
		if( m_reset.Contains( x, y ))
			return HIT_RESET;
		if( m_save.Contains( x, y ))
			return HIT_SAVE;
		if( m_exit.Contains( x, y ))
			return HIT_EXIT;
		if( m_collapse.Contains( x, y ))
			return HIT_COLLAPSE;
		if( m_bar.Contains( x, y ))
		{
			// a button or a HUD block peeking out between the bar's pills can still be taken
			button = ButtonAt( x, y );
			if( button >= 0 )
				return HIT_BUTTON + button;
			button = HudAt( x, y );
			return button >= 0 ? HIT_HUD + button : HIT_BAR;
		}
	}

	if(( m_iSelected >= 0 || m_iHudSelected >= 0 ) && m_panel.Contains( x, y ))
	{
		if( m_size.Contains( x, y ))
			return HIT_SIZE;
		if( m_opacity.Contains( x, y ))
			return HIT_OPACITY;
		if( m_iHudSelected >= 0 )
		{
			for( int i = 0; i < HUD_STYLES && m_iHudSelected != CzmHud::DOWNLOADS; i++ )
			{
				if( m_hudStyles[i].Contains( x, y ))
					return HIT_HUD_STYLE + i;
			}
			if( m_hudHide.Contains( x, y ))
				return HIT_HUD_HIDE;
			if( m_hudReset.Contains( x, y ))
				return HIT_HUD_RESET;
			return HIT_PANEL;
		}
		if( m_hide.Contains( x, y ))
			return HIT_HIDE;
		if( m_icon.Contains( x, y ))
			return HIT_ICON;
		if( m_command.Contains( x, y ))
			return HIT_COMMAND;
		if( m_delete.Contains( x, y ))
			return HIT_DELETE;
		return HIT_PANEL;
	}

	button = ButtonAt( x, y );
	if( button >= 0 )
		return HIT_BUTTON + button;
	button = HudAt( x, y );
	return button >= 0 ? HIT_HUD + button : HIT_NONE;
}

void CCzmTouchEditor::SetSlider( int which )
{
	const CzmRect &r = which == HIT_SIZE ? m_size : m_opacity;
	int x0 = r.x, x1 = r.x + r.w - H * 0.125f; // as drawn: the value sits right of the knob
	float t;

	if(( m_iSelected < 0 && m_iHudSelected < 0 ) || x1 <= x0 )
		return;

	t = bound( 0.0f, (float)( uiStatic.cursorX - x0 ) / ( x1 - x0 ), 1.0f );
	if( m_iHudSelected >= 0 )
	{
		CzmHudBlock &b = m_hud[m_iHudSelected];

		if( which == HIT_SIZE )
			b.scale = HudMinScale( m_iHudSelected ) + t * ( HudMaxScale( m_iHudSelected ) - HudMinScale( m_iHudSelected ));
		else
			b.opacity = 0.25f + t * 0.75f;
		m_bDirty = true;
		return;
	}
	if( which == HIT_SIZE )
		SetButtonSize( m_iSelected, 0.03f + t * 0.12f );
	else
		m_buttons[m_iSelected].color[3] = 40 + (int)( t * 215.0f );
	m_bDirty = true;
}

void CCzmTouchEditor::Activate( int hit )
{
	if( hit == HIT_NONE || hit == HIT_BAR || hit == HIT_PANEL || hit == HIT_OV_PANEL )
	{
		if( hit == HIT_NONE && m_overlay == OV_NONE )
			m_iSelected = m_iHudSelected = -1; // tap on the empty screen
		return;
	}

	if( hit >= HIT_BUTTON || ( hit >= HIT_HUD && hit < HIT_HUD + HUD_BLOCKS ))
		return; // buttons and HUD blocks are selected on press

	CZM_PlayClick();

	if( hit >= HIT_SCHEME + 1 && hit <= HIT_SCHEME + CZM_SCHEMES )
	{
		int scheme = hit - HIT_SCHEME;

		if( scheme == m_iScheme )
			return;
		m_iPendingScheme = scheme;
		if( m_bDirty )
			m_overlay = OV_CONFIRM_SCHEME;
		else
			Load( scheme, false );
		return;
	}

	if( hit >= HIT_HUD_STYLE && hit < HIT_HUD_STYLE + HUD_STYLES && m_iHudSelected >= 0 )
	{
		// the radar has its own looks, the chat and server messages share theirs, the text blocks one style
		if( m_iHudSelected == CzmHud::RADAR )
			m_iRadarStyle = hit - HIT_HUD_STYLE;
		else if( m_iHudSelected == CzmHud::CHAT || m_iHudSelected == CzmHud::MESSAGES )
			m_iMsgStyle = hit - HIT_HUD_STYLE;
		else
			m_iHudStyle = hit - HIT_HUD_STYLE;
		m_bDirty = true;
		return;
	}

	if( hit == HIT_HUD_RESET && m_iHudSelected >= 0 )
	{
		m_hud[m_iHudSelected] = HudDefault( m_iHudSelected );
		m_bDirty = true;
		Toast( "Блок на обычном месте", "Block moved back" );
		return;
	}

	if( hit == HIT_HUD_HIDE && m_iHudSelected >= 0 )
	{
		CzmHudBlock &b = m_hud[m_iHudSelected];

		b.hidden = !b.hidden;
		m_bDirty = true;
		if( b.hidden && !m_bShowHidden )
		{
			m_iHudSelected = -1;
			Toast( "Блок скрыт. Показать: «Скрытые»", "Block hidden. See it with \"Hidden\"" );
		}
		return;
	}

	if( hit >= HIT_GROUP && hit < HIT_GROUP + GROUP_COUNT )
	{
		m_iGroup = hit - HIT_GROUP;
		m_iPickerScroll = 0;
		m_say.End();
		m_cmd.End();
		return;
	}

	if( hit >= HIT_ITEM && hit < HIT_BUTTON )
	{
		int index = hit - HIT_ITEM;

		if( m_overlay == OV_ICON && index < CZM_ICONS && m_iSelected >= 0 )
		{
			snprintf( m_buttons[m_iSelected].texture, sizeof( m_buttons[0].texture ), TOUCH_DIR "%s", s_icons[index] );
			m_bDirty = true;
		}
		else if( m_overlay == OV_ADD && index < CZM_ACTIONS )
			AddButton( s_actions[index].icon, s_actions[index].command );
		else if( m_overlay == OV_COMMAND && index < CZM_ACTIONS && m_iSelected >= 0 )
			SetAction( s_actions[index].icon, s_actions[index].command );

		m_overlay = OV_NONE;
		return;
	}

	switch( hit )
	{
	case HIT_ADD:
		m_overlay = OV_ADD;
		m_iPickerScroll = 0;
		break;
	case HIT_HIDDEN:
		m_bShowHidden = !m_bShowHidden;
		break;
	case HIT_RESET:
		m_overlay = OV_CONFIRM_RESET;
		break;
	case HIT_SAVE:
		Apply();
		break;
	case HIT_EXIT:
		Exit();
		break;
	case HIT_COLLAPSE:
		m_bCollapsed = true;
		break;
	case HIT_EXPAND:
		m_bCollapsed = false;
		break;
	case HIT_HIDE:
		if( m_buttons[m_iSelected].flags & TOUCH_FLAG_HIDE )
			m_buttons[m_iSelected].flags &= ~( TOUCH_FLAG_HIDE | TOUCH_FLAG_DEF_HIDE );
		else
			m_buttons[m_iSelected].flags |= TOUCH_FLAG_HIDE | TOUCH_FLAG_DEF_HIDE;
		m_bDirty = true;
		if(( m_buttons[m_iSelected].flags & TOUCH_FLAG_HIDE ) && !m_bShowHidden )
		{
			m_iSelected = -1;
			Toast( "Кнопка скрыта. Показать: «Скрытые»", "Button hidden. See it with \"Hidden\"" );
		}
		break;
	case HIT_ICON:
		m_overlay = OV_ICON;
		m_iPickerScroll = 0;
		break;
	case HIT_COMMAND:
		m_overlay = OV_COMMAND;
		m_iPickerScroll = 0;
		break;
	case HIT_DELETE:
		memmove( &m_buttons[m_iSelected], &m_buttons[m_iSelected + 1], ( m_iButtons - m_iSelected - 1 ) * sizeof( m_buttons[0] ));
		m_iButtons--;
		m_iSelected = -1;
		m_bDirty = true;
		break;
	case HIT_OV_CLOSE:
	case HIT_OV_BACKDROP:
		m_say.End();
		m_cmd.End();
		m_overlay = OV_NONE;
		break;
	case HIT_OV_SAY_FIELD:
		m_cmd.End();
		m_say.Begin( m_say.text, m_sayField );
		break;
	case HIT_OV_CMD_FIELD:
		m_say.End();
		m_cmd.Begin( m_cmd.text, m_cmdField );
		break;
	case HIT_OV_SAY_ADD:
		FinishCustom( true );
		break;
	case HIT_OV_CMD_ADD:
		FinishCustom( false );
		break;
	case HIT_OV_NO:
		if( m_overlay == OV_CONFIRM_EXIT )
		{
			m_overlay = OV_NONE;
			Load( m_iScheme, false ); // drop the changes
			Hide();
			return;
		}
		if( m_overlay == OV_CONFIRM_SCHEME )
			Load( m_iPendingScheme, false );
		m_overlay = OV_NONE;
		break;
	case HIT_OV_YES:
		if( m_overlay == OV_CONFIRM_EXIT )
		{
			Apply();
			m_overlay = OV_NONE;
			Hide();
			return;
		}
		if( m_overlay == OV_CONFIRM_SCHEME )
		{
			Apply();
			Load( m_iPendingScheme, false );
		}
		else if( m_overlay == OV_CONFIRM_RESET )
		{
			Load( m_iScheme, true );
			Toast( "Стандартная раскладка", "Default layout" );
		}
		m_overlay = OV_NONE;
		break;
	}
}

bool CCzmTouchEditor::KeyDown( int key )
{
	Layout();

	if(( m_say.active && m_say.KeyDown( key )) || ( m_cmd.active && m_cmd.KeyDown( key )))
		return true;

	if( UI::Key::IsLeftMouse( key ))
	{
		int hit = HitTest();

		if(( m_say.active && hit != HIT_OV_SAY_FIELD && hit != HIT_OV_SAY_ADD )
			|| ( m_cmd.active && hit != HIT_OV_CMD_FIELD && hit != HIT_OV_CMD_ADD ))
		{
			m_say.End();
			m_cmd.End();
		}

		m_iPressed = hit;
		m_iDownX = uiStatic.cursorX;
		m_iDownY = uiStatic.cursorY;
		m_bMoved = false;
		m_iSlider = 0;
		m_iDragButton = -1;
		m_bPickerScrolling = false;
		m_bPickerMaybeScroll = ( m_overlay == OV_ADD || m_overlay == OV_COMMAND || m_overlay == OV_ICON ) && m_ovClip.HasCursor();
		m_iScrollAtDown = m_iPickerScroll;

		if( hit >= HIT_BUTTON )
		{
			const CzmTouchButton &b = m_buttons[hit - HIT_BUTTON];

			m_iSelected = m_iDragButton = hit - HIT_BUTTON;
			m_iHudSelected = -1;
			m_flGrabX = (float)uiStatic.cursorX / W - b.x1;
			m_flGrabY = (float)uiStatic.cursorY / H - b.y1;
		}
		else if( hit >= HIT_HUD && hit < HIT_HUD + HUD_BLOCKS )
		{
			int kind = hit - HIT_HUD;

			m_iHudSelected = m_iDragHud = kind;
			m_iSelected = -1;
			m_flGrabX = (float)uiStatic.cursorX / W - m_hud[kind].x;
			m_flGrabY = (float)uiStatic.cursorY / H - m_hud[kind].y;
		}
		else if( hit == HIT_SIZE || hit == HIT_OPACITY )
		{
			m_iSlider = hit;
			SetSlider( hit );
		}
		return true;
	}

	if( UI::Key::IsEscape( key ))
	{
		if( m_say.active || m_cmd.active )
		{
			m_say.End();
			m_cmd.End();
		}
		else if( m_overlay != OV_NONE )
			m_overlay = OV_NONE;
		else if( m_iSelected >= 0 || m_iHudSelected >= 0 )
			m_iSelected = m_iHudSelected = -1;
		else
			Exit();
		return true;
	}

	return CMenuFramework::KeyDown( key );
}

bool CCzmTouchEditor::KeyUp( int key )
{
	if( UI::Key::IsLeftMouse( key ))
	{
		int pressed = m_iPressed;
		int hit;
		bool tap = !m_bMoved && !m_bPickerScrolling && !m_iSlider;

		Layout();
		hit = HitTest();
		m_iPressed = HIT_NONE;
		m_iDragButton = m_iDragHud = -1;
		m_bSnapX = false;
		m_flSnapY = -1.0f;
		m_iSlider = 0;
		m_bPickerScrolling = m_bPickerMaybeScroll = false;

		if( tap && hit == pressed )
			Activate( hit );
		return true;
	}

	return CMenuFramework::KeyUp( key );
}

bool CCzmTouchEditor::MouseMove( int x, int y )
{
	int dx = uiStatic.cursorX - m_iDownX, dy = uiStatic.cursorY - m_iDownY;

	CMenuFramework::MouseMove( x, y );
	Layout();

	if( m_iSlider )
	{
		SetSlider( m_iSlider );
		return true;
	}

	if( m_iDragButton >= 0 )
	{
		CzmTouchButton &b = m_buttons[m_iDragButton];
		float w = b.x2 - b.x1, h = b.y2 - b.y1;
		float nx, ny;

		if( !m_bMoved && abs( dx ) + abs( dy ) < H * 0.012f )
			return true;

		m_bMoved = true;
		nx = bound( 0.0f, (float)uiStatic.cursorX / W - m_flGrabX, 1.0f - w );
		ny = bound( 0.0f, (float)uiStatic.cursorY / H - m_flGrabY, 1.0f - h );
		b.x1 = nx;
		b.y1 = ny;
		b.x2 = nx + w;
		b.y2 = ny + h;
		m_bDirty = true;
		return true;
	}

	if( m_iDragHud >= 0 )
	{
		CzmHudBlock &b = m_hud[m_iDragHud];
		CzmHud::Rect p;
		float nx, ny;

		if( !m_bMoved && abs( dx ) + abs( dy ) < H * 0.012f )
			return true;

		m_bMoved = true;
		nx = (float)uiStatic.cursorX / W - m_flGrabX;
		ny = (float)uiStatic.cursorY / H - m_flGrabY;

		// stick to the centre line and to the row of another block
		m_bSnapX = fabsf( nx - 0.5f ) < 0.012f;
		if( m_bSnapX )
			nx = 0.5f;
		m_flSnapY = -1.0f;
		for( int i = 0; i < HUD_BLOCKS; i++ )
		{
			// rows are for the text blocks, the others only stick to the centre
			if( i == m_iDragHud || i >= CzmHud::COUNT || m_iDragHud >= CzmHud::COUNT || m_hud[i].hidden )
				continue;
			if( fabsf( ny - m_hud[i].y ) < 0.015f )
			{
				ny = m_hud[i].y;
				m_flSnapY = ny;
				break;
			}
		}

		b.x = nx;
		b.y = ny;
		b = HudClamp( m_iDragHud, b );

		// keep the saved centre where the block is really drawn: it stops at the screen edges
		p = HudLayout( m_iDragHud );
		b.x = ( p.x + p.w * 0.5f ) / W;
		b.y = ( p.y + p.h * 0.5f ) / H;
		if( m_flSnapY >= 0.0f )
			m_flSnapY = b.y;
		m_bDirty = true;
		return true;
	}

	if( m_bPickerMaybeScroll )
	{
		if( !m_bPickerScrolling && abs( dy ) > H * 0.02f && m_iPickerMaxScroll > 0 )
		{
			m_bPickerScrolling = true;
			m_iPressed = HIT_NONE;
		}
		if( m_bPickerScrolling )
			m_iPickerScroll = bound( 0, m_iScrollAtDown - dy, m_iPickerMaxScroll );
	}

	return true;
}

void CCzmTouchEditor::Char( int key )
{
	m_say.Char( key );
	m_cmd.Char( key );
}

/*
=================
drawing
=================
*/
// the frame of server messages: a dashed border, two sample texts and its label in the middle
void CCzmTouchEditor::DrawMessageFrame( const CzmRect &r, float opacity, bool selected )
{
	HFont font = CZM_Font( CZMF_SMALL );
	HFont label = CZM_Font( CZMF_TILE_STATUS );
	const unsigned int color = selected ? PackRGBA( 239, 68, 68, 255 ) : CZM_White( 120 );
	int t = Q_max( 2, (int)( H * 0.004f )), dash = H * 0.03f;
	CzmRect chip = HudGrab( CzmHud::MESSAGES );

	for( int x = r.x; x < r.x + r.w; x += dash * 2 )
	{
		UI_FillRect( x, r.y, Q_min( dash, r.x + r.w - x ), t, color );
		UI_FillRect( x, r.y + r.h - t, Q_min( dash, r.x + r.w - x ), t, color );
	}
	for( int y = r.y; y < r.y + r.h; y += dash * 2 )
	{
		UI_FillRect( r.x, y, t, Q_min( dash, r.y + r.h - y ), color );
		UI_FillRect( r.x + r.w - t, y, t, Q_min( dash, r.y + r.h - y ), color );
	}

	DrawServerSample( m_iMsgStyle, CZM_Rect( r.x, r.y + H * 0.13f, r.w, r.h - H * 0.13f ), CZM_FontHeight( font ) + 6, opacity, font );

	CZM_DrawPill( UI_DIR "button_secondary.png", chip.x, chip.y, chip.w, chip.h, selected ? PackRGBA( 255, 170, 170, 255 ) : CZM_White( 225 ));
	CZM_DrawText( label, chip.x, chip.y + ( chip.h - CZM_FontHeight( label )) / 2, chip.w, HudName( CzmHud::MESSAGES ),
		selected ? PackRGBA( 255, 140, 140, 255 ) : CZM_White(), QM_CENTER );
}

void CCzmTouchEditor::DrawHud( void )
{
	CzmMenuHudPainter painter;
	int frame = Q_max( 2, (int)( H * 0.004f ));

	// the frame of server messages lies under everything, the blocks over it
	for( int n = 0; n < HUD_BLOCKS; n++ )
	{
		const int i = n == 0 ? CzmHud::MESSAGES : n - 1 < CzmHud::MESSAGES ? n - 1 : n;
		CzmHud::Rect p = HudLayout( i );
		CzmRect r = CZM_Rect( p.x, p.y, p.w, p.h );
		bool selected = i == m_iHudSelected, conflict = m_conflict[i] >= 0, hidden = m_hud[i].hidden;
		bool round = i == CzmHud::RADAR && m_iRadarStyle != CzmHud::RADAR_TACTICAL;

		if( hidden && !m_bShowHidden )
			continue;
		if( hidden )
			p.opacity *= 0.3f; // shown pale, like hidden buttons

		if( i == CzmHud::MESSAGES )
		{
			DrawMessageFrame( r, p.opacity, selected );
			continue;
		}

		if( round )
		{
			// a soft halo around the round radar instead of a frame
			int halo = r.w * 0.12f;
			if( conflict )
				CZM_DrawImage( UI_DIR "glow.png", r.x - halo, r.y - halo, r.w + halo * 2, r.h + halo * 2, ConflictColor( 230 ));
			if( selected )
				CZM_DrawImage( UI_DIR "glow.png", r.x - halo, r.y - halo, r.w + halo * 2, r.h + halo * 2, PackRGBA( 239, 68, 68, 230 ));
		}

		// the block exactly as in the match, at the player's opacity
		if( i == CzmHud::RADAR )
			CZM_DrawRadarPreview( m_iRadarStyle, r.x, r.y, r.w, p.opacity );
		else if( i == CzmHud::CHAT )
			DrawChatSample( m_iMsgStyle, r.x, r.y + r.h, (int)ChatLineHeight( H ), p.opacity, CZM_Font( CZMF_SMALL ));
		else if( i == CzmHud::DOWNLOADS )
			DrawDownloadSample( p );
		else
			CzmHud::Paint( painter, i, m_iHudStyle, p, CzmHud::samples[i], false );

		if( !round )
		{
			if( conflict )
			{
				UI_FillRect( r.x, r.y, r.w, r.h, ConflictColor( 60 ));
				DrawFrame( r.Grown( frame ), frame, ConflictColor( 255 ));
			}
			if( selected )
				DrawFrame( r.Grown( frame * ( conflict ? 2 : 1 )), frame, PackRGBA( 239, 68, 68, 255 ));
			else if( !conflict )
				DrawFrame( r, 1, CZM_White( 70 )); // the compact style has no plate, show where the block ends
		}

		if( hidden )
		{
			// crossed-out mark, as on hidden buttons
			int d = Q_min( r.w, r.h ) * 0.34f;
			CZM_DrawImage( UI_DIR "dot.png", r.x + r.w - d, r.y, d, d, PackRGBA( 60, 64, 72, 230 ));
			CZM_DrawImage( UI_DIR "icon_close.png", r.x + r.w - d + d / 5, r.y + d / 5, d * 3 / 5, d * 3 / 5 );
		}
		// no name under the block: the numbers say what it is, the panel and the warning name it
	}
}

void CCzmTouchEditor::DrawButtons( void )
{
	HFont font = CZM_Font( CZMF_SMALL );

	for( int i = 0; i < m_iButtons; i++ )
	{
		const CzmTouchButton &b = m_buttons[i];
		bool hidden = ( b.flags & TOUCH_FLAG_HIDE ) != 0;
		CzmRect r = ButtonRect( i );
		char texture[96];

		if( !ButtonEditable( b ) || ( hidden && !m_bShowHidden ))
			continue;

		if( m_conflict[HUD_BLOCKS + i] >= 0 )
		{
			int halo = r.w * 0.45f, ring = r.w * 0.08f;
			CZM_DrawImage( UI_DIR "glow.png", r.x - halo, r.y - halo, r.w + halo * 2, r.h + halo * 2, ConflictColor( 200 ));
			if( i != m_iSelected )
				CZM_DrawImage( UI_DIR "dot.png", r.x - ring, r.y - ring, r.w + ring * 2, r.h + ring * 2, ConflictColor( 220 ));
		}

		if( i == m_iSelected )
		{
			int glow = r.w * 0.12f;
			CZM_DrawImage( UI_DIR "dot.png", r.x - glow, r.y - glow, r.w + glow * 2, r.h + glow * 2, PackRGBA( 239, 68, 68, 150 ));
		}

		snprintf( texture, sizeof( texture ), "%s.png", b.texture );
		CZM_DrawImage( texture, r.x, r.y, r.w, r.h, PackRGBA( 255, 255, 255, hidden ? 70 : b.color[3] ));

		if( hidden )
		{
			// crossed-out mark for hidden buttons
			int d = r.w * 0.34f;
			CZM_DrawImage( UI_DIR "dot.png", r.x + r.w - d, r.y, d, d, PackRGBA( 60, 64, 72, 230 ));
			CZM_DrawImage( UI_DIR "icon_close.png", r.x + r.w - d + d / 5, r.y + d / 5, d * 3 / 5, d * 3 / 5 );
		}
		else if( !strcmp( b.command, "+reload" ))
			DrawReloadPreview( r ); // the match shows the clip on it

		// names only in the editor, like in PUBG
		CZM_DrawText( font, r.x + r.w / 2 - H * 0.14f, r.y + r.h + 2, H * 0.28f, ButtonLabel( b ),
			i == m_iSelected ? PackRGBA( 255, 120, 120, 255 ) : m_conflict[HUD_BLOCKS + i] >= 0 ? PackRGBA( 255, 196, 90, 255 ) : CZM_White( 230 ), QM_CENTER );
	}
}

// lines the dragged HUD block snapped to
void CCzmTouchEditor::DrawGuides( void )
{
	int t = Q_max( 1, (int)( H * 0.003f ));

	if( m_iDragHud < 0 )
		return;
	if( m_bSnapX )
		UI_FillRect( W / 2 - t / 2, 0, t, H, PackRGBA( 239, 68, 68, 170 ));
	if( m_flSnapY >= 0.0f )
		UI_FillRect( 0, (int)( m_flSnapY * H ) - t / 2, W, t, PackRGBA( 239, 68, 68, 170 ));
}

void CCzmTouchEditor::DrawBar( void )
{
	HFont font = CZM_Font( CZMF_TILE_STATUS );
	int inset;
	char text[8];

	if( m_bCollapsed )
	{
		CZM_DrawSliced( UI_DIR "card.png", m_expand.x, m_expand.y - H * 0.03f, m_expand.w, m_expand.h + H * 0.03f, 30, (int)( H * 0.02f ));
		CZM_DrawText( font, m_expand.x, m_expand.y + ( m_expand.h - CZM_FontHeight( font )) / 2, m_expand.w,
			CZM_IsRussian() ? "Панель" : "Panel", CZM_White(), QM_CENTER );
		return;
	}

	CZM_DrawPanel( m_bar );

	// scheme 1 | 2 | 3
	{
		CzmRect all = CZM_Rect( m_schemes[0].x, m_schemes[0].y, m_schemes[CZM_SCHEMES - 1].x + m_schemes[CZM_SCHEMES - 1].w - m_schemes[0].x, m_schemes[0].h );
		inset = all.h * 0.1f;
		CZM_DrawPill( UI_DIR "chip_lang.png", all.x, all.y, all.w, all.h );
		for( int i = 0; i < CZM_SCHEMES; i++ )
		{
			const CzmRect &r = m_schemes[i];
			bool active = i + 1 == m_iScheme;

			if( active )
				CZM_DrawPill( UI_DIR "pill_lang_on.png", r.x + inset, r.y + inset, r.w - inset * 2, r.h - inset * 2 );
			snprintf( text, sizeof( text ), "%d", i + 1 );
			CZM_DrawText( font, r.x, r.y + ( r.h - CZM_FontHeight( font )) / 2, r.w, text, active ? CZM_White() : CZM_Grey(), QM_CENTER );
		}
	}

	CZM_DrawButton( UI_DIR "button_secondary.png", m_add, CZM_IsRussian() ? "+ Добавить" : "+ Add", CZM_White(), IsPressed( HIT_ADD ), CZMF_TILE_STATUS );
	CZM_DrawButton( m_bShowHidden ? UI_DIR "button_danger.png" : UI_DIR "button_secondary.png", m_hidden,
		CZM_IsRussian() ? "Скрытые" : "Hidden", m_bShowHidden ? PackRGBA( 255, 150, 150, 255 ) : CZM_White(), IsPressed( HIT_HIDDEN ), CZMF_TILE_STATUS );
	CZM_DrawButton( UI_DIR "button_secondary.png", m_reset, CZM_IsRussian() ? "Сброс" : "Reset", CZM_White(), IsPressed( HIT_RESET ), CZMF_TILE_STATUS );
	CZM_DrawButton( UI_DIR "button_primary.png", m_save, CZM_IsRussian() ? "Сохранить" : "Save", CZM_White(), IsPressed( HIT_SAVE ), CZMF_TILE_STATUS );
	CZM_DrawButton( UI_DIR "button_secondary.png", m_exit, CZM_IsRussian() ? "Выход" : "Exit", CZM_White(), IsPressed( HIT_EXIT ), CZMF_TILE_STATUS );

	// collapse: a chevron pointing up
	{
		int s = m_collapse.h * 0.5f;
		CZM_DrawImage( UI_DIR "chip_round.png", m_collapse.x, m_collapse.y, m_collapse.w, m_collapse.h, IsPressed( HIT_COLLAPSE ) ? CZM_Grey() : CZM_White());
		CZM_DrawImage( TOUCH_DIR "forward.png", m_collapse.x + ( m_collapse.w - s ) / 2, m_collapse.y + ( m_collapse.h - s ) / 2, s, s );
	}
}

void CCzmTouchEditor::DrawSlider( const CzmRect &r, float t, const char *label, const char *value )
{
	HFont font = CZM_Font( CZMF_SMALL );
	HFont valueFont = CZM_Font( CZMF_TILE_STATUS );
	int valueW = H * 0.10f;
	int x0 = r.x, x1 = r.x + r.w - H * 0.125f; // the knob at 100% does not cover the value
	int cy = r.y + r.h * 0.62f;
	int track = Q_max( 3, (int)( H * 0.009f )), knob = H * 0.045f;
	int kx = x0 + (int)( bound( 0.0f, t, 1.0f ) * ( x1 - x0 ));

	CZM_DrawText( font, r.x, r.y - CZM_FontHeight( font ) / 2, r.w, label, CZM_Grey());
	UI_FillRect( x0, cy - track / 2, x1 - x0, track, CZM_White( 45 ));
	UI_FillRect( x0, cy - track / 2, kx - x0, track, PackRGBA( 230, 38, 38, 255 ));
	CZM_DrawImage( UI_DIR "dot.png", kx - knob / 2, cy - knob / 2, knob, knob );
	CZM_DrawText( valueFont, r.x + r.w - valueW, cy - CZM_FontHeight( valueFont ) / 2, valueW, value, CZM_White(), QM_RIGHT );
}

void CCzmTouchEditor::DrawPanel( void )
{
	const CzmTouchButton &b = m_buttons[m_iSelected];
	HFont titleFont = CZM_Font( CZMF_NICK );
	HFont smallFont = CZM_Font( CZMF_SMALL );
	int pad = H * 0.035f, icon = H * 0.07f;
	float size = ButtonSize( m_iSelected );
	char texture[96], value[32];
	bool hidden = ( b.flags & TOUCH_FLAG_HIDE ) != 0;

	CZM_DrawPanel( m_panel );

	// what the button is: icon, name and command
	snprintf( texture, sizeof( texture ), "%s.png", b.texture );
	CZM_DrawImage( texture, m_panel.x + pad, m_panel.y + H * 0.02f, icon, icon );
	CZM_DrawText( titleFont, m_panel.x + pad + icon + H * 0.02f, m_panel.y + H * 0.02f, m_panel.w - pad * 2 - icon, ButtonLabel( b ), CZM_White());
	if( m_conflict[HUD_BLOCKS + m_iSelected] >= 0 )
	{
		char text[160];

		snprintf( text, sizeof( text ), "%s %s", CZM_IsRussian() ? "Перекрывает:" : "Overlaps:", ItemName( m_conflict[HUD_BLOCKS + m_iSelected] ));
		CZM_DrawText( smallFont, m_panel.x + pad + icon + H * 0.02f, m_panel.y + H * 0.02f + CZM_FontHeight( titleFont ) + 2,
			m_panel.w - pad * 2 - icon, text, PackRGBA( 255, 196, 90, 255 ));
	}
	else
		CZM_DrawText( smallFont, m_panel.x + pad + icon + H * 0.02f, m_panel.y + H * 0.02f + CZM_FontHeight( titleFont ) + 2,
			m_panel.w - pad * 2 - icon, b.command, PackRGBA( 140, 146, 156, 255 ));

	snprintf( value, sizeof( value ), "%d%%", (int)( size / 0.06f * 100.0f + 0.5f ));
	DrawSlider( m_size, ( size - 0.03f ) / 0.12f, CZM_IsRussian() ? "Размер" : "Size", value );
	snprintf( value, sizeof( value ), "%d%%", (int)( b.color[3] * 100.0f / 255.0f + 0.5f ));
	DrawSlider( m_opacity, ( b.color[3] - 40 ) / 215.0f, CZM_IsRussian() ? "Видимость" : "Opacity", value );

	CZM_DrawButton( UI_DIR "button_secondary.png", m_hide, hidden ? ( CZM_IsRussian() ? "Показать" : "Show" ) : ( CZM_IsRussian() ? "Скрыть" : "Hide" ),
		CZM_White(), IsPressed( HIT_HIDE ), CZMF_TILE_STATUS );
	CZM_DrawButton( UI_DIR "button_secondary.png", m_icon, CZM_IsRussian() ? "Иконка" : "Icon", CZM_White(), IsPressed( HIT_ICON ), CZMF_TILE_STATUS );
	CZM_DrawButton( UI_DIR "button_secondary.png", m_command, CZM_IsRussian() ? "Действие" : "Action", CZM_White(), IsPressed( HIT_COMMAND ), CZMF_TILE_STATUS );
	CZM_DrawButton( UI_DIR "button_danger.png", m_delete, CZM_IsRussian() ? "Удалить" : "Delete", PackRGBA( 255, 150, 150, 255 ), IsPressed( HIT_DELETE ), CZMF_TILE_STATUS );
}

void CCzmTouchEditor::DrawHudPanel( void )
{
	const int kind = m_iHudSelected;
	const bool radar = kind == CzmHud::RADAR, messages = kind == CzmHud::CHAT || kind == CzmHud::MESSAGES;
	const bool downloads = kind == CzmHud::DOWNLOADS;
	const CzmHudBlock &b = m_hud[kind];
	const int current = radar ? m_iRadarStyle : messages ? m_iMsgStyle : m_iHudStyle;
	CzmMenuHudPainter painter;
	HFont titleFont = CZM_Font( CZMF_NICK );
	HFont smallFont = CZM_Font( CZMF_SMALL );
	int pad = H * 0.035f, icon = H * 0.07f;
	int miniW = radar ? icon : icon * 2.6f;
	int textX = m_panel.x + pad + miniW + H * 0.025f, textW = m_hudHide.x - H * 0.02f - textX;
	float minScale = HudMinScale( kind ), maxScale = HudMaxScale( kind );
	char text[160];

	CZM_DrawPanel( m_panel );

	// a small copy of the block in the chosen style, at full opacity
	if( radar )
		CZM_DrawRadarPreview( m_iRadarStyle, m_panel.x + pad, m_panel.y + H * 0.02f, icon, 1.0f );
	else if( messages )
	{
		// a tiny chat: three lines as coloured bars in the chosen look
		const int x = m_panel.x + pad, y = m_panel.y + H * 0.02f, bar = Q_max( 3, icon / 7 ), gap = bar;
		const int names[3][3] = { { 153, 204, 255 }, { 255, 63, 63 }, { 153, 255, 153 } };
		const float lengths[3][2] = { { 0.25f, 0.5f }, { 0.32f, 0.38f }, { 0.0f, 0.62f } };

		UI_FillRect( x, y, miniW, icon, PackRGBA( 40, 52, 60, 255 ));
		for( int k = 0; k < 3; k++ )
		{
			int ly = y + icon - ( 3 - k ) * ( bar + gap ) - gap / 2, lx = x + bar;
			int nameW = miniW * lengths[k][0], textW = miniW * lengths[k][1];

			if( m_iMsgStyle == CzmHud::MSG_CZM )
			{
				UI_FillRect( lx - bar / 2, ly - gap / 2, nameW + textW + bar, bar + gap, PackRGBA( 10, 14, 22, 200 ));
				UI_FillRect( lx - bar / 2, ly - gap / 2, 2, bar + gap, PackRGBA( 224, 37, 50, 255 ));
			}
			else if( m_iMsgStyle == CzmHud::MSG_OUTLINE )
				UI_FillRect( lx - 1, ly - 1, nameW + textW + 2, bar + 2, PackRGBA( 0, 0, 0, 255 ));
			if( nameW )
				UI_FillRect( lx, ly, nameW, bar, PackRGBA( names[k][0], names[k][1], names[k][2], 255 ));
			UI_FillRect( lx + nameW, ly, textW, bar, k == 2 ? PackRGBA( 153, 255, 153, 255 ) : PackRGBA( 255, 178, 0, 255 ));
		}
	}
	else if( downloads )
	{
		CzmHud::Rect mini = { (float)( m_panel.x + pad ), (float)( m_panel.y + H * 0.02f + icon * 0.2f ), (float)miniW, icon * 0.6f, 1.0f, 1.0f };
		DrawDownloadSample( mini );
	}
	else
	{
		CzmHud::Rect mini = { (float)( m_panel.x + pad ), (float)( m_panel.y + H * 0.02f ), (float)miniW, (float)icon, 1.0f, 1.0f };
		CzmHud::Paint( painter, kind, m_iHudStyle, mini, CzmHud::samples[kind], false );
	}

	CZM_DrawText( titleFont, textX, m_panel.y + H * 0.02f, textW, HudName( kind ), CZM_White());
	if( m_conflict[kind] >= 0 )
	{
		snprintf( text, sizeof( text ), "%s %s", CZM_IsRussian() ? "Перекрывает:" : "Overlaps:", ItemName( m_conflict[kind] ));
		CZM_DrawText( smallFont, textX, m_panel.y + H * 0.02f + CZM_FontHeight( titleFont ) + 2, textW, text, PackRGBA( 255, 196, 90, 255 ));
	}
	else
	{
		const bool ru = CZM_IsRussian();
		CZM_DrawText( smallFont, textX, m_panel.y + H * 0.02f + CZM_FontHeight( titleFont ) + 2, textW,
			radar ? ( ru ? "Свои игроки, бомба, заложники" : "Your team, the bomb, hostages" )
			: kind == CzmHud::CHAT ? ( ru ? "Новые строки внизу, ширина — ползунком" : "New lines at the bottom, the width with the slider" )
			: kind == CzmHud::MESSAGES ? ( ru ? "Тексты сервера останутся внутри рамки" : "Server texts stay inside the frame" )
			: downloads ? ( ru ? "Видна, пока скачиваются файлы сервера" : "Shown while server files download" )
			: ( ru ? "Интерфейс матча, один на все схемы" : "Match HUD, the same in every layout" ), PackRGBA( 140, 146, 156, 255 ));
	}

	// hide or show the block, back to its usual place
	CZM_DrawButton( UI_DIR "button_secondary.png", m_hudHide, b.hidden ? ( CZM_IsRussian() ? "Показать" : "Show" ) : ( CZM_IsRussian() ? "Скрыть" : "Hide" ),
		CZM_White(), IsPressed( HIT_HUD_HIDE ), CZMF_TILE_STATUS );
	CZM_DrawButton( UI_DIR "button_secondary.png", m_hudReset, CZM_IsRussian() ? "На место" : "Default", CZM_White(), IsPressed( HIT_HUD_RESET ), CZMF_TILE_STATUS );

	snprintf( text, sizeof( text ), "%d%%", (int)( b.scale * 100.0f + 0.5f ));
	DrawSlider( m_size, ( b.scale - minScale ) / ( maxScale - minScale ),
		kind == CzmHud::CHAT ? ( CZM_IsRussian() ? "Ширина" : "Width" ) : kind == CzmHud::MESSAGES ? ( CZM_IsRussian() ? "Размер рамки" : "Frame size" )
		: ( CZM_IsRussian() ? "Размер" : "Size" ), text );
	snprintf( text, sizeof( text ), "%d%%", (int)( b.opacity * 100.0f + 0.5f ));
	DrawSlider( m_opacity, ( b.opacity - 0.25f ) / 0.75f, CZM_IsRussian() ? "Видимость" : "Opacity", text );

	// the radar looks, or the style of all text blocks; the download indicator has one look
	for( int i = 0; i < HUD_STYLES && !downloads; i++ )
	{
		bool active = i == current;
		const char *name = radar ? CZM_RadarStyleName( i ) : messages ? CZM_MessageStyleName( i ) : CZM_IsRussian() ? s_hudStyles[i].ru : s_hudStyles[i].en;

		CZM_DrawButton( active ? UI_DIR "button_primary.png" : UI_DIR "button_secondary.png", m_hudStyles[i],
			name, active ? CZM_White() : PackRGBA( 200, 205, 215, 255 ), IsPressed( HIT_HUD_STYLE + i ), CZMF_TILE_STATUS );
	}
}

// what overlaps, under the bar; the editor shows it until the controls are moved apart
void CCzmTouchEditor::DrawConflictChip( void )
{
	HFont font = CZM_Font( CZMF_TILE_STATUS );
	char text[200];
	int dot, tw;
	CzmRect r;

	if( m_iConflicts > 1 )
		snprintf( text, sizeof( text ), CZM_IsRussian() ? "Перекрываются: %s и %s · ещё %d" : "Overlapping: %s and %s · %d more",
			ItemName( m_iConflictA ), ItemName( m_iConflictB ), m_iConflicts - 1 );
	else
		snprintf( text, sizeof( text ), CZM_IsRussian() ? "Перекрываются: %s и %s" : "Overlapping: %s and %s",
			ItemName( m_iConflictA ), ItemName( m_iConflictB ));

	dot = H * 0.022f;
	tw = Q_min( (int)( W * 0.8f ), CZM_TextWidth( font, text ) + dot * 2 + (int)( H * 0.10f ));
	r = CZM_Rect(( W - tw ) / 2, m_bCollapsed ? H * 0.075f : m_bar.y + m_bar.h + H * 0.02f, tw, H * 0.065f );

	CZM_DrawPill( UI_DIR "button_secondary.png", r.x, r.y, r.w, r.h, CZM_White( 235 ));
	CZM_DrawImage( UI_DIR "dot.png", r.x + H * 0.035f, r.y + ( r.h - dot ) / 2, dot, dot, ConflictColor( 255 ));
	CZM_DrawText( font, r.x + H * 0.035f + dot * 2, r.y + ( r.h - CZM_FontHeight( font )) / 2, r.w - H * 0.07f - dot * 2,
		text, PackRGBA( 255, 210, 130, 255 ), QM_CENTER );
}

void CCzmTouchEditor::DrawPicker( void )
{
	HFont titleFont = CZM_Font( CZMF_PANEL_TITLE );
	HFont font = CZM_Font( CZMF_TILE_STATUS );
	HFont smallFont = CZM_Font( CZMF_SMALL );
	int pad = H * 0.04f;
	int closeIcon = m_ovClose.h * 0.42f;
	const char *title;

	UI_FillRect( 0, 0, W, H, PackRGBA( 0, 0, 0, 170 ));
	CZM_DrawPanel( m_ovPanel );

	if( m_overlay == OV_ICON )
		title = CZM_IsRussian() ? "Выбери иконку" : "Choose an icon";
	else if( m_overlay == OV_ADD )
		title = CZM_IsRussian() ? "Новая кнопка" : "New button";
	else
		title = CZM_IsRussian() ? "Действие кнопки" : "Button action";

	CZM_DrawText( titleFont, m_ovPanel.x + pad, m_ovPanel.y + H * 0.03f, m_ovPanel.w - pad * 2, title, CZM_White());
	CZM_DrawImage( UI_DIR "icon_close.png", m_ovClose.x + ( m_ovClose.w - closeIcon ) / 2, m_ovClose.y + ( m_ovClose.h - closeIcon ) / 2,
		closeIcon, closeIcon, IsPressed( HIT_OV_CLOSE ) ? CZM_White() : PackRGBA( 190, 196, 206, 255 ));

	// groups on the left
	if( m_overlay != OV_ICON )
	{
		for( int i = 0; i < GROUP_COUNT; i++ )
		{
			const CzmRect &r = m_groups[i];
			bool active = i == m_iGroup;

			CZM_DrawSliced( active ? UI_DIR "tab_on.png" : UI_DIR "card.png", r.x, r.y, r.w, r.h, 30, (int)( H * 0.02f ),
				active || IsPressed( HIT_GROUP + i ) ? CZM_White() : CZM_White( 170 ));
			CZM_DrawText( font, r.x + H * 0.025f, r.y + ( r.h - CZM_FontHeight( font )) / 2, r.w - H * 0.04f,
				CZM_IsRussian() ? s_groups[i].ru : s_groups[i].en, active ? CZM_White() : PackRGBA( 200, 205, 215, 255 ));
		}
	}

	// own chat text and own command
	if( m_overlay != OV_ICON && m_iGroup == GROUP_CUSTOM )
	{
		CZM_DrawText( font, m_sayField.x, m_sayField.y - CZM_FontHeight( font ) - H * 0.012f, m_ovClip.w,
			CZM_IsRussian() ? "Сообщение в чат (например /zpmenu)" : "Chat message (for example /zpmenu)", CZM_White());
		CZM_DrawField( m_sayField, m_say, m_say.text, CZM_IsRussian() ? "Текст" : "Text", IsPressed( HIT_OV_SAY_FIELD ));
		CZM_DrawButton( UI_DIR "button_primary.png", m_sayAdd, CZM_IsRussian() ? "Готово" : "Done", CZM_White(), IsPressed( HIT_OV_SAY_ADD ), CZMF_TILE_STATUS );

		CZM_DrawText( font, m_cmdField.x, m_cmdField.y - CZM_FontHeight( font ) - H * 0.012f, m_ovClip.w,
			CZM_IsRussian() ? "Своя команда консоли (например +forward)" : "Own console command (for example +forward)", CZM_White());
		CZM_DrawField( m_cmdField, m_cmd, m_cmd.text, CZM_IsRussian() ? "Команда" : "Command", IsPressed( HIT_OV_CMD_FIELD ));
		CZM_DrawButton( UI_DIR "button_primary.png", m_cmdAdd, CZM_IsRussian() ? "Готово" : "Done", CZM_White(), IsPressed( HIT_OV_CMD_ADD ), CZMF_TILE_STATUS );

		CZM_DrawText( smallFont, m_cmdField.x, m_cmdField.y + m_cmdField.h + H * 0.03f, m_ovClip.w,
			CZM_IsRussian() ? "Команды с + работают, пока кнопка нажата: +forward, +jump, +duck" :
			"Commands with + work while the button is held: +forward, +jump, +duck", PackRGBA( 140, 146, 156, 255 ));
		return;
	}

	// cards: icon with the name under it
	UI::Scissor::PushScissor( m_ovClip.x, m_ovClip.y, m_ovClip.w, m_ovClip.h );
	for( int i = 0; i < m_iItems; i++ )
	{
		const CzmRect &r = m_items[i];
		int index = m_itemIndex[i];
		bool pressed = IsPressed( HIT_ITEM + index );
		const char *icon = m_overlay == OV_ICON ? s_icons[index] : s_actions[index].icon;
		int iconSize = m_overlay == OV_ICON ? r.w * 0.78f : r.w * 0.56f;
		bool current = m_overlay == OV_ICON && m_iSelected >= 0 && !stricmp( m_buttons[m_iSelected].texture + strlen( TOUCH_DIR ), icon );

		if( r.y + r.h < m_ovClip.y || r.y > m_ovClip.y + m_ovClip.h )
			continue;

		CZM_DrawSliced( current ? UI_DIR "card_on.png" : UI_DIR "card.png", r.x, r.y, r.w, r.h, 30, (int)( H * 0.02f ),
			pressed ? PackRGBA( 200, 200, 200, 255 ) : CZM_White());
		CZM_DrawImage( IconPath( icon ), r.x + ( r.w - iconSize ) / 2, r.y + ( m_overlay == OV_ICON ? ( r.h - iconSize ) / 2 : r.h * 0.08f ),
			iconSize, iconSize );

		if( m_overlay != OV_ICON )
			CZM_DrawText( smallFont, r.x + 4, r.y + r.h * 0.70f, r.w - 8, ActionLabel( s_actions[index] ), CZM_White(), QM_CENTER );
	}
	UI::Scissor::PopScissor();
}

void CCzmTouchEditor::DrawConfirm( void )
{
	HFont titleFont = CZM_Font( CZMF_PANEL_TITLE );
	int pad = H * 0.04f;
	int titleY = m_ovPanel.y + ( m_ovNo.y - m_ovPanel.y - CZM_FontHeight( titleFont )) / 2;
	const char *title, *yes, *no;
	bool ru = CZM_IsRussian();

	if( m_overlay == OV_CONFIRM_RESET )
	{
		title = ru ? "Вернуть стандартные кнопки и интерфейс?" : "Restore the default buttons and HUD?";
		yes = ru ? "Вернуть" : "Restore";
		no = ru ? "Отмена" : "Cancel";
	}
	else
	{
		title = ru ? "Сохранить изменения?" : "Save the changes?";
		yes = ru ? "Сохранить" : "Save";
		no = ru ? "Не сохранять" : "Don't save";
	}

	UI_FillRect( 0, 0, W, H, PackRGBA( 0, 0, 0, 170 ));
	CZM_DrawPanel( m_ovPanel );
	CZM_DrawText( titleFont, m_ovPanel.x + pad, titleY, m_ovPanel.w - pad * 2, title, CZM_White(), QM_CENTER );
	CZM_DrawButton( UI_DIR "button_secondary.png", m_ovNo, no, CZM_White(), IsPressed( HIT_OV_NO ));
	CZM_DrawButton( UI_DIR "button_primary.png", m_ovYes, yes, CZM_White(), IsPressed( HIT_OV_YES ));
}

void CCzmTouchEditor::Draw()
{
	bool dragging;

	Layout();

	// Always repaint the opaque preview, including while connected. Rendering the
	// paused world is not guaranteed and leaves old HUD/buttons in the framebuffer.
	CZM_DrawCover( CZM_Image( UI_DIR "editor_bg.png" ), 0, 0, W, H );

	// the match HUD under the buttons, as the game draws them
	FindConflicts();
	DrawHud();
	DrawButtons();

	// while a button or a HUD block is dragged nothing covers the screen
	dragging = ( m_iDragButton >= 0 || m_iDragHud >= 0 ) && m_bMoved;

	if( m_iSelected < 0 && m_iHudSelected < 0 && m_overlay == OV_NONE && !dragging && uiStatic.realTime - m_iShowTime < 6000 )
	{
		HFont font = CZM_Font( CZMF_TILE_STATUS );
		const char *hint = CZM_IsRussian() ? "Нажми на кнопку или блок интерфейса, чтобы настроить. Тащи, чтобы переместить."
			: "Tap a button or a HUD block to set it up. Drag it to move.";
		int tw = CZM_TextWidth( font, hint ) + H * 0.08f;
		CzmRect r = CZM_Rect(( W - tw ) / 2, H - H * 0.10f, tw, H * 0.065f );

		CZM_DrawPill( UI_DIR "button_secondary.png", r.x, r.y, r.w, r.h, CZM_White( 220 ));
		CZM_DrawText( font, r.x, r.y + ( r.h - CZM_FontHeight( font )) / 2, r.w, hint, CZM_White(), QM_CENTER );
	}

	if( dragging )
	{
		DrawGuides();
		return;
	}

	DrawBar();

	if( m_overlay == OV_NONE )
	{
		if( m_iSelected >= 0 )
			DrawPanel();
		else if( m_iHudSelected >= 0 )
			DrawHudPanel();
		else if( m_iConflicts > 0 )
			DrawConflictChip();
	}

	if( m_szToast && uiStatic.realTime - m_iToastTime < 2200 )
	{
		HFont font = CZM_Font( CZMF_TILE_STATUS );
		int tw = CZM_TextWidth( font, m_szToast ) + H * 0.08f;
		CzmRect r = CZM_Rect(( W - tw ) / 2, H * 0.45f, tw, H * 0.075f );

		CZM_DrawPill( UI_DIR "button_secondary.png", r.x, r.y, r.w, r.h );
		CZM_DrawText( font, r.x, r.y + ( r.h - CZM_FontHeight( font )) / 2, r.w, m_szToast, CZM_White(), QM_CENTER );
	}

	if( m_overlay == OV_ADD || m_overlay == OV_COMMAND || m_overlay == OV_ICON )
		DrawPicker();
	else if( m_overlay != OV_NONE )
		DrawConfirm();
}

ADD_MENU( menu_czmtouch, CCzmTouchEditor, UI_CzmTouch_Menu );

void CZM_OpenTouchEditor( void )
{
	UI_CzmTouch_Menu();
}
