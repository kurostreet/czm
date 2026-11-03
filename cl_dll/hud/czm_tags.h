/* Counter Zombie Mobile: the LVL MOD tags of our servers. GPL-2.0-or-later. */
#pragma once

// what a player wears for everyone to see: sent by czm_lvl.amxx in the CzmTag message
struct CzmTag
{
	int lvl;              // 0: a guest, no LVL MOD
	int wr;               // wins, %
	char prefix[32];      // bought in the LVL MOD shop, in its owner's language
	int r, g, b;          // the prefix colour
	char priv[16];        // VIP+, PREMIUM, DELUXE, TESTER
};

void CZM_TagsInit( void );
void CZM_TagsReset( void );
const CzmTag *CZM_TagFor( int index );          // NULL when the server sent none
void CZM_LevelColor( int lvl, int *r, int *g, int *b );
// the player in the crosshair and the toasts, once a frame after the HUD
void CZM_TagsDraw( float flTime );
bool CZM_AimTagShown( void );                   // the stock status line steps aside
