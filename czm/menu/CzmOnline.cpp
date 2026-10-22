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

#include "extdll_menu.h"
#include "BaseMenu.h"
#include "Utils.h"
#include "CzmMenu.h"
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

	int newsLast;         // the newest news number on the server
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
	return !CZM_NetCanSelfUpdate() || s_online.development;
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
	s_online.newsLast = j.Int( j.Get( 0, "news" ));
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

	if( s_online.preserveAvatar || s_online.uploadId || !photo[0] || CZM_CurrentAvatar() != CZM_AVATAR_PHOTO )
		return;
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
// 30 minutes; the bell shows the update when Play offers one and opens Play's update screen.
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
	}
	else if( s_online.update.store )
		memset( &s_online.update, 0, sizeof( s_online.update ));
}

void CZM_OnlineFrame( void )
{
	CZM_SprayFrame();
	double now = EngFuncs::DoubleTime();
	int status;
	CUtlString body;

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
            EngFuncs::CvarSetString("czm_connect_adr",address);EngFuncs::CvarSetString("czm_connect_name",address);EngFuncs::ClientCmdF(false,"connect \"%s\" %s\n",address,protocol);
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
			if( j.Parse( body.Get( )))
				ReadBan( j, j.Get( 0, "ban" ));
			EngFuncs::CvarSetString( "czm_avatar_sent", s_online.uploading ); // no retries while banned
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
	s_online.newsId = CZM_NetRequest( "GET", CZM_OnlineUrl( "/api/v1/news" ), "", "" );
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
