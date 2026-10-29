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
// Message.cpp
//
// implementation of CHudMessage class
//

#include "hud.h"
#include "hud/czm_hud.h"
#include "cl_util.h"
#include <string.h>
#include <stdio.h>
#include "parsemsg.h"
#include "vgui_parser.h"
#include "draw_util.h"

static int Utf8StringLen(const char *pszText)
{
	if ( !pszText ) return 0;
	int length = 0;
	Con_UtfProcessChar( 0 );
	while ( *pszText )
	{
		int uch = Con_UtfProcessChar( (unsigned char)*pszText );
		if ( uch )
			length++;
		pszText++;
	}
	return length;
}

// FNV-1a: whether a channel got another text
static unsigned int TextHash( const char *text )
{
	unsigned int hash = 2166136261u;

	for ( ; text && *text; text++ )
		hash = ( hash ^ (unsigned char)*text ) * 16777619u;
	return hash;
}

int CHudMessage::Init(void)
{
	HOOK_MESSAGE( gHUD.m_Message, HudText );
	HOOK_MESSAGE( gHUD.m_Message, GameTitle );
	HOOK_MESSAGE( gHUD.m_Message, HudTextPro );
	HOOK_MESSAGE( gHUD.m_Message, HudTextArgs );

	gHUD.AddHudElem(this);
	Reset();

	return 1;
}

int CHudMessage::VidInit( void )
{
	m_HUD_title_half = gHUD.GetSpriteIndex( "title_half" );
	m_HUD_title_life = gHUD.GetSpriteIndex( "title_life" );

	return 1;
}


void CHudMessage::Reset( void )
{
	memset( m_pMessages, 0, sizeof( m_pMessages[0] ) * maxHUDMessages );
	memset( m_startTime, 0, sizeof( m_startTime[0] ) * maxHUDMessages );
	memset( m_textHash, 0, sizeof( m_textHash[0] ) * maxHUDMessages );
	m_iLastSlot = -1;
	
	m_gameTitleTime = 0;
	m_pGameTitle = NULL;
}


float CHudMessage::FadeBlend( float fadein, float fadeout, float hold, float localTime )
{
	float fadeTime = fadein + hold;
	float fadeBlend;

	if ( localTime < 0 )
		return 0;

	if ( localTime < fadein )
	{
		fadeBlend = 1 - ((fadein - localTime) / fadein);
	}
	else if ( localTime > fadeTime )
	{
		if ( fadeout > 0 )
			fadeBlend = 1 - ((localTime - fadeTime) / fadeout);
		else
			fadeBlend = 0;
	}
	else
		fadeBlend = 1;

	return fadeBlend;
}


// The frame of server messages from the editor (czm_hud_msgs_*): a server places its texts on the
// screen, the player may squeeze them into a smaller frame away from the buttons. Whole screen by default.
static CzmHud::Rect s_frame;
static bool s_framesHidden;
static int s_messageStyle;
// "As a list" (czm_hud_msg_list 1): texts a server puts at the side (x != -1) stack in one column
// at the top of the frame instead of their own places; texts in the centre stay where they are
static bool s_list;
static int s_listY;

static void CzmMessageFrame( void )
{
	s_frame = CzmHud::MessageFrame( ScreenWidth, ScreenHeight,
		CZM_HudValue( CzmHud::MESSAGES, "x", CzmHud::defaults[CzmHud::MESSAGES][0] ), CZM_HudValue( CzmHud::MESSAGES, "y", CzmHud::defaults[CzmHud::MESSAGES][1] ),
		CZM_HudValue( CzmHud::MESSAGES, "scale", 1 ), CZM_HudValue( CzmHud::MESSAGES, "opacity", 1 ));
	s_framesHidden = CZM_HudValue( CzmHud::MESSAGES, "hidden", 0 ) > 0.5f;
	s_messageStyle = (int)CzmHud::Clamp( gEngfuncs.pfnGetCvarFloat( "czm_hud_msg_style" ), 0, CzmHud::MSG_STYLES - 1, 0 );
	s_list = gEngfuncs.pfnGetCvarFloat( "czm_hud_msg_list" ) > 0.5f;
	s_listY = (int)( s_frame.h > 0 ? s_frame.y : 0 ) + gHUD.GetCharHeight() / 2; // every frame starts the column again
}

static int CzmListX( int width )
{
	const int left = (int)( s_frame.w > 0 ? s_frame.x : 0 ) + gHUD.GetCharHeight() / 2;
	return left + width > ScreenWidth ? ( ScreenWidth - width > 0 ? ScreenWidth - width : 0 ) : left;
}

int	CHudMessage::XPosition( float x, int width, int totalWidth )
{
	int xPos;
	const float left = s_frame.w > 0 ? s_frame.x : 0, wide = s_frame.w > 0 ? s_frame.w : ScreenWidth;

	if ( x == -1 )
	{
		xPos = left + (wide - width) / 2;
	}
	else
	{
		if ( x < 0 )
			xPos = left + (1.0 + x) * wide - totalWidth;	// Alight right
		else
			xPos = left + x * wide;
	}

	if ( xPos + width > ScreenWidth )
		xPos = ScreenWidth - width;
	else if ( xPos < 0 )
		xPos = 0;

	return xPos;
}


int CHudMessage::YPosition( float y, int height )
{
	int yPos;
	const float top = s_frame.h > 0 ? s_frame.y : 0, tall = s_frame.h > 0 ? s_frame.h : ScreenHeight;

	if ( y == -1 )	// Centered?
		yPos = top + (tall - height) * 0.5;
	else
	{
		// Alight bottom?
		if ( y < 0 )
			yPos = top + (1.0 + y) * tall - height;	// Alight bottom
		else // align top
			yPos = top + y * tall;
	}

	if ( yPos + height > ScreenHeight )
		yPos = ScreenHeight - height;
	else if ( yPos < 0 )
		yPos = 0;

	return yPos;
}


void CHudMessage::MessageScanNextChar( void )
{
	int srcRed = m_parms.pMessage->r1;
	int srcGreen = m_parms.pMessage->g1;
	int srcBlue = m_parms.pMessage->b1;
	int destRed, destGreen, destBlue, blend;
	destRed = destGreen = destBlue = blend = 0;

	switch( m_parms.pMessage->effect )
	{
	// Fade-in / Fade-out
	case 0:
	case 1:
		destRed = destGreen = destBlue = 0;
		blend = m_parms.fadeBlend;
		break;

	case 2:
		m_parms.charTime += m_parms.pMessage->fadein;
		if ( m_parms.charTime > m_parms.time )
		{
			srcRed = srcGreen = srcBlue = 0;
			blend = 0;	// pure source
		}
		else
		{
			float deltaTime = m_parms.time - m_parms.charTime;

			destRed = destGreen = destBlue = 0;
			if ( m_parms.time > m_parms.fadeTime )
			{
				blend = m_parms.fadeBlend;
			}
			else if ( deltaTime > m_parms.pMessage->fxtime )
				blend = 0;	// pure dest
			else
			{
				destRed = m_parms.pMessage->r2;
				destGreen = m_parms.pMessage->g2;
				destBlue = m_parms.pMessage->b2;
				blend = 255 - (deltaTime * (1.0/m_parms.pMessage->fxtime) * 255.0 + 0.5);
			}
		}
		break;
	}
	if ( blend > 255 )
		blend = 255;
	else if ( blend < 0 )
		blend = 0;

	m_parms.r = ((srcRed * (255-blend)) + (destRed * blend)) >> 8;
	m_parms.g = ((srcGreen * (255-blend)) + (destGreen * blend)) >> 8;
	m_parms.b = ((srcBlue * (255-blend)) + (destBlue * blend)) >> 8;

	// effect 1, a flicker frame: the main loop draws the character once more in the second colour
	// (here it went in byte by byte between the bytes of the main draw, and the engine could not put
	// the letters of a UTF-8 text together: Russian letters were gone in those frames)
}


void CHudMessage::MessageScanStart( void )
{
	switch( m_parms.pMessage->effect )
	{
	// Fade-in / out with flicker
	case 1:
	case 0:
		m_parms.fadeTime = m_parms.pMessage->fadein + m_parms.pMessage->holdtime;
		

		if ( m_parms.time < m_parms.pMessage->fadein )
		{
			m_parms.fadeBlend = ((m_parms.pMessage->fadein - m_parms.time) * (1.0/m_parms.pMessage->fadein) * 255);
		}
		else if ( m_parms.time > m_parms.fadeTime )
		{
			if ( m_parms.pMessage->fadeout > 0 )
				m_parms.fadeBlend = (((m_parms.time - m_parms.fadeTime) / m_parms.pMessage->fadeout) * 255);
			else
				m_parms.fadeBlend = 255; // Pure dest (off)
		}
		else
			m_parms.fadeBlend = 0;	// Pure source (on)
		m_parms.charTime = 0;

		if ( m_parms.pMessage->effect == 1 && (rand()%100) < 10 )
			m_parms.charTime = 1;
		break;

	case 2:
		m_parms.fadeTime = (m_parms.pMessage->fadein * m_parms.length) + m_parms.pMessage->holdtime;
		
		if ( m_parms.time > m_parms.fadeTime && m_parms.pMessage->fadeout > 0 )
			m_parms.fadeBlend = (((m_parms.time - m_parms.fadeTime) / m_parms.pMessage->fadeout) * 255);
		else
			m_parms.fadeBlend = 0;
		break;
	}
}


void CHudMessage::MessageDrawScan( client_textmessage_t *pMessage, float time )
{
	int i, j, length, width;
	const char *pText;
	unsigned char line[512];

	pText = pMessage->pMessage;
	// Count lines
	m_parms.lines = 1;
	m_parms.time = time;
	m_parms.pMessage = pMessage;
	length = 0;
	width = 0;
	m_parms.totalWidth = 0;
	Con_UtfProcessChar( 0 );
	while ( *pText )
	{
		if ( *pText == '\n' )
		{
			m_parms.lines++;
			if ( width > m_parms.totalWidth )
				m_parms.totalWidth = width;
			width = 0;
		}
		else
		{
			int uch = Con_UtfProcessChar( (unsigned char)*pText );

			if ( !uch )
			{
				pText++;
				continue;
			}
			width += gHUD.GetCharWidth( uch );
		}
		pText++;
		length++;
	}
	m_parms.length = length;
	m_parms.totalHeight = (m_parms.lines * gHUD.GetCharHeight());


	// one text of a channel is one line of the list: a channel's new text replaces its old one
	const bool listed = s_list && pMessage->x != -1;
	m_parms.y = listed ? s_listY : YPosition( pMessage->y, m_parms.totalHeight );
	pText = pMessage->pMessage;

	m_parms.charTime = 0;

	MessageScanStart();

	for ( i = 0; i < m_parms.lines; i++ )
	{
		m_parms.lineLength = 0;
		m_parms.width = 0;
		while ( *pText && *pText != '\n' && m_parms.lineLength < sizeof (line) - 1)
		{
			unsigned char c = *pText;
			line[m_parms.lineLength] = c;
			m_parms.lineLength++;
			int uch = Con_UtfProcessChar( c );

			if ( !uch )
			{
				pText++;
				continue;
			}
			m_parms.width += gHUD.GetCharWidth( uch );
			pText++;
		}
		pText++;		// Skip LF
		line[m_parms.lineLength] = 0;

		m_parms.x = listed ? CzmListX( m_parms.width ) : XPosition( pMessage->x, m_parms.width, m_parms.totalWidth );

		// CZM: a dark plate with an edge of the message colour; outline: a soft dark band under the text
		if ( s_messageStyle != CzmHud::MSG_CLASSIC && m_parms.width > 0 )
		{
			float shown = 1.0f - m_parms.fadeBlend / 255.0f;
			int pad = gHUD.GetCharHeight() / 3, h = gHUD.GetCharHeight();

			if ( pMessage->effect == 2 && m_parms.time < m_parms.fadeTime )
				shown = 1.0f; // the scan-out keeps its plate while it writes
			shown = shown < 0 ? 0 : shown > 1 ? 1 : shown;
			shown *= s_frame.opacity;
			if ( s_messageStyle == CzmHud::MSG_CZM )
			{
				FillRGBABlend( m_parms.x - pad, m_parms.y, m_parms.width + pad * 2, h, 10, 14, 22, (int)( 170 * shown ));
				FillRGBABlend( m_parms.x - pad, m_parms.y, 3, h, pMessage->r1, pMessage->g1, pMessage->b1, (int)( 255 * shown ));
			}
			else
				FillRGBABlend( m_parms.x - pad, m_parms.y, m_parms.width + pad * 2, h, 0, 0, 0, (int)( 95 * shown ));
		}

		const bool flicker = pMessage->effect == 1 && m_parms.charTime != 0;
		int charStart = 0;

		Con_UtfProcessChar( 0 );
		for ( j = 0; j < m_parms.lineLength; j++ )
		{
			m_parms.text = line[j];
			int uch = Con_UtfProcessChar( m_parms.text );
			int next = m_parms.x + gHUD.GetCharWidth( uch ? uch : m_parms.text );
			const int charX = m_parms.x; // the first bytes of a UTF-8 letter do not move it
			const bool inside = m_parms.x >= 0 && m_parms.y >= 0 && next <= ScreenWidth;

			float savedCharTime = m_parms.charTime;
			MessageScanNextChar();

			if ( !uch )
				m_parms.charTime = savedCharTime;
			
			if ( inside )
				m_parms.x += DrawUtils::TextMessageDrawChar( m_parms.x, m_parms.y, m_parms.text,
					m_parms.r * s_frame.opacity, m_parms.g * s_frame.opacity, m_parms.b * s_frame.opacity ); // additive: darker is fainter

			if ( !uch )
				continue;
			// the flicker: the whole letter, all its bytes in a row, once the main draw is done with it
			if ( flicker && inside )
			{
				for ( int k = charStart; k <= j; k++ )
					DrawUtils::TextMessageDrawChar( charX, m_parms.y, line[k], pMessage->r2 * s_frame.opacity,
						pMessage->g2 * s_frame.opacity, pMessage->b2 * s_frame.opacity );
			}
			charStart = j + 1;
		}

		m_parms.y += gHUD.GetCharHeight();
	}
	if ( listed )
		s_listY = m_parms.y + gHUD.GetCharHeight() / 3; // the next text goes under this one
}


int CHudMessage::Draw( float fTime )
{
	int i, drawn;
	client_textmessage_t *pMessage;
	float endTime;

	drawn = 0;
	CzmMessageFrame();

	if ( m_gameTitleTime > 0 )
	{
		float localTime = gHUD.m_flTime - m_gameTitleTime;
		float brightness;

		// Maybe timer isn't set yet
		if ( m_gameTitleTime > gHUD.m_flTime )
			m_gameTitleTime = gHUD.m_flTime;

		if ( localTime > (m_pGameTitle->fadein + m_pGameTitle->holdtime + m_pGameTitle->fadeout) )
			m_gameTitleTime = 0;
		else
		{
			brightness = FadeBlend( m_pGameTitle->fadein, m_pGameTitle->fadeout, m_pGameTitle->holdtime, localTime );

			int halfWidth = gHUD.GetSpriteRect(m_HUD_title_half).Width();
			int fullWidth = halfWidth + gHUD.GetSpriteRect(m_HUD_title_life).Width();
			int fullHeight = gHUD.GetSpriteRect(m_HUD_title_half).Height();

			int x = XPosition( m_pGameTitle->x, fullWidth, fullWidth );
			int y = YPosition( m_pGameTitle->y, fullHeight );


			SPR_Set( gHUD.GetSprite(m_HUD_title_half), brightness * m_pGameTitle->r1, brightness * m_pGameTitle->g1, brightness * m_pGameTitle->b1 );
			SPR_DrawAdditive( 0, x, y, &gHUD.GetSpriteRect(m_HUD_title_half) );

			SPR_Set( gHUD.GetSprite(m_HUD_title_life), brightness * m_pGameTitle->r1, brightness * m_pGameTitle->g1, brightness * m_pGameTitle->b1 );
			SPR_DrawAdditive( 0, x + halfWidth, y, &gHUD.GetSpriteRect(m_HUD_title_life) );

			drawn = 1;
		}
	}
	// Fixup level transitions
	for ( i = 0; i < maxHUDMessages; i++ )
	{
		// Assume m_parms.time contains last time
		if ( m_pMessages[i].pMessage )
		{
			pMessage = m_pMessages[i].pMessage;
			if ( m_startTime[i] > gHUD.m_flTime )
				m_startTime[i] = gHUD.m_flTime + m_parms.time - m_startTime[i] + 0.2;	// Server takes 0.2 seconds to spawn, adjust for this
		}
	}

	for ( i = 0; i < maxHUDMessages; i++ )
	{
		if ( m_pMessages[i].pMessage )
		{
			pMessage = m_pMessages[i].pMessage;

			// This is when the message is over
			switch( pMessage->effect )
			{
			// TODO: HACK to prevent crashing
			default:
			case 0:
			case 1:
				endTime = m_startTime[i] + pMessage->fadein + pMessage->fadeout + pMessage->holdtime;
				break;
			
			// Fade in is per character in scanning messages
			case 2:
				endTime = m_startTime[i] + (pMessage->fadein * Utf8StringLen( pMessage->pMessage )) + pMessage->fadeout + pMessage->holdtime;
				break;
			}

			if ( fTime <= endTime )
			{
				float messageTime = fTime - m_startTime[i];

				// Draw the message
				// effect 0 is fade in/fade out
				// effect 1 is flickery credits
				// effect 2 is write out (training room)
				if ( !s_framesHidden ) // taken off the screen in the editor: they still time out
					MessageDrawScan( pMessage, messageTime );

				drawn++;
			}
			else
			{
				// The message is over
				if( !strcmp( m_pMessages[i].pMessage->pName, "Custom" ) )
				{
					delete[] m_pMessages[i].pMessage->pMessage;
				}
				m_pMessages[i].pMessage = NULL;
			}
		}
	}

	// Remember the time -- to fix up level transitions
	m_parms.time = gHUD.m_flTime;
	// Don't call until we get another message
	if ( !drawn )
		m_iFlags &= ~HUD_DRAW;

	return 1;
}


void CHudMessage::MessageAdd( const char *pName, float time, qboolean hintMessage/*, unsigned int font */ )
{
	int i, j;
	client_textmessage_t *tempMessage;
	client_textmessage_t *message;

	for ( i = 0; i < maxHUDMessages; i++ )
	{
		if ( !m_pMessages[i].pMessage )
		{
			// Trim off a leading # if it's there
			if ( pName[0] == '#' ) 
				tempMessage = TextMessageGet( pName+1 );
			else
				tempMessage = TextMessageGet( pName );

			if( tempMessage )
			{
				if( tempMessage->pMessage[0] == '#' )
				{
					message = AllocMessage( CHudTextMessage::BufferedLocaliseTextString( tempMessage->pMessage ), tempMessage );
				}
				else if( !strcmp( tempMessage->pName, "Custom" ) ) // Hey, it's mine way of detecting allocated message
				{
					message = AllocMessage( tempMessage->pMessage, tempMessage );
				}
				else
				{
					message = tempMessage;
				}
			}
			else
			{
				char *localized = (char *)pName;
				if( pName[0] == '#' )
				{
					localized = (char *)Localize( pName + 1 );
				}

				// If we couldnt find it in the titles.txt, just create it
				message = AllocMessage( localized );

				message->effect = 2;
				message->r1 = message->g1 = message->b1 = message->a1 = 100;
				message->r2 = 240;
				message->g2 = 110;
				message->b2 = 0;
				message->a2 = 0;
				message->x = -1;		// Centered
				message->y = 0.7;
				message->fadein = 0.01;
				message->fadeout = 1.5;
				message->fxtime = 0.25;
				message->holdtime = 5;
			}

			if ( message && hintMessage )
			{
				message->effect = 2;
				message->r1 = 40;
				message->g1 = 255;
				message->b1 = 40;
				message->a1 = 200;
				message->r2 = 0;
				message->g2 = 255;
				message->b2 = 0;
				message->a2 = 200;
				message->x = -1.0;
				message->y = 0.7;
				message->fadein = 0.01;
				message->fadeout = 0.7;
				message->fxtime = 0.07;
				message->holdtime = 5.0;

				if ( !strcmp( pName, "#Spec_Duck" ) )
				{
					message->holdtime = 6.0;
				}
				else if ( message->pMessage )
				{
					float lengthHold = (float)Utf8StringLen( message->pMessage ) / 25.0f;
					if ( lengthHold < 1.0f )
						lengthHold = 1.0f;
					message->holdtime = lengthHold;
				}
				else
				{
					message->holdtime = 1.0;
				}
			}

			// safety check - don't add empty messages
            if ( !message || !message->pMessage || message->pMessage[0] == '\0' ) 
            {
                // clean up custom messages
                if ( message && !strcmp(message->pName, "Custom") ) 
                {
                    delete[] message->pMessage;
                }
                return; // bail out if message is empty
            }

			for ( j = 0; j < maxHUDMessages; j++ )
			{
				if ( m_pMessages[j].pMessage )
				{
					// is this message already in the list: it stays up (CZM, see MessageKeep)
					if ( m_pMessages[j].pMessage == message || !strcmp( message->pMessage, m_pMessages[j].pMessage->pMessage ) )
					{
						MessageKeep( j, message, time );
						if( !strcmp( message->pName, "Custom" ) && message != m_pMessages[j].pMessage )
						{
							delete[] message->pMessage;
						}
						return;
					}

					// get rid of any other messages in same location (only one displays at a time)
					if ( fabs( message->y - m_pMessages[j].pMessage->y ) < 0.0001 && fabs( message->x - m_pMessages[j].pMessage->x ) < 0.0001 )
					{
						if( !strcmp( m_pMessages[j].pMessage->pName, "Custom" ) )
						{
							delete[] m_pMessages[j].pMessage->pMessage;
						}
						m_pMessages[j].pMessage = NULL;
					}
				}
			}

			m_pMessages[i].pMessage = message;
			// m_pMessages[i].font = font;
			m_startTime[i] = time;
			m_textHash[i] = TextHash( message->pMessage );
			m_iLastSlot = i;
			return;
		}
	}
}


// A server sends its texts again and again: a panel of numbers every second, often with a hold time
// of about a second. The stock code kept the first copy and dropped the others, so the text ran out
// after its hold time and stayed away until a copy found the place free: the panel blinked, about a
// second on and a second off. A copy now keeps the text up, held from now and shown in full, without
// a new fade-in or write-out; another text of a write-out message on the same channel is written anew.
void CHudMessage::MessageKeep( int slot, client_textmessage_t *message, float time )
{
	client_textmessage_t *shown = m_pMessages[slot].pMessage;
	const unsigned int hash = TextHash( message->pMessage );

	if ( shown->effect == 2 && hash != m_textHash[slot] )
		m_startTime[slot] = time;
	else
	{
		const float in = shown->effect == 2 ? shown->fadein * Utf8StringLen( shown->pMessage ) : shown->fadein;

		if ( time - m_startTime[slot] > in )
			m_startTime[slot] = time - in;
	}
	m_textHash[slot] = hash;
	m_iLastSlot = slot;
}


int CHudMessage::MsgFunc_HudText( const char *pszName,  int iSize, void *pbuf )
{
	BufferReader reader( pszName, pbuf, iSize );

	char *pString = reader.ReadString();

	MessageAdd( pString, gHUD.m_flTime );
	// Remember the time -- to fix up level transitions
	m_parms.time = gHUD.m_flTime;

	// Turn on drawing
	m_iFlags |= HUD_DRAW;

	return 1;
}


int CHudMessage::MsgFunc_GameTitle( const char *pszName,  int iSize, void *pbuf )
{
	m_pGameTitle = TextMessageGet( "GAMETITLE" );
	if ( m_pGameTitle != NULL )
	{
		m_gameTitleTime = gHUD.m_flTime;

		// Turn on drawing
		m_iFlags |= HUD_DRAW;
	}

	return 1;
}

void CHudMessage::MessageAdd(client_textmessage_t * newMessage )
{
	client_textmessage_t *message;

	m_parms.time = gHUD.m_flTime;

	// Turn on drawing
	m_iFlags |= HUD_DRAW;

	if( !strcmp( newMessage->pName, "Custom" ) ) // Hey, it's mine way of detecting allocated message
	{
		message = AllocMessage( newMessage->pMessage, newMessage );
	}
	else
	{
		message = newMessage;
	}

	for ( int i = 0; i < maxHUDMessages; i++ )
	{
		if ( !m_pMessages[i].pMessage )
		{
			m_pMessages[i].pMessage = message;
			m_startTime[i] = gHUD.m_flTime;
			m_textHash[i] = TextHash( message->pMessage );
			return;
		}
	}

}


int CHudMessage::MsgFunc_HudTextPro( const char *pszName, int iSize, void *pbuf )
{
	const char *sz;
	qboolean hintMessage;
	BufferReader reader( pszName, pbuf, iSize );
	sz = reader.ReadString();
	hintMessage = reader.ReadByte();

	MessageAdd(sz, gHUD.m_flTime, hintMessage/*, Newfont*/ ); // TODO

	// Remember the time -- to fix up level transitions
	m_parms.time = gHUD.m_flTime;

	// Turn on drawing
	m_iFlags |= HUD_DRAW;
	return 1;
}

int CHudMessage::MsgFunc_HudTextArgs( const char *pszName, int iSize, void *pbuf )
{
	BufferReader reader( pszName, pbuf, iSize );

	const char *sz = reader.ReadString();
	qboolean hintMessage = reader.ReadByte();

	m_iLastSlot = -1;
	MessageAdd( sz, gHUD.m_flTime, hintMessage/*, Newfont*/ ); // TODO

	// the slot it went to, or the one that already showed it (the arguments may be new)
	int slot = m_iLastSlot >= 0 && m_pMessages[m_iLastSlot].pMessage ? m_iLastSlot : -1;

	if ( slot != -1 )
	{
		int argCount = reader.ReadByte();
		if ( argCount > 4 ) argCount = 4;
		if ( argCount < 0 ) argCount = 0;

		m_pMessages[slot].arg_count = argCount;

		for ( int i = 0; i < argCount; i++ )
		{
			const char *arg = reader.ReadString();
			if ( !arg ) arg = "";

			const char *localizedArg = Localize( arg );
			strncpy( m_pMessages[slot].args[i], localizedArg, 128 );
			m_pMessages[slot].args[i][127] = 0;
		}
	}

	// Remember the time -- to fix up level transitions
	m_parms.time = gHUD.m_flTime;

	// Turn on drawing
	m_iFlags |= HUD_DRAW;

	return 1;
}

client_textmessage_t *CHudMessage::AllocMessage( const char *text, client_textmessage_t *copyFrom )
{
	const int MAX_CUSTOM_MESSAGES = 16;
	const int MAX_CUSTOM_MESSAGES_MASK = (MAX_CUSTOM_MESSAGES-1);
	static client_textmessage_t	g_pCustomMessage[MAX_CUSTOM_MESSAGES] = { };
	static int g_iCustomMessageMod = 0;

	client_textmessage_t *ret = &g_pCustomMessage[g_iCustomMessageMod];
	g_iCustomMessageMod = (g_iCustomMessageMod + 1) & MAX_CUSTOM_MESSAGES_MASK;

	if( copyFrom )
	{
		*ret = *copyFrom;
	}

	if( text )
	{
		int len = strlen( text );
		char *szCustomText = new char[len + 1];
		strcpy( szCustomText, text );

		ret->pName = "Custom";
		ret->pMessage = szCustomText;
	}

	return ret;
}
