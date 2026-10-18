/***
*
*	Copyright (c) 1996-2002, Valve LLC. All rights reserved.
*	
*	This product contains software technology licensed from Id 
*	Software, Inc. ("Id Technology").  Id Technology (c) 1996 Id Software, Inc. 
*	All Rights Reserved.
*
*   Use, distribution, and modification of this source code and/or resulting
*   object code is restricted to non-commercial enhancements to products from
*   Valve LLC.  All other use, distribution, or modification is prohibited
*   without written permission from Valve LLC.
*
****/
//
// hud_redraw.cpp
//
#include <math.h>
#include <stdlib.h>
#include "hud.h"
#include "hud/czm_hud.h"
#include "cl_util.h"
#include "triangleapi.h"

#include <string.h>

#include "draw_util.h"
#include "strl.h"

#define MAX_LOGO_FRAMES 56

int grgLogoFrame[MAX_LOGO_FRAMES] = 
{
	1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 13, 13, 13, 13, 13, 12, 11, 10, 9, 8, 14, 15,
	16, 17, 18, 19, 20, 20, 20, 20, 20, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 
	29, 29, 29, 29, 29, 28, 27, 26, 25, 24, 30, 31 
};


extern int g_iVisibleMouse;

float HUD_GetFOV( void );

// Think
void CHud::Think(void)
{
	int newfov;

	extern int g_weaponselect_frames;
	if( g_weaponselect_frames )
		g_weaponselect_frames--;

	for( HUDLIST *pList = m_pHudList; pList; pList = pList->pNext )
	{
		if( pList->p->m_iFlags & HUD_THINK )
			pList->p->Think();
	}

	newfov = HUD_GetFOV();
	m_iFOV = newfov ? newfov : default_fov->value;

	// the clients fov is actually set in the client data update section of the hud

	// Set a new sensitivity
	if ( m_iFOV == default_fov->value )
	{  
		// reset to saved sensitivity
		m_flMouseSensitivity = 0;
	}
	else
	{  
		// set a new sensitivity that is proportional to the change from the FOV default
		m_flMouseSensitivity = sensitivity->value * ((float)newfov / (float)default_fov->value) * zoom_sens_ratio->value;
	}

	// think about default fov
	if ( m_iFOV == 0 )
	{  // only let players adjust up in fov,  and only if they are not overriden by something else
		m_iFOV = max( default_fov->value, 90 );
	}

}

// Redraw
// step through the local data,  placing the appropriate graphics & text as appropriate
// returns 1 if they've changed, 0 otherwise
bool IN_AutoRunActive( void ); // input_xash3d.cpp
bool CL_IsDead( void );

// Counter Zombie Mobile: the shop in the menu library shows money, owned weapons and armor
static void CZM_UpdateShopState( void )
{
	static char last[96];
	char state[96];

	snprintf( state, sizeof( state ), "%d %d %u %d %d %d", gHUD.m_Money.GetMoney(), g_iTeamNumber,
		(unsigned int)gHUD.m_iWeaponBits, gHUD.m_Battery.GetArmor(), gHUD.m_Battery.HasHelmet() ? 1 : 0, CL_IsDead() ? 0 : 1 );

	if( strcmp( state, last ))
	{
		strlcpy( last, state, sizeof( last ));
		gEngfuncs.Cvar_Set( "czm_buy_state", state );
	}
}

// Counter Zombie Mobile: label in the middle of the screen while auto run is on
static void CZM_DrawAutoRunLabel( float flTime )
{
	const char *lang = gEngfuncs.pfnGetCvarString( "czm_lang" );
	const char *locale = getenv( "CZM_LOCALE" );
	float pulse = 0.7f + 0.3f * sinf( flTime * 5.0f );
	const char *text;
	bool russian;
	int width = 0, height = 0;

	// the language chosen in the menu, else the phone language
	if( lang && lang[0] )
		russian = !strcmp( lang, "ru" );
	else
		russian = !locale || !locale[0] || !strncmp( locale, "ru", 2 ) || !strncmp( locale, "uk", 2 )
			|| !strncmp( locale, "be", 2 ) || !strncmp( locale, "kk", 2 );

	text = russian ? "\xD0\x90\xD0\x92\xD0\xA2\xD0\x9E\xD0\x91\xD0\x95\xD0\x93" : "AUTO RUN"; // АВТОБЕГ in UTF-8
	DrawUtils::ConsoleStringSize( text, &width, &height );
	DrawUtils::SetConsoleTextColor( (unsigned char)255, (unsigned char)( 90 * pulse ), (unsigned char)( 90 * pulse ));
	DrawUtils::DrawConsoleString(( ScreenWidth - width ) / 2, ScreenHeight * 0.70f, text );
}

int CHud :: Redraw( float flTime, int intermission )
{
	m_fOldTime = m_flTime;	// save time of previous redraw
	m_flTime = flTime;
	m_flTimeDelta = (double)m_flTime - m_fOldTime;
	static int m_flShotTime = 0;

	// Clock was reset, reset delta
	if ( m_flTimeDelta < 0 )
		m_flTimeDelta = 0;

	if (m_flShotTime && m_flShotTime < flTime)
	{
		gEngfuncs.pfnClientCmd("snapshot\n");
		m_flShotTime = 0;
	}

	m_iIntermission = intermission;

	UpdateDefaultHUDColor();
	CZM_UpdateShopState();

	CZM_AmmoFrameBegin();
	if ( m_pCvarDraw->value && (intermission || !(m_iHideHUDDisplay & HIDEHUD_ALL) ) )
	{
		for( HUDLIST *pList = m_pHudList; pList; pList = pList->pNext )
		{
			if( pList->p->m_iFlags & HUD_DRAW )
			{
				if( intermission && !(pList->p->m_iFlags & HUD_INTERMISSION) )
					continue; // skip no-intermission during intermission

				pList->p->Draw( flTime );
			}
		}

		if( !intermission && IN_AutoRunActive( ))
			CZM_DrawAutoRunLabel( flTime );
	}
	CZM_AmmoFrameEnd(); // the reload button shows the clip only while the ammo HUD has one

	// are we in demo mode? do we need to draw the logo in the top corner?
	if (m_iLogo)
	{
		int x, y, i;

		if (m_hsprLogo == 0)
			m_hsprLogo = LoadSprite("sprites/%d_logo.spr");

		SPR_Set(m_hsprLogo, 250, 250, 250 );
		
		x = SPR_Width(m_hsprLogo, 0);
		x = ScreenWidth - x;
		y = SPR_Height(m_hsprLogo, 0)/2;

		// Draw the logo at 20 fps
		int iFrame = (int)(flTime * 20) % MAX_LOGO_FRAMES;
		i = grgLogoFrame[iFrame] - 1;

		SPR_DrawAdditive(i, x, y, NULL);
	}

	// update codepage parameters
	if( !stricmp( con_charset->string, "cp1251" ))
	{
		g_codepage = 1251;
	}
	else if( !stricmp( con_charset->string, "cp1252" ))
	{
		g_codepage = 1252;
	}
	else
	{
		g_codepage = 0;
	}

	g_accept_utf8 = !stricmp( cl_charset->string, "utf-8" );

	return 1;
}

void CHud::UpdateDefaultHUDColor()
{
	int r, g, b;

	if (sscanf(m_pCvarColor->string, "%d %d %d", &r, &g, &b) == 3) {
		r = max(r, 0);
		g = max(g, 0);
		b = max(b, 0);

		r = min(r, 255);
		g = min(g, 255);
		b = min(b, 255);

		m_iDefaultHUDColor = (r << 16) | (g << 8) | b;
	} else {
		m_iDefaultHUDColor = RGB_YELLOWISH;
	}
}
