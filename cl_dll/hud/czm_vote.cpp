/* The next-map vote of our servers: CzmVote messages become the czm_vote cvar for the window. */
#include "hud.h"
#include "cl_util.h"
#include "parsemsg.h"
#include "czm_vote.h"
#include "../../common/czm_vote.h"
#include <cstring>

static CzmVote::Ballot s_shown;    // what the window has
static CzmVote::Ballot s_incoming; // a state whose rows are still arriving
static int s_received, s_serial, s_opens;
static bool s_filling;

static void Publish()
{
	char text[CzmVote::MAX_ROWS * 48 + 128];
	s_shown.serial = ++s_serial;
	CzmVote::Format( s_shown, text, sizeof( text ));
	gEngfuncs.Cvar_Set( "czm_vote", text );
}

static int MsgFunc_CzmVote( const char *name, int size, void *buffer )
{
	if( size < 1 ) return 1;
	const unsigned char *data = static_cast<const unsigned char *>( buffer );
	BufferReader reader( name, buffer, size );
	const int type = reader.ReadByte();
	if( type == 1 && size == 11 )
	{
		CzmVote::Ballot b;
		b.flags = reader.ReadByte(); b.count = reader.ReadByte(); b.own = reader.ReadByte() - 1;
		b.seconds = reader.ReadByte(); b.voters = reader.ReadByte(); b.players = reader.ReadByte();
		b.session = reader.ReadLong();
		if( b.count < 1 || b.count > CzmVote::MAX_ROWS ) { s_filling = false; return 1; }
		// "Open it now" is an event: a counter, so a state sent again later never reopens a closed window.
		if( b.flags & CzmVote::OPEN ) s_opens++;
		b.opens = s_opens;
		s_incoming = b;
		s_received = 0;
		s_filling = true;
	}
	else if( type == 2 && s_filling )
	{
		// rows: number, votes, map name
		for( int at = 1; at + 4 <= size && s_received < s_incoming.count; )
		{
			CzmVote::Row &row = s_incoming.rows[s_received];
			row.number = data[at]; row.votes = data[at + 1]; at += 2;
			const int start = at;
			while( at < size && data[at] ) at++;
			if( at >= size ) { s_filling = false; return 1; }
			char raw[64];
			const int length = at - start;
			if( length <= 0 || length >= (int)sizeof( raw )) { s_filling = false; return 1; }
			memcpy( raw, data + start, length ); raw[length] = 0;
			at++;
			if( !CzmVote::MapName( raw, row.map, sizeof( row.map ))) { s_filling = false; return 1; }
			s_received++;
		}
		if( s_received == s_incoming.count )
		{
			s_shown = s_incoming;
			s_filling = false;
			Publish();
		}
	}
	else if( type == 4 && size == 8 && s_shown.count )
	{
		const int seconds = reader.ReadByte(), voters = reader.ReadByte(), players = reader.ReadByte();
		if( reader.ReadLong() != s_shown.session ) return 1;
		s_shown.seconds = seconds; s_shown.voters = voters; s_shown.players = players;
		Publish();
	}
	else if( type == 3 && size == 5 )
	{
		const int session = reader.ReadLong();
		if( s_shown.count && session == s_shown.session ) CZM_VoteReset();
	}
	return 1;
}

void CZM_VoteInit( void )
{
	gEngfuncs.pfnHookUserMsg( "CzmVote", MsgFunc_CzmVote );
	CZM_VoteReset();
}

// A new connection or map: no vote until the server sends one.
void CZM_VoteReset( void )
{
	s_shown = CzmVote::Ballot();
	s_incoming = CzmVote::Ballot();
	s_received = 0;
	s_filling = false;
	if( gEngfuncs.pfnGetCvarString( "czm_vote" ) && gEngfuncs.pfnGetCvarString( "czm_vote" )[0] )
		gEngfuncs.Cvar_Set( "czm_vote", "" );
}
