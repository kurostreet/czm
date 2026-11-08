/*
CzmOnline.cpp - Counter Zombie Mobile: the player on our service (counter-zombie.ru)
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

#include "extdll_menu.h"
#include "BaseMenu.h"
#include "Utils.h"
#include "CzmMenu.h"
#include "CzmTranslation.h"
#include "CzmJson.h"

/*
The game introduces the player once a start and again when the nick or the avatar
changes ("hello"): a secret key kept in czm_online.key, the phone fingerprint for bans,
nick, avatar, language, version. The answer brings the player number, a ban, the last
news number and an update. The player's own photo is uploaded once per new photo.
Other players' photos are downloaded into czm_cache/ for the chat.
Everything here runs from CZM_OnlineFrame, every frame, in the menu and in a match.
*/
#define KEY_FILE "czm_online.key"
#define HELLO_EVERY 600.0 // seconds, news and updates while the game stays open
#define RETRY_AFTER 30.0
#define MAX_AVATARS 256

static struct
{
	bool started;
	char key[80];
	int helloId;          // request in flight
	double nextHello;
	char sentNick[64];
	char sentAvatar[80];
	bool ready;
	bool account;
	bool development;
	bool refreshDistribution;
	int identity;
	int player;
	char myAvatar[32];

	bool banned;
	bool banForever;
	int banUntil;
	char banReason[128];

	bool support;         // current in-game moderation capability; the API checks every action
	bool admin;           // separately allowlisted head administrator
	char role[16];
	struct { bool active, forever; int until; char reason[128]; } limits[CZM_LIMIT_COUNT];
	int warning;          // the newest moderator warning not yet shown, its text
	char warningReason[220];
	int warningShown, warningSeenId;

	int newsLast;         // the newest news number on the server
	struct { int code; char version[16]; char notes[512], notes_en[512]; } play[3]; // releases on the Play tracks, what is new in each
	int newsId;           // news list request in flight
	bool newsLoaded;
	CUtlVector<CzmNews> news;

	CzmUpdateInfo update;
	int uploadId;
	char uploading[64];
	int profilePhoto; // restored account photo request, no upload until it has completed
	char profilePhotoPath[64];
	bool preserveAvatar;
	double photoRetry;

	int onlineId;         // players-online request in flight
	double nextOnline;
	int onlineCount;      // -1 until the service answers
} s_online;

bool CZM_OnlinePlayAllowed( void )
{
    // The obsolete migration-only gate no longer belongs in the new
    // private test APK. Existing retired builds stay retired on their own.
    // Distribution and Google Play update restrictions remain server-side.
    return true;
}

static struct
{
	int player;
	int rev;
	int state;            // 0 nothing, 1 downloading, 2 ready, 3 failed
	int request;
	double retry;
	char path[64];
} s_avatars[MAX_AVATARS];
static int s_numAvatars;

const char *CZM_OnlineUrl( const char *path )
{
	static char url[2][512];
	static int which;

	which ^= 1;
	snprintf( url[which], sizeof( url[0] ), "https://counter-zombie.ru%s", path );
	return url[which];
}

int CZM_OnlineCount( void )
{
	return s_online.started && s_online.onlineCount > 0 ? s_online.onlineCount : -1;
}

const char *CZM_OnlineKey( void )
{
	return s_online.key;
}

bool CZM_OnlineReady( void )
{
	return s_online.ready;
}

bool CZM_OnlineAccount( void ) { return s_online.account; }
int CZM_OnlineIdentity( void ) { return s_online.identity; }

int CZM_OnlinePlayer( void )
{
	return s_online.player;
}

bool CZM_OnlineBan( int *until, bool *forever, const char **reason )
{
	if( !s_online.banned )
		return false;
	if( until ) *until = s_online.banUntil;
	if( forever ) *forever = s_online.banForever;
	if( reason ) *reason = s_online.banReason;
	return true;
}

bool CZM_OnlineSupport( void )
{
	return s_online.ready && s_online.support;
}

const char *CZM_OnlineRole( void ) { return s_online.ready ? s_online.role : ""; }
bool CZM_OnlineAdmin( void ) { return s_online.ready && s_online.admin; }

void CZM_OnlineSetLimit( int kind, const CzmJson &j, int node )
{
	if( kind < 0 || kind >= CZM_LIMIT_COUNT )
		return;
	if( j.Type( node ) != CzmJson::T_OBJECT )
	{
		s_online.limits[kind].active = false;
		return;
	}
	s_online.limits[kind].active = true;
	s_online.limits[kind].until = j.Int( j.Get( node, "until" ));
	s_online.limits[kind].forever = j.Bool( j.Get( node, "forever" ));
	Q_strncpy( s_online.limits[kind].reason, j.String( j.Get( node, "reason" )), sizeof( s_online.limits[kind].reason ));
}

bool CZM_OnlineLimited( int kind, char *text, size_t size )
{
	if( kind < 0 || kind >= CZM_LIMIT_COUNT || !s_online.limits[kind].active )
		return false;
	if( !s_online.limits[kind].forever && s_online.limits[kind].until <= (int)time( NULL ))
	{
		s_online.limits[kind].active = false; // it ran out; the next hello confirms
		return false;
	}
	if( text && size )
	{
		static const char *ru[CZM_LIMIT_COUNT] = { "Чат ограничен модератором", "Голос ограничен модератором", "Фото ограничено модератором" };
		static const char *en[CZM_LIMIT_COUNT] = { "A moderator limited your chat", "A moderator limited your voice", "A moderator limited your photo" };
		char when[48] = "";
		if( s_online.limits[kind].forever )
			Q_strncpy( when, CZM_IsRussian() ? " навсегда" : " for good", sizeof( when ));
		else
		{
			time_t until = s_online.limits[kind].until;
			struct tm date;
			char stamp[24];
			localtime_r( &until, &date );
			strftime( stamp, sizeof( stamp ), "%d.%m %H:%M", &date );
			snprintf( when, sizeof( when ), CZM_IsRussian() ? " до %s" : " until %s", stamp );
		}
		snprintf( text, size, "%s%s%s%s", CZM_IsRussian() ? ru[kind] : en[kind], when,
			s_online.limits[kind].reason[0] ? ". " : "", s_online.limits[kind].reason );
	}
	return true;
}

void CZM_OnlineSetBan( bool banned, int until, bool forever, const char *reason )
{
	s_online.banned = banned;
	s_online.banUntil = until;
	s_online.banForever = forever;
	Q_strncpy( s_online.banReason, reason ? reason : "", sizeof( s_online.banReason ));
}

static void LoadKey( void )
{
	int length = 0;
	byte *data = EngFuncs::COM_LoadFile( KEY_FILE, &length );

	s_online.key[0] = 0;
	if( data )
	{
		int n = 0;

		for( int i = 0; i < length && n < (int)sizeof( s_online.key ) - 1; i++ )
		{
			if(( data[i] >= '0' && data[i] <= '9' ) || ( data[i] >= 'a' && data[i] <= 'f' ))
				s_online.key[n++] = (char)data[i];
		}
		s_online.key[n] = 0;
		EngFuncs::COM_FreeFile( data );
	}

	if( strlen( s_online.key ) < 32 )
	{
		CZM_NetNewKey( s_online.key, sizeof( s_online.key ));
		if( strlen( s_online.key ) >= 32 )
			EngFuncs::COM_SaveFile( KEY_FILE, s_online.key, strlen( s_online.key ));
	}
}

// the avatar as the service knows it: "", "1".."10" or "photo"
static void AvatarForServer( char *out, size_t size )
{
	int current = CZM_CurrentAvatar();

	if( current == CZM_AVATAR_PHOTO )
		Q_strncpy( out, "photo", size );
	else if( current >= 0 )
		snprintf( out, size, "%d", current + 1 );
	else
		out[0] = 0;
}

static void SendHello( void )
{
	CUtlString body;
	char nick[64], avatar[16];
	char code[32];

	CZM_CleanName( EngFuncs::GetCvarString( "name" ), nick, sizeof( nick ));
	AvatarForServer( avatar, sizeof( avatar ));
	snprintf( code, sizeof( code ), "%d", CZM_NetVersionCode( ));

	body.Append( "{\"key\":" ); CZM_JsonQuote( body, s_online.key );
	body.Append( ",\"device\":" ); CZM_JsonQuote( body, CZM_NetDeviceId( ));
	body.Append( ",\"nick\":" ); CZM_JsonQuote( body, nick );
	body.Append( ",\"avatar\":" ); CZM_JsonQuote( body, avatar );
	body.Append( ",\"lang\":" ); CZM_JsonQuote( body, CZM_IsRussian() ? "ru" : "en" );
	body.Append( ",\"version\":" ); CZM_JsonQuote( body, CZM_Version( ));
	body.Append( ",\"code\":" ); body.Append( code );
	if( s_online.preserveAvatar ) body.Append( ",\"keep_avatar\":true" );
	body.Append( ",\"rules\":1" ); // this game shows the community rules before posting
	body.Append( CZM_NetCanSelfUpdate() ? ",\"store\":0" : ",\"store\":1" ); // the site build or Google Play
	body.Append( "}" );

	Q_strncpy( s_online.sentNick, nick, sizeof( s_online.sentNick ));
	Q_strncpy( s_online.sentAvatar, avatar, sizeof( s_online.sentAvatar ));
	s_online.helloId = CZM_NetRequest( "POST", CZM_OnlineUrl( "/api/v1/hello" ), "", body.Get( ));
}

static void ReadBan( const CzmJson &j, int ban )
{
	if( j.Type( ban ) != CzmJson::T_OBJECT )
		CZM_OnlineSetBan( false, 0, false, "" );
	else
		CZM_OnlineSetBan( true, j.Int( j.Get( ban, "until" )), j.Bool( j.Get( ban, "forever" )), j.String( j.Get( ban, "reason" )));
}

void CZM_OnlineReadBan( const CzmJson &j, int ban )
{
	ReadBan( j, ban );
}

// the menu font has no arrows: "Settings → Sound" showed gaps. "›" and "‹" have the same length
static void PlainArrows( char *text )
{
	for( char *p = text; ( p = strstr( p, "\xE2\x86" )) != NULL; )
	{
		if( !p[2] ) break; // a cut sequence at the end
		if( (unsigned char)p[2] == 0x92 ) { p[1] = (char)0x80; p[2] = (char)0xBA; } // → becomes ›
		else if( (unsigned char)p[2] == 0x90 ) { p[1] = (char)0x80; p[2] = (char)0xB9; } // ← becomes ‹
		p += 3;
	}
}

static void OnHello( int status, const char *body )
{
	CzmJson j;
	int update;

	if( status != 200 || !j.Parse( body ))
	{
		if( status == 401 ) { s_online.ready = false; s_online.development = false; }
		s_online.nextHello = EngFuncs::DoubleTime() + ( status == 409 ? 1.0 : RETRY_AFTER );
		return;
	}

	s_online.ready = true;
	s_online.development = j.Bool( j.Get( j.Get( 0, "distribution" ), "development" ));
	s_online.player = j.Int( j.Get( 0, "id" ));
	Q_strncpy( s_online.myAvatar, j.String( j.Get( 0, "avatar" )), sizeof( s_online.myAvatar ));
	ReadBan( j, j.Get( 0, "ban" ));
	Q_strncpy( s_online.role, j.String( j.Get( 0, "role" )), sizeof( s_online.role ));
	const int capabilities = j.Get( 0, "capabilities" );
	s_online.support = j.Type( capabilities ) == CzmJson::T_OBJECT ? j.Bool( j.Get( capabilities, "moderate" )) : !strcmp( s_online.role, "support" );
	s_online.admin = j.Bool( j.Get( capabilities, "admin" ));
	{
		int moderation = j.Get( 0, "moderation" ), warning = j.Get( moderation, "warning" );
		static const char *kinds[CZM_LIMIT_COUNT] = { "text", "voice", "photo" };
		for( int k = 0; k < CZM_LIMIT_COUNT; k++ )
			CZM_OnlineSetLimit( k, j, j.Get( moderation, kinds[k] ));
		// the service already shows the logo instead of the photo: the own screens agree
		if( CZM_OnlineLimited( CZM_LIMIT_PHOTO ) && CZM_CurrentAvatar() == CZM_AVATAR_PHOTO )
			CZM_SetAvatar( CZM_AVATAR_LOGO );
		s_online.warning = j.Type( warning ) == CzmJson::T_OBJECT ? j.Int( j.Get( warning, "id" )) : 0;
		Q_strncpy( s_online.warningReason, s_online.warning ? j.String( j.Get( warning, "reason" )) : "", sizeof( s_online.warningReason ));
	}
	{
		int rules = j.Get( 0, "rules" );
		if( j.Type( rules ) == CzmJson::T_OBJECT )
			CZM_RulesSetState( j.Int( j.Get( rules, "version" )), j.Bool( j.Get( rules, "accepted" )), j.String( j.Get( rules, "url" )));
		else
			CZM_RulesSetState( 0, false, "" );
	}
	// the project's own servers; an older service sends nothing and the cached ones stay
	{
		int official = j.Get( 0, "official" );
		if( j.Type( official ) == CzmJson::T_OBJECT )
			CZM_OfficialSet( j.Bool( j.Get( official, "enabled" )), j.String( j.Get( official, "survival" )), j.String( j.Get( official, "escape" )));
	}
	s_online.newsLast = j.Int( j.Get( 0, "news" ));
	{
		int play = j.Get( 0, "play" );
		memset( s_online.play, 0, sizeof( s_online.play ));
		for( int i = 0; i < j.Count( play ) && i < 3; i++ )
		{
			int item = j.At( play, i );
			s_online.play[i].code = j.Int( j.Get( item, "code" ));
			Q_strncpy( s_online.play[i].version, j.String( j.Get( item, "version" )), sizeof( s_online.play[i].version ));
			Q_strncpy( s_online.play[i].notes, j.String( j.Get( item, "notes" )), sizeof( s_online.play[i].notes ));
			Q_strncpy( s_online.play[i].notes_en, j.String( j.Get( item, "notes_en" )), sizeof( s_online.play[i].notes_en ));
			PlainArrows( s_online.play[i].notes );
			PlainArrows( s_online.play[i].notes_en );
		}
	}
	s_online.nextHello = EngFuncs::DoubleTime() + HELLO_EVERY;
	if( s_online.refreshDistribution ) { s_online.refreshDistribution = false; s_online.nextHello = 0; }

	update = j.Get( 0, "update" );
	if( j.Type( update ) == CzmJson::T_OBJECT && CZM_NetCanSelfUpdate( ))
	{
		CzmUpdateInfo &u = s_online.update;

		u.available = true;
		Q_strncpy( u.version, j.String( j.Get( update, "version" )), sizeof( u.version ));
		u.code = j.Int( j.Get( update, "code" ));
		u.size = j.Number( j.Get( update, "size" ));
		Q_strncpy( u.sha256, j.String( j.Get( update, "sha256" )), sizeof( u.sha256 ));
		Q_strncpy( u.url, j.String( j.Get( update, "url" )), sizeof( u.url ));
		Q_strncpy( u.notes, j.String( j.Get( update, "notes" )), sizeof( u.notes ));
		PlainArrows( u.notes );
		u.patchSize = j.Int( j.Get( update, "patch_format" )) == 1 ? j.Number( j.Get( update, "patch_size" )) : 0;
		Q_strncpy( u.patchUrl, j.String( j.Get( update, "patch_url" )), sizeof( u.patchUrl ));
		Q_strncpy( u.patchSha256, j.String( j.Get( update, "patch_sha256" )), sizeof( u.patchSha256 ));
		Q_strncpy( u.baseSha256, j.String( j.Get( update, "base_sha256" )), sizeof( u.baseSha256 ));
	}
	else if( s_online.update.store )
	{
		// Google Play build: the store answers about updates (CZM_OnlineFrame), not our service
	}
	else
	{
		// up to date: a downloaded update is no longer needed
		if( s_online.update.available || !s_online.update.cleaned )
			CZM_UpdateCleanup();
		memset( &s_online.update, 0, sizeof( s_online.update ));
		s_online.update.cleaned = true;
	}
}

// the player's own photo goes to the service once per new photo
static void SyncPhoto( void )
{
	const char *photo = CZM_AvatarPhoto();

	// a photo is shown to everyone: it waits for the community rules
	if( s_online.preserveAvatar || s_online.uploadId || !photo[0] || CZM_CurrentAvatar() != CZM_AVATAR_PHOTO || !CZM_RulesAccepted( ))
		return;
	if( CZM_OnlineLimited( CZM_LIMIT_PHOTO ))
		return; // a moderator took the photo away for a while
	if( !strcmp( photo, EngFuncs::GetCvarString( "czm_avatar_sent" )))
		return;

	Q_strncpy( s_online.uploading, photo, sizeof( s_online.uploading ));
	s_online.uploadId = CZM_NetUpload( CZM_OnlineUrl( "/api/v1/avatar" ), s_online.key, photo, "image/png" );
}

static void PollAvatars( void )
{
	for( int i = 0; i < s_numAvatars; i++ )
	{
		int status;
		CUtlString body;

		if( s_avatars[i].state != 1 || !CZM_NetPoll( s_avatars[i].request, &status, body ))
			continue;
		s_avatars[i].state = status == 200 ? 2 : 3;
		s_avatars[i].retry = EngFuncs::DoubleTime() + RETRY_AFTER;
	}
}

void CZM_OnlineAvatarChanged( void )
{
	s_online.preserveAvatar = false;
}

// Google Play build: the game does not update itself, Google Play does. Java asks Play every
// 30 minutes; the bell shows the update when Play offers one and opens the game's store page.
static void StoreUpdateFrame( double now )
{
	static int selfUpdate = -1;
	static double next;
	int code;
	double bytes;

	if( selfUpdate < 0 )
		selfUpdate = CZM_NetCanSelfUpdate() ? 1 : 0;
	if( selfUpdate || now < next )
		return;
	next = now + 5.0;
	if( CZM_NetStoreUpdate( &code, &bytes ))
	{
		CzmUpdateInfo &u = s_online.update;

		if( !u.store || u.code != code )
		{
			memset( &u, 0, sizeof( u ));
			u.available = u.store = u.cleaned = true;
			u.code = code;
			u.size = bytes;
		}
		// what is new in it, when the service knows this very release (never another one's notes)
		u.version[0] = u.notes[0] = 0;
		for( int i = 0; i < 3; i++ )
		{
			if( s_online.play[i].code != code || !code )
				continue;
			Q_strncpy( u.version, s_online.play[i].version, sizeof( u.version ));
			// in the menu's language; a release without English notes keeps the Russian ones
			const bool english = !CZM_IsRussian() && s_online.play[i].notes_en[0];
			Q_strncpy( u.notes, english ? s_online.play[i].notes_en : s_online.play[i].notes, sizeof( u.notes ));
		}
	}
	else if( s_online.update.store )
		memset( &s_online.update, 0, sizeof( s_online.update ));
}

// a moderator warning is shown once, in the menu, and the service learns it was seen
static void WarningFrame( void )
{
	int status;
	CUtlString body;

	if( s_online.warningSeenId && CZM_NetPoll( s_online.warningSeenId, &status, body ))
		s_online.warningSeenId = 0;
	if( !s_online.warning || s_online.warning == s_online.warningShown || s_online.warningSeenId || CL_IsActive( ))
		return;
	char text[400], payload[48];
	snprintf( text, sizeof( text ), CZM_IsRussian()
		? "%s\n\nПовторное нарушение может закончиться ограничением чата, голоса или блокировкой. Правила: counter-zombie.ru/rules"
		: "%s\n\nAnother violation may limit your chat or voice or end in a ban. Rules: counter-zombie.ru/rules",
		s_online.warningReason );
	CZM_ShowNotice( CZM_IsRussian() ? "Предупреждение модератора" : "Moderator warning", text );
	s_online.warningShown = s_online.warning;
	snprintf( payload, sizeof( payload ), "{\"id\":%d}", s_online.warning );
	s_online.warningSeenId = CZM_NetRequest( "POST", CZM_OnlineUrl( "/api/v1/moderation/warning/seen" ), s_online.key, payload );
}

// ---------------------------------------------------------------- tickets for our servers
// The API signs a short ticket for one of our addresses (server/czm/czm/game_ticket.py). The game
// puts it in userinfo (_czm) only right before it connects to that very server and takes it out
// a minute later, so the CZM profile reaches our server and no other one.
static struct
{
	char address[64];
	char ticket[96];
	double fresh;    // until when the ticket is worth sending (the server accepts it 15 minutes)
	double nextTry;
	int requestId;
	int requestIdentity;
	int identity;
} s_tickets[CZM_OFFICIAL_COUNT];
static double s_ticketClearAt;

bool CZM_OnSurvivalServer()
{
	CzmServer *server = CZM_ConfiguredServer( CZM_OFFICIAL_SURVIVAL );
	auto *api = EngFuncs::textfuncs.pNetAPI;
	if( !CL_IsActive() || !server || !server->address[0] || !api || !api->Status || !api->StringToAdr || !api->CompareAdr )
		return false;
	net_status_t status = {};
	api->Status( &status );
	netadr_t address = {};
	return status.connected && api->StringToAdr( server->address, &address ) && api->CompareAdr( &status.remote_address, &address );
}

static void SurvivalProfileFrame( double now )
{
	static int request, requestIdentity, sentPlayer;
	static double nextTry;
	static char requested[33], requestedAddress[64], submitted[33];
	const bool connected = CZM_OnSurvivalServer();
	const char *challenge = EngFuncs::GetCvarString( "czm_profile_challenge" );
	if( !connected )
	{
		sentPlayer = 0;
		submitted[0] = 0;
		nextTry = 0;
	}
	else if( sentPlayer && ( !s_online.account || s_online.player != sentPlayer ))
	{
		// The server pins a verified profile to this connection. A new account needs a new session.
		sentPlayer = 0;
		EngFuncs::ClientCmd( true, "disconnect\n" );
		return;
	}
	if( request )
	{
		int status;
		CUtlString body;
		if( !CZM_NetPoll( request, &status, body )) return;
		request = 0;
		if( !connected || !challenge || strcmp( challenge, requested ) || requestIdentity != s_online.identity
			|| strcmp( CZM_ConfiguredServer( CZM_OFFICIAL_SURVIVAL )->address, requestedAddress ))
			return;
		CzmJson json;
		const char *proof = status == 200 && json.Parse( body.Get() ) ? json.String( json.Get( 0, "ticket" )) : "";
		if( !proof[0] || strlen( proof ) >= 64 || proof[strspn( proof, "0123456789abcdef." )] || atoi( proof ) != s_online.player
			|| strcmp( json.String( json.Get( 0, "address" )), requestedAddress ))
			return;
		Q_strncpy( submitted, challenge, sizeof( submitted ));
		sentPlayer = s_online.player;
		EngFuncs::ClientCmdF( true, "czm_profile_ticket %s\n", proof );
		return;
	}
	if( !connected || !s_online.account || s_online.player <= 0 || now < nextTry || !challenge || strlen( challenge ) != 32
		|| strspn( challenge, "0123456789abcdef" ) != 32 || !strcmp( submitted, challenge ))
		return;
	Q_strncpy( requested, challenge, sizeof( requested ));
	Q_strncpy( requestedAddress, CZM_ConfiguredServer( CZM_OFFICIAL_SURVIVAL )->address, sizeof( requestedAddress ));
	char payload[144];
	snprintf( payload, sizeof( payload ), "{\"address\":\"%s\",\"challenge\":\"%s\"}", requestedAddress, requested );
	requestIdentity = s_online.identity;
	nextTry = now + 5.0;
	request = CZM_NetRequest( "POST", CZM_OnlineUrl( "/api/v1/game/ticket" ), s_online.key, payload );
}

static void TicketFrame( double now )
{
	int status;
	CUtlString body;

	if( s_ticketClearAt > 0.0 && now >= s_ticketClearAt )
	{
		EngFuncs::ClientCmd( false, "setinfo _czm \"\"\n" );
		s_ticketClearAt = 0.0;
	}
	for( int i = 0; i < CZM_OFFICIAL_COUNT; i++ )
	{
		auto &t = s_tickets[i];
		CzmServer *server = CZM_ConfiguredServer( i );
		const char *address = server ? server->address : "";

		if( strcmp( t.address, address ) || t.identity != s_online.identity )
		{
			// another address or another profile: the old ticket is no use
			Q_strncpy( t.address, address, sizeof( t.address ));
			t.ticket[0] = 0;
			t.fresh = 0.0;
			t.nextTry = now;
			t.identity = s_online.identity;
		}
		if( t.requestId )
		{
			if( !CZM_NetPoll( t.requestId, &status, body ))
				continue;
			t.requestId = 0;
			CzmJson j;
			const char *ticket = status == 200 && j.Parse( body.Get( )) ? j.String( j.Get( 0, "ticket" )) : "";
			if( ticket[0] && strlen( ticket ) < sizeof( t.ticket ) && t.requestIdentity == s_online.identity
				&& !strcmp( j.String( j.Get( 0, "address" )), t.address ))
			{
				Q_strncpy( t.ticket, ticket, sizeof( t.ticket ));
				t.fresh = now + 600.0;
			}
			else t.nextTry = now + 60.0;
			continue;
		}
		// asked for in the menus only; a game in progress does not need a new one
		if( !t.address[0] || !s_online.ready || CL_IsActive( ) || now < t.nextTry || ( t.ticket[0] && now < t.fresh ))
			continue;
		char payload[96];
		snprintf( payload, sizeof( payload ), "{\"address\":\"%s\"}", t.address );
		t.requestIdentity = s_online.identity;
		t.nextTry = now + 30.0;
		t.requestId = CZM_NetRequest( "POST", CZM_OnlineUrl( "/api/v1/game/ticket" ), s_online.key, payload );
	}
}

void CZM_PrepareConnect( const char *address )
{
	double now = EngFuncs::DoubleTime();
	const char *ticket = "";

	for( int i = 0; address && address[0] && i < CZM_OFFICIAL_COUNT; i++ )
	{
		// a ticket older than 14 minutes might expire on the way
		if( s_tickets[i].ticket[0] && now < s_tickets[i].fresh + 240.0 && !strcmp( s_tickets[i].address, address ))
			ticket = s_tickets[i].ticket;
	}
	EngFuncs::ClientCmdF( false, "setinfo _czm \"%s\"\n", ticket );
	s_ticketClearAt = ticket[0] ? now + 60.0 : 0.0;
}

// A new click replaces the previous pending join. No network or hashing runs on
// the game thread; Android publishes a snapshot only after checking the current
// endpoint against the trusted catalog. Keep the selected password/name with it.
static struct
{
	char address[64], protocol[8], name[128], password[128];
	CMenuBaseWindow *origin;
	bool active, shown;
} s_resourceJoin;

void CZM_CancelResourceJoin( void )
{
	if( !s_resourceJoin.active ) return;
	s_resourceJoin.active = false;
	CZM_ServerResourcesCancelConnection();
}

void CZM_ConnectWithResources( const char *address, const char *protocol )
{
	if( !address || !address[0] || strlen( address ) >= sizeof( s_resourceJoin.address )
		|| strspn( address, "0123456789abcdefABCDEF.[]:" ) != strlen( address )
		|| !protocol || ( strcmp( protocol, "gs" ) && strcmp( protocol, "49" )))
		return;
	Q_strncpy( s_resourceJoin.address, address, sizeof( s_resourceJoin.address ));
	Q_strncpy( s_resourceJoin.protocol, protocol, sizeof( s_resourceJoin.protocol ));
	Q_strncpy( s_resourceJoin.name, EngFuncs::GetCvarString( "czm_connect_name" ), sizeof( s_resourceJoin.name ));
	Q_strncpy( s_resourceJoin.password, EngFuncs::GetCvarString( "password" ), sizeof( s_resourceJoin.password ));
	s_resourceJoin.active = true;
	s_resourceJoin.shown = false;
	s_resourceJoin.origin = uiStatic.menu.Current();
	CZM_ServerResourcesRefresh( address );
}

static void ResourceJoinFrame( void )
{
	if( !s_resourceJoin.active ) return;
	if( s_resourceJoin.origin != uiStatic.menu.Current() )
	{
		s_resourceJoin.active = false;
		CZM_ServerResourcesCancelConnection();
		return;
	}
	const int state = CZM_ServerResourcesPrepare( s_resourceJoin.address );
	if( state == 2 ) return; // checking or transferring
	if( state == 3 )
	{
		if( !s_resourceJoin.shown )
		{
			s_resourceJoin.shown = true;
			CZM_ServerResourcesShow( s_resourceJoin.address, CZM_IsRussian() );
		}
		return;
	}
	s_resourceJoin.active = false;
	if( state < 0 )
	{
		CZM_ServerResourcesCancelConnection();
		if( state != -2 ) CZM_ShowNotice( CZM_IsRussian() ? "Ресурсы сервера" : "Server resources",
			CZM_IsRussian() ? "Не удалось проверить ресурсы. Открой карточку сервера и попробуй ещё раз."
			: "Could not check server resources. Open the server card and try again." );
		return;
	}
	if( state != 0 && state != 1 ) { CZM_ServerResourcesCancelConnection(); return; }
	if( !CZM_OnlinePlayAllowed() || CZM_ServerBlocked( s_resourceJoin.address ))
	{
		CZM_ServerResourcesCancelConnection();
		return;
	}
	EngFuncs::CvarSetString( "czm_connect_name", s_resourceJoin.name );
	EngFuncs::CvarSetString( "czm_connect_adr", s_resourceJoin.address );
	EngFuncs::CvarSetString( "password", s_resourceJoin.password );
	CZM_PrepareConnect( s_resourceJoin.address );
	EngFuncs::ClientCmdF( false, "connect \"%s\" %s\n", s_resourceJoin.address, s_resourceJoin.protocol );
}

// ---------------------------------------------------------------- the player panel, signed in
// czm_panel (the "Player panel" item of our servers' menu, or the console): the API gives a one-time
// link that signs this account in on counter-zombie.ru/panel, and the phone's browser opens it.
static int s_panelRequest;
static double s_panelNext;

int CZM_OfficialSlotNow( void )
{
	const char *address = EngFuncs::GetCvarString( "czm_connect_adr" );
	for( int i = 0; address && address[0] && i < CZM_OFFICIAL_COUNT; i++ )
	{
		CzmServer *server = CZM_ConfiguredServer( i );
		if( server && server->address[0] && !strcmp( server->address, address ))
			return i;
	}
	return -1;
}

static bool CZM_OnOfficialServer( void )
{
	return CZM_OfficialSlotNow() >= 0;
}

bool CZM_PlayServer( void )
{
	return CL_IsActive() && EngFuncs::GetCvarFloat( "czm_play_mode" ) == 1.0f;
}

static void CZM_PanelOpen_f( void )
{
	double now = EngFuncs::DoubleTime();

	// in a game only our servers may ask for it: no other server opens the browser
	if( CL_IsActive( ) && !CZM_OnOfficialServer( ))
		return;
	if( s_panelRequest || now < s_panelNext || !s_online.key[0] )
		return;
	if( !CZM_OnlineAccount( ))
	{
		CZM_ShowNotice( CZM_IsRussian() ? "Панель игрока" : "Player panel", CZM_IsRussian()
			? "Панель на сайте открывается для аккаунта CZM. Создай его: Профиль → Аккаунт."
			: "The site panel opens for a CZM account. Create one: Profile → Account." );
		return;
	}
	s_panelNext = now + 3.0;
	s_panelRequest = CZM_NetRequest( "POST", CZM_OnlineUrl( "/api/v1/auth/web-link" ), s_online.key, "{}" );
}
ADD_COMMAND( czm_panel, CZM_PanelOpen_f );

static void PanelFrame( void )
{
	int status;
	CUtlString body;
	static const char prefix[] = "https://counter-zombie.ru/panel#login=";

	if( !s_panelRequest || !CZM_NetPoll( s_panelRequest, &status, body ))
		return;
	s_panelRequest = 0;
	CzmJson j;
	const char *url = status == 200 && j.Parse( body.Get( )) ? j.String( j.Get( 0, "url" )) : "";
	if( !strncmp( url, prefix, sizeof( prefix ) - 1 ) && strlen( url ) < 256 )
	{
		EngFuncs::ShellExecute( url, NULL, false );
		return;
	}
	CZM_ShowNotice( CZM_IsRussian() ? "Панель игрока" : "Player panel", CZM_IsRussian()
		? "Панель не открылась. Проверь интернет и попробуй ещё раз."
		: "The panel did not open. Check the connection and try again." );
}

void CZM_OnlineFrame( void )
{
	CZM_TranslationFrame();
	CZM_SprayFrame();
	CZM_RulesFrame();
	CZM_ModerationFrame();
	WarningFrame();
	double now = EngFuncs::DoubleTime();
	int status;
	CUtlString body;
	static double nextPolicy;
	if( now >= nextPolicy ) { CZM_ServerPolicyRevision(); CZM_ServerBlocksFrame(); nextPolicy = now + 1.0; }

	if( !s_online.started )
	{
		if( !CZM_NetAvailable( ))
			return;
		s_online.started = true;
		LoadKey();
		CZM_AccountContext( s_online.key, EngFuncs::GetCvarString( "name" ));
		s_online.nextHello = now;
	}

	if( !s_online.key[0] )
		return;
	TicketFrame( now );
	PanelFrame();
	StoreUpdateFrame( now );
	if( CZM_DistributionChanged() )
	{
		s_online.development = false;
		s_online.nextHello = now;
		if( s_online.helloId ) s_online.refreshDistribution = true;
	}
	// Account changes arrive from Java without a password or session token in the engine.
	if( CZM_AccountEvent( body ))
	{
		s_resourceJoin.active = false;
		CZM_ServerResourcesCancelConnection();
		CzmJson j;
		if( j.Parse( body.Get() ))
		{
			s_online.identity++;
			s_online.account=false;
			s_online.development=false;
			CZM_TabReset();
			s_online.ready = false;
			s_online.player = 0;
			s_online.nextHello = now;
			s_online.preserveAvatar = false;
			int profile = j.Get( 0, "profile" );
			if( j.Bool( j.Get( 0, "guest" )))
			{
				CZM_NetNewKey( s_online.key, sizeof( s_online.key ));
				EngFuncs::COM_SaveFile( KEY_FILE, s_online.key, strlen( s_online.key ));
				EngFuncs::CvarSetString( "czm_avatar_photo", "" );
				CZM_SetAvatar( CZM_AVATAR_LOGO );
			}
			else if( j.Type( profile ) == CzmJson::T_OBJECT )
			{
				s_online.account=j.String(j.Get(profile,"login"))[0]!=0;
				// signed in from the first window: the nickname comes from the account
				if( s_online.account && CZM_FirstStart( ))
					CZM_FinishFirstStart();
				const char *avatar = j.String( j.Get( profile, "avatar" ));
				s_online.player = j.Int( j.Get( profile, "id" ));
				CZM_SetNick( j.String( j.Get( profile, "nick" )));
				EngFuncs::CvarSetString( "czm_avatar_photo", "" );
				if( !strncmp( avatar, "photo:", 6 ))
				{
					char path[128];
					s_online.preserveAvatar = true;
					EngFuncs::CvarSetString( "czm_avatar", "" );
					snprintf( s_online.profilePhotoPath, sizeof( s_online.profilePhotoPath ), "czm_cache/account_%d_%d.png", s_online.player, atoi( avatar + 6 ));
					snprintf( path, sizeof( path ), "/avatars/%d.png?v=%d", s_online.player, atoi( avatar + 6 ));
					s_online.profilePhoto = CZM_NetDownload( CZM_OnlineUrl( path ), s_online.profilePhotoPath );
				}
				else CZM_SetAvatar( atoi( avatar ) - 1 );
			}
		}
	}
	SurvivalProfileFrame( now );
	if( s_online.preserveAvatar && !s_online.profilePhoto && now >= s_online.photoRetry )
	{
		char path[128];
		snprintf( path, sizeof( path ), "/avatars/%d.png", s_online.player );
		s_online.profilePhoto = CZM_NetDownload( CZM_OnlineUrl( path ), s_online.profilePhotoPath );
	}
	if( s_online.profilePhoto && CZM_NetPoll( s_online.profilePhoto, &status, body ))
	{
		s_online.profilePhoto = 0;
		if( status == 200 && s_online.preserveAvatar )
		{
			EngFuncs::CvarSetString( "czm_avatar_photo", s_online.profilePhotoPath );
			EngFuncs::CvarSetString( "czm_avatar_sent", s_online.profilePhotoPath );
			CZM_SetAvatar( CZM_AVATAR_PHOTO );
			s_online.preserveAvatar = false;
		}
		else
		{
			// Keep the remote photo on failures without blocking chat, updates or gameplay.
			s_online.photoRetry = now + RETRY_AFTER;
		}
	}
    { CUtlString request;if(CZM_WidgetEvent(request)) {
        char address[64],protocol[8],tail;
        if(CZM_OnlinePlayAllowed() && sscanf(request.Get(),"%63s %7s %c",address,protocol,&tail)==2 && strspn(address,"0123456789.:")==strlen(address) && (!strcmp(protocol,"gs")||!strcmp(protocol,"49"))) {
            EngFuncs::CvarSetString("czm_connect_adr",address);EngFuncs::CvarSetString("czm_connect_name",address);CZM_ConnectWithResources( address, protocol );
        }
    }}
	CZM_CloudFrame();
	CZM_MapPicturesFrame();

	// how many players are in the game right now, for the chat button
	if( s_online.onlineId )
	{
		if( CZM_NetPoll( s_online.onlineId, &status, body ))
		{
			CzmJson j;

			s_online.onlineId = 0;
			if( status == 200 && j.Parse( body.Get( )))
				s_online.onlineCount = j.Int( j.Get( 0, "online" ));
		}
	}
	else if( now >= s_online.nextOnline )
	{
		s_online.nextOnline = now + 60.0;
		s_online.onlineId = CZM_NetRequest( "GET", CZM_OnlineUrl( "/api/v1/online" ), "", "" );
	}

	if( s_online.helloId )
	{
		if( CZM_NetPoll( s_online.helloId, &status, body ))
		{
			s_online.helloId = 0;
			OnHello( status, body.Get( ));
		}
	}
	else
	{
		char nick[64], avatar[16];
		static double lastCheck;

		// the nick or the avatar changed: introduce again (checked twice a second)
		if( s_online.ready && now - lastCheck > 0.5 )
		{
			lastCheck = now;
			CZM_CleanName( EngFuncs::GetCvarString( "name" ), nick, sizeof( nick ));
			AvatarForServer( avatar, sizeof( avatar ));
			if( strcmp( nick, s_online.sentNick ) || strcmp( avatar, s_online.sentAvatar ))
				s_online.nextHello = Q_min( s_online.nextHello, now + 2.0 );
		}

		if( now >= s_online.nextHello && !s_online.uploadId )
			SendHello();
	}

	if( s_online.ready )
		SyncPhoto();

	if( s_online.uploadId && CZM_NetPoll( s_online.uploadId, &status, body ))
	{
		s_online.uploadId = 0;
		if( status == 200 )
		{
			EngFuncs::CvarSetString( "czm_avatar_sent", s_online.uploading );
			s_online.nextHello = now; // the service now has the photo
		}
		else if( status == 403 )
		{
			CzmJson j;
			bool parsed = j.Parse( body.Get( ));
			if( parsed && !strcmp( j.String( j.Get( 0, "error" )), "rules" ))
				CZM_RulesSetState( Q_max( 1, j.Int( j.Get( 0, "version" ))), false, "" ); // uploads again once accepted
			else if( parsed && !strcmp( j.String( j.Get( 0, "error" )), "photo_restricted" ))
			{
				char why[300];
				CZM_OnlineSetLimit( CZM_LIMIT_PHOTO, j, j.Get( 0, "restriction" ));
				CZM_SetAvatar( CZM_AVATAR_LOGO ); // others see the logo too: the service reset the photo
				if( CZM_OnlineLimited( CZM_LIMIT_PHOTO, why, sizeof( why )))
					CZM_ShowNotice( CZM_IsRussian() ? "Фото недоступно" : "Photo unavailable", why );
			}
			else
			{
				if( parsed )
					ReadBan( j, j.Get( 0, "ban" ));
				EngFuncs::CvarSetString( "czm_avatar_sent", s_online.uploading ); // no retries while banned
			}
		}
	}

	if( s_online.newsId && CZM_NetPoll( s_online.newsId, &status, body ))
	{
		CzmJson j;

		s_online.newsId = 0;
		if( status == 200 && j.Parse( body.Get( )))
		{
			int list = j.Get( 0, "news" );

			s_online.news.RemoveAll();
			for( int i = 0; i < j.Count( list ); i++ )
			{
				int item = j.At( list, i );
				CzmNews n;

				n.id = j.Int( j.Get( item, "id" ));
				n.time = j.Int( j.Get( item, "ts" ));
				Q_strncpy( n.text, j.String( j.Get( item, "text" )), sizeof( n.text ));
				PlainArrows( n.text );
				s_online.news.AddToTail( n );
				s_online.newsLast = Q_max( s_online.newsLast, n.id );
			}
			s_online.newsLoaded = true;
		}
	}

	PollAvatars();
	CZM_TabFrame();
	CZM_SocialFrame();
	CZM_LobbyFrame();
	ResourceJoinFrame();
}

/*
=================
news
=================
*/
int CZM_NewsUnread( void )
{
	int seen = (int)EngFuncs::GetCvarFloat( "czm_news_seen" );

	if( !s_online.ready || s_online.newsLast <= seen )
		return 0;
	// how many exactly is known once the list is loaded
	if( s_online.newsLoaded )
	{
		int count = 0;
		for( int i = 0; i < s_online.news.Count(); i++ )
			count += s_online.news[i].id > seen;
		return Q_max( count, 1 );
	}
	return 1;
}

void CZM_NewsOpen( void )
{
	if( !s_online.ready || s_online.newsId )
		return;
	// the bell in the menu's language: the service sends the English text when an item has one
	s_online.newsId = CZM_NetRequest( "GET", CZM_OnlineUrl( CZM_IsRussian() ? "/api/v1/news?lang=ru" : "/api/v1/news?lang=en" ), "", "" );
}

void CZM_NewsMarkRead( void )
{
	if( s_online.newsLast > (int)EngFuncs::GetCvarFloat( "czm_news_seen" ))
		EngFuncs::CvarSetValue( "czm_news_seen", s_online.newsLast );
}

bool CZM_NewsLoading( void )
{
	return s_online.newsId != 0;
}

int CZM_NewsCount( void )
{
	return s_online.news.Count();
}

const CzmNews *CZM_NewsItem( int index )
{
	return index >= 0 && index < s_online.news.Count() ? &s_online.news[index] : NULL;
}

/*
=================
update
=================
*/
const CzmUpdateInfo *CZM_Update( void )
{
	return s_online.update.available ? &s_online.update : NULL;
}

/*
=================
avatars of other players
=================
*/
const char *CZM_AvatarFor( const char *ref, int player )
{
	int rev;

	if( !ref || !ref[0] )
		return CZM_AvatarImage( CZM_AVATAR_LOGO );

	if( strncmp( ref, "photo:", 6 ))
	{
		int index = atoi( ref ) - 1;
		return CZM_AvatarImage( index >= 0 && index < CZM_AvatarCount() ? index : CZM_AVATAR_LOGO );
	}

	rev = atoi( ref + 6 );
	for( int i = 0; i < s_numAvatars; i++ )
	{
		if( s_avatars[i].player == player && s_avatars[i].rev == rev )
		{
			if( s_avatars[i].state == 3 && EngFuncs::DoubleTime() >= s_avatars[i].retry )
			{
				char url[160]; snprintf( url, sizeof( url ), "/avatars/%d.png?v=%d", player, rev );
				s_avatars[i].request = CZM_NetDownload( CZM_OnlineUrl( url ), s_avatars[i].path );
				s_avatars[i].state = s_avatars[i].request ? 1 : 3;
				s_avatars[i].retry = EngFuncs::DoubleTime() + RETRY_AFTER;
			}
			return s_avatars[i].state == 2 ? s_avatars[i].path : CZM_AvatarImage( CZM_AVATAR_LOGO );
		}
	}

	// a new photo: download it once
	{
		int slot = s_numAvatars < MAX_AVATARS ? s_numAvatars++ : player % MAX_AVATARS;
		char url[160];

		s_avatars[slot].player = player;
		s_avatars[slot].rev = rev;
		snprintf( s_avatars[slot].path, sizeof( s_avatars[slot].path ), "czm_cache/av_%d_%d.png", player, rev );

		if( EngFuncs::FileExists( s_avatars[slot].path, true ))
		{
			s_avatars[slot].state = 2;
			return s_avatars[slot].path;
		}

		snprintf( url, sizeof( url ), "/avatars/%d.png?v=%d", player, rev );
		s_avatars[slot].request = CZM_NetDownload( CZM_OnlineUrl( url ), s_avatars[slot].path );
		s_avatars[slot].state = s_avatars[slot].request ? 1 : 3;
		s_avatars[slot].retry = EngFuncs::DoubleTime() + RETRY_AFTER;
	}

	return CZM_AvatarImage( CZM_AVATAR_LOGO );
}
