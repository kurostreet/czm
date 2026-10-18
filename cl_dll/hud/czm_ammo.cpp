/* The clip and the reserve for the reload button, given to the engine. GPL-2.0-or-later.
   The engine draws them on every "+reload" touch button (patch czm-reload-ammo). */
#include "hud.h"
#include "cl_util.h"
#include "czm_hud.h"
#include <cstdio>
#include <cstring>

// full clips of the standard weapons by weapon id; a server may give bigger clips, the biggest seen wins
static const int s_fullClip[32] = { 0, 13, 0, 10, 0, 7, 0, 30, 30, 0, 30, 20, 25, 30, 35, 25,
	12, 20, 10, 30, 100, 8, 30, 30, 20, 0, 7, 30, 30, 0, 50, 0 };
static int s_seen[32];
static bool s_reported;
static char s_state[48];

static void Publish( const char *state )
{
	if( !strcmp( state, s_state ))
		return;
	snprintf( s_state, sizeof( s_state ), "%s", state );
	gEngfuncs.Cvar_Set( "czm_ammo_state", s_state );
}

void CZM_AmmoReset()
{
	memset( s_seen, 0, sizeof( s_seen ));
}

void CZM_AmmoFrameBegin()
{
	s_reported = false;
}

void CZM_AmmoReport( int weapon, int clip, int reserve )
{
	char state[48];
	int full = 0;

	if( clip < 0 || gHUD.m_fPlayerDead )
		return;
	if( weapon >= 0 && weapon < 32 )
	{
		if( clip > s_seen[weapon] )
			s_seen[weapon] = clip;
		full = s_fullClip[weapon] > s_seen[weapon] ? s_fullClip[weapon] : s_seen[weapon];
	}
	if( full <= 0 )
		full = clip > 0 ? clip : 1;

	snprintf( state, sizeof( state ), "%d %d %d", clip, reserve < 0 ? 0 : reserve, full );
	Publish( state );
	s_reported = true;
}

// nothing reported this frame (knife, grenade, dead, spectator, HUD hidden): the button shows nothing
void CZM_AmmoFrameEnd()
{
	if( !s_reported )
		Publish( "" );
}
