/*
CzmMenu.h - Counter Zombie Mobile menu: shared drawing, language, servers, loading screen
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
#pragma once
#ifndef CZM_MENU_H
#define CZM_MENU_H

#include <stddef.h>
#include "BaseMenu.h"

/*
 * fonts
 */
enum CzmFontId
{
	CZMF_LOAD_HOST = 0,
	CZMF_LOAD_PERCENT,
	CZMF_LOAD_INFO,
	CZMF_LOAD_STATUS,
	CZMF_LOAD_TIP,
	CZMF_BUTTON,
	CZMF_TILE_TITLE,
	CZMF_TILE_TEXT,
	CZMF_TILE_STATUS,
	CZMF_NICK,
	CZMF_SMALL,
	CZMF_NAV,
	CZMF_LANG,
	CZMF_PANEL_TITLE,
	CZMF_PANEL_TEXT,
	CZMF_SHOP_MONEY,
	CZMF_SHOP_NAME,
	CZMF_SHOP_PRICE,
	CZMF_SHOP_BIG,
	CZMF_SHOP_CARD,
	CZMF_SHOP_CARD_PRICE,
	CZMF_MENU_TITLE,
	CZMF_TILE_NAME,   // server name on a main-screen tile, two lines
	CZMF_COUNT
};

HFont CZM_Font( int id );
int CZM_FontHeight( HFont font );
int CZM_TextWidth( HFont font, const char *text );
// single line, cut with an ellipsis when it does not fit into w
void CZM_DrawText( HFont font, int x, int y, int w, const char *text, unsigned int color, unsigned int justify = QM_LEFT );
// line starts of text wrapped into width (starts needs maxLines + 1 places), returns the number of lines
int CZM_WrapText( HFont font, const char *text, int width, int *starts, int maxLines );
void CZM_WrapLine( const char *text, const int *starts, int l, char *out, size_t size );

// fonts are recreated together with the menu fonts when the resolution changes
void CZM_CreateFonts( float scale );
bool CZM_FindFontFile( const char *name, char *dataFile, size_t dataFileChars );

/*
 * images (loaded once, by path)
 */
HIMAGE CZM_Image( const char *path );
void CZM_DrawImage( const char *path, int x, int y, int w, int h, unsigned int color = 0xFFFFFFFF, bool transparent = true );
// stretches a rounded image, the corners keep their shape
void CZM_DrawSliced( const char *path, int x, int y, int w, int h, int imageBorder, int screenBorder, unsigned int color = 0xFFFFFFFF );
// pill-shaped image: the round ends keep their shape, the middle stretches
void CZM_DrawPill( const char *path, int x, int y, int w, int h, unsigned int color = 0xFFFFFFFF );
int CZM_ImageAspect1000( const char *path ); // width * 1000 / height, 0 if missing
void CZM_DrawCover( HIMAGE image, int x, int y, int w, int h );

/*
 * misc
 */
void CZM_Init( void ); // registers our cvars, safe to call often
unsigned int CZM_PingColor( int ping );
void CZM_CleanName( const char *in, char *out, size_t size ); // drops colour codes
bool CZM_CursorIn( int x, int y, int w, int h );
const char *CZM_Version( void );
void CZM_OpenConsole( void ); // hidden debug entry

/*
 * language: Russian or English, the default follows the phone language
 */
const char *CZM_T( const char *key );
bool CZM_IsRussian( void );
void CZM_SetLanguage( bool russian );

/*
 * our servers: the mode tiles of the main screen
 */
// the main-screen tiles are the servers the player pinned (a heart in the server list), up to 3
#define CZM_HOME_MAX 3

struct CzmServer
{
	char address[64];     // ip:port
	char prot[8];         // "gs" or "49"
	char name[64];        // the server's own name, the address until it answers
	unsigned int accent;  // tile colour, from the map
	char map[64];
	int players;
	int maxplayers;
	int ping;             // milliseconds, -1 while unknown
	double queryTime;     // last query sent
	double answerTime;    // last info received
	int misses;           // queries in a row without an answer
};

int CZM_ServerCount( void );          // pinned servers, 0..CZM_HOME_MAX
CzmServer *CZM_Server( int index );
void CZM_QueryServers( bool force );
bool CZM_OnServerInfo( netadr_t adr, const char *info ); // true for our own messages, which the stock list must not see
void CZM_ConnectToServer( int index );
int CZM_PingUpdate( int old, int fresh ); // keeps a real ping when a late answer reads ~0 ms
void CZM_QuickPlayStart( void );                  // look for the best open zombie server
void CZM_QuickPlayCancel( void );
bool CZM_QuickPlayActive( void );
int CZM_QuickPlayFrame( char *name, size_t size ); // 0 looking, 1 connecting (name of the server), -1 nothing fits

// pinned servers of the main screen, kept in home_servers.lst
void CZM_HomeReload( void );                 // read the file into the tiles, call when the main screen opens
int  CZM_HomePinCount( void );
bool CZM_HomePinned( const char *address );
bool CZM_HomeSetPinned( const char *address, const char *prot, bool on ); // false when 3 are already pinned

// map picture and accent colour for a server tile (czm/menu/CzmServers.cpp)
HIMAGE CZM_MapPicture( const char *map );                  // 0 when there is none
HIMAGE CZM_MapPreview( const char *map );
bool CZM_MapInstalled( const char *map );
void CZM_DrawMapPreview( const char *map, int x, int y, int w, int h, const char *server = NULL );
const char *CZM_MapModeArt( const char *map, const char *server ); // zombie / escape / classic picture for maps without one
void CZM_MapPicturesFrame( void );
unsigned int CZM_MapAccent( const char *map, const char *name );

/*
 * screens
 */
// draws the full-screen art behind every menu window, returns false if the art is missing
bool CZM_DrawMenuBackground( Point pos, Size size );
// the button editor keeps the game picture clear behind it
void CZM_SetGameVisible( bool visible );

// draws the loading screen while the engine connects, returns true if it owns the frame
bool CZM_DrawLoadingScreen( void );

/*
 * shared pieces of our windows
 */
struct CzmRect
{
	int x, y, w, h;

	bool Contains( int px, int py ) const
	{
		return w > 0 && h > 0 && px >= x && px < x + w && py >= y && py < y + h;
	}

	bool HasCursor( void ) const;

	// touch targets are a bit larger than what is drawn
	CzmRect Grown( int by ) const
	{
		CzmRect r = { x - by, y - by, w + by * 2, h + by * 2 };
		return r;
	}
};

CzmRect CZM_Rect( int x, int y, int w, int h );
unsigned int CZM_White( int alpha = 255 );
unsigned int CZM_Grey( void );
int CZM_LineWidth( void );
void CZM_PlayClick( void );
void CZM_MenuAudioFrame( void );
void CZM_DrawPanel( const CzmRect &r );
void CZM_DrawButton( const char *image, const CzmRect &r, const char *label, unsigned int textColor, bool pressed, int font = CZMF_BUTTON );

// one-line text input with the phone keyboard (nickname)
struct CzmTextEdit
{
	char text[32];
	bool active;

	void Begin( const char *initial, const CzmRect &r );
	void End( void );
	bool KeyDown( int key ); // true if the key belonged to the field
	void Char( int ch );
};

void CZM_DrawField( const CzmRect &r, const CzmTextEdit &edit, const char *value, const char *placeholder, bool pressed );

/*
 * settings and profile
 */
enum
{
	CZM_TAB_LAST = -1, // the tab the player saw last time
	CZM_TAB_CONTROLS = 0,
	CZM_TAB_GRAPHICS,
	CZM_TAB_SOUND,
	CZM_TAB_GAME,
	CZM_TAB_HUD,
	CZM_TAB_PROFILE,
	CZM_TAB_COUNT
};

void CZM_OpenSettings( int tab );

bool CZM_NickIsValid( const char *nick );
void CZM_SetNick( const char *nick );

int CZM_SprayCount( void );
const char *CZM_SprayName( int index );  // file name without the extension
const char *CZM_SprayImage( int index ); // logos/<name>.png
int CZM_CurrentSpray( void );            // -1 if the player uses a stock spray
void CZM_SetSpray( int index );
void CZM_SprayFrame( void );

// avatars: the game logo, our pictures, the player's own photo from the gallery
#define CZM_AVATAR_LOGO -1
#define CZM_AVATAR_PHOTO 100
int CZM_AvatarCount( void );
const char *CZM_AvatarImage( int index );  // our picture, the logo for CZM_AVATAR_LOGO
const char *CZM_AvatarPhoto( void );       // the photo file, "" if there is none
int CZM_CurrentAvatar( void );             // CZM_AVATAR_LOGO, 0..count-1 or CZM_AVATAR_PHOTO
const char *CZM_CurrentAvatarImage( void );
void CZM_SetAvatar( int index );
void CZM_PickAvatarPhoto( void );          // opens the gallery
bool CZM_AvatarPending( void );            // waiting for the gallery; call while the avatar is on the screen

// first start: language and nickname window, good network settings once
bool CZM_FirstStart( void );
void CZM_FinishFirstStart( void );
// settings the engine does not keep by itself, call when the main screen opens
void CZM_ApplyStartupSettings( void );

/*
 * touch buttons: three layouts and our editor
 */
int CZM_TouchScheme( void ); // 1..3
// switches the layout; fromPreset drops the player's changes to that layout
void CZM_SetTouchScheme( int scheme, bool fromPreset );
void CZM_TouchStartup( void ); // first start of this version: our layout replaces the stock one
void CZM_SaveTouchConfig( void ); // writes the current buttons and touch settings to the layout file
void CZM_OpenTouchEditor( void );
void CZM_TouchResetHud( void ); // HUD places and sizes back to the defaults

/*
 * shop (buy menu) and server menus as cards
 */
// the client asks for a buy menu; true if our shop took it
bool CZM_ShopShow( int menuType, int team );
// in a match: server menus (plugins, votes) drawn as cards over the game
void CZM_DrawGameOverlay( void );

/*
 * network through the Android side (czm/menu/CzmNet.cpp, CzmNet.java)
 */
class CUtlString;
bool CZM_NetAvailable( void );
void CZM_ServerAuthShow( const char *address, const char *name );
void CZM_AccountShow( const char *key, const char *nick );
bool CZM_AccountEvent( CUtlString &body );
void CZM_ColorPickerShow( int r, int g, int b );
void CZM_LayoutsShow( void );
bool CZM_CloudEvent( CUtlString &body );
bool CZM_WidgetEvent( CUtlString &body );
void CZM_CloudApplied( int request, bool success );
void CZM_CloudFrame( void );
bool CZM_ColorPickerEvent( int &r, int &g, int &b );
void CZM_OnlineAvatarChanged( void );
void CZM_TabFrame( void );
void CZM_TabReset( void );
void CZM_StartupReady( void );
// a request number, 0 if there is no network layer; body is UTF-8 JSON or ""
int CZM_NetRequest( const char *method, const char *url, const char *key, const char *body );
int CZM_NetUpload( const char *url, const char *key, const char *path, const char *contentType ); // path in the game folder
int CZM_NetDownload( const char *url, const char *path );                                          // path in the game folder
// true once the answer is there (status 0: no network), the number is then forgotten
bool CZM_NetPoll( int id, int *status, CUtlString &body );
const char *CZM_NetDeviceId( void );
void CZM_NetNewKey( char *out, size_t size );
int CZM_NetVersionCode( void );
bool CZM_NetCanSelfUpdate( void );

// update from inside the game
enum
{
	CZM_UPDATE_IDLE = 0,
	CZM_UPDATE_DOWNLOADING,
	CZM_UPDATE_VERIFYING,
	CZM_UPDATE_READY,
	CZM_UPDATE_ERROR,
	CZM_UPDATE_INSTALLING,
	CZM_UPDATE_PERMISSION,
};
struct CzmUpdateInfo;
void CZM_UpdateStart( const CzmUpdateInfo &update );
void CZM_UpdateState( int *state, double *done, double *total, char *error, size_t errorSize );
void CZM_UpdateInstall( void );
void CZM_UpdateCancel( void );
void CZM_UpdateCleanup( void );

/*
 * the player on our service (czm/menu/CzmOnline.cpp)
 */
struct CzmNews
{
	int id;
	int time;
	char text[1024];
};

struct CzmUpdateInfo
{
	bool available;
	bool cleaned;
	char version[32];
	int code;
	double size;
	char sha256[80];
	char url[256];
	char notes[512];
	double patchSize;
	char patchUrl[256];
	char patchSha256[80];
	char baseSha256[80];
};

class CzmJson;
void CZM_OnlineFrame( void );          // every frame
const char *CZM_OnlineUrl( const char *path );
const char *CZM_OnlineKey( void );
bool CZM_OnlineReady( void );
bool CZM_OnlineAccount( void );
int CZM_OnlineCount( void ); // players in the game right now, -1 unknown
int CZM_OnlineIdentity( void );
int CZM_OnlinePlayer( void );
bool CZM_OnlineBan( int *until, bool *forever, const char **reason );
void CZM_OnlineReadBan( const CzmJson &j, int ban );
int CZM_NewsUnread( void );
void CZM_NewsOpen( void );             // loads the list
void CZM_NewsMarkRead( void );
bool CZM_NewsLoading( void );
int CZM_NewsCount( void );
const CzmNews *CZM_NewsItem( int index );
const CzmUpdateInfo *CZM_Update( void ); // NULL if there is none
// picture of a chat avatar ("", "1".."10", "photo:<rev>"), downloads photos when needed
const char *CZM_AvatarFor( const char *ref, int player );

// chat window (czm/menu/CzmChat.cpp)
void CZM_OpenChat( void );

// Account profiles, friends and private dialogs (independent of game-server mods).
void CZM_OpenFriends( void );
void CZM_OpenProfile( int player, int chatMessage = 0 );
void CZM_SocialFrame( void );
int CZM_SocialUnread( void );
int CZM_SocialRequests( void );
bool CZM_CopyText( const char *text );
void CZM_JoinAddress( const char *address );

/*
 * server list: the game's list of servers in our look (czm/menu/CzmServers.cpp)
 */
void CZM_OpenServerList( void );
void CZM_ServerListInfo( netadr_t adr, const char *info ); // every server answer, "\czmping\N" too
void CZM_ServerListResetPing( void );                     // the engine sent the queries for the master list
// the main screen opens: back to the list if the last game was started from it
bool CZM_ServerListReturn( void );

#endif // CZM_MENU_H
