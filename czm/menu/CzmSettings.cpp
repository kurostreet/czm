/*
CzmSettings.cpp - Counter Zombie Mobile settings screen
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
#include "utlstring.h"
#include "CzmMenu.h"

#define UI_DIR "gfx/czm/ui/"

/*
=================
setting values

Each row reads and writes the engine and client cvars directly,
changes apply at once and are saved when the screen closes.
=================
*/
namespace
{

float GetCvar( const char *name )
{
	return EngFuncs::GetCvarFloat( name );
}

void SetCvar( const char *name, float value )
{
	EngFuncs::CvarSetValue( name, value );
}

// avatars: the photo card, the game logo, our pictures
int AvatarCards( void )
{
	return 2 + CZM_AvatarCount();
}

// controls
float GetLook( void ) { return GetCvar( "sensitivity" ); }
void SetLook( float v ) { SetCvar( "sensitivity", v ); }

float GetZoom( void ) { return GetCvar( "czm_zoom_sens" ); }
void SetZoom( float v )
{
	SetCvar( "czm_zoom_sens", v );
	SetCvar( "zoom_sensitivity_ratio", v );
}

// movement: a smaller touch zone reaches full speed with a shorter finger move
#define CZM_ZONE_MAX 0.17f
#define CZM_ZONE_STEP 0.014f
float GetMove( void )
{
	return ( CZM_ZONE_MAX - GetCvar( "touch_forwardzone" )) / CZM_ZONE_STEP;
}

void SetMove( float v )
{
	float forward = GetCvar( "touch_forwardzone" );
	float side = GetCvar( "touch_sidezone" );
	float ratio = ( forward > 0.001f && side > 0.001f ) ? bound( 0.3f, side / forward, 1.5f ) : 0.6f;
	float zone = CZM_ZONE_MAX - v * CZM_ZONE_STEP;

	SetCvar( "touch_forwardzone", zone );
	SetCvar( "touch_sidezone", zone * ratio );
}

bool GyroAvailable( void ) { return GetCvar( "gyro_available" ) != 0.0f; }
float GetGyro( void ) { return GetCvar( "gyro_enable" ); }
void SetGyro( float v ) { SetCvar( "gyro_enable", v ); }
bool GyroOn( void ) { return GyroAvailable() && GetGyro() != 0.0f; }

float GetGyroPower( void ) { return GetCvar( "gyro_yaw" ); }
void SetGyroPower( float v )
{
	SetCvar( "gyro_yaw", v );
	SetCvar( "gyro_pitch", v );
}

// graphics
float GetBrightness( void ) { return GetCvar( "brightness" ); }
void SetBrightness( float v ) { SetCvar( "brightness", v ); }
float GetParallax( void ) { return GetCvar("czm_parallax")!=0.0f; }
void SetParallax( float v ) { SetCvar("czm_parallax",v); }

const int s_fpsValues[] = { 30, 60, 90, 120 };
float GetFps( void )
{
	float fps = GetCvar( "fps_max" );
	int best = 1;

	for( int i = 0; i < 4; i++ )
	{
		if( fabs( fps - s_fpsValues[i] ) < fabs( fps - s_fpsValues[best] ))
			best = i;
	}

	return best;
}
void SetFps( float v ) { SetCvar( "fps_max", s_fpsValues[(int)v] ); }

float GetShowFps( void ) { return GetCvar( "cl_showfps" ) != 0.0f; }
void SetShowFps( float v ) { SetCvar( "cl_showfps", v ); }

float GetShowPing( void ) { return GetCvar( "net_graph" ) != 0.0f; }
void SetShowPing( float v ) { SetCvar( "net_graph", v ? 3.0f : 0.0f ); }

// how the game draws: some phones show a black world with one renderer and work with another.
// The engine reads r_refdll from video.cfg at start and saves that file only on a clean exit,
// Android often just stops the app, so the line is written into video.cfg at once.
const char *s_renderers[3] = { "gles1", "gl4es", "gles3compat" };
float GetRenderer( void )
{
	const char *name = EngFuncs::GetCvarString( "r_refdll" );

	if( !name || !name[0] )
		name = EngFuncs::GetCvarString( "r_refdll_loaded" );
	for( int i = 0; i < 3; i++ )
	{
		if( name && !stricmp( name, s_renderers[i] ))
			return i;
	}
	return 0;
}
void SetRenderer( float v )
{
	const char *name = s_renderers[bound( 0, (int)v, 2 )];
	byte *old = EngFuncs::COM_LoadFile( "video.cfg" );
	CUtlString text;

	EngFuncs::CvarSetString( "r_refdll", name );

	// keep every other line of video.cfg
	for( const char *p = old ? (const char *)old : ""; *p; )
	{
		const char *end = strchr( p, '\n' );
		size_t len = end ? (size_t)( end - p + 1 ) : strlen( p );
		const char *q = p;

		while( *q == ' ' || *q == '\t' )
			q++;
		if( strncmp( q, "r_refdll ", 9 ) && strncmp( q, "r_refdll\t", 9 ))
			text.AppendFormat( "%.*s", (int)len, p );
		p += len;
	}
	if( text.Length() && text.Get()[text.Length() - 1] != '\n' )
		text.Append( "\n" );
	text.AppendFormat( "r_refdll \"%s\"\n", name );

	if( old )
		EngFuncs::COM_FreeFile( old );
	EngFuncs::COM_SaveFile( "video.cfg", text.Get(), text.Length());
}

// effects presets: corpse time, shells, smoke puffs, smoke sprite quality
const float s_effects[3][4] = { { 5, 10, 5, 2 }, { 60, 40, 20, 1 }, { 600, 120, 60, 0 } };
float GetEffects( void )
{
	float stay = GetCvar( "cl_corpsestay" );
	return stay <= 10.0f ? 0 : ( stay <= 120.0f ? 1 : 2 );
}
void SetEffects( float v )
{
	const float *preset = s_effects[(int)v];

	SetCvar( "cl_corpsestay", preset[0] );
	SetCvar( "max_shells", preset[1] );
	SetCvar( "max_smokepuffs", preset[2] );
	SetCvar( "fastsprites", preset[3] );
}

// text size: the console font (chat, messages) grows by whole steps and stays sharp
float GetTextSize( void )
{
	float scale = GetCvar( "con_fontscale" );
	return scale < 1.5f ? 0 : ( scale < 2.5f ? 1 : 2 );
}
void SetTextSize( float v ) { SetCvar( "con_fontscale", 1.0f + v ); }

// HUD size: the engine scales the client HUD, the new size is used from the next map
const float s_hudScales[3] = { 0.0f, 1.5f, 2.0f };
float GetHudSize( void )
{
	float scale = GetCvar( "hud_scale" );
	return scale < 1.25f ? 0 : ( scale < 1.75f ? 1 : 2 );
}
void SetHudSize( float v ) { SetCvar( "hud_scale", s_hudScales[(int)v] ); }

float GetShadows( void ) { return GetCvar( "cl_shadows" ) != 0.0f; }
void SetShadows( float v ) { SetCvar( "cl_shadows", v ); }
float GetWeather( void ) { return GetCvar( "cl_weather" ) != 0.0f; }
void SetWeather( float v ) { SetCvar( "cl_weather", v ); }
// cl_radartype 0 is the see-through radar

// sound
float GetVolume( void ) { return GetCvar( "volume" ); }
void SetVolume( float v ) { SetCvar( "volume", v ); }
float GetMusic( void ) { return GetCvar( "MP3Volume" ); }
void SetMusic( float v ) { SetCvar( "MP3Volume", v ); }
float GetMenuMusic( void ) { return bound( 0, (int)GetCvar( "czm_menu_music" ), 3 ); }
void SetMenuMusic( float v ) { SetCvar( "czm_menu_music", bound( 0, (int)v, 3 )); }
float GetUiVolume( void ) { return GetCvar( "czm_ui_volume" ); }
void SetUiVolume( float v ) { SetCvar( "czm_ui_volume", v ); }
float GetVoice( void ) { return GetCvar( "voice_enable" ) != 0.0f; }
void SetVoice( float v ) { SetCvar( "voice_enable", v ); }
bool VoiceOn( void ) { return GetVoice() != 0.0f; }
float GetVoiceIn( void ) { return GetCvar( "voice_scale" ); }
void SetVoiceIn( float v ) { SetCvar( "voice_scale", v ); }
float GetVoiceOut( void ) { return GetCvar( "voice_transmit_scale" ); }
void SetVoiceOut( float v ) { SetCvar( "voice_transmit_scale", v ); }
// in a match the voice chat owns the microphone, the test runs in the main menu
bool MicTestAvailable( void ) { return !CL_IsActive(); }

// game
float GetLang( void ) { return CZM_IsRussian() ? 0 : 1; }
void SetLang( float v ) { CZM_SetLanguage( v == 0.0f ); }

const char *s_xhairSizes[] = { "auto", "small", "medium", "large" };
float GetXhairSize( void )
{
	const char *size = EngFuncs::GetCvarString( "cl_crosshair_size" );

	for( int i = 0; i < 4; i++ )
	{
		if( size && !stricmp( size, s_xhairSizes[i] ))
			return i;
	}
	return 0;
}
void SetXhairSize( float v ) { EngFuncs::CvarSetString( "cl_crosshair_size", s_xhairSizes[(int)v] ); }

const struct { int r, g, b; } s_xhairColors[] =
{
	{ 50, 250, 50 }, { 250, 50, 50 }, { 50, 250, 250 }, { 250, 250, 50 }, { 255, 255, 255 },
};
#define CZM_XHAIR_COLORS ( sizeof( s_xhairColors ) / sizeof( s_xhairColors[0] ))

float GetXhairColor( void )
{
	int r = 50, g = 250, b = 50;

	sscanf( EngFuncs::GetCvarString( "cl_crosshair_color" ), "%d %d %d", &r, &g, &b );
	for( size_t i = 0; i < CZM_XHAIR_COLORS; i++ )
	{
		if( s_xhairColors[i].r == r && s_xhairColors[i].g == g && s_xhairColors[i].b == b )
			return i;
	}
	return -1;
}
void SetXhairColor( float v )
{
	char color[32];
	int i = (int)v;
	if( i < 0 || i >= (int)CZM_XHAIR_COLORS ) return;

	snprintf( color, sizeof( color ), "%d %d %d", s_xhairColors[i].r, s_xhairColors[i].g, s_xhairColors[i].b );
	EngFuncs::CvarSetString( "cl_crosshair_color", color );
}

float GetXhairDynamic( void ) { return GetCvar( "cl_dynamiccrosshair" ) != 0.0f; }
void SetXhairDynamic( float v ) { SetCvar( "cl_dynamiccrosshair", v ); }

float GetXhairTrans( void ) { return GetCvar( "cl_crosshair_translucent" ) != 0.0f; }
void SetXhairTrans( float v ) { SetCvar( "cl_crosshair_translucent", v ); }

// right hand is the first option
float GetHand( void ) { return GetCvar( "cl_righthand" ) != 0.0f ? 0 : 1; }
void SetHand( float v ) { SetCvar( "cl_righthand", v == 0.0f ? 1.0f : 0.0f ); }

float GetAutoSwitch( void ) { return GetCvar( "_cl_autowepswitch" ) != 0.0f; }
void SetAutoSwitch( float v ) { SetCvar( "_cl_autowepswitch", v ); }

float GetScheme( void ) { return CZM_TouchScheme() - 1; }
void SetScheme( float v ) { CZM_SetTouchScheme( (int)v + 1, false ); }

// shop: our wheel or grid, or the server's classic text menu (shown as cards)
float GetShop( void )
{
	if( GetCvar( "_vgui_menus" ) == 0.0f )
		return 2;
	return GetCvar( "czm_shop" ) == 2.0f ? 1 : 0;
}
void SetShop( float v )
{
	int style = (int)v;

	SetCvar( "_vgui_menus", style == 2 ? 0.0f : 1.0f );
	if( style < 2 )
		SetCvar( "czm_shop", style + 1.0f );
}

float GetShopAuto( void ) { return GetCvar( "czm_shop_auto" ) != 0.0f; }
void SetShopAuto( float v ) { SetCvar( "czm_shop_auto", v ); }
float GetMenuCards( void ) { return GetCvar( "czm_menu_cards" ) != 0.0f; }
void SetMenuCards( float v ) { SetCvar( "czm_menu_cards", v ); }
float GetTabStyle( void ) { return bound( 0, (int)GetCvar( "czm_tab_style" ), 2 ); }
// the radar look; its place and size are set in the editor of buttons and HUD
float GetRadarStyle( void ) { return bound( 0, (int)GetCvar( "czm_hud_radar_style" ), 2 ); }
void SetRadarStyle( float v ) { SetCvar( "czm_hud_radar_style", bound( 0, (int)v, 2 )); EngFuncs::ClientCmd( false, "host_writeconfig\n" ); }
// how the chat and the server messages look
float GetMsgStyle( void ) { return bound( 0, (int)GetCvar( "czm_hud_msg_style" ), 2 ); }
void SetMsgStyle( float v ) { SetCvar( "czm_hud_msg_style", bound( 0, (int)v, 2 )); EngFuncs::ClientCmd( false, "host_writeconfig\n" ); }
void SetTabStyle( float v ) { SetCvar( "czm_tab_style", bound( 0, (int)v, 2 )); }

/*
=================
rows
=================
*/
enum ERowType
{
	ROW_SLIDER = 0,
	ROW_SWITCH,
	ROW_CHOICE,
	ROW_BUTTONS,  // touch layout: edit and reset
	ROW_COLORS,   // crosshair colours
	ROW_XHAIR,    // crosshair preview
	ROW_TABPREVIEW,
	ROW_NICK,
	ROW_ACCOUNT,
	ROW_AVATARS,
	ROW_SPRAYS,
	ROW_LAYOUTS,
	ROW_HUDEDIT,
	ROW_RADAR,    // three radar looks as cards
	ROW_MSGSTYLE, // three looks of the chat and server messages as cards
	ROW_MIC,      // microphone test: level meter and a start/stop button
};

enum EFormat
{
	FMT_DECIMAL = 0, // 1,5
	FMT_PERCENT,     // value * 100 %
	FMT_RANGE,       // share of the range in %
	FMT_INT,
};

struct CzmRow
{
	int type;
	const char *label;
	const char *hint;
	float ( *get )( void );
	void ( *set )( float );
	bool ( *active )( void ); // NULL: always active
	float min, max, step;
	int format;
	const char *options[4];
	int numOptions;
};

// everything about the layout of buttons and HUD sits together at the top
const CzmRow s_controls[] =
{
	{ ROW_CHOICE, "s_scheme", "s_scheme_hint", GetScheme, SetScheme, NULL, 0, 2, 1, 0, { "opt_scheme1", "opt_scheme2", "opt_scheme3" }, 3 },
	{ ROW_BUTTONS, "s_buttons", "s_buttons_hint", NULL, NULL, NULL, 0, 0, 0, 0, { "b_edit", "b_reset" }, 2 },
	{ ROW_LAYOUTS, "s_layouts", "s_layouts_hint", NULL, NULL, NULL, 0, 0, 0, 0, {}, 0 },
	{ ROW_SLIDER, "s_look", "s_look_hint", GetLook, SetLook, NULL, 0.5f, 10.0f, 0.1f, FMT_DECIMAL, {}, 0 },
	{ ROW_SLIDER, "s_zoom", "s_zoom_hint", GetZoom, SetZoom, NULL, 0.2f, 3.0f, 0.05f, FMT_DECIMAL, {}, 0 },
	{ ROW_SLIDER, "s_move", "s_move_hint", GetMove, SetMove, NULL, 1.0f, 10.0f, 1.0f, FMT_INT, {}, 0 },
	{ ROW_SWITCH, "s_gyro", "s_gyro_hint", GetGyro, SetGyro, GyroAvailable, 0, 1, 1, 0, {}, 0 },
	{ ROW_SLIDER, "s_gyro_power", NULL, GetGyroPower, SetGyroPower, GyroOn, 0.2f, 4.0f, 0.1f, FMT_DECIMAL, {}, 0 },
};

const CzmRow s_graphics[] =
{
	{ ROW_SLIDER, "s_brightness", NULL, GetBrightness, SetBrightness, NULL, 0.0f, 3.0f, 0.05f, FMT_RANGE, {}, 0 },
	{ ROW_CHOICE, "s_fps", "s_fps_hint", GetFps, SetFps, NULL, 0, 3, 1, 0, { "30", "60", "90", "120" }, 4 },
	{ ROW_CHOICE, "s_render", "s_render_hint", GetRenderer, SetRenderer, NULL, 0, 2, 1, 0, { "render_classic", "render_compatible", "render_modern" }, 3 },
	{ ROW_CHOICE, "s_textsize", "s_textsize_hint", GetTextSize, SetTextSize, NULL, 0, 2, 1, 0, { "opt_small", "opt_medium", "opt_large" }, 3 },
	{ ROW_CHOICE, "s_hudsize", "s_hudsize_hint", GetHudSize, SetHudSize, NULL, 0, 2, 1, 0, { "opt_small", "opt_medium", "opt_large" }, 3 },
	{ ROW_SWITCH, "s_showfps", NULL, GetShowFps, SetShowFps, NULL, 0, 1, 1, 0, {}, 0 },
	{ ROW_SWITCH, "s_showping", NULL, GetShowPing, SetShowPing, NULL, 0, 1, 1, 0, {}, 0 },
	{ ROW_CHOICE, "s_effects", "s_effects_hint", GetEffects, SetEffects, NULL, 0, 2, 1, 0, { "opt_low", "opt_mid", "opt_high" }, 3 },
	{ ROW_SWITCH, "s_shadows", NULL, GetShadows, SetShadows, NULL, 0, 1, 1, 0, {}, 0 },
	{ ROW_SWITCH, "s_weather", "s_weather_hint", GetWeather, SetWeather, NULL, 0, 1, 1, 0, {}, 0 },
	{ ROW_SWITCH, "s_parallax", "s_parallax_hint", GetParallax, SetParallax, NULL, 0, 1, 1, 0, {}, 0 },
};

const CzmRow s_sound[] =
{
	{ ROW_SLIDER, "s_volume", NULL, GetVolume, SetVolume, NULL, 0.0f, 1.0f, 0.05f, FMT_PERCENT, {}, 0 },
	{ ROW_SLIDER, "s_music", NULL, GetMusic, SetMusic, NULL, 0.0f, 1.0f, 0.05f, FMT_PERCENT, {}, 0 },
	{ ROW_CHOICE, "s_music_track", "s_music_track_hint", GetMenuMusic, SetMenuMusic, NULL, 0, 3, 1, 0, { "opt_music_silent", "opt_music_city", "opt_music_thoughts", "opt_music_rain" }, 4 },
	{ ROW_SLIDER, "s_ui_volume", NULL, GetUiVolume, SetUiVolume, NULL, 0.0f, 1.0f, 0.05f, FMT_PERCENT, {}, 0 },
	{ ROW_SWITCH, "s_voice", "s_voice_hint", GetVoice, SetVoice, NULL, 0, 1, 1, 0, {}, 0 },
	{ ROW_SLIDER, "s_voice_in", NULL, GetVoiceIn, SetVoiceIn, VoiceOn, 0.0f, 2.0f, 0.05f, FMT_PERCENT, {}, 0 },
	{ ROW_SLIDER, "s_voice_out", NULL, GetVoiceOut, SetVoiceOut, VoiceOn, 0.0f, 2.0f, 0.05f, FMT_PERCENT, {}, 0 },
	{ ROW_MIC, "s_mic", "s_mic_hint", NULL, NULL, MicTestAvailable, 0, 0, 0, 0, { "b_check", "b_stop" }, 2 },
};

const CzmRow s_game[] =
{
	{ ROW_CHOICE, "s_lang", NULL, GetLang, SetLang, NULL, 0, 1, 1, 0, { "RU", "EN" }, 2 },
	{ ROW_XHAIR, "s_xhair", "s_xhair_hint", NULL, NULL, NULL, 0, 0, 0, 0, {}, 0 },
	{ ROW_CHOICE, "s_xhair_size", NULL, GetXhairSize, SetXhairSize, NULL, 0, 3, 1, 0, { "opt_auto", "opt_small", "opt_medium", "opt_large" }, 4 },
	{ ROW_COLORS, "s_xhair_color", "s_xhair_color_hint", GetXhairColor, SetXhairColor, NULL, 0, 0, 0, 0, {}, 0 },
	{ ROW_SWITCH, "s_xhair_dyn", "s_xhair_dyn_hint", GetXhairDynamic, SetXhairDynamic, NULL, 0, 1, 1, 0, {}, 0 },
	{ ROW_SWITCH, "s_xhair_trans", NULL, GetXhairTrans, SetXhairTrans, NULL, 0, 1, 1, 0, {}, 0 },
	{ ROW_CHOICE, "s_hand", NULL, GetHand, SetHand, NULL, 0, 1, 1, 0, { "opt_right", "opt_left" }, 2 },
	{ ROW_SWITCH, "s_autoswitch", "s_autoswitch_hint", GetAutoSwitch, SetAutoSwitch, NULL, 0, 1, 1, 0, {}, 0 },
	{ ROW_CHOICE, "s_shop", "s_shop_hint", GetShop, SetShop, NULL, 0, 2, 1, 0, { "opt_wheel", "opt_grid", "opt_classic" }, 3 },
	{ ROW_SWITCH, "s_shop_auto", "s_shop_auto_hint", GetShopAuto, SetShopAuto, NULL, 0, 1, 1, 0, {}, 0 },
	{ ROW_SWITCH, "s_menucards", "s_menucards_hint", GetMenuCards, SetMenuCards, NULL, 0, 1, 1, 0, {}, 0 },
};

const CzmRow s_hud[] =
{
	{ ROW_RADAR, "s_radar_style", "s_radar_style_hint", GetRadarStyle, SetRadarStyle, NULL, 0, 2, 1, 0, {}, 3 },
	{ ROW_MSGSTYLE, "s_msg_style", "s_msg_style_hint", GetMsgStyle, SetMsgStyle, NULL, 0, 2, 1, 0, {}, 3 },
	{ ROW_CHOICE, "s_tab_style", "s_tab_style_hint", GetTabStyle, SetTabStyle, NULL, 0, 2, 1, 0, { "opt_tab_default", "opt_tab_compact", "opt_tab_tactical" }, 3 },
	{ ROW_TABPREVIEW, "s_tab_preview", "s_tab_preview_hint", NULL, NULL, NULL, 0, 0, 0, 0, {}, 0 },
};

const CzmRow s_profile[] =
{
	{ ROW_ACCOUNT, "s_account", "s_account_hint", NULL, NULL, NULL, 0, 0, 0, 0, {}, 0 },
	{ ROW_NICK, "s_nick", "s_nick_hint", NULL, NULL, NULL, 0, 0, 0, 0, {}, 0 },
	{ ROW_AVATARS, "s_avatar", "s_avatar_hint", NULL, NULL, NULL, 0, 0, 0, 0, {}, 0 },
	{ ROW_SPRAYS, "s_spray", "s_spray_hint", NULL, NULL, NULL, 0, 0, 0, 0, {}, 0 },
};

const struct
{
	const char *label;
	const char *icon;
	const CzmRow *rows;
	int count;
} s_tabs[CZM_TAB_COUNT] =
{
	{ "tab_controls", UI_DIR "icon_stick.png", s_controls, sizeof( s_controls ) / sizeof( s_controls[0] ) },
	{ "tab_graphics", UI_DIR "icon_display.png", s_graphics, sizeof( s_graphics ) / sizeof( s_graphics[0] ) },
	{ "tab_sound", UI_DIR "icon_sound.png", s_sound, sizeof( s_sound ) / sizeof( s_sound[0] ) },
	{ "tab_game", UI_DIR "icon_target.png", s_game, sizeof( s_game ) / sizeof( s_game[0] ) },
	{ "tab_hud", UI_DIR "icon_display.png", s_hud, sizeof( s_hud ) / sizeof( s_hud[0] ) },
	{ "tab_profile", UI_DIR "icon_user.png", s_profile, sizeof( s_profile ) / sizeof( s_profile[0] ) },
};

#define MAX_ROWS 12

void FillClipped( int x, int y, int w, int h, unsigned int color, const CzmRect &clip )
{
	int x0 = Q_max( x, clip.x ), y0 = Q_max( y, clip.y );
	int x1 = Q_min( x + w, clip.x + clip.w ), y1 = Q_min( y + h, clip.y + clip.h );

	if( x1 > x0 && y1 > y0 )
		UI_FillRect( x0, y0, x1 - x0, y1 - y0, color );
}

void FormatValue( const CzmRow &row, float value, char *buf, size_t size )
{
	switch( row.format )
	{
	case FMT_PERCENT:
		snprintf( buf, size, "%d%%", (int)( value * 100.0f + 0.5f ));
		break;
	case FMT_RANGE:
		snprintf( buf, size, "%d%%", (int)(( value - row.min ) / ( row.max - row.min ) * 100.0f + 0.5f ));
		break;
	case FMT_INT:
		snprintf( buf, size, "%d", (int)( value + 0.5f ));
		break;
	default:
		snprintf( buf, size, row.step < 0.1f ? "%.2f" : "%.1f", value );
		if( CZM_IsRussian( ))
		{
			for( char *p = buf; *p; p++ )
			{
				if( *p == '.' )
					*p = ',';
			}
		}
		break;
	}
}

} // namespace

/*
=================
CCzmSettings
=================
*/
class CCzmSettings : public CMenuFramework
{
public:
	CCzmSettings();

	void OpenTab( int tab );

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
		HIT_BACK,
		HIT_CONFIRM_YES,
		HIT_CONFIRM_NO,
		HIT_CONFIRM_PANEL,
		HIT_BACKDROP,
		HIT_TAB = 10,     // + tab
		HIT_ROW = 100,    // + row * 20 + part
	};

	struct RowLayout
	{
		CzmRect rect;      // whole row
		CzmRect control;   // slider track, switch, choice, field
		CzmRect parts[16]; // choice segments, buttons, colours, avatars, sprays
		int numParts;
	};

	void Layout( void );
	int HitTest( void ) const;
	bool IsPressed( int hit ) const { return m_iPressed == hit && HitTest() == hit; }
	void Activate( int hit );
	void SetSliderFromCursor( int row );
	void FinishNickEdit( void );
	void Toast( const char *key );
	void Save( void );
	void StopMicTest( void );

	const CzmRow &Row( int i ) const { return s_tabs[m_iTab].rows[i]; }
	int RowCount( void ) const { return s_tabs[m_iTab].count; }
	bool RowActive( int i ) const { return !Row( i ).active || Row( i ).active(); }

	void DrawTabs( void );
	void DrawRow( int i );
	void DrawSlider( int i, const RowLayout &l );
	void DrawSwitch( const CzmRect &r, bool on, bool dim );
	void DrawChoice( int i, const RowLayout &l );
	void DrawCrosshairPreview( const CzmRect &box );
	void DrawTabPreview( const CzmRect &box );
	void DrawConfirm( void );

	int m_iTab;
	int m_iPressed;
	int m_iDragRow;      // slider being dragged
	bool m_bMaybeScroll;
	bool m_bScrolling;
	int m_iDownY;
	int m_iScrollAtDown;
	int m_iScroll;
	int m_iMaxScroll;
	bool m_bConfirm;
	bool m_bTouchChanged;
	bool m_bMicTest;     // the microphone test runs
	bool m_bMicHeard;    // the meter moved during the test
	int m_iMicPing;      // last time the test was kept alive
	const char *m_szToast;
	int m_iToastTime;
	CzmTextEdit m_nick;

	// layout
	int W, H;
	CzmRect m_back, m_tabs[CZM_TAB_COUNT], m_panel, m_clip;
	CzmRect m_confirmPanel, m_confirmYes, m_confirmNo;
	RowLayout m_rows[MAX_ROWS];
};

CCzmSettings::CCzmSettings() : CMenuFramework( "CzmSettings" )
{
	m_iTab = CZM_TAB_CONTROLS;
	m_iPressed = HIT_NONE;
	m_iDragRow = -1;
	m_bMaybeScroll = m_bScrolling = false;
	m_iDownY = m_iScrollAtDown = m_iScroll = m_iMaxScroll = 0;
	m_bConfirm = false;
	m_bTouchChanged = false;
	m_bMicTest = m_bMicHeard = false;
	m_iMicPing = 0;
	m_szToast = NULL;
	m_iToastTime = 0;
	memset( &m_nick, 0, sizeof( m_nick ));
	W = H = 0;
}

void CCzmSettings::OpenTab( int tab )
{
	if( tab >= 0 && tab < CZM_TAB_COUNT && tab != m_iTab )
	{
		m_nick.End();
		StopMicTest();
		m_iTab = tab;
		m_iScroll = 0;
	}
}

void CCzmSettings::Show()
{
	m_iPressed = HIT_NONE;
	m_iDragRow = -1;
	m_bMaybeScroll = m_bScrolling = false;
	m_bConfirm = false;
	m_szToast = NULL;
	CMenuFramework::Show();
}

void CCzmSettings::Save( void )
{
	EngFuncs::ClientCmd( false, "host_writeconfig\n" );

	// movement zones live in the touch config
	if( m_bTouchChanged )
	{
		CZM_SaveTouchConfig();
		m_bTouchChanged = false;
	}
}

void CCzmSettings::StopMicTest( void )
{
	if( !m_bMicTest )
		return;

	m_bMicTest = false;
	EngFuncs::ClientCmd( false, "czm_mictest 0\n" );
}

void CCzmSettings::Hide()
{
	StopMicTest();
	FinishNickEdit();
	Save();
	CMenuFramework::Hide();
}

void CCzmSettings::Toast( const char *key )
{
	m_szToast = key;
	m_iToastTime = uiStatic.realTime;
}

void CCzmSettings::FinishNickEdit( void )
{
	if( !m_nick.active )
		return;

	m_nick.End();
	if( CZM_NickIsValid( m_nick.text ))
		CZM_SetNick( m_nick.text );
	else
		Toast( "nick_bad" );
}

/*
Avatar and spray cards: one row when the cards fit with a little shrinking,
otherwise even rows (12 cards in two rows of 6, never 11 and a lonely one).
*/
static void CardGrid( int width, int count, int *card, int *gap, int *columns )
{
	const int H = ScreenHeight;
	int c = H * 0.105f, g = H * 0.016f;

	count = Q_max( 1, count );
	if( count * c + ( count - 1 ) * g > width )
	{
		int fit = ( width - ( count - 1 ) * g ) / count; // one row with smaller cards
		if( fit >= H * 0.085f )
			c = fit;
	}

	int cols = Q_max( 1, ( width + g ) / ( c + g ));
	if( cols < count )
	{
		int lines = ( count + cols - 1 ) / cols;
		cols = ( count + lines - 1 ) / lines;
	}

	*card = c;
	*gap = g;
	*columns = Q_min( cols, count );
}

void CCzmSettings::Layout( void )
{
	int margin, tabW, tabH, gap, pad, contentY, contentH, rowH, controlW, total;

	W = ScreenWidth;
	H = ScreenHeight;
	margin = ( W - Q_min( (int)( W * 0.94f ), (int)( H * 1.85f ))) / 2;

	m_back = CZM_Rect( margin, H * 0.035f, H * 0.075f, H * 0.075f );

	// tabs on the left
	tabW = Q_min( (int)( W * 0.21f ), (int)( H * 0.34f ));
	tabH = H * 0.085f;
	gap = H * 0.012f;
	for( int i = 0; i < CZM_TAB_COUNT; i++ )
		m_tabs[i] = CZM_Rect( margin, H * 0.17f + i * ( tabH + gap ), tabW, tabH );

	// content panel
	m_panel = CZM_Rect( margin + tabW + H * 0.035f, H * 0.15f, 0, 0 );
	m_panel.w = W - margin - m_panel.x;
	m_panel.h = H - m_panel.y - H * 0.045f;

	pad = H * 0.028f;
	contentY = m_panel.y + H * 0.02f;
	contentH = m_panel.h - H * 0.04f;
	m_clip = CZM_Rect( m_panel.x, contentY, m_panel.w, contentH );

	rowH = H * 0.096f;
	controlW = Q_min( (int)(( m_panel.w - pad * 2 ) * 0.52f ), (int)( H * 0.66f ));

	// rows, scrolled
	total = 0;
	for( int i = 0; i < RowCount() && i < MAX_ROWS; i++ )
	{
		const CzmRow &row = Row( i );
		RowLayout &l = m_rows[i];
		int h = rowH;

		if( row.type == ROW_XHAIR )
			h = rowH * 1.6f;
		else if( row.type == ROW_TABPREVIEW )
			h = H * 0.50f;
		else if( row.type == ROW_RADAR || row.type == ROW_MSGSTYLE )
			h = H * 0.47f;
		else if( row.type == ROW_SPRAYS || row.type == ROW_AVATARS )
		{
			int card, cardGap, columns;
			int count = row.type == ROW_SPRAYS ? CZM_SprayCount() : AvatarCards();
			CardGrid( m_panel.w - pad * 2, Q_min( count, 16 ), &card, &cardGap, &columns );
			int lines = ( Q_min( count, 16 ) + columns - 1 ) / columns;

			h = H * 0.105f + lines * ( card + cardGap );
		}

		l.rect = CZM_Rect( m_panel.x + pad, contentY + total - m_iScroll, m_panel.w - pad * 2, h );
		l.control = CZM_Rect( l.rect.x + l.rect.w - controlW, l.rect.y, controlW, h );
		l.numParts = 0;
		total += h;

		switch( row.type )
		{
		case ROW_SLIDER:
			// whole height is a touch target, the value text sits on the right
			l.control = CZM_Rect( l.control.x, l.rect.y, controlW, h );
			break;
		case ROW_SWITCH:
		{
			int sw = H * 0.105f, sh = H * 0.056f;
			l.control = CZM_Rect( l.rect.x + l.rect.w - sw, l.rect.y + ( h - sh ) / 2, sw, sh );
			break;
		}
		case ROW_CHOICE:
		{
			int ch = H * 0.064f;
			int cw = row.get == GetRenderer || row.get == GetTabStyle || row.get == GetMenuMusic ? controlW : Q_min( controlW, (int)( row.numOptions * H * 0.16f ));
			l.control = CZM_Rect( l.rect.x + l.rect.w - cw, l.rect.y + ( h - ch ) / 2, cw, ch );
			for( int k = 0; k < row.numOptions; k++ )
				l.parts[k] = CZM_Rect( l.control.x + l.control.w * k / row.numOptions, l.control.y,
					l.control.w * ( k + 1 ) / row.numOptions - l.control.w * k / row.numOptions, ch );
			l.numParts = row.numOptions;
			break;
		}
		case ROW_MIC:
		{
			// level meter on the left of the control area, the button on the right
			int bh = H * 0.064f, bgap = H * 0.025f, bw = ( controlW - bgap ) / 2, mh = Q_max( 6, (int)( H * 0.018f ));
			l.parts[0] = CZM_Rect( l.control.x + l.control.w - bw, l.rect.y + ( h - bh ) / 2, bw, bh );
			l.control = CZM_Rect( l.control.x, l.rect.y + ( h - mh ) / 2, l.control.w - bw - bgap, mh );
			l.numParts = 1;
			break;
		}
		case ROW_BUTTONS:
		{
			int bh = H * 0.064f, bgap = H * 0.02f, bw = ( controlW - bgap ) / 2;
			for( int k = 0; k < 2; k++ )
				l.parts[k] = CZM_Rect( l.control.x + k * ( bw + bgap ), l.rect.y + ( h - bh ) / 2, bw, bh );
			l.numParts = 2;
			break;
		}
		case ROW_COLORS:
		{
			int d = H * 0.056f, cgap = H * 0.026f;
			int count = CZM_XHAIR_COLORS + 1;
			int x = l.rect.x + l.rect.w - count * d - ( count - 1 ) * cgap;
			for( int k = 0; k < count; k++ )
				l.parts[k] = CZM_Rect( x + k * ( d + cgap ), l.rect.y + ( h - d ) / 2, d, d );
			l.numParts = count;
			break;
		}
		case ROW_XHAIR:
		{
			int bw = Q_min( controlW, (int)( H * 0.42f ));
			l.control = CZM_Rect( l.rect.x + l.rect.w - bw, l.rect.y + H * 0.015f, bw, h - H * 0.03f );
			break;
		}
		case ROW_TABPREVIEW:
			l.control = CZM_Rect( l.rect.x, l.rect.y + H * 0.14f, l.rect.w, h - H * 0.16f );
			break;
		case ROW_RADAR:
		case ROW_MSGSTYLE:
		{
			// three cards under the title: the picture and its name
			int cardGap = H * 0.025f, cardW = ( l.rect.w - cardGap * 2 ) / 3, cardH = h - H * 0.135f;
			for( int k = 0; k < 3; k++ )
				l.parts[k] = CZM_Rect( l.rect.x + k * ( cardW + cardGap ), l.rect.y + H * 0.12f, cardW, cardH );
			l.numParts = 3;
			break;
		}
		case ROW_LAYOUTS:
		case ROW_HUDEDIT:
		case ROW_ACCOUNT:
		case ROW_NICK:
		{
			int fh = H * 0.07f;
			l.control = CZM_Rect( l.control.x, l.rect.y + ( h - fh ) / 2, controlW, fh );
			break;
		}
		case ROW_SPRAYS:
		case ROW_AVATARS:
		{
			int card, cardGap, columns;
			int count = Q_min( row.type == ROW_SPRAYS ? CZM_SprayCount() : AvatarCards(), 16 );
			CardGrid( l.rect.w, count, &card, &cardGap, &columns );

			for( int k = 0; k < count; k++ )
				l.parts[k] = CZM_Rect( l.rect.x + ( k % columns ) * ( card + cardGap ),
					l.rect.y + H * 0.105f + ( k / columns ) * ( card + cardGap ), card, card );
			l.numParts = count;
			break;
		}
		}
	}

	m_iMaxScroll = Q_max( 0, total - contentH );
	if( m_iScroll > m_iMaxScroll )
		m_iScroll = m_iMaxScroll;

	// confirm window
	{
		int cw = H * 0.74f, ch = H * 0.28f, cpad = H * 0.03f, bh = H * 0.07f;
		int bw = ( cw - cpad * 3 ) / 2;

		m_confirmPanel = CZM_Rect(( W - cw ) / 2, ( H - ch ) / 2, cw, ch );
		m_confirmNo = CZM_Rect( m_confirmPanel.x + cpad, m_confirmPanel.y + ch - cpad - bh, bw, bh );
		m_confirmYes = CZM_Rect( m_confirmPanel.x + cpad * 2 + bw, m_confirmNo.y, bw, bh );
	}
}

int CCzmSettings::HitTest( void ) const
{
	const int grow = ScreenHeight * 0.015f;
	int x = uiStatic.cursorX, y = uiStatic.cursorY;

	if( m_bConfirm )
	{
		if( m_confirmYes.HasCursor( ))
			return HIT_CONFIRM_YES;
		if( m_confirmNo.HasCursor( ))
			return HIT_CONFIRM_NO;
		return m_confirmPanel.HasCursor() ? HIT_CONFIRM_PANEL : HIT_BACKDROP;
	}

	if( m_back.Grown( grow ).HasCursor( ))
		return HIT_BACK;

	for( int i = 0; i < CZM_TAB_COUNT; i++ )
	{
		if( m_tabs[i].HasCursor( ))
			return HIT_TAB + i;
	}

	if( !m_clip.Contains( x, y ))
		return HIT_NONE;

	for( int i = 0; i < RowCount() && i < MAX_ROWS; i++ )
	{
		const RowLayout &l = m_rows[i];
		const CzmRow &row = Row( i );

		if( !l.rect.Contains( x, y ) || !RowActive( i ))
			continue;

		for( int k = 0; k < l.numParts; k++ )
		{
			if( l.parts[k].Grown( grow / 2 ).Contains( x, y ))
				return HIT_ROW + i * 20 + 1 + k;
		}

		switch( row.type )
		{
		case ROW_SLIDER:
			if( l.control.Contains( x, y ))
				return HIT_ROW + i * 20;
			break;
		case ROW_SWITCH:
			return HIT_ROW + i * 20; // the whole row toggles
		case ROW_LAYOUTS:
		case ROW_HUDEDIT:
		case ROW_ACCOUNT:
		case ROW_NICK:
			if( l.control.Grown( grow ).Contains( x, y ))
				return HIT_ROW + i * 20;
			break;
		}

		return HIT_NONE;
	}

	return HIT_NONE;
}

void CCzmSettings::SetSliderFromCursor( int i )
{
	const CzmRow &row = Row( i );
	const RowLayout &l = m_rows[i];
	int valueW = ScreenHeight * 0.11f;
	int x0 = l.control.x, x1 = l.control.x + l.control.w - valueW;
	float t, value;

	if( x1 <= x0 )
		return;

	t = bound( 0.0f, (float)( uiStatic.cursorX - x0 ) / ( x1 - x0 ), 1.0f );
	value = row.min + t * ( row.max - row.min );
	value = row.min + floorf(( value - row.min ) / row.step + 0.5f ) * row.step;
	value = bound( row.min, value, row.max );

	if( fabs( value - row.get()) > row.step * 0.25f )
	{
		row.set( value );
		if( row.set == SetMove )
			m_bTouchChanged = true;
	}
}

void CCzmSettings::Activate( int hit )
{
	if( hit == HIT_CONFIRM_PANEL || hit == HIT_NONE )
		return;

	CZM_PlayClick();

	if( hit == HIT_BACK )
	{
		Hide();
		return;
	}

	if( hit == HIT_CONFIRM_NO || hit == HIT_BACKDROP )
	{
		m_bConfirm = false;
		return;
	}

	if( hit == HIT_CONFIRM_YES )
	{
		// our default for the current layout, the player's changes to it are dropped
		m_bConfirm = false;
		CZM_SetTouchScheme( CZM_TouchScheme(), true );
		CZM_TouchResetHud();
		Toast( "reset_done" );
		return;
	}

	if( hit >= HIT_TAB && hit < HIT_TAB + CZM_TAB_COUNT )
	{
		OpenTab( hit - HIT_TAB );
		return;
	}

	if( hit >= HIT_ROW )
	{
		int i = ( hit - HIT_ROW ) / 20;
		int part = ( hit - HIT_ROW ) % 20 - 1;
		const CzmRow &row = Row( i );

		switch( row.type )
		{
		case ROW_SWITCH:
			row.set( row.get() != 0.0f ? 0.0f : 1.0f );
			break;
		case ROW_CHOICE:
		case ROW_RADAR:
		case ROW_MSGSTYLE:
		case ROW_COLORS:
			if( part >= 0 )
			{
				if( row.type == ROW_COLORS && part == (int)CZM_XHAIR_COLORS )
				{
					int r = 50, g = 250, b = 50;
					sscanf( EngFuncs::GetCvarString( "cl_crosshair_color" ), "%d %d %d", &r, &g, &b );
					CZM_ColorPickerShow( r, g, b );
					break;
				}
				bool changed = row.set == SetRenderer && (int)row.get() != part;

				row.set( part );
				if( changed )
					Toast( "s_render_restart" );
			}
			break;
		case ROW_MIC:
			if( part != 0 )
				break;
			if( m_bMicTest )
				StopMicTest();
			else
			{
				m_bMicTest = true;
				m_bMicHeard = false;
				m_iMicPing = uiStatic.realTime;
				EngFuncs::ClientCmd( false, "czm_mictest 1\n" );
			}
			break;
		case ROW_BUTTONS:
			if( part == 0 )
				CZM_OpenTouchEditor();
			else if( part == 1 )
				m_bConfirm = true;
			break;
		case ROW_LAYOUTS:
			CZM_LayoutsShow();
			break;
		case ROW_HUDEDIT:
			// the HUD is edited together with the buttons
			CZM_OpenTouchEditor();
			break;
		case ROW_ACCOUNT:
			CZM_AccountShow( CZM_OnlineKey(), EngFuncs::GetCvarString( "name" ));
			break;
		case ROW_NICK:
		{
			char clean[64];
			CZM_CleanName( EngFuncs::GetCvarString( "name" ), clean, sizeof( clean ));
			m_nick.Begin( CZM_NickIsValid( clean ) ? clean : "", m_rows[i].control );
			break;
		}
		case ROW_SPRAYS:
			if( part >= 0 )
				CZM_SetSpray( part );
			break;
		case ROW_AVATARS:
			// the photo card: choose the photo, a second tap (or no photo yet) opens the gallery
			CZM_OnlineAvatarChanged();
			if( part == 0 )
			{
				if( CZM_AvatarPhoto()[0] && CZM_CurrentAvatar() != CZM_AVATAR_PHOTO )
					CZM_SetAvatar( CZM_AVATAR_PHOTO );
				else
				{
					CZM_PickAvatarPhoto();
					Toast( "s_avatar_wait" );
				}
			}
			else if( part == 1 )
				CZM_SetAvatar( CZM_AVATAR_LOGO );
			else if( part >= 2 )
				CZM_SetAvatar( part - 2 );
			break;
		}
	}
}

bool CCzmSettings::KeyDown( int key )
{
	Layout();

	if( m_nick.active && m_nick.KeyDown( key ))
	{
		if( !m_nick.active ) // enter finished the edit
		{
			m_nick.active = true;
			FinishNickEdit();
		}
		return true;
	}

	if( UI::Key::IsLeftMouse( key ))
	{
		int hit = HitTest();

		// a tap outside the nick field finishes typing
		if( m_nick.active && ( hit < HIT_ROW || Row(( hit - HIT_ROW ) / 20 ).type != ROW_NICK ))
			FinishNickEdit();

		m_iPressed = hit;
		m_iDownY = uiStatic.cursorY;
		m_iScrollAtDown = m_iScroll;
		m_bScrolling = false;
		m_bMaybeScroll = !m_bConfirm && m_clip.HasCursor();
		m_iDragRow = -1;

		if( hit >= HIT_ROW && ( hit - HIT_ROW ) % 20 == 0 && Row(( hit - HIT_ROW ) / 20 ).type == ROW_SLIDER )
		{
			m_iDragRow = ( hit - HIT_ROW ) / 20;
			m_bMaybeScroll = false;
			SetSliderFromCursor( m_iDragRow );
		}
		return true;
	}

	if( UI::Key::IsEscape( key ))
	{
		if( m_nick.active )
			FinishNickEdit();
		else if( m_bConfirm )
			m_bConfirm = false;
		else
			Hide();
		return true;
	}

	return CMenuFramework::KeyDown( key );
}

bool CCzmSettings::KeyUp( int key )
{
	if( UI::Key::IsLeftMouse( key ))
	{
		int pressed = m_iPressed;
		bool tap = !m_bScrolling && m_iDragRow < 0;
		int hit;

		Layout();
		hit = HitTest();
		m_iPressed = HIT_NONE;
		m_bMaybeScroll = m_bScrolling = false;

		if( m_iDragRow >= 0 )
		{
			if( Row( m_iDragRow ).set == SetMove )
				m_bTouchChanged = true;
			m_iDragRow = -1;
		}
		else if( tap && hit != HIT_NONE && hit == pressed )
			Activate( hit );

		return true;
	}

	return CMenuFramework::KeyUp( key );
}

bool CCzmSettings::MouseMove( int x, int y )
{
	CMenuFramework::MouseMove( x, y );

	if( m_iDragRow >= 0 )
	{
		Layout();
		SetSliderFromCursor( m_iDragRow );
		return true;
	}

	if( m_bMaybeScroll )
	{
		int dy = uiStatic.cursorY - m_iDownY;

		if( !m_bScrolling && abs( dy ) > ScreenHeight * 0.02f && m_iMaxScroll > 0 )
		{
			m_bScrolling = true;
			m_iPressed = HIT_NONE;
		}

		if( m_bScrolling )
			m_iScroll = bound( 0, m_iScrollAtDown - dy, m_iMaxScroll );
	}

	return true;
}

void CCzmSettings::Char( int key )
{
	m_nick.Char( key );
}

/*
=================
drawing
=================
*/
void CCzmSettings::DrawTabs( void )
{
	HFont font = CZM_Font( CZMF_LANG );
	int iconSize = H * 0.044f;

	for( int i = 0; i < CZM_TAB_COUNT; i++ )
	{
		const CzmRect &r = m_tabs[i];
		bool active = i == m_iTab;
		bool pressed = IsPressed( HIT_TAB + i );
		unsigned int color = active || pressed ? CZM_White() : PackRGBA( 190, 196, 206, 255 );
		int x = r.x + H * 0.03f;

		if( active )
			CZM_DrawSliced( UI_DIR "tab_on.png", r.x, r.y, r.w, r.h, 32, (int)( H * 0.026f ));
		else
			CZM_DrawSliced( UI_DIR "card.png", r.x, r.y, r.w, r.h, 30, (int)( H * 0.026f ), pressed ? CZM_White() : CZM_White( 170 ));

		CZM_DrawImage( s_tabs[i].icon, x, r.y + ( r.h - iconSize ) / 2, iconSize, iconSize, color );
		x += iconSize + H * 0.025f;
		CZM_DrawText( font, x, r.y + ( r.h - CZM_FontHeight( font )) / 2, r.x + r.w - x - H * 0.02f, CZM_T( s_tabs[i].label ), color );
	}
}

void CCzmSettings::DrawSwitch( const CzmRect &r, bool on, bool dim )
{
	int inset = r.h * 0.12f;
	int knob = r.h - inset * 2;
	unsigned int tint = dim ? CZM_White( 90 ) : CZM_White();

	CZM_DrawPill( on ? UI_DIR "pill_lang_on.png" : UI_DIR "chip_lang.png", r.x, r.y, r.w, r.h, tint );
	CZM_DrawImage( UI_DIR "dot.png", on ? r.x + r.w - inset - knob : r.x + inset, r.y + inset, knob, knob,
		dim ? PackRGBA( 150, 150, 150, 120 ) : CZM_White());
}

void CCzmSettings::DrawSlider( int i, const RowLayout &l )
{
	const CzmRow &row = Row( i );
	HFont font = CZM_Font( CZMF_TILE_STATUS );
	bool dim = !RowActive( i );
	int valueW = H * 0.11f;
	int x0 = l.control.x, x1 = l.control.x + l.control.w - valueW;
	int cy = l.rect.y + l.rect.h / 2;
	int track = Q_max( 3, (int)( H * 0.010f ));
	int knob = H * 0.05f;
	float value = row.get();
	float t = bound( 0.0f, ( value - row.min ) / ( row.max - row.min ), 1.0f );
	int kx = x0 + (int)( t * ( x1 - x0 ));
	char text[32];

	FillClipped( x0, cy - track / 2, x1 - x0, track, CZM_White( dim ? 25 : 45 ), m_clip );
	FillClipped( x0, cy - track / 2, kx - x0, track, dim ? PackRGBA( 120, 60, 60, 160 ) : PackRGBA( 230, 38, 38, 255 ), m_clip );

	CZM_DrawImage( UI_DIR "dot.png", kx - knob / 2 - 2, cy - knob / 2 - 2, knob + 4, knob + 4, PackRGBA( 0, 0, 0, 120 ));
	CZM_DrawImage( UI_DIR "dot.png", kx - knob / 2, cy - knob / 2, knob, knob, dim ? PackRGBA( 140, 140, 140, 255 ) : CZM_White());

	FormatValue( row, value, text, sizeof( text ));
	CZM_DrawText( font, x1, cy - CZM_FontHeight( font ) / 2, valueW, text, dim ? CZM_Grey() : CZM_White(), QM_RIGHT );
}

void CCzmSettings::DrawChoice( int i, const RowLayout &l )
{
	const CzmRow &row = Row( i );
	HFont font = CZM_Font( CZMF_TILE_STATUS );
	int current = (int)row.get();
	int inset = l.control.h * 0.1f;

	CZM_DrawPill( UI_DIR "chip_lang.png", l.control.x, l.control.y, l.control.w, l.control.h );

	for( int k = 0; k < l.numParts; k++ )
	{
		const CzmRect &p = l.parts[k];
		bool active = k == current;
		bool pressed = IsPressed( HIT_ROW + i * 20 + 1 + k );

		if( active )
			CZM_DrawPill( UI_DIR "pill_lang_on.png", p.x + inset, p.y + inset, p.w - inset * 2, p.h - inset * 2 );
		else if( pressed )
			CZM_DrawPill( UI_DIR "button_secondary.png", p.x + inset, p.y + inset, p.w - inset * 2, p.h - inset * 2 );

		const char *label = CZM_T( row.options[k] );
		int available = p.w - inset * 2;
		int textH = CZM_FontHeight( font );
		int textW = CZM_TextWidth( font, label );
		if( textW > available && available > 0 )
			textH = Q_max( 1, textH * available / textW );
		UI_DrawString( font, p.x + inset, p.y + ( p.h - textH ) / 2, available, textH, label,
			active ? CZM_White() : PackRGBA( 190, 196, 206, 255 ), textH, QM_CENTER | QM_TOP, ETF_NO_WRAP | ETF_FORCECOL );
	}
}

void CCzmSettings::DrawCrosshairPreview( const CzmRect &box )
{
	static const struct { float length, gap; } sizes[4] = { { 0.026f, 0.012f }, { 0.018f, 0.008f }, { 0.026f, 0.012f }, { 0.036f, 0.016f } };
	int r = 250, g = 50, b = 50;
	int size = (int)GetXhairSize();
	int alpha = GetXhairTrans() != 0.0f ? 170 : 255;
	int length = H * sizes[size].length, gap = H * sizes[size].gap;
	int thick = Q_max( 2, H / 380 );
	int cx = box.x + box.w / 2, cy = box.y + box.h / 2;
	unsigned int color;

	sscanf( EngFuncs::GetCvarString( "cl_crosshair_color" ), "%d %d %d", &r, &g, &b );
	color = PackRGBA( r, g, b, alpha );

	// a piece of the game art behind the crosshair
	UI::Scissor::PushScissor( box.x, box.y, box.w, box.h );
	CZM_DrawCover( CZM_Image( "gfx/czm/loading_2.png" ), box.x, box.y, box.w, box.h );
	UI::Scissor::PopScissor();

	FillClipped( cx - thick / 2, cy - gap - length, thick, length, color, m_clip );
	FillClipped( cx - thick / 2, cy + gap, thick, length, color, m_clip );
	FillClipped( cx - gap - length, cy - thick / 2, length, thick, color, m_clip );
	FillClipped( cx + gap, cy - thick / 2, length, thick, color, m_clip );
}

void CCzmSettings::DrawTabPreview( const CzmRect &box )
{
	if( box.w <= 0 || box.h <= 0 )
		return;

	const int style = (int)GetTabStyle();
	const int pad = Q_max( 4, (int)( H * 0.012f ));
	HFont font = CZM_Font( CZMF_SMALL );
	const int fh = CZM_FontHeight( font );
	CzmRect clip;
	clip.x = Q_max( box.x, m_clip.x );
	clip.y = Q_max( box.y, m_clip.y );
	clip.w = Q_min( box.x + box.w, m_clip.x + m_clip.w ) - clip.x;
	clip.h = Q_min( box.y + box.h, m_clip.y + m_clip.h ) - clip.y;
	if( clip.w <= 0 || clip.h <= 0 )
		return;
	// Cover artwork is larger than the requested box. Clip the whole preview,
	// including text, against its own frame and the enclosing scroll panel.
	UI::Scissor::PushScissor( box.x, box.y, box.w, box.h );
	CZM_DrawCover( CZM_Image( "gfx/czm/loading_2.png" ), box.x, box.y, box.w, box.h );
	FillClipped( box.x, box.y, box.w, box.h, PackRGBA( 0, 0, 0, 90 ), clip );
	int w = style == 1 ? box.w * 0.72f : box.w - pad * 2;
	int h = style == 1 ? box.h * 0.88f : box.h - pad * 2;
	int x = box.x + ( box.w - w ) / 2, y = box.y + ( box.h - h ) / 2;
	const int cols = style == 1 ? 1 : 2, rows = style == 1 ? 6 : 3;
	const bool ru = CZM_IsRussian();
	// the same blocks as the real scoreboard: title, server, column names, players
	const int titleY = y + pad, serverY = titleY + fh + pad / 2, headY = serverY + fh + pad;
	const int head = headY + fh + pad / 2 - y, gap = style == 2 ? pad * 3 : pad;
	const int cw = ( w - pad * 2 - gap * ( cols - 1 )) / cols;
	const int rh = Q_max( 1, ( h - head - pad ) / rows );
	if( style != 2 )
		FillClipped( x, y, w, h, PackRGBA( 10, 13, 19, 235 ), clip );
	else
		FillClipped( x, y, w, headY - pad / 2 - y, PackRGBA( 10, 13, 19, 235 ), clip );
	FillClipped( x, y, w, 2, PackRGBA( 224, 35, 47, 255 ), clip );
	CZM_DrawText( font, x + pad, titleY, w - pad * 2, ru ? "ИГРОКИ  /  6" : "PLAYERS  /  6", CZM_White() );
	CZM_DrawText( font, x + pad, serverY, w - pad * 2, "COUNTER ZOMBIE MOBILE", PackRGBA( 158, 168, 185, 255 ));
	for( int c = 0; c < cols; c++ )
	{
		int left = x + pad + c * ( cw + gap );
		int nameW = cw * 0.57f, statW = cw * 0.13f;
		const unsigned int headColor = PackRGBA( 162, 171, 187, 255 );
		static const char *stats[3] = { "12", "4", "48" };

		if( style == 2 )
			FillClipped( left - pad / 2, headY - pad / 2, cw + pad, h - ( headY - pad / 2 - y ) - pad / 2, PackRGBA( 10, 13, 19, 230 ), clip );
		CZM_DrawText( font, left, headY, nameW, ru ? "ИГРОК" : "PLAYER", headColor );
		CZM_DrawText( font, left + nameW, headY, statW, ru ? "УБ." : "KILLS", headColor, QM_CENTER );
		CZM_DrawText( font, left + nameW + statW, headY, statW, ru ? "СМ." : "DEATHS", headColor, QM_CENTER );
		CZM_DrawText( font, left + nameW + statW * 2, headY, cw - nameW - statW * 2, ru ? "ПИНГ" : "PING", headColor, QM_CENTER );
		for( int row = 0; row < rows; row++ )
		{
			int n = c * rows + row, ry = y + head + row * rh;
			int inset = style == 2 ? pad / 2 : 1;
			FillClipped( left, ry, cw, rh - inset, n == 1 ? PackRGBA( 90, 24, 34, 230 ) : PackRGBA( 24, 28, 38, 210 ), clip );
			FillClipped( left, ry, 2, rh - inset, n < 3 ? PackRGBA( 233, 84, 101, 255 ) : PackRGBA( 75, 167, 245, 255 ), clip );
			char name[48]; snprintf( name, sizeof( name ), "PLAYER %02d", n + 1 );
			int ty = ry + Q_max( 0, ( rh - inset - fh ) / 2 );
			CZM_DrawText( font, left + pad, ty, nameW - pad, name, CZM_White() );
			for( int k = 0; k < 3; k++ )
				CZM_DrawText( font, left + nameW + statW * k, ty, k < 2 ? statW : cw - nameW - statW * 2, stats[k], PackRGBA( 150, 210, 180, 255 ), QM_CENTER );
		}
	}
	UI::Scissor::PopScissor();
}

void CCzmSettings::DrawRow( int i )
{
	const CzmRow &row = Row( i );
	const RowLayout &l = m_rows[i];
	HFont labelFont = CZM_Font( CZMF_TILE_STATUS );
	HFont hintFont = CZM_Font( CZMF_SMALL );
	bool dim = !RowActive( i );
	const char *hint = row.hint ? CZM_T( row.hint ) : NULL;
	bool cards = row.type == ROW_SPRAYS || row.type == ROW_AVATARS || row.type == ROW_TABPREVIEW || row.type == ROW_RADAR || row.type == ROW_MSGSTYLE;
	int labelW = ( cards ? l.rect.w : l.control.x - l.rect.x - H * 0.03f );
	int labelH = CZM_FontHeight( labelFont ), hintH = CZM_FontHeight( hintFont );
	int blockH = labelH + ( hint ? hintH + H * 0.008f : 0 );
	int labelY;

	if( cards )
		labelY = l.rect.y + H * 0.03f;
	else
		labelY = l.rect.y + ( l.rect.h - blockH ) / 2;

	// the gyroscope row explains why it is off
	if( row.get == GetGyro && !GyroAvailable( ))
		hint = CZM_T( "s_gyro_none" );

	// the microphone row tells how the test went
	if( row.type == ROW_MIC )
	{
		if( !MicTestAvailable( ))
			hint = CZM_T( "s_mic_match" );
		else if( !m_bMicTest && EngFuncs::GetCvarFloat( "czm_miclevel" ) < 0.0f )
			hint = CZM_T( "s_mic_none" );
		else if( m_bMicHeard )
			hint = CZM_T( "s_mic_ok" );
	}

	if( l.rect.y + l.rect.h < m_clip.y || l.rect.y > m_clip.y + m_clip.h )
		return;

	CZM_DrawText( labelFont, l.rect.x, labelY, labelW, CZM_T( row.label ), dim ? CZM_Grey() : CZM_White());
	if( hint )
		CZM_DrawText( hintFont, l.rect.x, labelY + labelH + H * 0.008f, labelW, hint, PackRGBA( 140, 146, 156, 255 ));

	switch( row.type )
	{
	case ROW_SLIDER:
		DrawSlider( i, l );
		break;
	case ROW_SWITCH:
		DrawSwitch( l.control, row.get() != 0.0f, dim );
		break;
	case ROW_CHOICE:
		DrawChoice( i, l );
		break;
	case ROW_MIC:
	{
		float level = m_bMicTest ? bound( 0.0f, EngFuncs::GetCvarFloat( "czm_miclevel" ), 100.0f ) : 0.0f;
		int fill = l.control.w * level / 100.0f;

		FillClipped( l.control.x, l.control.y, l.control.w, l.control.h, CZM_White( dim ? 20 : 45 ), m_clip );
		FillClipped( l.control.x, l.control.y, fill, l.control.h, level > 12.0f ? PackRGBA( 34, 197, 94, 255 ) : PackRGBA( 200, 205, 215, 255 ), m_clip );
		CZM_DrawButton( m_bMicTest ? UI_DIR "button_danger.png" : UI_DIR "button_secondary.png", l.parts[0],
			CZM_T( m_bMicTest ? row.options[1] : row.options[0] ), dim ? CZM_Grey() : CZM_White(), IsPressed( HIT_ROW + i * 20 + 1 ), CZMF_TILE_STATUS );
		break;
	}
	case ROW_BUTTONS:
		CZM_DrawButton( UI_DIR "button_secondary.png", l.parts[0], CZM_T( row.options[0] ), CZM_White(),
			IsPressed( HIT_ROW + i * 20 + 1 ), CZMF_TILE_STATUS );
		CZM_DrawButton( UI_DIR "button_danger.png", l.parts[1], CZM_T( row.options[1] ), PackRGBA( 255, 150, 150, 255 ),
			IsPressed( HIT_ROW + i * 20 + 2 ), CZMF_TILE_STATUS );
		break;
	case ROW_COLORS:
	{
		int current = (int)row.get();

		for( int k = 0; k < l.numParts; k++ )
		{
			const CzmRect &p = l.parts[k];
			int ring = Q_max( 3, (int)( H * 0.007f ));

			if( k == current || ( current < 0 && k == (int)CZM_XHAIR_COLORS ))
				CZM_DrawImage( UI_DIR "dot.png", p.x - ring, p.y - ring, p.w + ring * 2, p.h + ring * 2 );
			else
				CZM_DrawImage( UI_DIR "dot.png", p.x - 1, p.y - 1, p.w + 2, p.h + 2, PackRGBA( 0, 0, 0, 160 ));

			if( k == (int)CZM_XHAIR_COLORS )
				CZM_DrawImage( UI_DIR "color_wheel.png", p.x, p.y, p.w, p.h, CZM_White( IsPressed( HIT_ROW + i * 20 + 1 + k ) ? 170 : 255 ));
			else
				CZM_DrawImage( UI_DIR "dot.png", p.x, p.y, p.w, p.h,
					PackRGBA( s_xhairColors[k].r, s_xhairColors[k].g, s_xhairColors[k].b, IsPressed( HIT_ROW + i * 20 + 1 + k ) ? 170 : 255 ));
		}
		break;
	}
	case ROW_XHAIR:
		DrawCrosshairPreview( l.control );
		break;
	case ROW_TABPREVIEW:
		DrawTabPreview( l.control );
		break;
	case ROW_MSGSTYLE:
	{
		int current = (int)GetMsgStyle(), corner = H * 0.02f;
		HFont nameFont = CZM_Font( CZMF_TILE_STATUS );

		for( int k = 0; k < l.numParts; k++ )
		{
			const CzmRect &p = l.parts[k];
			bool pressed = IsPressed( HIT_ROW + i * 20 + 1 + k );
			int nameH = CZM_FontHeight( nameFont ), inset = H * 0.018f;
			CzmRect shot = CZM_Rect( p.x + inset, p.y + inset, p.w - inset * 2, p.h - nameH - H * 0.06f );

			CZM_DrawSliced( k == current ? UI_DIR "card_on.png" : UI_DIR "card.png", p.x, p.y, p.w, p.h, 30, corner,
				pressed ? PackRGBA( 200, 200, 200, 255 ) : CZM_White());
			UI::Scissor::PushScissor( shot.x, shot.y, shot.w, shot.h );
			CZM_DrawMessagePreview( k, shot.x, shot.y, shot.w, shot.h );
			UI::Scissor::PopScissor();
			CZM_DrawText( nameFont, p.x, p.y + p.h - nameH - H * 0.022f, p.w, CZM_MessageStyleName( k ),
				k == current ? CZM_White() : PackRGBA( 200, 205, 215, 255 ), QM_CENTER );
		}
		break;
	}
	case ROW_RADAR:
	{
		int current = (int)GetRadarStyle(), corner = H * 0.02f;
		HFont nameFont = CZM_Font( CZMF_TILE_STATUS );

		for( int k = 0; k < l.numParts; k++ )
		{
			const CzmRect &p = l.parts[k];
			bool pressed = IsPressed( HIT_ROW + i * 20 + 1 + k );
			int nameH = CZM_FontHeight( nameFont );
			int size = Q_min( p.w - H * 0.06f, p.h - nameH - H * 0.07f );

			CZM_DrawSliced( k == current ? UI_DIR "card_on.png" : UI_DIR "card.png", p.x, p.y, p.w, p.h, 30, corner,
				pressed ? PackRGBA( 200, 200, 200, 255 ) : CZM_White());
			CZM_DrawRadarPreview( k, p.x + ( p.w - size ) / 2, p.y + H * 0.025f, size, 1.0f );
			CZM_DrawText( nameFont, p.x, p.y + p.h - nameH - H * 0.022f, p.w, CZM_RadarStyleName( k ),
				k == current ? CZM_White() : PackRGBA( 200, 205, 215, 255 ), QM_CENTER );
		}
		break;
	}
	case ROW_LAYOUTS:
	case ROW_HUDEDIT:
	case ROW_ACCOUNT:
		CZM_DrawButton( UI_DIR "button_secondary.png", l.control, CZM_T( "s_account_open" ), CZM_White(),
			IsPressed( HIT_ROW + i * 20 ), CZMF_TILE_STATUS );
		break;
	case ROW_NICK:
	{
		char clean[64];
		CZM_CleanName( EngFuncs::GetCvarString( "name" ), clean, sizeof( clean ));
		CZM_DrawField( l.control, m_nick, clean, CZM_T( "nick_placeholder" ), IsPressed( HIT_ROW + i * 20 ));
		break;
	}
	case ROW_AVATARS:
	{
		int current = CZM_CurrentAvatar();
		bool pending = CZM_AvatarPending();
		const char *photo = CZM_AvatarPhoto();
		int corner = H * 0.02f;

		for( int k = 0; k < l.numParts; k++ )
		{
			const CzmRect &p = l.parts[k];
			bool pressed = IsPressed( HIT_ROW + i * 20 + 1 + k );
			int index = k == 0 ? CZM_AVATAR_PHOTO : k == 1 ? CZM_AVATAR_LOGO : k - 2;
			bool selected = index == current;
			int inset = p.w * 0.10f;

			CZM_DrawSliced( selected ? UI_DIR "card_on.png" : UI_DIR "card.png", p.x, p.y, p.w, p.h, 30, corner,
				pressed ? PackRGBA( 200, 200, 200, 255 ) : CZM_White());

			if( k == 0 && !photo[0] )
			{
				// no photo yet: a plus and the word
				HFont font = CZM_Font( CZMF_SMALL );
				int icon = p.w * 0.34f;
				unsigned int color = pending ? PackRGBA( 239, 68, 68, 255 ) : PackRGBA( 200, 205, 215, 255 );

				CZM_DrawImage( UI_DIR "icon_plus.png", p.x + ( p.w - icon ) / 2, p.y + p.h * 0.22f, icon, icon, color );
				CZM_DrawText( font, p.x, p.y + p.h * 0.66f, p.w, CZM_T( "s_avatar_photo" ), color, QM_CENTER );
			}
			else
			{
				CZM_DrawImage( k == 0 ? photo : CZM_AvatarImage( index ), p.x + inset, p.y + inset, p.w - inset * 2, p.h - inset * 2 );

				// the photo card can be changed: a small plus in the corner
				if( k == 0 )
				{
					int badge = p.w * 0.28f;
					CZM_DrawImage( UI_DIR "dot.png", p.x - badge / 4, p.y + p.h - badge * 3 / 4, badge, badge,
						pending ? PackRGBA( 239, 68, 68, 255 ) : PackRGBA( 40, 44, 54, 255 ));
					CZM_DrawImage( UI_DIR "icon_plus.png", p.x - badge / 4 + badge / 4, p.y + p.h - badge * 3 / 4 + badge / 4,
						badge / 2, badge / 2 );
				}
			}

			if( selected )
			{
				int check = p.w * 0.26f;
				CZM_DrawImage( UI_DIR "dot.png", p.x + p.w - check * 3 / 4, p.y - check / 4, check, check, PackRGBA( 239, 68, 68, 255 ));
				CZM_DrawImage( UI_DIR "icon_check.png", p.x + p.w - check * 3 / 4 + check / 5, p.y - check / 4 + check / 5,
					check * 3 / 5, check * 3 / 5 );
			}
		}
		break;
	}
	case ROW_SPRAYS:
	{
		int current = CZM_CurrentSpray();
		int corner = H * 0.02f;

		for( int k = 0; k < l.numParts; k++ )
		{
			const CzmRect &p = l.parts[k];
			bool pressed = IsPressed( HIT_ROW + i * 20 + 1 + k );
			int inset = p.w * 0.12f;

			CZM_DrawSliced( k == current ? UI_DIR "card_on.png" : UI_DIR "card.png", p.x, p.y, p.w, p.h, 30, corner,
				pressed ? PackRGBA( 200, 200, 200, 255 ) : CZM_White());
			CZM_DrawImage( CZM_SprayImage( k ), p.x + inset, p.y + inset, p.w - inset * 2, p.h - inset * 2 );

			if( k == current )
			{
				int check = p.w * 0.26f;
				CZM_DrawImage( UI_DIR "dot.png", p.x + p.w - check * 3 / 4, p.y - check / 4, check, check, PackRGBA( 239, 68, 68, 255 ));
				CZM_DrawImage( UI_DIR "icon_check.png", p.x + p.w - check * 3 / 4 + check / 5, p.y - check / 4 + check / 5,
					check * 3 / 5, check * 3 / 5 );
			}
		}
		break;
	}
	}

	// thin line under the row
	if( i < RowCount() - 1 )
		FillClipped( l.rect.x, l.rect.y + l.rect.h - 1, l.rect.w, CZM_LineWidth(), CZM_White( 22 ), m_clip );
}

void CCzmSettings::DrawConfirm( void )
{
	HFont titleFont = CZM_Font( CZMF_PANEL_TITLE );
	int pad = H * 0.028f;
	int titleY = m_confirmPanel.y + ( m_confirmNo.y - m_confirmPanel.y - CZM_FontHeight( titleFont )) / 2;

	UI_FillRect( 0, 0, W, H, PackRGBA( 0, 0, 0, 170 ));
	CZM_DrawPanel( m_confirmPanel );
	CZM_DrawText( titleFont, m_confirmPanel.x + pad, titleY, m_confirmPanel.w - pad * 2, CZM_T( "reset_confirm" ), CZM_White(), QM_CENTER );
	CZM_DrawButton( UI_DIR "button_secondary.png", m_confirmNo, CZM_T( "cancel" ), CZM_White(), IsPressed( HIT_CONFIRM_NO ));
	CZM_DrawButton( UI_DIR "button_primary.png", m_confirmYes, CZM_T( "b_reset" ), CZM_White(), IsPressed( HIT_CONFIRM_YES ));
}

void CCzmSettings::Draw()
{
	int r, g, b;
	if( CZM_ColorPickerEvent( r, g, b ))
	{
		char color[32];
		snprintf( color, sizeof( color ), "%d %d %d", r, g, b );
		EngFuncs::CvarSetString( "cl_crosshair_color", color );
		Save();
	}
	HFont titleFont = CZM_Font( CZMF_PANEL_TITLE );
	int iconSize;

	Layout();

	// microphone test: stop on errors, mark the voice as heard, keep the engine side running
	if( m_bMicTest )
	{
		float level = EngFuncs::GetCvarFloat( "czm_miclevel" );

		if( level < 0.0f || !MicTestAvailable( ))
			m_bMicTest = false;
		else
		{
			if( level > 12.0f )
				m_bMicHeard = true;
			if( uiStatic.realTime - m_iMicPing > 10000 )
			{
				m_iMicPing = uiStatic.realTime;
				EngFuncs::ClientCmd( false, "czm_mictest 1\n" );
			}
		}
	}

	// calm the art down so the controls read well
	UI_FillRect( 0, 0, W, H, PackRGBA( 0, 0, 0, CL_IsActive() ? 60 : 110 ));
	CZM_DrawImage( UI_DIR "fade_top.png", 0, 0, W, H * 0.22f, CZM_White( 200 ));

	// header: back button and title
	CZM_DrawImage( UI_DIR "chip_round.png", m_back.x, m_back.y, m_back.w, m_back.h, IsPressed( HIT_BACK ) ? PackRGBA( 170, 170, 170, 255 ) : CZM_White());
	iconSize = m_back.h * 0.5f;
	CZM_DrawImage( UI_DIR "icon_back.png", m_back.x + ( m_back.w - iconSize ) / 2, m_back.y + ( m_back.h - iconSize ) / 2, iconSize, iconSize );
	CZM_DrawText( titleFont, m_back.x + m_back.w + H * 0.03f, m_back.y + ( m_back.h - CZM_FontHeight( titleFont )) / 2, W * 0.5f,
		CZM_T( "set_title" ), CZM_White());

	DrawTabs();

	CZM_DrawPanel( m_panel );
	UI::Scissor::PushScissor( m_clip.x, m_clip.y, m_clip.w, m_clip.h );
	for( int i = 0; i < RowCount() && i < MAX_ROWS; i++ )
		DrawRow( i );
	UI::Scissor::PopScissor();

	// scroll bar
	if( m_iMaxScroll > 0 )
	{
		int trackH = m_clip.h - H * 0.04f;
		int barH = Q_max( (int)( H * 0.06f ), trackH * m_clip.h / ( m_clip.h + m_iMaxScroll ));
		int barY = m_clip.y + H * 0.02f + ( trackH - barH ) * m_iScroll / m_iMaxScroll;

		UI_FillRect( m_panel.x + m_panel.w - H * 0.016f, barY, Q_max( 3, (int)( H * 0.006f )), barH, CZM_White( 70 ));
	}

	// short notice at the bottom
	if( m_szToast && uiStatic.realTime - m_iToastTime < 2200 )
	{
		HFont font = CZM_Font( CZMF_TILE_STATUS );
		int tw = CZM_TextWidth( font, CZM_T( m_szToast )) + H * 0.08f;
		int th = H * 0.07f;
		CzmRect r = CZM_Rect( m_panel.x + ( m_panel.w - tw ) / 2, m_panel.y + m_panel.h - th - H * 0.03f, tw, th );

		CZM_DrawPill( UI_DIR "button_secondary.png", r.x, r.y, r.w, r.h );
		CZM_DrawText( font, r.x, r.y + ( r.h - CZM_FontHeight( font )) / 2, r.w, CZM_T( m_szToast ), CZM_White(), QM_CENTER );
	}

	if( m_bConfirm )
		DrawConfirm();
}

ADD_MENU3( menu_czmsettings, CCzmSettings, UI_CzmSettings_Menu );

void UI_CzmSettings_Menu( void )
{
	menu_czmsettings->Show();
}

void CZM_OpenSettings( int tab )
{
	menu_czmsettings->OpenTab( tab );
	menu_czmsettings->Show();
}
