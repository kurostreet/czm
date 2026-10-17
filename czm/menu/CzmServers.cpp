/*
CzmServers.cpp - Counter Zombie Mobile server list: search, favorites, history, server details
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

#include <ctype.h>
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
#include "utlvector.h"
#include "utlstring.h"
#include "CzmMenu.h"

/*
The game's own server list, the one CS16Client has (menus/ServerBrowser.cpp), drawn
our way. The data comes the same way:
- "internetservers" asks the master lists, the engine queries every server it gets;
- favorites and history are the stock files favorite_servers.lst and history_servers.lst,
  each server there is queried with "ui_queryserver";
- every answer goes through UI_AddServerToList, the engine adds "\czmping\N" with the ping;
- players come from a NetAPI players request for the selected server.
*/

#define UI_DIR "gfx/czm/ui/"
#define MAP_DIR "gfx/czm/maps/"
#define FAVORITES_FILE "favorite_servers.lst"
#define HISTORY_FILE "history_servers.lst"
#define MAX_ENTRIES 6000
#define HASH_SIZE 8192 // power of two, larger than MAX_ENTRIES
#define MAX_HISTORY 20
#define MAX_PLAYERS 64
#define LIST_TIMEOUT 8.0     // a refresh waits this long for answers
#define LIST_MAX_AGE 60.0    // the list is asked again when it is older
#define DETAILS_PERIOD 4.0   // the selected server is asked again this often
#define PLAYERS_CONTEXT 0x435a4d40

enum
{
	SRC_INTERNET = 1,
	SRC_FAVORITE = 2,
	SRC_HISTORY = 4,
};

enum
{
	TAB_ALL = 0,
	TAB_FAVORITES,
	TAB_HISTORY,
	TAB_COUNT
};

enum
{
	FILTER_NOT_EMPTY = 0,
	FILTER_NOT_FULL,
	FILTER_NO_PASSWORD,
	FILTER_ZOMBIE,
	FILTER_COUNT
};

enum
{
	SORT_PLAYERS = 0,
	SORT_PING,
	SORT_NAME,
	SORT_COUNT
};

enum
{
	MODE_ZOMBIE = 0,
	MODE_ESCAPE,
	MODE_CLASSIC,
	MODE_OTHER
};

struct CzmEntry
{
	netadr_t adr;
	char address[64];
	char name[64];
	char map[32];
	char badge[8];       // map prefix: ZM, DE, AIM...
	char search[200];    // name, map and address folded for the search
	int players;
	int maxPlayers;
	int bots;
	int ping;            // milliseconds, -1 unknown
	int mode;
	int sources;
	int historyOrder;    // larger is more recent
	bool password;
	bool gs;             // GoldSrc protocol, else Xash
	bool xash;           // answered a Xash query: a Xash server, whatever else it answers
	bool answered;       // info arrived at least once
	double queryTime;    // last query we sent, for the ping
	double pendingSince; // first query that is still without an answer
	double answerTime;   // last info received
};

struct CzmListAddress
{
	char address[64];
	char prot[8];
};

struct CzmPlayer
{
	char name[48];
	int frags;
	float time;
};

/*
=================
text helpers
=================
*/
// lower case for the search: ASCII and Russian letters, colour codes dropped, ё is е
static void FoldText( const char *in, char *out, size_t size )
{
	size_t n = 0;

	for( const unsigned char *s = (const unsigned char *)( in ? in : "" ); *s && n + 3 < size; s++ )
	{
		if( s[0] == '^' && s[1] >= '0' && s[1] <= '9' )
		{
			s++;
			continue;
		}

		if( s[0] == 0xD0 && s[1] >= 0x90 && s[1] <= 0x9F ) // А-П
		{
			out[n++] = (char)0xD0;
			out[n++] = (char)( s[1] + 0x20 );
			s++;
		}
		else if( s[0] == 0xD0 && s[1] >= 0xA0 && s[1] <= 0xAF ) // Р-Я
		{
			out[n++] = (char)0xD1;
			out[n++] = (char)( s[1] - 0x20 );
			s++;
		}
		else if(( s[0] == 0xD0 && s[1] == 0x81 ) || ( s[0] == 0xD1 && s[1] == 0x91 )) // Ё ё
		{
			out[n++] = (char)0xD0;
			out[n++] = (char)0xB5;
			s++;
		}
		else if( s[0] < 0x80 )
			out[n++] = (char)tolower( s[0] );
		else
			out[n++] = (char)s[0];
	}

	out[n] = 0;
}

static bool HasWord( const char *folded, const char *word )
{
	size_t len = strlen( word );

	for( const char *p = strstr( folded, word ); p; p = strstr( p + 1, word ))
	{
		bool startOk = p == folded || !isalnum( (unsigned char)p[-1] );
		bool endOk = !isalnum( (unsigned char)p[len] );

		if( startOk && endOk )
			return true;
	}

	return false;
}

static const char *Plural( int n, const char *one, const char *few, const char *many )
{
	int m10 = n % 10, m100 = n % 100;

	if( m10 == 1 && m100 != 11 )
		return one;
	if( m10 >= 2 && m10 <= 4 && ( m100 < 12 || m100 > 14 ))
		return few;
	return many;
}

// "23 сервера", "1 server"
static void CountText( char *buf, size_t size, int n, const char *ru1, const char *ru2, const char *ru5, const char *en1, const char *en2 )
{
	if( CZM_IsRussian( ))
		snprintf( buf, size, "%d %s", n, Plural( n, ru1, ru2, ru5 ));
	else
		snprintf( buf, size, "%d %s", n, n == 1 ? en1 : en2 );
}

// the longest start of text, cut at a space, that fits into w; returns where the rest begins
static const char *FitWords( HFont font, const char *text, int w, char *line, size_t size )
{
	size_t best = 0, len = strlen( text );
	char buf[128];

	for( size_t i = 0; i <= len && i < sizeof( buf ); i++ )
	{
		if( text[i] != ' ' && text[i] != 0 )
			continue;

		memcpy( buf, text, i );
		buf[i] = 0;
		if( i > 0 && CZM_TextWidth( font, buf ) > w )
			break;
		best = i;
	}

	if( best == 0 || best >= len )
	{
		Q_strncpy( line, text, size );
		return text + len;
	}

	Q_strncpy( line, text, Q_min( size, best + 1 ));
	text += best;
	while( *text == ' ' )
		text++;
	return text;
}

/*
=================
map pictures

Our zombie map previews, then the overview of a standard map from the game data
(cropped to the map and made small in memory), then a picture for the mode.
=================
*/
static void DrawMapPicture( const CzmEntry *e, int x, int y, int w, int h )
{
	CZM_DrawMapPreview( e ? e->map : "", x, y, w, h, e ? e->name : NULL );
}

static void ClassifyMap( CzmEntry *e )
{
	char folded[96], prefix[8];
	size_t i;

	FoldText( e->name, folded, sizeof( folded ));

	// "de_dust2" -> "de"
	for( i = 0; e->map[i] && e->map[i] != '_' && i < sizeof( prefix ) - 1; i++ )
		prefix[i] = (char)tolower( (unsigned char)e->map[i] );
	prefix[i] = 0;
	if( e->map[i] != '_' || i == 0 || i > 5 )
		prefix[0] = 0;

	if( !strcmp( prefix, "ze" ) || (( HasWord( folded, "ze" ) || strstr( folded, "escape" ) || strstr( folded, "побег" ))
		&& ( strstr( folded, "zombie" ) || strstr( folded, "зомби" ) || !strcmp( prefix, "zm" ))))
		e->mode = MODE_ESCAPE;
	else if( !strcmp( prefix, "zm" ) || !strcmp( prefix, "zp" ) || !strcmp( prefix, "zs" ) || !strcmp( prefix, "zh" )
		|| !strcmp( prefix, "zr" ) || !strcmp( prefix, "zombie" ) || strstr( folded, "zombie" ) || strstr( folded, "зомби" )
		|| strstr( folded, "biohazard" ) || HasWord( folded, "zm" ) || HasWord( folded, "zp" ))
		e->mode = MODE_ZOMBIE;
	else if( !strcmp( prefix, "de" ) || !strcmp( prefix, "cs" ) || !strcmp( prefix, "as" ) || !strcmp( prefix, "es" ))
		e->mode = MODE_CLASSIC;
	else
		e->mode = MODE_OTHER;

	if( prefix[0] )
	{
		for( i = 0; prefix[i]; i++ )
			e->badge[i] = (char)toupper( (unsigned char)prefix[i] );
		e->badge[i] = 0;
	}
	else
		Q_strncpy( e->badge, e->mode == MODE_ESCAPE ? "ZE" : e->mode == MODE_ZOMBIE ? "ZM" : "", sizeof( e->badge ));
}

static unsigned int ModeColor( int mode )
{
	switch( mode )
	{
	case MODE_ZOMBIE: return PackRGBA( 220, 38, 38, 255 );
	case MODE_ESCAPE: return PackRGBA( 8, 145, 178, 255 );
	case MODE_CLASSIC: return PackRGBA( 37, 99, 235, 255 );
	default: return PackRGBA( 124, 58, 237, 255 );
	}
}

// fills under a scissor: the engine clips pictures but not plain rectangles
static void FillRect( int x, int y, int w, int h, unsigned int color )
{
	CZM_DrawImage( UI_DIR "white.png", x, y, w, h, color );
}

// shared with the main-screen tiles (CzmMain.cpp): map colour and picture
unsigned int CZM_MapAccent( const char *map, const char *name )
{
	CzmEntry e;

	memset( &e, 0, sizeof( e ));
	Q_strncpy( e.map, map ? map : "", sizeof( e.map ));
	Q_strncpy( e.name, name ? name : "", sizeof( e.name ));
	ClassifyMap( &e );
	return ModeColor( e.mode );
}

const char *CZM_MapModeArt( const char *map, const char *server )
{
	CzmEntry e;

	memset( &e, 0, sizeof( e ));
	Q_strncpy( e.map, map ? map : "", sizeof( e.map ));
	Q_strncpy( e.name, server ? server : "", sizeof( e.name ));
	ClassifyMap( &e );
	switch( e.mode )
	{
	case MODE_ZOMBIE: return MAP_DIR "_zombie.png";
	case MODE_ESCAPE: return MAP_DIR "_escape.png";
	case MODE_CLASSIC: return MAP_DIR "_classic.png";
	default: return MAP_DIR "_other.png";
	}
}

HIMAGE CZM_MapPicture( const char *map )
{
	return CZM_MapPreview( map );
}

/*
=================
CCzmServers
=================
*/
class CCzmServers : public CMenuFramework
{
public:
	CCzmServers();
	~CCzmServers() override;

	void Show() override;
	void Hide() override;
	void Draw() override;
	bool KeyDown( int key ) override;
	bool KeyUp( int key ) override;
	bool MouseMove( int x, int y ) override;
	void Char( int key ) override;

	void OnServerInfo( netadr_t adr, const char *info );
	void OnPlayers( net_response_t *response );
	void ResetPing( void ) { m_flPingBase = EngFuncs::DoubleTime(); }
	void JoinAddress( const char *address );

	bool m_bReturnHere; // a game started from the list: show it again after the game

	// quick play from the main screen: the best open zombie server for this phone
	void QuickStart( void );
	void QuickCancel( void ) { m_bQuick = false; }
	int QuickFrame( char *name, size_t size ); // 0 still looking, 1 connecting (name filled), -1 nothing fits
	bool QuickActive( void ) const { return m_bQuick; }
	bool m_bQuick;
	double m_flQuickStart;

private:
	enum EHit
	{
		HIT_NONE = 0,
		HIT_BACK,
		HIT_SEARCH,
		HIT_SEARCH_CLEAR,
		HIT_REFRESH,
		HIT_ADD,
		HIT_TAB,                         // TAB_COUNT
		HIT_FILTER = HIT_TAB + TAB_COUNT, // FILTER_COUNT
		HIT_SORT = HIT_FILTER + FILTER_COUNT,
		HIT_EMPTY_BUTTON,
		HIT_PLAY,
		HIT_ADMIN,
		HIT_FAVORITE,
		HIT_DETAILS,
		HIT_DIALOG_FIELD,
		HIT_DIALOG_PASTE,
		HIT_DIALOG_OK,
		HIT_DIALOG_CANCEL,
		HIT_DIALOG_PANEL,
		HIT_BACKDROP,
		HIT_ROW = 1000,                  // + index * 2, + 1 for the star
	};

	enum EDialog
	{
		DLG_NONE = 0,
		DLG_ADD,
		DLG_PASSWORD,
	};

	// data
	CzmEntry *Find( const netadr_t &adr );
	CzmEntry *Add( const netadr_t &adr );
	CzmEntry *FindAddress( const char *address );
	CzmEntry *AddAddress( const char *address, const char *prot );
	void UpdateEntry( CzmEntry *e, const char *info );
	bool IsStale( const CzmEntry &e ) const;
	void LoadLists( void );
	void SaveLists( void );
	void ParseList( const char *file, CUtlVector<CzmListAddress> &list );
	void QueryList( const CUtlVector<CzmListAddress> &list, double now );
	void Refresh( bool force );
	void SetFavorite( CzmEntry *e, bool favorite );
	void AddHistory( const CzmEntry *e );
	void Connect( CzmEntry *e, const char *password );
	void RequestDetails( CzmEntry *e );

	// view
	void Rebuild( void );
	bool Passes( const CzmEntry &e ) const;
	CzmEntry *Selected( void );
	void Select( CzmEntry *e );
	int ViewCount( void ) const { return m_view.Count(); }
	bool Refreshing( void ) const { return m_flRefreshTime > 0.0 && EngFuncs::DoubleTime() - m_flRefreshTime < LIST_TIMEOUT; }
	// the empty list shows a button, except while the first servers are being looked for
	bool EmptyHasButton( void ) const { return !( m_iTab == TAB_ALL && Refreshing() && !m_iFilters && !m_szQuery[0] ); }

	// screen
	void Layout( void );
	int HitTest( void ) const;
	bool IsPressed( int hit ) const { return m_iPressed == hit && HitTest() == hit; }
	void Activate( int hit );
	void OpenDialog( int dialog );
	void CloseDialog( void );
	void SubmitDialog( void );
	void Toast( const char *text );
	void ClampScroll( void );
	int MaxScroll( void ) const;
	CzmRect RowRect( int index ) const;
	CzmTextEdit *ActiveEdit( void );

	void DrawHeader( void );
	void DrawFilters( void );
	void DrawList( void );
	void DrawRow( int index, const CzmRect &r );
	void DrawEmpty( void );
	void DrawDetails( void );
	void DrawDialog( void );
	void DrawChip( const CzmRect &r, const char *icon, bool pressed, bool active = false );

	CUtlVector<CzmEntry> m_entries;
	int m_hash[HASH_SIZE];
	CUtlVector<int> m_view;
	CUtlVector<CzmListAddress> m_favorites;
	CUtlVector<CzmListAddress> m_history;
	bool m_bListsLoaded;
	bool m_bDirty;
	bool m_bForceRebuild;
	double m_flLastRebuild;

	double m_flRefreshTime;  // last "internetservers"
	double m_flPingBase;     // when the engine sent the queries for the master list
	double m_flDetailsTime;
	char m_szSelected[64];

	// players of the selected server
	CzmPlayer m_players[MAX_PLAYERS];
	int m_iNumPlayers;
	int m_iPlayersState;     // 0 nothing, 1 asked, 2 received
	int m_iPlayersContext;
	char m_szPlayersFor[64];

	int m_iTab;
	int m_iFilters;
	int m_iSort;
	CzmTextEdit m_search;
	char m_szQuery[64];      // folded search text

	int m_iDialog;
	CzmTextEdit m_field;
	char m_szDialogError[128];
	char m_szPending[64];    // server waiting for its password
	char m_szJoinAddress[64];
	double m_flJoinStarted;

	char m_szToast[128];
	double m_flToastTime;

	// touch
	int m_iPressed;
	bool m_bMaybeScroll, m_bScrolling;
	int m_iDownY;
	float m_flScrollAtDown;
	float m_flScroll;
	float m_flVelocity;
	int m_iLastMoveY;
	double m_flLastMoveTime;
	double m_flLastDraw;
	double m_flLastTap;
	int m_iLastTapRow;

	// layout
	int W, H, m_iMargin;
	CzmRect m_back, m_title, m_searchBox, m_searchClear, m_refresh, m_add;
	CzmRect m_tabs[TAB_COUNT], m_filters[FILTER_COUNT];
	CzmRect m_listHead, m_sort, m_clip, m_details, m_emptyButton;
	CzmRect m_play, m_fav, m_admin;
	CzmRect m_dlgPanel, m_dlgField, m_dlgPaste, m_dlgOk, m_dlgCancel;
	int m_iRowH, m_iRowStep;
	bool m_bThumbs;
};

static CCzmServers *s_browser;

CCzmServers::CCzmServers() : CMenuFramework( "CzmServers" )
{
	s_browser = this;
	m_bReturnHere = false;
	m_bQuick = false;
	m_flQuickStart = 0.0;
	memset( m_hash, 0, sizeof( m_hash ));
	m_bListsLoaded = false;
	m_bDirty = m_bForceRebuild = true;
	m_flLastRebuild = 0.0;
	m_flRefreshTime = m_flPingBase = m_flDetailsTime = 0.0;
	m_szSelected[0] = 0;
	m_iNumPlayers = 0;
	m_iPlayersState = 0;
	m_iPlayersContext = 0;
	m_szPlayersFor[0] = 0;
	m_iTab = TAB_ALL;
	m_iFilters = 0;
	m_iSort = SORT_PLAYERS;
	memset( &m_search, 0, sizeof( m_search ));
	m_szQuery[0] = 0;
	m_iDialog = DLG_NONE;
	memset( &m_field, 0, sizeof( m_field ));
	m_szDialogError[0] = 0;
	m_szPending[0] = 0;
	m_szJoinAddress[0] = 0; m_flJoinStarted = 0;
	m_szToast[0] = 0;
	m_flToastTime = 0.0;
	m_iPressed = HIT_NONE;
	m_bMaybeScroll = m_bScrolling = false;
	m_iDownY = 0;
	m_flScrollAtDown = m_flScroll = m_flVelocity = 0.0f;
	m_iLastMoveY = 0;
	m_flLastMoveTime = m_flLastDraw = m_flLastTap = 0.0;
	m_iLastTapRow = -1;
	W = H = m_iMargin = 0;
	m_iRowH = m_iRowStep = 1;
	m_bThumbs = true;
}

CCzmServers::~CCzmServers()
{
	if( s_browser == this )
		s_browser = NULL;
}

/*
=================
data
=================
*/
static unsigned int HashAddress( const char *address )
{
	unsigned int h = 2166136261u;

	for( const char *p = address; *p; p++ )
		h = ( h ^ (unsigned char)*p ) * 16777619u;

	return h & ( HASH_SIZE - 1 );
}

CzmEntry *CCzmServers::FindAddress( const char *address )
{
	unsigned int h = HashAddress( address );

	for( int i = 0; i < HASH_SIZE; i++ )
	{
		int slot = m_hash[( h + i ) & ( HASH_SIZE - 1 )];

		if( !slot )
			return NULL;
		if( !strcmp( m_entries[slot - 1].address, address ))
			return &m_entries[slot - 1];
	}

	return NULL;
}

CzmEntry *CCzmServers::Find( const netadr_t &adr )
{
	return FindAddress( EngFuncs::NET_AdrToString( adr ));
}

CzmEntry *CCzmServers::Add( const netadr_t &adr )
{
	const char *address = EngFuncs::NET_AdrToString( adr );
	CzmEntry *e = FindAddress( address );
	unsigned int h;

	if( e )
		return e;

	if( m_entries.Count() >= MAX_ENTRIES )
		return NULL;

	CzmEntry entry;
	memset( &entry, 0, sizeof( entry ));
	entry.adr = adr;
	Q_strncpy( entry.address, address, sizeof( entry.address ));
	Q_strncpy( entry.name, address, sizeof( entry.name ));
	entry.ping = -1;
	entry.gs = true;
	entry.mode = MODE_OTHER;
	FoldText( address, entry.search, sizeof( entry.search ));

	m_entries.AddToTail( entry );

	h = HashAddress( address );
	for( int i = 0; i < HASH_SIZE; i++ )
	{
		int &slot = m_hash[( h + i ) & ( HASH_SIZE - 1 )];

		if( !slot )
		{
			slot = m_entries.Count();
			break;
		}
	}

	m_bDirty = true;
	return &m_entries[m_entries.Count() - 1];
}

CzmEntry *CCzmServers::AddAddress( const char *address, const char *prot )
{
	netadr_t adr;
	CzmEntry *e;

	memset( &adr, 0, sizeof( adr ));
	if( !EngFuncs::textfuncs.pNetAPI->StringToAdr( (char *)address, &adr ))
		return NULL;

	e = Add( adr );
	if( e && !e->answered )
		e->gs = !prot || stricmp( prot, "49" ) != 0;
	return e;
}

void CCzmServers::UpdateEntry( CzmEntry *e, const char *info )
{
	char name[64], map[32], temp[160];
	double now = EngFuncs::DoubleTime();

	CZM_CleanName( Info_ValueForKey( info, "host" ), name, sizeof( name ));
	Q_strncpy( map, Info_ValueForKey( info, "map" ), sizeof( map ));
	if( name[0] )
		Q_strncpy( e->name, name, sizeof( e->name ));
	Q_strncpy( e->map, map, sizeof( e->map ));
	e->players = atoi( Info_ValueForKey( info, "numcl" ));
	e->maxPlayers = atoi( Info_ValueForKey( info, "maxcl" ));
	e->bots = atoi( Info_ValueForKey( info, "bots" ));
	e->bots = bound( 0, e->bots, e->players );
	e->password = !strcmp( Info_ValueForKey( info, "password" ), "1" );
	if( strcmp( Info_ValueForKey( info, "gs" ), "1" ))
		e->xash = true;
	e->gs = !e->xash;

	// a ping until the engine sends the real one
	if( !e->answered || e->ping < 0 )
	{
		double base = Q_max( e->queryTime, m_flPingBase );

		if( base > 0.0 && now - base < 5.0 )
			e->ping = CZM_PingUpdate( e->ping, (int)(( now - base ) * 1000.0 ));
	}

	e->answered = true;
	e->answerTime = now;

	snprintf( temp, sizeof( temp ), "%s %s %s", e->name, e->map, e->address );
	FoldText( temp, e->search, sizeof( e->search ));
	ClassifyMap( e );
	m_bDirty = true;
}

void CCzmServers::OnServerInfo( netadr_t adr, const char *info )
{
	const char *value = Info_ValueForKey( info, "czmping" );
	CzmEntry *e;

	if( value && value[0] )
	{
		e = Find( adr );
		if( e )
		{
			e->ping = CZM_PingUpdate( e->ping, atoi( value ));
			m_bDirty = true;
		}
		return;
	}

	// this game only
	if( stricmp( Info_ValueForKey( info, "gamedir" ), gMenu.m_gameinfo.gamefolder ))
		return;

	e = Find( adr );
	if( !e )
	{
		// a new server answers while the master list is being asked
		if( m_flRefreshTime <= 0.0 || EngFuncs::DoubleTime() - m_flRefreshTime > LIST_TIMEOUT * 2 )
			return;

		e = Add( adr );
		if( !e )
			return;
	}

	// whatever answers during a refresh is on the master list
	if( m_flRefreshTime > 0.0 && EngFuncs::DoubleTime() - m_flRefreshTime < LIST_TIMEOUT * 2 )
		e->sources |= SRC_INTERNET;

	UpdateEntry( e, info );
	if( m_szJoinAddress[0] && !strcmp( m_szJoinAddress, e->address ))
	{
		m_szJoinAddress[0] = 0;
		if( e->maxPlayers > 0 && e->players >= e->maxPlayers ) Toast( CZM_IsRussian() ? "Сервер заполнен. Попробуйте позже" : "Server is full. Try later" );
		else Connect( e, NULL );
	}
}

bool CCzmServers::IsStale( const CzmEntry &e ) const
{
	double asked = e.pendingSince > e.answerTime ? e.pendingSince : 0.0;

	// servers from the master list are asked again by every refresh
	if(( e.sources & SRC_INTERNET ) && m_flRefreshTime > e.answerTime && ( asked <= 0.0 || m_flRefreshTime < asked ))
		asked = m_flRefreshTime;

	// asked a while ago and no answer since
	return asked > 0.0 && EngFuncs::DoubleTime() - asked > LIST_TIMEOUT;
}

static void MarkQueried( CzmEntry *e, double now )
{
	e->queryTime = now;
	if( e->pendingSince <= e->answerTime )
		e->pendingSince = now;
}

void CCzmServers::ParseList( const char *file, CUtlVector<CzmListAddress> &list )
{
	byte *data = EngFuncs::COM_LoadFile( file );
	char *p = (char *)data;

	list.RemoveAll();
	if( !data )
		return;

	while( p )
	{
		CzmListAddress entry;

		p = EngFuncs::COM_ParseFile( p, entry.address, sizeof( entry.address ));
		if( !p || !entry.address[0] )
			break;
		p = EngFuncs::COM_ParseFile( p, entry.prot, sizeof( entry.prot ));
		if( !p )
			break;

		// the legacy protocol is gone from the engine
		if( !strcmp( entry.prot, "48" ))
			continue;

		list.AddToTail( entry );
	}

	EngFuncs::COM_FreeFile( data );
}

void CCzmServers::LoadLists( void )
{
	if( m_bListsLoaded )
		return;

	m_bListsLoaded = true;
	ParseList( FAVORITES_FILE, m_favorites );
	ParseList( HISTORY_FILE, m_history );

	for( int i = 0; i < m_favorites.Count(); i++ )
	{
		CzmEntry *e = AddAddress( m_favorites[i].address, m_favorites[i].prot );
		if( e )
			e->sources |= SRC_FAVORITE;
	}

	for( int i = 0; i < m_history.Count(); i++ )
	{
		CzmEntry *e = AddAddress( m_history[i].address, m_history[i].prot );
		if( e )
		{
			e->sources |= SRC_HISTORY;
			e->historyOrder = i + 1;
		}
	}
}

void CCzmServers::SaveLists( void )
{
	const CUtlVector<CzmListAddress> *lists[2] = { &m_favorites, &m_history };
	const char *files[2] = { FAVORITES_FILE, HISTORY_FILE };

	for( int k = 0; k < 2; k++ )
	{
		CUtlString s;

		if( lists[k]->Count() == 0 )
		{
			EngFuncs::DeleteFile( files[k] );
			continue;
		}

		for( int i = 0; i < lists[k]->Count(); i++ )
			s.AppendFormat( "%s %s\n", lists[k]->Element( i ).address, lists[k]->Element( i ).prot );

		EngFuncs::COM_SaveFile( files[k], s.Get(), s.Length());
	}
}

void CCzmServers::QueryList( const CUtlVector<CzmListAddress> &list, double now )
{
	for( int i = 0; i < list.Count(); i++ )
	{
		CzmEntry *e = FindAddress( list[i].address );

		if( !e )
			continue;

		MarkQueried( e, now );
		// a server added by hand may speak either protocol
		if( !e->answered && !strcmp( list[i].prot, "gs" ))
			EngFuncs::ClientCmdF( false, "ui_queryserver \"%s\" 49\n", e->address );
		EngFuncs::ClientCmdF( false, "ui_queryserver \"%s\" %s\n", e->address, e->answered ? ( e->gs ? "gs" : "49" ) : list[i].prot );
	}
}

void CCzmServers::Refresh( bool force )
{
	double now = EngFuncs::DoubleTime();

	LoadLists();

	// the button can not flood the network
	if( m_flRefreshTime > 0.0 && now - m_flRefreshTime < 3.0 )
		return;

	if( force || m_flRefreshTime <= 0.0 || now - m_flRefreshTime > LIST_MAX_AGE )
	{
		m_flRefreshTime = now;
		m_flPingBase = now;
		EngFuncs::ClientCmd( false, "internetservers\n" );
	}

	QueryList( m_favorites, now );
	QueryList( m_history, now );
	m_bDirty = m_bForceRebuild = true;
}

void CCzmServers::SetFavorite( CzmEntry *e, bool favorite )
{
	if( !e )
		return;

	for( int i = 0; i < m_favorites.Count(); i++ )
	{
		if( !strcmp( m_favorites[i].address, e->address ))
		{
			m_favorites.Remove( i );
			break;
		}
	}

	if( favorite )
	{
		CzmListAddress entry;

		Q_strncpy( entry.address, e->address, sizeof( entry.address ));
		Q_strncpy( entry.prot, e->gs ? "gs" : "49", sizeof( entry.prot ));
		m_favorites.AddToTail( entry );
		e->sources |= SRC_FAVORITE;
	}
	else
		e->sources &= ~SRC_FAVORITE;

	SaveLists();
	m_bDirty = m_bForceRebuild = true;
}

void CCzmServers::AddHistory( const CzmEntry *e )
{
	CzmListAddress entry;
	int order = 0;

	for( int i = 0; i < m_history.Count(); i++ )
	{
		if( !strcmp( m_history[i].address, e->address ))
		{
			m_history.Remove( i );
			break;
		}
	}

	if( m_history.Count() >= MAX_HISTORY )
		m_history.Remove( 0 );

	Q_strncpy( entry.address, e->address, sizeof( entry.address ));
	Q_strncpy( entry.prot, e->gs ? "gs" : "49", sizeof( entry.prot ));
	m_history.AddToTail( entry );

	for( int i = 0; i < m_entries.Count(); i++ )
	{
		order = Q_max( order, m_entries[i].historyOrder );
		if( m_entries[i].historyOrder && !strcmp( m_entries[i].address, e->address ))
			m_entries[i].historyOrder = 0;
	}

	CzmEntry *target = FindAddress( e->address );
	if( target )
	{
		target->sources |= SRC_HISTORY;
		target->historyOrder = order + 1;
	}

	SaveLists();
	m_bDirty = true;
}

void CCzmServers::Connect( CzmEntry *e, const char *password )
{
	if( !e )
		return;

	// the server says it needs a password
	if( e->password && !password )
	{
		Q_strncpy( m_szPending, e->address, sizeof( m_szPending ));
		OpenDialog( DLG_PASSWORD );
		return;
	}

	AddHistory( e );
	EngFuncs::CvarSetString( "password", password ? password : "" );
	EngFuncs::CvarSetString( "czm_connect_name", e->answered ? e->name : e->address );
	EngFuncs::CvarSetString( "czm_connect_adr", e->address );
	m_bReturnHere = true;
	EngFuncs::ClientCmdF( false, "connect \"%s\" %s\n", e->address, e->gs ? "gs" : "49" );
}

void CCzmServers::QuickStart( void )
{
	m_bQuick = true;
	m_flQuickStart = EngFuncs::DoubleTime();
	Refresh( false ); // asks the master list again only when it is old
}

/*
Zombie and escape servers that are open (no password, free slots) and alive.
Many real players and a low ping win; a nearly full server loses a little,
the next player may not fit. Empty servers are only taken when nothing else answers.
*/
int CCzmServers::QuickFrame( char *name, size_t size )
{
	double now = EngFuncs::DoubleTime(), elapsed = now - m_flQuickStart;
	CzmEntry *best = NULL;
	float bestScore = 0.0f;

	if( !m_bQuick )
		return -1;

	for( int pass = 0; pass < 2 && !best; pass++ )
	{
		for( int i = 0; i < m_entries.Count(); i++ )
		{
			CzmEntry &e = m_entries[i];
			int humans = e.players - e.bots, ping = e.ping >= 0 ? e.ping : 400;
			float score;

			if( !e.answered || IsStale( e ) || ( e.mode != MODE_ZOMBIE && e.mode != MODE_ESCAPE ))
				continue;
			if( e.password || e.maxPlayers <= 0 || e.players >= e.maxPlayers )
				continue;
			if( pass == 0 && humans < 2 )
				continue;

			score = Q_min( humans, 28 ) * 6.0f - ping * 0.12f;
			if( e.maxPlayers - e.players < 2 )
				score -= 12.0f;
			if( ping > 350 )
				score -= 40.0f;
			if( !best || score > bestScore )
			{
				best = &e;
				bestScore = score;
			}
		}
	}

	// a fresh refresh is given a moment for the pings; a long silence ends the search
	if( !best || ( Refreshing() && elapsed < 3.0 ))
	{
		if( elapsed > LIST_TIMEOUT + 1.0 )
		{
			m_bQuick = false;
			return -1;
		}
		return 0;
	}

	m_bQuick = false;
	CZM_CleanName( best->name[0] ? best->name : best->address, name, size );
	Connect( best, NULL );
	m_bReturnHere = false; // after the game the player comes back to the main screen
	return 1;
}

static void CZM_PlayersResponse( net_response_t *response )
{
	if( s_browser )
		s_browser->OnPlayers( response );
}

void CCzmServers::RequestDetails( CzmEntry *e )
{
	double now = EngFuncs::DoubleTime();

	if( !e )
		return;

	m_flDetailsTime = now;
	MarkQueried( e, now );
	EngFuncs::ClientCmdF( false, "ui_queryserver \"%s\" %s\n", e->address, e->gs ? "gs" : "49" );

	m_iPlayersContext = PLAYERS_CONTEXT + ( m_iPlayersContext + 1 ) % 0x100;
	if( strcmp( m_szPlayersFor, e->address ))
	{
		Q_strncpy( m_szPlayersFor, e->address, sizeof( m_szPlayersFor ));
		m_iNumPlayers = 0;
		m_iPlayersState = 1;
	}

	// shorter than the period: a server that keeps silent is noticed
	EngFuncs::textfuncs.pNetAPI->SendRequest( m_iPlayersContext, NETAPI_REQUEST_PLAYERS, 0, DETAILS_PERIOD - 0.5, &e->adr, CZM_PlayersResponse );
}

static int ComparePlayers( const void *a, const void *b )
{
	const CzmPlayer *pa = (const CzmPlayer *)a, *pb = (const CzmPlayer *)b;

	if( pa->frags != pb->frags )
		return pb->frags - pa->frags;
	return pb->time > pa->time ? 1 : pb->time < pa->time ? -1 : 0;
}

void CCzmServers::OnPlayers( net_response_t *response )
{
	char *s;
	int count;

	if( response->context != m_iPlayersContext )
		return;

	// no answer: the server does not give its players (or is down)
	if( !response->response )
	{
		if( m_iPlayersState == 1 )
			m_iPlayersState = 3;
		return;
	}

	if( strcmp( EngFuncs::NET_AdrToString( response->remote_address ), m_szPlayersFor ))
		return;

	s = (char *)response->response;
	count = Q_min( atoi( Info_ValueForKey( s, "players" )), MAX_PLAYERS );
	m_iNumPlayers = 0;

	for( int i = 0; i < count; i++ )
	{
		CzmPlayer &p = m_players[m_iNumPlayers];
		char key[32];

		snprintf( key, sizeof( key ), "p%ifrags", i );
		p.frags = atoi( Info_ValueForKey( s, key ));
		snprintf( key, sizeof( key ), "p%itime", i );
		p.time = atof( Info_ValueForKey( s, key ));
		snprintf( key, sizeof( key ), "p%iname", i );
		CZM_CleanName( Info_ValueForKey( s, key ), p.name, sizeof( p.name ));

		// players still connecting have no name yet
		if( p.name[0] )
			m_iNumPlayers++;
	}

	qsort( m_players, m_iNumPlayers, sizeof( m_players[0] ), ComparePlayers );
	m_iPlayersState = 2;
}

/*
=================
view: what the list shows, in which order
=================
*/
bool CCzmServers::Passes( const CzmEntry &e ) const
{
	switch( m_iTab )
	{
	case TAB_ALL:
		if( !e.answered || IsStale( e ))
			return false;
		if( !( e.sources & SRC_INTERNET ))
			return false;
		break;
	case TAB_FAVORITES:
		if( !( e.sources & SRC_FAVORITE ))
			return false;
		break;
	case TAB_HISTORY:
		if( !( e.sources & SRC_HISTORY ))
			return false;
		break;
	}

	if( m_iFilters )
	{
		// a silent server can not pass a filter
		if( !e.answered )
			return false;
		if(( m_iFilters & ( 1 << FILTER_NOT_EMPTY )) && e.players - e.bots <= 0 )
			return false;
		if(( m_iFilters & ( 1 << FILTER_NOT_FULL )) && e.players >= e.maxPlayers )
			return false;
		if(( m_iFilters & ( 1 << FILTER_NO_PASSWORD )) && e.password )
			return false;
		if(( m_iFilters & ( 1 << FILTER_ZOMBIE )) && e.mode != MODE_ZOMBIE && e.mode != MODE_ESCAPE )
			return false;
	}

	if( m_szQuery[0] && !strstr( e.search, m_szQuery ))
		return false;

	return true;
}

static const CzmEntry *s_sortEntries;
static int s_sortMode;
static int s_sortTab;

static int CompareEntries( const void *a, const void *b )
{
	const CzmEntry &ea = s_sortEntries[*(const int *)a];
	const CzmEntry &eb = s_sortEntries[*(const int *)b];
	int humansA = ea.players - ea.bots, humansB = eb.players - eb.bots;

	if( s_sortTab == TAB_HISTORY )
		return eb.historyOrder - ea.historyOrder;

	// silent servers last
	if( ea.answered != eb.answered )
		return ea.answered ? -1 : 1;

	switch( s_sortMode )
	{
	case SORT_PING:
		if(( ea.ping < 0 ) != ( eb.ping < 0 ))
			return ea.ping < 0 ? 1 : -1;
		if( ea.ping != eb.ping )
			return ea.ping - eb.ping;
		break;
	case SORT_NAME:
	{
		int c = strcmp( ea.search, eb.search );
		if( c )
			return c;
		break;
	}
	default:
		if( humansA != humansB )
			return humansB - humansA;
		if( ea.players != eb.players )
			return eb.players - ea.players;
		if(( ea.ping < 0 ) != ( eb.ping < 0 ))
			return ea.ping < 0 ? 1 : -1;
		if( ea.ping != eb.ping )
			return ea.ping - eb.ping;
		break;
	}

	return strcmp( ea.address, eb.address );
}

void CCzmServers::Rebuild( void )
{
	m_view.RemoveAll();
	for( int i = 0; i < m_entries.Count(); i++ )
	{
		if( Passes( m_entries[i] ))
			m_view.AddToTail( i );
	}

	s_sortEntries = m_entries.Base();
	s_sortMode = m_iSort;
	s_sortTab = m_iTab;
	if( m_view.Count() > 1 )
		qsort( m_view.Base(), m_view.Count(), sizeof( int ), CompareEntries );

	m_bDirty = m_bForceRebuild = false;
	m_flLastRebuild = EngFuncs::DoubleTime();
}

CzmEntry *CCzmServers::Selected( void )
{
	return m_szSelected[0] ? FindAddress( m_szSelected ) : NULL;
}

void CCzmServers::Select( CzmEntry *e )
{
	if( !e )
	{
		m_szSelected[0] = 0;
		return;
	}

	if( strcmp( m_szSelected, e->address ))
	{
		Q_strncpy( m_szSelected, e->address, sizeof( m_szSelected ));
		m_iNumPlayers = 0;
		m_iPlayersState = 0;
		m_szPlayersFor[0] = 0;
	}

	RequestDetails( e );
}

/*
=================
window
=================
*/
void CCzmServers::Show()
{
	CZM_Init();
	m_szJoinAddress[0] = 0;
	m_iFilters = (int)EngFuncs::GetCvarFloat( "czm_srv_filters" ) & (( 1 << FILTER_COUNT ) - 1 );
	m_iSort = bound( 0, (int)EngFuncs::GetCvarFloat( "czm_srv_sort" ), SORT_COUNT - 1 );
	m_iPressed = HIT_NONE;
	m_bMaybeScroll = m_bScrolling = false;
	m_flVelocity = 0.0f;
	m_iDialog = DLG_NONE;
	m_field.End();
	m_bReturnHere = false;

	CMenuFramework::Show();
	Refresh( false );

	// the selected server gets fresh players
	if( Selected( ))
		RequestDetails( Selected( ));
}

void CCzmServers::Hide()
{
	m_szJoinAddress[0] = 0;
	m_search.End();
	m_field.End();
	m_bReturnHere = false;
	CMenuFramework::Hide();
}

void CCzmServers::Toast( const char *text )
{
	Q_strncpy( m_szToast, text, sizeof( m_szToast ));
	m_flToastTime = EngFuncs::DoubleTime();
}

CzmTextEdit *CCzmServers::ActiveEdit( void )
{
	if( m_field.active )
		return &m_field;
	if( m_search.active )
		return &m_search;
	return NULL;
}

void CCzmServers::OpenDialog( int dialog )
{
	m_search.End();
	m_iDialog = dialog;
	m_szDialogError[0] = 0;
	memset( &m_field, 0, sizeof( m_field ));
	Layout();
	m_field.Begin( "", m_dlgField );
}

void CCzmServers::CloseDialog( void )
{
	m_field.End();
	m_iDialog = DLG_NONE;
	m_szPending[0] = 0;
}

void CCzmServers::SubmitDialog( void )
{
	if( m_iDialog == DLG_PASSWORD )
	{
		char password[64];
		CzmEntry *e = FindAddress( m_szPending );

		Q_strncpy( password, m_field.text, sizeof( password ));
		CloseDialog();
		Connect( e, password );
		return;
	}

	if( m_iDialog == DLG_ADD )
	{
		char address[64];
		netadr_t adr;
		CzmEntry *e;
		size_t len;

		// "1.2.3.4" means the usual port
		Q_strncpy( address, m_field.text, sizeof( address ));
		len = strlen( address );
		while( len > 0 && address[len - 1] == ' ' )
			address[--len] = 0;
		if( address[0] && !strchr( address, ':' ) && len + 7 < sizeof( address ))
			strcat( address, ":27015" );

		memset( &adr, 0, sizeof( adr ));
		if( !address[0] || !EngFuncs::textfuncs.pNetAPI->StringToAdr( address, &adr ))
		{
			Q_strncpy( m_szDialogError, CZM_T( "srv_add_bad" ), sizeof( m_szDialogError ));
			return;
		}

		e = Add( adr );
		if( !e )
			return;

		CloseDialog();
		SetFavorite( e, true );
		MarkQueried( e, EngFuncs::DoubleTime( ));
		EngFuncs::ClientCmdF( false, "ui_queryserver \"%s\" gs\n", e->address );
		EngFuncs::ClientCmdF( false, "ui_queryserver \"%s\" 49\n", e->address );
		m_iTab = TAB_FAVORITES;
		m_flScroll = 0.0f;
		Select( e );
		m_bForceRebuild = true;
		Toast( CZM_T( "srv_add_done" ));
	}
}

int CCzmServers::MaxScroll( void ) const
{
	return Q_max( 0, ViewCount() * m_iRowStep - ( m_iRowStep - m_iRowH ) - m_clip.h );
}

void CCzmServers::ClampScroll( void )
{
	float max = MaxScroll();

	if( m_flScroll > max )
	{
		m_flScroll = max;
		m_flVelocity = 0.0f;
	}
	if( m_flScroll < 0.0f )
	{
		m_flScroll = 0.0f;
		m_flVelocity = 0.0f;
	}
}

CzmRect CCzmServers::RowRect( int index ) const
{
	return CZM_Rect( m_clip.x, m_clip.y + index * m_iRowStep - (int)m_flScroll, m_clip.w, m_iRowH );
}

void CCzmServers::Layout( void )
{
	HFont titleFont = CZM_Font( CZMF_PANEL_TITLE );
	HFont chipFont = CZM_Font( CZMF_TILE_STATUS );
	int top, hb, x, rowY, rowH, gap, contentY, bottom, dw, listW, chipPad;
	static const char *filterKeys[FILTER_COUNT] = { "srv_f_notempty", "srv_f_notfull", "srv_f_nopass", "srv_f_zombie" };
	static const char *tabKeys[TAB_COUNT] = { "srv_tab_all", "srv_tab_fav", "srv_tab_hist" };

	W = ScreenWidth;
	H = ScreenHeight;
	m_iMargin = W * 0.03f;

	// header: back, title, search, refresh, add
	top = H * 0.035f;
	hb = H * 0.075f;
	m_back = CZM_Rect( m_iMargin, top, hb, hb );
	m_title = CZM_Rect( m_back.x + hb + H * 0.03f, top, CZM_TextWidth( titleFont, CZM_T( "srv_title" )), hb );
	m_add = CZM_Rect( W - m_iMargin - hb, top, hb, hb );
	m_refresh = CZM_Rect( m_add.x - H * 0.02f - hb, top, hb, hb );
	x = m_title.x + m_title.w + H * 0.05f;
	m_searchBox = CZM_Rect( 0, top, Q_min( (int)( H * 0.95f ), m_refresh.x - H * 0.03f - x ), hb );
	m_searchBox.x = m_refresh.x - H * 0.03f - m_searchBox.w;
	m_searchClear = CZM_Rect( m_searchBox.x + m_searchBox.w - hb, top, hb, hb );

	// tabs and filter chips
	rowY = top + hb + H * 0.03f;
	rowH = H * 0.064f;
	chipPad = H * 0.03f;
	x = m_iMargin;
	for( int i = 0; i < TAB_COUNT; i++ )
	{
		char label[64];
		int count = 0;

		if( i == TAB_FAVORITES )
			count = m_favorites.Count();
		else if( i == TAB_HISTORY )
			count = m_history.Count();

		if( count > 0 )
			snprintf( label, sizeof( label ), "%s  %d", CZM_T( tabKeys[i] ), count );
		else
			Q_strncpy( label, CZM_T( tabKeys[i] ), sizeof( label ));

		m_tabs[i] = CZM_Rect( x, rowY, CZM_TextWidth( chipFont, label ) + chipPad * 2, rowH );
		x += m_tabs[i].w;
	}

	x += H * 0.04f;
	gap = H * 0.016f;
	for( int i = 0; i < FILTER_COUNT; i++ )
	{
		int w = CZM_TextWidth( chipFont, CZM_T( filterKeys[i] )) + chipPad * 2 + rowH * 0.5f;

		m_filters[i] = CZM_Rect( x, rowY, w, rowH );
		x += w + gap;
	}

	// chips that do not fit squeeze together
	if( x - gap > W - m_iMargin )
	{
		int extra = ( x - gap - ( W - m_iMargin ) + FILTER_COUNT ) / FILTER_COUNT;

		x = m_filters[0].x;
		for( int i = 0; i < FILTER_COUNT; i++ )
		{
			m_filters[i].x = x;
			m_filters[i].w = Q_max( (int)( rowH * 1.2f ), m_filters[i].w - extra );
			x += m_filters[i].w + gap;
		}
	}

	// list on the left, details on the right
	contentY = rowY + rowH + H * 0.03f;
	bottom = H - H * 0.035f;
	dw = bound( (int)( H * 0.52f ), (int)( W * 0.31f ), (int)( H * 0.74f ));
	m_details = CZM_Rect( W - m_iMargin - dw, contentY, dw, bottom - contentY );
	listW = m_details.x - H * 0.03f - m_iMargin;

	m_listHead = CZM_Rect( m_iMargin, contentY, listW, H * 0.05f );
	{
		HFont font = CZM_Font( CZMF_SMALL );
		static const char *sortKeys[SORT_COUNT] = { "srv_sort_players", "srv_sort_ping", "srv_sort_name" };
		const char *label = CZM_T( m_iTab == TAB_HISTORY ? "srv_sort_recent" : sortKeys[m_iSort] );
		int w = CZM_TextWidth( font, label ) + m_listHead.h * 2;

		m_sort = CZM_Rect( m_listHead.x + m_listHead.w - w, m_listHead.y, w, m_listHead.h );
	}

	m_clip = CZM_Rect( m_iMargin, m_listHead.y + m_listHead.h + H * 0.015f, listW, 0 );
	m_clip.h = bottom - m_clip.y;
	m_iRowH = H * 0.108f;
	m_iRowStep = m_iRowH + H * 0.012f;
	m_bThumbs = listW >= H * 1.05f;

	// empty list button
	{
		int bw = H * 0.46f, bh = H * 0.08f;
		m_emptyButton = CZM_Rect( m_clip.x + ( m_clip.w - bw ) / 2, m_clip.y + m_clip.h * 0.56f, bw, bh );
	}

	// details buttons
	{
		int pad = H * 0.03f, bh = H * 0.085f, inner = m_details.w - pad * 2;
		int fw = Q_max( bh, (int)( inner * 0.36f ));

		m_fav = CZM_Rect( m_details.x + pad, m_details.y + m_details.h - pad - bh, fw, bh );
		m_play = CZM_Rect( m_fav.x + fw + H * 0.02f, m_fav.y, inner - fw - H * 0.02f, bh );
		m_admin = CZM_Rect( m_fav.x, m_fav.y - H * 0.065f - H * 0.012f, inner, H * 0.065f );
	}

	// dialogs
	{
		int pw = Q_min( (int)( H * 0.92f ), W - m_iMargin * 2 ), ph = H * 0.36f, pad = H * 0.03f;
		int fh = H * 0.07f, bh = H * 0.07f, bw = ( pw - pad * 3 ) / 2;
		int pasteW = m_iDialog == DLG_ADD ? H * 0.24f : 0;

		// the phone keyboard covers the lower half, the window sits high
		m_dlgPanel = CZM_Rect(( W - pw ) / 2, H * 0.06f, pw, ph );
		m_dlgField = CZM_Rect( m_dlgPanel.x + pad, m_dlgPanel.y + ph * 0.42f, pw - pad * 2 - ( pasteW ? pasteW + H * 0.02f : 0 ), fh );
		m_dlgPaste = CZM_Rect( m_dlgField.x + m_dlgField.w + H * 0.02f, m_dlgField.y, pasteW, fh );
		m_dlgCancel = CZM_Rect( m_dlgPanel.x + pad, m_dlgPanel.y + ph - pad - bh, bw, bh );
		m_dlgOk = CZM_Rect( m_dlgPanel.x + pad * 2 + bw, m_dlgCancel.y, bw, bh );
	}
}

int CCzmServers::HitTest( void ) const
{
	const int grow = H * 0.012f;
	int x = uiStatic.cursorX, y = uiStatic.cursorY;

	if( m_iDialog != DLG_NONE )
	{
		if( m_dlgField.HasCursor( ))
			return HIT_DIALOG_FIELD;
		if( m_iDialog == DLG_ADD && m_dlgPaste.HasCursor( ))
			return HIT_DIALOG_PASTE;
		if( m_dlgOk.HasCursor( ))
			return HIT_DIALOG_OK;
		if( m_dlgCancel.HasCursor( ))
			return HIT_DIALOG_CANCEL;
		return m_dlgPanel.HasCursor() ? HIT_DIALOG_PANEL : HIT_BACKDROP;
	}

	if( m_back.Grown( grow ).HasCursor( ))
		return HIT_BACK;
	if( m_refresh.Grown( grow ).HasCursor( ))
		return HIT_REFRESH;
	if( m_add.Grown( grow ).HasCursor( ))
		return HIT_ADD;
	if( m_search.text[0] && m_searchClear.HasCursor( ))
		return HIT_SEARCH_CLEAR;
	if( m_searchBox.Grown( grow / 2 ).HasCursor( ))
		return HIT_SEARCH;

	for( int i = 0; i < TAB_COUNT; i++ )
	{
		if( m_tabs[i].HasCursor( ))
			return HIT_TAB + i;
	}

	for( int i = 0; i < FILTER_COUNT; i++ )
	{
		if( m_filters[i].HasCursor( ))
			return HIT_FILTER + i;
	}

	if( m_iTab != TAB_HISTORY && m_sort.Grown( grow ).HasCursor( ))
		return HIT_SORT;

	if( m_details.HasCursor( ))
	{
		if( m_szSelected[0] && m_admin.HasCursor( ))
			return HIT_ADMIN;
		if( m_play.HasCursor( ))
			return HIT_PLAY;
		if( m_fav.HasCursor( ))
			return HIT_FAVORITE;
		return HIT_DETAILS;
	}

	if( m_clip.HasCursor( ))
	{
		int index = ( y - m_clip.y + (int)m_flScroll ) / m_iRowStep;

		if( index >= 0 && index < ViewCount( ))
		{
			CzmRect r = RowRect( index );

			if( r.Contains( x, y ))
			{
				int col = 0; // the row

				if( x >= r.x + r.w - r.h )
					col = 1; // the star
				else if( x >= r.x + r.w - r.h * 2 )
					col = 2; // the heart (pin to the main screen)
				return HIT_ROW + index * 3 + col;
			}
		}

		if( ViewCount() == 0 && EmptyHasButton() && m_emptyButton.HasCursor( ))
			return HIT_EMPTY_BUTTON;
	}

	return HIT_NONE;
}

void CCzmServers::Activate( int hit )
{
	if( hit == HIT_NONE || hit == HIT_DETAILS || hit == HIT_DIALOG_PANEL )
		return;

	if( hit < HIT_ROW )
		CZM_PlayClick();

	switch( hit )
	{
	case HIT_BACK:
		Hide();
		return;
	case HIT_SEARCH:
		m_search.Begin( m_search.text, m_searchBox );
		return;
	case HIT_SEARCH_CLEAR:
		m_search.text[0] = 0;
		m_search.End();
		m_szQuery[0] = 0;
		m_flScroll = 0.0f;
		m_bForceRebuild = true;
		return;
	case HIT_REFRESH:
		Refresh( true );
		return;
	case HIT_ADD:
		OpenDialog( DLG_ADD );
		return;
	case HIT_SORT:
		m_iSort = ( m_iSort + 1 ) % SORT_COUNT;
		EngFuncs::CvarSetValue( "czm_srv_sort", m_iSort );
		m_flScroll = 0.0f;
		m_bForceRebuild = true;
		return;
	case HIT_EMPTY_BUTTON:
		if( m_iFilters || m_szQuery[0] )
		{
			m_iFilters = 0;
			EngFuncs::CvarSetValue( "czm_srv_filters", 0.0f );
			m_search.text[0] = 0;
			m_search.End();
			m_szQuery[0] = 0;
			m_bForceRebuild = true;
		}
		else if( m_iTab == TAB_FAVORITES )
			OpenDialog( DLG_ADD );
		else if( m_iTab == TAB_HISTORY )
		{
			m_iTab = TAB_ALL;
			m_bForceRebuild = true;
		}
		else
			Refresh( true );
		return;
	case HIT_PLAY:
		Connect( Selected(), NULL );
		return;
	case HIT_ADMIN:
	{
		CzmEntry *e = Selected();
		if( e ) CZM_ServerAuthShow( e->address, e->answered ? e->name : e->address );
		return;
	}
	case HIT_FAVORITE:
	{
		CzmEntry *e = Selected();

		if( e )
		{
			bool on = !( e->sources & SRC_FAVORITE );

			SetFavorite( e, on );
			Toast( CZM_T( on ? "srv_fav_on" : "srv_fav_off" ));
		}
		return;
	}
	case HIT_DIALOG_FIELD:
		m_field.Begin( m_field.text, m_dlgField );
		return;
	case HIT_DIALOG_PASTE:
	{
		char *clip = EngFuncs::GetClipboardData();

		if( clip )
		{
			char clean[32];
			size_t n = 0;

			// keep what an address is made of
			for( const char *p = clip; *p && n < sizeof( clean ) - 1; p++ )
			{
				if( isalnum( (unsigned char)*p ) || *p == '.' || *p == ':' || *p == '-' )
					clean[n++] = *p;
			}
			clean[n] = 0;
			Q_strncpy( m_field.text, clean, sizeof( m_field.text ));
		}
		return;
	}
	case HIT_DIALOG_OK:
		SubmitDialog();
		return;
	case HIT_DIALOG_CANCEL:
	case HIT_BACKDROP:
		CloseDialog();
		return;
	}

	if( hit >= HIT_TAB && hit < HIT_TAB + TAB_COUNT )
	{
		m_iTab = hit - HIT_TAB;
		m_flScroll = 0.0f;
		m_flVelocity = 0.0f;
		m_bForceRebuild = true;
		return;
	}

	if( hit >= HIT_FILTER && hit < HIT_FILTER + FILTER_COUNT )
	{
		m_iFilters ^= 1 << ( hit - HIT_FILTER );
		EngFuncs::CvarSetValue( "czm_srv_filters", m_iFilters );
		m_flScroll = 0.0f;
		m_bForceRebuild = true;
		return;
	}

	if( hit >= HIT_ROW )
	{
		int index = ( hit - HIT_ROW ) / 3;
		int col = ( hit - HIT_ROW ) % 3;
		CzmEntry *e;

		if( index >= ViewCount( ))
			return;

		e = &m_entries[m_view[index]];
		if( col == 1 ) // the star: favorites
		{
			bool on = !( e->sources & SRC_FAVORITE );

			CZM_PlayClick();
			SetFavorite( e, on );
			Toast( CZM_T( on ? "srv_fav_on" : "srv_fav_off" ));
			return;
		}
		if( col == 2 ) // the heart: pin to the main screen (max 3)
		{
			bool on = !CZM_HomePinned( e->address );

			CZM_PlayClick();
			if( CZM_HomeSetPinned( e->address, e->gs ? "gs" : "49", on ))
				Toast( CZM_T( on ? "srv_pin_on" : "srv_pin_off" ));
			else
				Toast( CZM_T( "srv_pin_full" ));
			return;
		}

		// a second tap on the same server joins it
		if( index == m_iLastTapRow && EngFuncs::DoubleTime() - m_flLastTap < 0.4 && !strcmp( m_szSelected, e->address ))
		{
			m_iLastTapRow = -1;
			CZM_PlayClick();
			Connect( e, NULL );
			return;
		}

		m_iLastTapRow = index;
		m_flLastTap = EngFuncs::DoubleTime();
		Select( e );
	}
}

bool CCzmServers::KeyDown( int key )
{
	CzmTextEdit *edit = ActiveEdit();

	Layout();

	if( edit && edit->KeyDown( key ))
	{
		// enter finished typing
		if( !edit->active && edit == &m_field )
		{
			edit->active = true;
			SubmitDialog();
		}
		return true;
	}

	if( UI::Key::IsLeftMouse( key ))
	{
		int hit = HitTest();

		// a tap outside the field hides the keyboard
		if( m_search.active && hit != HIT_SEARCH && hit != HIT_SEARCH_CLEAR )
			m_search.End();

		m_iPressed = hit;
		m_iDownY = m_iLastMoveY = uiStatic.cursorY;
		m_flLastMoveTime = EngFuncs::DoubleTime();
		m_flScrollAtDown = m_flScroll;
		m_flVelocity = 0.0f;
		m_bScrolling = false;
		m_bMaybeScroll = m_iDialog == DLG_NONE && m_clip.HasCursor();
		return true;
	}

	if( key == K_MWHEELDOWN || key == K_MWHEELUP )
	{
		m_flScroll += ( key == K_MWHEELDOWN ? 1 : -1 ) * m_iRowStep;
		ClampScroll();
		return true;
	}

	if( UI::Key::IsEscape( key ))
	{
		if( m_iDialog != DLG_NONE )
			CloseDialog();
		else if( m_search.active )
			m_search.End();
		else
			Hide();
		EngFuncs::PlayLocalSound( uiStatic.sounds[SND_OUT] );
		return true;
	}

	return CMenuFramework::KeyDown( key );
}

bool CCzmServers::KeyUp( int key )
{
	if( UI::Key::IsLeftMouse( key ))
	{
		int pressed = m_iPressed;
		bool tap = !m_bScrolling;
		int hit;

		Layout();
		hit = HitTest();
		m_iPressed = HIT_NONE;

		// a finger that stopped before lifting does not fling
		if( m_bScrolling && EngFuncs::DoubleTime() - m_flLastMoveTime > 0.08 )
			m_flVelocity = 0.0f;

		m_bMaybeScroll = m_bScrolling = false;

		if( tap && hit != HIT_NONE && hit == pressed )
			Activate( hit );

		return true;
	}

	return CMenuFramework::KeyUp( key );
}

bool CCzmServers::MouseMove( int x, int y )
{
	CMenuFramework::MouseMove( x, y );

	if( m_bMaybeScroll )
	{
		double now = EngFuncs::DoubleTime();
		int dy = uiStatic.cursorY - m_iDownY;

		if( !m_bScrolling && abs( dy ) > ScreenHeight * 0.02f )
		{
			m_bScrolling = true;
			m_iPressed = HIT_NONE;
		}

		if( m_bScrolling )
		{
			double dt = now - m_flLastMoveTime;

			m_flScroll = m_flScrollAtDown - dy;
			ClampScroll();

			if( dt > 0.001 )
			{
				float v = -( uiStatic.cursorY - m_iLastMoveY ) / dt;
				m_flVelocity = m_flVelocity * 0.3f + v * 0.7f;
			}
		}

		m_iLastMoveY = uiStatic.cursorY;
		m_flLastMoveTime = now;
	}

	return true;
}

void CCzmServers::Char( int key )
{
	CzmTextEdit *edit = ActiveEdit();

	if( edit )
		edit->Char( key );
}

/*
=================
drawing
=================
*/
void CCzmServers::DrawChip( const CzmRect &r, const char *icon, bool pressed, bool active )
{
	int size = r.h * 0.48f;

	CZM_DrawImage( active ? UI_DIR "pill_lang_on.png" : UI_DIR "chip_round.png", r.x, r.y, r.w, r.h,
		pressed ? PackRGBA( 170, 170, 170, 255 ) : CZM_White());
	CZM_DrawImage( icon, r.x + ( r.w - size ) / 2, r.y + ( r.h - size ) / 2, size, size );
}

void CCzmServers::DrawHeader( void )
{
	HFont titleFont = CZM_Font( CZMF_PANEL_TITLE );
	HFont font = CZM_Font( CZMF_TILE_STATUS );
	const CzmRect &s = m_searchBox;
	int icon = s.h * 0.42f, pad = s.h * 0.4f, textX, textW, textY;
	bool refreshing = Refreshing();

	DrawChip( m_back, UI_DIR "icon_back.png", IsPressed( HIT_BACK ));
	CZM_DrawText( titleFont, m_title.x, m_title.y + ( m_title.h - CZM_FontHeight( titleFont )) / 2, m_title.w + 4, CZM_T( "srv_title" ), CZM_White());

	// search field
	CZM_DrawPill( m_search.active ? UI_DIR "button_danger.png" : UI_DIR "button_secondary.png", s.x, s.y, s.w, s.h,
		IsPressed( HIT_SEARCH ) ? PackRGBA( 200, 200, 200, 255 ) : CZM_White());
	CZM_DrawImage( UI_DIR "icon_search.png", s.x + pad, s.y + ( s.h - icon ) / 2, icon, icon, PackRGBA( 170, 176, 186, 255 ));
	textX = s.x + pad + icon + s.h * 0.25f;
	textW = s.x + s.w - textX - ( m_search.text[0] ? s.h : pad );
	textY = s.y + ( s.h - CZM_FontHeight( font )) / 2;

	if( m_search.text[0] )
	{
		int cw = CZM_TextWidth( font, m_search.text );
		int closeSize = s.h * 0.34f;

		// the end of a long query stays visible while typing
		if( cw > textW )
		{
			const char *p = m_search.text;

			while( *p && CZM_TextWidth( font, p ) > textW )
			{
				p++;
				while(( *p & 0xC0 ) == 0x80 )
					p++;
			}
			CZM_DrawText( font, textX, textY, textW, p, CZM_White());
			cw = CZM_TextWidth( font, p );
		}
		else
			CZM_DrawText( font, textX, textY, textW, m_search.text, CZM_White());

		if( m_search.active && ( uiStatic.realTime / 500 ) % 2 == 0 )
			UI_FillRect( textX + Q_min( cw, textW ) + 2, textY, Q_max( 2, H / 400 ), CZM_FontHeight( font ), PackRGBA( 239, 68, 68, 255 ));

		CZM_DrawImage( UI_DIR "icon_close.png", m_searchClear.x + ( m_searchClear.w - closeSize ) / 2, m_searchClear.y + ( m_searchClear.h - closeSize ) / 2,
			closeSize, closeSize, IsPressed( HIT_SEARCH_CLEAR ) ? CZM_White() : PackRGBA( 170, 176, 186, 255 ));
	}
	else
	{
		CZM_DrawText( font, textX, textY, textW, CZM_T( "srv_search" ), PackRGBA( 130, 136, 146, 255 ));
		if( m_search.active && ( uiStatic.realTime / 500 ) % 2 == 0 )
			UI_FillRect( textX, textY, Q_max( 2, H / 400 ), CZM_FontHeight( font ), PackRGBA( 239, 68, 68, 255 ));
	}

	// refresh pulses while servers answer
	DrawChip( m_refresh, UI_DIR "icon_refresh.png", IsPressed( HIT_REFRESH ));
	if( refreshing )
	{
		float t = (float)fmod( EngFuncs::DoubleTime() * 2.0, 2.0 );
		int a = (int)( 60 + 120 * ( t < 1.0f ? t : 2.0f - t ));
		int d = m_refresh.h * 0.2f;

		CZM_DrawImage( UI_DIR "dot.png", m_refresh.x + m_refresh.w - d, m_refresh.y, d, d, PackRGBA( 239, 68, 68, 135 + a / 2 ));
	}
	DrawChip( m_add, UI_DIR "icon_plus.png", IsPressed( HIT_ADD ));
}

void CCzmServers::DrawFilters( void )
{
	HFont font = CZM_Font( CZMF_TILE_STATUS );
	static const char *tabKeys[TAB_COUNT] = { "srv_tab_all", "srv_tab_fav", "srv_tab_hist" };
	static const char *filterKeys[FILTER_COUNT] = { "srv_f_notempty", "srv_f_notfull", "srv_f_nopass", "srv_f_zombie" };
	CzmRect bar = CZM_Rect( m_tabs[0].x, m_tabs[0].y, m_tabs[TAB_COUNT - 1].x + m_tabs[TAB_COUNT - 1].w - m_tabs[0].x, m_tabs[0].h );
	int inset = bar.h * 0.09f;

	// tabs: one pill, the active part is red
	CZM_DrawPill( UI_DIR "chip_lang.png", bar.x, bar.y, bar.w, bar.h );
	for( int i = 0; i < TAB_COUNT; i++ )
	{
		const CzmRect &r = m_tabs[i];
		bool active = i == m_iTab;
		int count = i == TAB_FAVORITES ? m_favorites.Count() : i == TAB_HISTORY ? m_history.Count() : 0;
		const char *label = CZM_T( tabKeys[i] );
		int textW = CZM_TextWidth( font, label ), textY = r.y + ( r.h - CZM_FontHeight( font )) / 2;
		unsigned int color = active || IsPressed( HIT_TAB + i ) ? CZM_White() : PackRGBA( 170, 176, 186, 255 );
		char number[16];
		int x;

		if( active )
			CZM_DrawPill( UI_DIR "pill_lang_on.png", r.x + inset, r.y + inset, r.w - inset * 2, r.h - inset * 2 );

		number[0] = 0;
		if( count > 0 )
			snprintf( number, sizeof( number ), "  %d", count );

		x = r.x + ( r.w - textW - CZM_TextWidth( font, number )) / 2;
		CZM_DrawText( font, x, textY, textW + 2, label, color );
		if( number[0] )
			CZM_DrawText( font, x + textW, textY, CZM_TextWidth( font, number ) + 2, number, active ? CZM_White( 200 ) : PackRGBA( 120, 126, 136, 255 ));
	}

	// filters: tap to switch on and off
	for( int i = 0; i < FILTER_COUNT; i++ )
	{
		const CzmRect &r = m_filters[i];
		bool on = ( m_iFilters & ( 1 << i )) != 0;
		bool pressed = IsPressed( HIT_FILTER + i );
		int d = r.h * 0.26f, textX = r.x + r.h * 0.42f + d;

		CZM_DrawPill( on ? UI_DIR "pill_lang_on.png" : UI_DIR "chip_lang.png", r.x, r.y, r.w, r.h,
			pressed ? PackRGBA( 190, 190, 190, 255 ) : CZM_White());
		// a check mark when on, a hollow dot when off
		if( on )
			CZM_DrawImage( UI_DIR "icon_check.png", r.x + r.h * 0.30f, r.y + ( r.h - d * 1.4f ) / 2, d * 1.4f, d * 1.4f );
		else
			CZM_DrawImage( UI_DIR "dot.png", r.x + r.h * 0.36f, r.y + ( r.h - d ) / 2, d, d, PackRGBA( 110, 116, 126, 255 ));
		CZM_DrawText( font, textX, r.y + ( r.h - CZM_FontHeight( font )) / 2, r.x + r.w - textX - r.h * 0.25f, CZM_T( filterKeys[i] ),
			on ? CZM_White() : PackRGBA( 200, 205, 215, 255 ));
	}
}

void CCzmServers::DrawRow( int index, const CzmRect &r )
{
	CzmEntry &e = m_entries[m_view[index]];
	HFont nameFont = CZM_Font( CZMF_SHOP_NAME );
	HFont subFont = CZM_Font( CZMF_TILE_TEXT );
	HFont statFont = CZM_Font( CZMF_TILE_STATUS );
	HFont badgeFont = CZM_Font( CZMF_SHOP_PRICE );
	bool selected = !strcmp( e.address, m_szSelected );
	bool pressed = m_iPressed == HIT_ROW + index * 3 && IsPressed( m_iPressed );
	int pad = r.h * 0.12f, x, right, statsW, starSize, textW, textX, y;
	unsigned int dim = PackRGBA( 154, 163, 175, 255 );
	char text[128];

	CZM_DrawSliced( selected ? UI_DIR "card_on.png" : UI_DIR "card.png", r.x, r.y, r.w, r.h, 30, (int)( H * 0.02f ),
		pressed ? PackRGBA( 200, 200, 200, 255 ) : CZM_White( selected ? 255 : 235 ));

	// picture with the mode badge, or the badge alone
	x = r.x + pad;
	if( m_bThumbs )
	{
		int th = r.h - pad * 2, tw = th * 2;

		DrawMapPicture( &e, x, r.y + pad, tw, th );
		if( e.badge[0] )
		{
			int bh = th * 0.36f, bw = CZM_TextWidth( badgeFont, e.badge ) + bh * 0.7f;

			CZM_DrawPill( UI_DIR "pill_lang_on.png", x + th * 0.08f, r.y + pad + th * 0.08f, bw, bh, ModeColor( e.mode ));
			CZM_DrawText( badgeFont, x + th * 0.08f, r.y + pad + th * 0.08f + ( bh - CZM_FontHeight( badgeFont )) / 2, bw, e.badge, CZM_White(), QM_CENTER );
		}
		x += tw + pad * 1.4f;
	}
	else
	{
		int size = r.h - pad * 2;

		CZM_DrawSliced( UI_DIR "card.png", x, r.y + pad, size, size, 30, size / 4, ModeColor( e.mode ));
		CZM_DrawText( badgeFont, x, r.y + pad + ( size - CZM_FontHeight( badgeFont )) / 2, size, e.badge[0] ? e.badge : "?", CZM_White(), QM_CENTER );
		x += size + pad * 1.4f;
	}

	// star, heart, ping, players on the right
	starSize = r.h * 0.36f;
	right = r.x + r.w - r.h;
	{
		bool fav = ( e.sources & SRC_FAVORITE ) != 0;
		bool starPressed = m_iPressed == HIT_ROW + index * 3 + 1 && IsPressed( m_iPressed );

		CZM_DrawImage( fav ? UI_DIR "icon_star_on.png" : UI_DIR "icon_star.png", right + ( r.h - starSize ) / 2, r.y + ( r.h - starSize ) / 2,
			starSize, starSize, fav ? PackRGBA( 250, 204, 21, 255 ) : starPressed ? CZM_White() : PackRGBA( 110, 116, 126, 255 ));
	}

	// heart to the left of the star: pin to the main screen (max 3)
	{
		int heartSize = r.h * 0.34f;
		int heartX = right - r.h;
		bool pinned = CZM_HomePinned( e.address );
		bool heartPressed = m_iPressed == HIT_ROW + index * 3 + 2 && IsPressed( m_iPressed );

		CZM_DrawImage( pinned ? UI_DIR "icon_heart_on.png" : UI_DIR "icon_heart.png",
			heartX + ( r.h - heartSize ) / 2, r.y + ( r.h - heartSize ) / 2, heartSize, heartSize,
			pinned ? PackRGBA( 244, 63, 94, 255 ) : heartPressed ? CZM_White() : PackRGBA( 110, 116, 126, 255 ));
	}
	right -= r.h; // the stats and the name stop before the heart

	statsW = H * 0.30f;
	if( e.answered )
	{
		int humans = e.players - e.bots;
		int pingX = right - H * 0.12f, playersX = pingX - H * 0.17f;
		int barW = H * 0.11f, barH = Q_max( 3, (int)( H * 0.006f ));
		float fill = e.maxPlayers > 0 ? (float)e.players / e.maxPlayers : 0.0f;
		unsigned int barColor = fill >= 1.0f ? PackRGBA( 248, 113, 113, 255 ) : fill >= 0.75f ? PackRGBA( 250, 204, 21, 255 ) : PackRGBA( 74, 222, 128, 255 );

		// the count with a bar under it, both centred in the row
		int gap = H * 0.01f, blockY = r.y + ( r.h - CZM_FontHeight( statFont ) - gap - barH ) / 2;
		int barY = blockY + CZM_FontHeight( statFont ) + gap;

		snprintf( text, sizeof( text ), "%d/%d", e.players, e.maxPlayers );
		CZM_DrawText( statFont, playersX, blockY, barW + H * 0.04f, text, humans > 0 ? CZM_White() : dim );
		FillRect( playersX, barY, barW, barH, CZM_White( 36 ));
		if( fill > 0.0f )
			FillRect( playersX, barY, Q_max( barH, (int)( barW * Q_min( fill, 1.0f ))), barH, barColor );

		if( e.ping >= 0 )
		{
			int d = r.h * 0.12f;

			snprintf( text, sizeof( text ), "%d %s", e.ping, CZM_T( "ms" ));
			CZM_DrawImage( UI_DIR "dot.png", pingX, r.y + ( r.h - d ) / 2, d, d, CZM_PingColor( e.ping ));
			CZM_DrawText( statFont, pingX + d * 1.7f, r.y + ( r.h - CZM_FontHeight( statFont )) / 2, H * 0.10f, text, CZM_PingColor( e.ping ));
		}
		statsW = right - playersX + H * 0.02f;
	}
	else
	{
		const char *status = IsStale( e ) ? CZM_T( "offline" ) : CZM_T( "querying" );

		statsW = Q_min( CZM_TextWidth( statFont, status ), (int)( H * 0.34f )) + H * 0.02f;
		CZM_DrawText( statFont, right - statsW, r.y + ( r.h - CZM_FontHeight( statFont )) / 2, statsW, status,
			IsStale( e ) ? PackRGBA( 248, 113, 113, 255 ) : dim );
		statsW += H * 0.02f;
	}

	// name: lock, the name
	textW = right - statsW - x;
	textX = x;
	y = r.y + r.h * 0.17f;
	if( e.password )
	{
		int size = CZM_FontHeight( nameFont ) * 0.8f;

		CZM_DrawImage( UI_DIR "icon_lock.png", x, y + ( CZM_FontHeight( nameFont ) - size ) / 2, size, size, PackRGBA( 250, 204, 21, 255 ));
		x += size + H * 0.01f;
		textW -= size + H * 0.01f;
	}
	CZM_DrawText( nameFont, x, y, textW, e.name, e.answered ? CZM_White() : dim );

	// map, bots or the address
	if( e.answered )
	{
		if( e.bots > 0 )
		{
			char bots[32];

			CountText( bots, sizeof( bots ), e.bots, "бот", "бота", "ботов", "bot", "bots" );
			snprintf( text, sizeof( text ), "%s  ·  %s", e.map, bots );
		}
		else
			Q_strncpy( text, e.map, sizeof( text ));
	}
	else
		Q_strncpy( text, e.address, sizeof( text ));

	// the second line starts under the badges
	CZM_DrawText( subFont, textX, r.y + r.h * 0.57f, right - statsW - textX, text, dim );
}

void CCzmServers::DrawEmpty( void )
{
	HFont titleFont = CZM_Font( CZMF_NICK );
	HFont textFont = CZM_Font( CZMF_PANEL_TEXT );
	const char *title, *text, *button = NULL, *icon;
	int iconSize = H * 0.10f, y;

	if( !EmptyHasButton( ))
	{
		static const char *dots[4] = { "", ".", "..", "..." };

		icon = UI_DIR "icon_globe.png";
		title = CZM_T( "srv_searching" );
		text = dots[( uiStatic.realTime / 400 ) % 4];
	}
	else if( m_iFilters || m_szQuery[0] )
	{
		icon = UI_DIR "icon_search.png";
		title = CZM_T( "srv_nothing" );
		text = CZM_T( "srv_nothing_hint" );
		button = CZM_T( "srv_reset" );
	}
	else if( m_iTab == TAB_FAVORITES )
	{
		icon = UI_DIR "icon_star.png";
		title = CZM_T( "srv_fav_empty" );
		text = CZM_T( "srv_fav_hint" );
		button = CZM_T( "srv_add_title" );
	}
	else if( m_iTab == TAB_HISTORY )
	{
		icon = UI_DIR "icon_clock.png";
		title = CZM_T( "srv_hist_empty" );
		text = CZM_T( "srv_hist_hint" );
		button = CZM_T( "srv_tab_all" );
	}
	else
	{
		icon = UI_DIR "icon_globe.png";
		title = CZM_T( "srv_none" );
		text = CZM_T( "srv_none_hint" );
		button = CZM_T( "srv_refresh" );
	}

	y = m_clip.y + m_clip.h * 0.12f;
	CZM_DrawImage( icon, m_clip.x + ( m_clip.w - iconSize ) / 2, y, iconSize, iconSize, CZM_White( 70 ));
	y += iconSize + H * 0.03f;
	CZM_DrawText( titleFont, m_clip.x, y, m_clip.w, title, CZM_White(), QM_CENTER );
	y += CZM_FontHeight( titleFont ) + H * 0.012f;
	CZM_DrawText( textFont, m_clip.x + H * 0.04f, y, m_clip.w - H * 0.08f, text, PackRGBA( 165, 172, 182, 255 ), QM_CENTER );

	if( button )
		CZM_DrawButton( UI_DIR "button_secondary.png", m_emptyButton, button, CZM_White(), IsPressed( HIT_EMPTY_BUTTON ));
}

void CCzmServers::DrawList( void )
{
	HFont font = CZM_Font( CZMF_SMALL );
	char text[160], servers[48], players[48], pinned[48];
	int total = 0, first, last, pins = CZM_HomePinCount();
	bool refreshing = Refreshing();
	static const char *sortKeys[SORT_COUNT] = { "srv_sort_players", "srv_sort_ping", "srv_sort_name" };

	// what is on the list and how it is sorted
	for( int i = 0; i < ViewCount(); i++ )
		total += Q_max( 0, m_entries[m_view[i]].players - m_entries[m_view[i]].bots );

	CountText( servers, sizeof( servers ), ViewCount(), "сервер", "сервера", "серверов", "server", "servers" );
	CountText( players, sizeof( players ), total, "игрок", "игрока", "игроков", "player", "players" );
	if( pins > 0 )
		snprintf( pinned, sizeof( pinned ), "  ·  %s %d/%d", CZM_T( "srv_pinned" ), pins, CZM_HOME_MAX );
	else
		pinned[0] = 0;
	snprintf( text, sizeof( text ), "%s  ·  %s%s%s", servers, players, refreshing ? CZM_T( "srv_updating" ) : "", pinned );
	CZM_DrawText( font, m_listHead.x + H * 0.01f, m_listHead.y + ( m_listHead.h - CZM_FontHeight( font )) / 2, m_sort.x - m_listHead.x - H * 0.02f,
		text, PackRGBA( 154, 163, 175, 255 ));

	{
		const CzmRect &r = m_sort;
		bool history = m_iTab == TAB_HISTORY;
		int icon = r.h * 0.5f;
		unsigned int color = history ? PackRGBA( 120, 126, 136, 255 ) : IsPressed( HIT_SORT ) ? CZM_White() : PackRGBA( 200, 205, 215, 255 );

		if( !history )
			CZM_DrawPill( UI_DIR "chip_lang.png", r.x, r.y, r.w, r.h, IsPressed( HIT_SORT ) ? PackRGBA( 190, 190, 190, 255 ) : CZM_White());
		CZM_DrawImage( UI_DIR "icon_sort.png", r.x + r.h * 0.45f, r.y + ( r.h - icon ) / 2, icon, icon, color );
		CZM_DrawText( font, r.x + r.h * 0.45f + icon + r.h * 0.2f, r.y + ( r.h - CZM_FontHeight( font )) / 2, r.w - r.h, CZM_T( history ? "srv_sort_recent" : sortKeys[m_iSort] ), color );
	}

	if( ViewCount() == 0 )
	{
		DrawEmpty();
		return;
	}

	first = Q_max( 0, (int)m_flScroll / m_iRowStep );
	last = Q_min( ViewCount() - 1, ( (int)m_flScroll + m_clip.h ) / m_iRowStep );

	UI::Scissor::PushScissor( m_clip.x, m_clip.y, m_clip.w, m_clip.h );
	for( int i = first; i <= last; i++ )
		DrawRow( i, RowRect( i ));
	UI::Scissor::PopScissor();

	// scroll bar
	if( MaxScroll() > 0 )
	{
		int trackH = m_clip.h;
		int barH = Q_max( (int)( H * 0.06f ), trackH * m_clip.h / ( m_clip.h + MaxScroll()));
		int barY = m_clip.y + ( trackH - barH ) * (int)m_flScroll / MaxScroll();

		UI_FillRect( m_clip.x + m_clip.w + H * 0.008f, barY, Q_max( 3, (int)( H * 0.005f )), barH, CZM_White( 70 ));
	}
}

void CCzmServers::DrawDetails( void )
{
	CzmEntry *e = Selected();
	const CzmRect &d = m_details;
	int pad = H * 0.03f, x = d.x + pad, w = d.w - pad * 2, y;
	HFont nameFont = CZM_Font( CZMF_NICK );
	HFont statFont = CZM_Font( CZMF_TILE_STATUS );
	HFont smallFont = CZM_Font( CZMF_SMALL );
	HFont textFont = CZM_Font( CZMF_TILE_TEXT );
	HFont badgeFont = CZM_Font( CZMF_SHOP_PRICE );
	const unsigned int dim = PackRGBA( 154, 163, 175, 255 );
	char text[160];

	CZM_DrawPanel( d );

	if( !e )
	{
		int iconSize = H * 0.10f;

		y = d.y + d.h * 0.36f;
		CZM_DrawImage( UI_DIR "icon_globe.png", d.x + ( d.w - iconSize ) / 2, y, iconSize, iconSize, CZM_White( 60 ));
		CZM_DrawText( CZM_Font( CZMF_PANEL_TEXT ), d.x + pad, y + iconSize + H * 0.03f, w, CZM_T( "srv_pick" ), PackRGBA( 165, 172, 182, 255 ), QM_CENTER );
		return;
	}

	// map picture, the badge and the map name over its lower edge
	{
		int ih = Q_min( (int)( w * 0.38f ), (int)( H * 0.21f ));

		DrawMapPicture( e, x, d.y + pad, w, ih );
		CZM_DrawImage( "gfx/czm/fade_bottom.png", x, d.y + pad + ih / 3, w, ih - ih / 3, CZM_White( 230 ));

		if( e->badge[0] )
		{
			int bh = H * 0.04f, bw = CZM_TextWidth( badgeFont, e->badge ) + bh * 0.8f;

			CZM_DrawPill( UI_DIR "pill_lang_on.png", x + H * 0.015f, d.y + pad + H * 0.015f, bw, bh, ModeColor( e->mode ));
			CZM_DrawText( badgeFont, x + H * 0.015f, d.y + pad + H * 0.015f + ( bh - CZM_FontHeight( badgeFont )) / 2, bw, e->badge, CZM_White(), QM_CENTER );
		}

		if( e->map[0] )
			CZM_DrawText( statFont, x + H * 0.02f, d.y + pad + ih - CZM_FontHeight( statFont ) - H * 0.012f, w - H * 0.04f, e->map, CZM_White());

		y = d.y + pad + ih + H * 0.022f;
	}

	// name in up to two lines
	{
		char line[128];
		const char *rest = FitWords( nameFont, e->answered ? e->name : e->address, w, line, sizeof( line ));

		CZM_DrawText( nameFont, x, y, w, line, CZM_White());
		y += CZM_FontHeight( nameFont );
		if( *rest )
		{
			CZM_DrawText( nameFont, x, y, w, rest, CZM_White());
			y += CZM_FontHeight( nameFont );
		}
		y += H * 0.012f;
	}

	// players, ping, password
	{
		int icon = CZM_FontHeight( statFont ), sx = x;

		if( e->answered )
		{
			CZM_DrawImage( UI_DIR "icon_users.png", sx, y, icon, icon, PackRGBA( 200, 205, 215, 255 ));
			sx += icon + H * 0.01f;
			snprintf( text, sizeof( text ), "%d/%d", e->players, e->maxPlayers );
			CZM_DrawText( statFont, sx, y, w, text, CZM_White());
			sx += CZM_TextWidth( statFont, text ) + H * 0.035f;

			if( e->ping >= 0 )
			{
				int dot = icon * 0.5f;

				CZM_DrawImage( UI_DIR "dot.png", sx, y + ( icon - dot ) / 2, dot, dot, CZM_PingColor( e->ping ));
				sx += dot + H * 0.01f;
				snprintf( text, sizeof( text ), "%d %s", e->ping, CZM_T( "ms" ));
				CZM_DrawText( statFont, sx, y, w, text, CZM_PingColor( e->ping ));
				sx += CZM_TextWidth( statFont, text ) + H * 0.035f;
			}

			if( e->password && sx < x + w )
			{
				CZM_DrawImage( UI_DIR "icon_lock.png", sx, y, icon, icon, PackRGBA( 250, 204, 21, 255 ));
				sx += icon + H * 0.01f;
				CZM_DrawText( statFont, sx, y, x + w - sx, CZM_T( "srv_password" ), PackRGBA( 250, 204, 21, 255 ));
			}
		}
		else
		{
			bool stale = IsStale( *e );
			CZM_DrawText( statFont, x, y, w, CZM_T( stale ? "offline" : "querying" ), stale ? PackRGBA( 248, 113, 113, 255 ) : dim );
		}
		y += icon + H * 0.01f;

		snprintf( text, sizeof( text ), "IP  %s", e->address );
		CZM_DrawText( smallFont, x, y, w, text, dim );
		y += CZM_FontHeight( smallFont ) + H * 0.02f;
	}

	// players on the server
	{
		int bottom = m_admin.y - H * 0.02f;
		int lineH = CZM_FontHeight( textFont ) + H * 0.01f;
		int fragsW = H * 0.06f;

		if( y + CZM_FontHeight( smallFont ) + lineH <= bottom )
		{
			UI_FillRect( x, y, w, CZM_LineWidth(), CZM_White( 30 ));
			y += H * 0.015f;

			if( m_iPlayersState == 2 && m_iNumPlayers > 0 )
				snprintf( text, sizeof( text ), "%s  ·  %d", CZM_T( "srv_players" ), m_iNumPlayers );
			else
				Q_strncpy( text, CZM_T( "srv_players" ), sizeof( text ));
			CZM_DrawText( smallFont, x, y, w - fragsW, text, dim );
			if( m_iPlayersState == 2 && m_iNumPlayers > 0 && w < H * 0.6f )
				CZM_DrawText( smallFont, x + w - fragsW, y, fragsW, CZM_T( "srv_frags" ), dim, QM_RIGHT );
			y += CZM_FontHeight( smallFont ) + H * 0.01f;

			if( m_iPlayersState != 2 || m_iNumPlayers == 0 || strcmp( m_szPlayersFor, e->address ))
			{
				const char *key = !e->answered ? "" : ( m_iPlayersState <= 1 || strcmp( m_szPlayersFor, e->address )) ? "srv_players_wait"
					: e->players > 0 ? "srv_players_hidden" : "srv_players_none";

				if( key[0] )
					CZM_DrawText( textFont, x, y, w, CZM_T( key ), PackRGBA( 120, 126, 136, 255 ));
			}
			else
			{
				// two columns on a wide panel, best players first, top to bottom
				int columns = w >= H * 0.6f ? 2 : 1;
				int colGap = H * 0.035f, colW = ( w - colGap * ( columns - 1 )) / columns;
				int rows = Q_max( 1, ( bottom - y ) / lineH );
				int fit = rows * columns;
				int shown = m_iNumPlayers > fit ? fit - 1 : m_iNumPlayers;

				for( int i = 0; i < shown; i++ )
				{
					int cx = x + ( i / rows ) * ( colW + colGap ), cy = y + ( i % rows ) * lineH;

					snprintf( text, sizeof( text ), "%d", m_players[i].frags );
					CZM_DrawText( textFont, cx, cy, colW - fragsW - H * 0.015f, m_players[i].name, CZM_White());
					CZM_DrawText( textFont, cx + colW - fragsW, cy, fragsW, text, PackRGBA( 200, 205, 215, 255 ), QM_RIGHT );
				}

				if( shown < m_iNumPlayers )
				{
					char more[64];
					int i = shown;

					snprintf( more, sizeof( more ), CZM_T( "srv_more" ), m_iNumPlayers - shown );
					CZM_DrawText( textFont, x + ( i / rows ) * ( colW + colGap ), y + ( i % rows ) * lineH, colW, more, PackRGBA( 120, 126, 136, 255 ));
				}
			}
		}
	}

	CZM_DrawButton( UI_DIR "button_secondary.png", m_admin, CZM_IsRussian() ? "Админка/VIP" : "Admin/VIP", CZM_White(), IsPressed( HIT_ADMIN ));

	// favorite and play
	{
		bool fav = ( e->sources & SRC_FAVORITE ) != 0;
		HFont font = CZM_Font( CZMF_BUTTON );
		const CzmRect &f = m_fav;
		int icon = f.h * 0.42f;
		const char *label = CZM_T( fav ? "srv_fav_in" : "srv_fav_add" );
		int textW = CZM_TextWidth( font, label );

		CZM_DrawPill( UI_DIR "button_secondary.png", f.x, f.y, f.w, f.h, IsPressed( HIT_FAVORITE ) ? PackRGBA( 185, 185, 185, 255 ) : CZM_White());
		if( f.w >= icon + textW + f.h * 0.9f )
		{
			int sx = f.x + ( f.w - icon - textW - H * 0.012f ) / 2;

			CZM_DrawImage( fav ? UI_DIR "icon_star_on.png" : UI_DIR "icon_star.png", sx, f.y + ( f.h - icon ) / 2, icon, icon,
				fav ? PackRGBA( 250, 204, 21, 255 ) : CZM_White());
			CZM_DrawText( font, sx + icon + H * 0.012f, f.y + ( f.h - CZM_FontHeight( font )) / 2, textW + 2, label, CZM_White());
		}
		else
			CZM_DrawImage( fav ? UI_DIR "icon_star_on.png" : UI_DIR "icon_star.png", f.x + ( f.w - icon ) / 2, f.y + ( f.h - icon ) / 2, icon, icon,
				fav ? PackRGBA( 250, 204, 21, 255 ) : CZM_White());

		CZM_DrawButton( UI_DIR "button_primary.png", m_play, CZM_T( "srv_play" ), CZM_White(), IsPressed( HIT_PLAY ));
	}
}

void CCzmServers::DrawDialog( void )
{
	HFont titleFont = CZM_Font( CZMF_PANEL_TITLE );
	HFont textFont = CZM_Font( CZMF_PANEL_TEXT );
	HFont fieldFont = CZM_Font( CZMF_TILE_STATUS );
	const CzmRect &p = m_dlgPanel;
	const CzmRect &f = m_dlgField;
	int pad = H * 0.045f, textY = f.y + ( f.h - CZM_FontHeight( fieldFont )) / 2;
	bool password = m_iDialog == DLG_PASSWORD;
	char shown[128];

	UI_FillRect( 0, 0, W, H, PackRGBA( 0, 0, 0, 180 ));
	CZM_DrawPanel( p );

	CZM_DrawText( titleFont, p.x + pad, p.y + pad * 0.8f, p.w - pad * 2, CZM_T( password ? "srv_pass_title" : "srv_add_title" ), CZM_White());
	CZM_DrawText( textFont, p.x + pad, p.y + pad * 0.8f + CZM_FontHeight( titleFont ) + H * 0.012f, p.w - pad * 2,
		m_szDialogError[0] ? m_szDialogError : CZM_T( password ? "srv_pass_text" : "srv_add_text" ),
		m_szDialogError[0] ? PackRGBA( 248, 113, 113, 255 ) : PackRGBA( 165, 172, 182, 255 ));

	// the field; a password shows as dots
	if( password )
	{
		size_t n = 0;

		for( const char *s = m_field.text; *s && n + 4 < sizeof( shown ); s++ )
		{
			if(( *s & 0xC0 ) == 0x80 )
				continue;
			memcpy( shown + n, "\xE2\x80\xA2", 3 );
			n += 3;
		}
		shown[n] = 0;
	}
	else
		Q_strncpy( shown, m_field.text, sizeof( shown ));

	CZM_DrawPill( m_field.active ? UI_DIR "button_danger.png" : UI_DIR "button_secondary.png", f.x, f.y, f.w, f.h,
		IsPressed( HIT_DIALOG_FIELD ) ? PackRGBA( 200, 200, 200, 255 ) : CZM_White());
	if( shown[0] )
		CZM_DrawText( fieldFont, f.x + f.h * 0.45f, textY, f.w - f.h * 0.9f, shown, CZM_White());
	else
		CZM_DrawText( fieldFont, f.x + f.h * 0.45f, textY, f.w - f.h * 0.9f, password ? CZM_T( "srv_pass_hint" ) : "1.2.3.4:27015", PackRGBA( 130, 136, 146, 255 ));
	if( m_field.active && ( uiStatic.realTime / 500 ) % 2 == 0 )
		UI_FillRect( f.x + f.h * 0.45f + Q_min( CZM_TextWidth( fieldFont, shown ), (int)( f.w - f.h * 0.9f )) + 2, textY, Q_max( 2, H / 400 ),
			CZM_FontHeight( fieldFont ), PackRGBA( 239, 68, 68, 255 ));

	if( !password )
		CZM_DrawButton( UI_DIR "button_secondary.png", m_dlgPaste, CZM_T( "srv_paste" ), CZM_White(), IsPressed( HIT_DIALOG_PASTE ), CZMF_TILE_STATUS );

	CZM_DrawButton( UI_DIR "button_secondary.png", m_dlgCancel, CZM_T( "cancel" ), CZM_White(), IsPressed( HIT_DIALOG_CANCEL ));
	CZM_DrawButton( UI_DIR "button_primary.png", m_dlgOk, CZM_T( password ? "srv_pass_go" : "srv_add_ok" ), CZM_White(), IsPressed( HIT_DIALOG_OK ));
}

void CCzmServers::Draw()
{
	double now = EngFuncs::DoubleTime();
	if( m_szJoinAddress[0] && now - m_flJoinStarted > LIST_TIMEOUT )
	{
		m_szJoinAddress[0] = 0;
		Toast( CZM_IsRussian() ? "Сервер друга не ответил. Можно повторить подключение" : "Your friend's server did not respond. Try again" );
	}
	float dt = (float)bound( 0.0, now - m_flLastDraw, 0.05 );
	char query[64];

	m_flLastDraw = now;
	Layout();

	// the search follows typing at once
	FoldText( m_search.text, query, sizeof( query ));
	if( strcmp( query, m_szQuery ))
	{
		Q_strncpy( m_szQuery, query, sizeof( m_szQuery ));
		m_flScroll = 0.0f;
		m_bForceRebuild = true;
	}

	// answers stream in: the order settles twice a second, not under the finger
	if( m_bForceRebuild || ( m_bDirty && !m_bMaybeScroll && now - m_flLastRebuild > 0.5 ))
		Rebuild();

	// fling
	if( !m_bScrolling && fabsf( m_flVelocity ) > 1.0f )
	{
		m_flScroll += m_flVelocity * dt;
		m_flVelocity *= expf( -3.5f * dt );
		if( fabsf( m_flVelocity ) < 20.0f )
			m_flVelocity = 0.0f;
	}
	ClampScroll();

	// the selected server stays fresh
	if( Selected() && now - m_flDetailsTime > DETAILS_PERIOD && m_iDialog == DLG_NONE )
		RequestDetails( Selected( ));

	// calm the art down so the list reads well
	UI_FillRect( 0, 0, W, H, PackRGBA( 0, 0, 0, 130 ));
	CZM_DrawImage( UI_DIR "fade_top.png", 0, 0, W, H * 0.24f, CZM_White( 210 ));

	DrawHeader();
	DrawFilters();
	DrawList();
	DrawDetails();

	if( m_szToast[0] && now - m_flToastTime < 2.0 )
	{
		HFont font = CZM_Font( CZMF_TILE_STATUS );
		int tw = CZM_TextWidth( font, m_szToast ) + H * 0.08f, th = H * 0.07f;
		CzmRect r = CZM_Rect( m_clip.x + ( m_clip.w - tw ) / 2, H - th - H * 0.05f, tw, th );

		CZM_DrawPill( UI_DIR "button_secondary.png", r.x, r.y, r.w, r.h );
		CZM_DrawText( font, r.x, r.y + ( r.h - CZM_FontHeight( font )) / 2, r.w, m_szToast, CZM_White(), QM_CENTER );
	}

	if( m_iDialog != DLG_NONE )
		DrawDialog();
}

/*
=================
registration and hooks
=================
*/
ADD_MENU3( menu_czmservers, CCzmServers, UI_CzmServers_Menu );

void UI_CzmServers_Menu( void )
{
	// stop the background demo so the network can be used
	if( gpGlobals->demoplayback && EngFuncs::GetCvarFloat( "cl_background" ))
		EngFuncs::ClientCmd( false, "stop\n" );

	menu_czmservers->Show();
}

void CZM_OpenServerList( void )
{
	UI_CzmServers_Menu();
}

void CCzmServers::JoinAddress( const char *address )
{
	CzmEntry *e = AddAddress( address, "gs" );
	if( !e ) { Toast( CZM_IsRussian() ? "Некорректный адрес сервера" : "Invalid server address" ); return; }
	m_iTab = TAB_ALL; m_iFilters = 0; m_search.text[0] = m_szQuery[0] = 0;
	e->sources |= SRC_INTERNET;
	Select( e ); m_bForceRebuild = true;
	Q_strncpy( m_szJoinAddress, e->address, sizeof( m_szJoinAddress ));
	m_flJoinStarted = EngFuncs::DoubleTime();
	RequestDetails( e );
	Toast( CZM_IsRussian() ? "Проверяем сервер друга…" : "Checking your friend's server…" );
}

void CZM_JoinAddress( const char *address )
{
	if( !address || strlen( address ) >= 64 || strspn( address, "0123456789abcdefABCDEF.:[]" ) != strlen( address )) return;
	UI_CzmServers_Menu();
	menu_czmservers->JoinAddress( address );
}

void CZM_QuickPlayStart( void )
{
	if( s_browser )
		s_browser->QuickStart();
}

void CZM_QuickPlayCancel( void )
{
	if( s_browser )
		s_browser->QuickCancel();
}

bool CZM_QuickPlayActive( void )
{
	return s_browser && s_browser->QuickActive();
}

int CZM_QuickPlayFrame( char *name, size_t size )
{
	return s_browser ? s_browser->QuickFrame( name, size ) : -1;
}

void CZM_ServerListInfo( netadr_t adr, const char *info )
{
	if( s_browser )
		s_browser->OnServerInfo( adr, info );
}

void CZM_ServerListResetPing( void )
{
	if( s_browser )
		s_browser->ResetPing();
}

bool CZM_ServerListReturn( void )
{
	if( !s_browser || !s_browser->m_bReturnHere )
		return false;

	s_browser->m_bReturnHere = false;
	UI_CzmServers_Menu();
	return true;
}
