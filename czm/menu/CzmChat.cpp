/*
CzmChat.cpp - Counter Zombie Mobile: world chat with Global, RU and EN rooms
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
#include <time.h>

#include "extdll_menu.h"
#include "BaseMenu.h"
#include "Utils.h"
#include "Framework.h"
#include "Scissor.h"
#include "keydefs.h"
#include "utlvector.h"
#include "utlstring.h"
#include "CzmMenu.h"
#include "CzmJson.h"

/*
Messages come from our service (server/czm): the open room is asked for new messages
every 2.5 seconds while the window is open. The server cleans swear words, limits the
pace and keeps the last 100 messages of a room for 7 days. A tap opens the player
card with friendship, messages and a contextual complaint; the owner moderates in his Telegram bot.
*/
#define UI_DIR "gfx/czm/ui/"
#define ROOMS 3
#define MAX_MESSAGES 100
#define MAX_LINES 8
#define POLL_EVERY 2.5
#define INPUT_CHARS 200

#include "CzmConversationStyle.h"

static const char *s_roomIds[ROOMS] = { "global", "ru", "en" };
static const char *s_roomNames[ROOMS] = { "Global", "RU", "EN" };

struct CzmChatMessage
{
	int id;
	int player;
	int time;
	bool support;         // the official SUPPORT account
	char role[16], project[132];
	int place;            // the place in the Top 100, 0 outside it
	char nick[100];
	char avatar[24];
	char text[1604];

	// wrapping for the width it was last drawn at
	int wrapWidth;
	int numLines;
	int starts[MAX_LINES + 1];
};

struct CzmChatRoom
{
	CUtlVector<CzmChatMessage> messages;
	int lastId;
	bool loaded;
	int request;
	double nextPoll;
};

static int Utf8Chars( const char *s )
{
	int n = 0;
	for( ; *s; s++ )
		n += (( *s & 0xC0 ) != 0x80 );
	return n;
}

class CCzmChat : public CMenuFramework
{
public:
	CCzmChat();

	void Show() override;
	void Hide() override;
	void Draw() override;
	bool IsRoot() const override { return false; }
	bool KeyDown( int key ) override;
	bool KeyUp( int key ) override;
	bool MouseMove( int x, int y ) override;
	void Char( int key ) override;

private:
	enum EHit
	{
		HIT_NONE = 0,
		HIT_BACK,
		HIT_ROOM,                    // ROOMS
		HIT_INPUT = HIT_ROOM + ROOMS,
		HIT_SEND,
		HIT_HANDLE,
		HIT_POPUP_COPY,
		HIT_POPUP_MESSAGE,
		HIT_POPUP_AVATAR,
		HIT_POPUP_CANCEL,
		HIT_POPUP_PANEL,
		HIT_BACKDROP,
		HIT_MESSAGE = 1000,          // + index
		HIT_PROFILE = 2000,          // tap on a player's avatar or name
		HIT_OPTIONS = 3000,
		HIT_TRANSLATE = 4000,
	};

	void Layout( void );
	int HitTest( void ) const;
	// our pictures are not reported, only players' own photos
	bool PopupHasAvatar( void ) const
	{
		const CzmChatRoom &room = m_rooms[m_iRoom];
		return m_iPopup >= 0 && m_iPopup < room.messages.Count() && !strncmp( room.messages[m_iPopup].avatar, "photo:", 6 );
	}
	bool IsPressed( int hit ) const { return m_iPressed == hit && HitTest() == hit; }
	void Activate( int hit );

	void Poll( void );
	void ReadMessages( CzmChatRoom &room, const char *body );
	void Send( void );
	static void AfterRules( void ); // the message waits in the field while the rules are read
	friend void CZM_ChatHidePlayer( int player );
	void Report( bool avatar );
	void Toast( const char *text );

	void BeginInput( void );
	void EndInput( void );

	int MessageHeight( CzmChatMessage &m );
	int RowHeight(int index);bool DateBefore(int index)const;
	void DrawMessages( void );
	void DrawInput( void );
	void DrawPopup( void );
	int ContentHeight( void );

	CzmChatRoom m_rooms[ROOMS];
	int m_iRoom;
	int m_iSendId;
	char m_szSending[600];
	int m_iReportId;

	char m_szInput[600];
	bool m_bTyping;

	int m_iPopup;                // message index, -1 none
	int m_popupId;bool m_reportConfirm;
	char m_szToast[160];
	double m_flToastTime;

	int m_iPressed;
	bool m_bMaybeScroll, m_bScrolling;
	int m_iDownY;
	float m_flScrollAtDown;
	float m_flScroll;            // from the bottom: 0 shows the newest messages
	float m_flVelocity;
	int m_iLastMoveY;
	double m_flLastMoveTime, m_flLastDraw;
	float m_flOpen;
	bool m_bClosing, m_bHandleDrag;

	int W, H;
	CzmRect m_sheet, m_handle;
	CzmRect m_back, m_rooms_[ROOMS], m_panel, m_clip, m_input, m_send;
	CzmRect m_popup, m_popupMessage, m_popupAvatar, m_popupCancel,m_popupCopy;
	int m_iAvatar, m_iTextX, m_iTextW, m_iGap;
};

CCzmChat::CCzmChat() : CMenuFramework( "CzmChat" )
{
	m_iRoom = 0;
	m_iSendId = m_iReportId = 0;
	m_szSending[0] = m_szInput[0] = 0;
	m_bTyping = false;
	m_iPopup = -1;
	m_popupId=0;m_reportConfirm=false;
	m_szToast[0] = 0;
	m_flToastTime = 0.0;
	m_iPressed = HIT_NONE;
	m_bMaybeScroll = m_bScrolling = false;
	m_iDownY = m_iLastMoveY = 0;
	m_flScrollAtDown = m_flScroll = m_flVelocity = 0.0f;
	m_flLastMoveTime = m_flLastDraw = 0.0;
	m_flOpen = 0.0f;
	m_bClosing = m_bHandleDrag = false;
	W = H = 0;
	m_iAvatar = m_iTextX = m_iTextW = m_iGap = 1;
	for( int i = 0; i < ROOMS; i++ )
	{
		m_rooms[i].lastId = 0;
		m_rooms[i].loaded = false;
		m_rooms[i].request = 0;
		m_rooms[i].nextPoll = 0.0;
	}
}

void CCzmChat::Show()
{
	CZM_Init();
	m_iRoom = bound( 0, (int)EngFuncs::GetCvarFloat( "czm_chat_room" ), ROOMS - 1 );
	m_iPressed = HIT_NONE;
	m_iPopup = -1;
	m_flScroll = 0.0f;
	m_flVelocity = 0.0f;
	m_rooms[m_iRoom].nextPoll = 0.0; // fresh messages at once
	m_flOpen = 0.0f;
	m_bClosing = m_bHandleDrag = false;
	m_flLastDraw = EngFuncs::DoubleTime();
	CMenuFramework::Show();
	DisableTransition(); // The sheet has its own slide; keep the main screen behind it.
}

void CCzmChat::Hide()
{
	EndInput();
	m_bClosing = true;
	m_bHandleDrag = false;
	m_iPopup = -1;
	m_flVelocity = 0.0f;
}

void CCzmChat::Toast( const char *text )
{
	Q_strncpy( m_szToast, text, sizeof( m_szToast ));
	m_flToastTime = EngFuncs::DoubleTime();
}

void CCzmChat::BeginInput( void )
{
	m_bTyping = true;
	EngFuncs::SetTextInputRect( m_input.x, m_input.y, m_input.w, m_input.h );
	UI_EnableTextInput( true );
}

void CCzmChat::EndInput( void )
{
	if( !m_bTyping )
		return;
	m_bTyping = false;
	UI_EnableTextInput( false );
}

/*
=================
network
=================
*/
void CCzmChat::ReadMessages( CzmChatRoom &room, const char *body )
{
	CzmJson j;
	int list, deleted;
	int added = 0;

	if( !j.Parse( body ))
		return;

	CZM_OnlineReadBan( j, j.Get( 0, "ban" ));

	// removed by the owner
	deleted = j.Get( 0, "deleted" );
	for( int i = 0; i < j.Count( deleted ); i++ )
	{
		int id = j.Int( j.At( deleted, i ));
		for( int k = 0; k < room.messages.Count(); k++ )
		{
			if( room.messages[k].id == id )
			{
				room.messages.Remove( k );
				break;
			}
		}
	}

	list = j.Get( 0, "messages" );
	for( int i = 0; i < j.Count( list ); i++ )
	{
		int item = j.At( list, i );
		int id = j.Int( j.Get( item, "id" ));
		CzmChatMessage m;

		if( id <= room.lastId )
			continue;

		memset( &m, 0, sizeof( m ));
		m.id = id;
		m.player = j.Int( j.Get( item, "p" ));
		m.time = j.Int( j.Get( item, "ts" ));
		Q_strncpy( m.nick, j.String( j.Get( item, "n" )), sizeof( m.nick ));
		Q_strncpy( m.avatar, j.String( j.Get( item, "a" )), sizeof( m.avatar ));
		Q_strncpy( m.text, j.String( j.Get( item, "t" )), sizeof( m.text ));
		Q_strncpy(m.role,j.String(j.Get(item,"r")),sizeof(m.role));
		Q_strncpy(m.project,j.String(j.Get(item,"rp")),sizeof(m.project));
		m.support = m.role[0] != 0;
		m.place = j.Int( j.Get( item, "k" ));
		room.messages.AddToTail( m );
		room.lastId = id;
		added++;
	}

	while( room.messages.Count() > MAX_MESSAGES )
		room.messages.Remove( 0 );

	// a player reading older messages keeps his place
	if( added && m_flScroll > 0.0f && &room == &m_rooms[m_iRoom] )
	{
		for( int i = room.messages.Count() - added; i < room.messages.Count(); i++ )
			m_flScroll += RowHeight(i);
	}

	room.loaded = true;
}

void CCzmChat::Poll( void )
{
	double now = EngFuncs::DoubleTime();
	CzmChatRoom &room = m_rooms[m_iRoom];
	int status;
	CUtlString body;
	if(CZM_OnlineAccount()&&m_pStack->Current()==this&&m_flScroll<=1.0f&&room.loaded)
		CZM_ChatMarkRead(m_iRoom,room.lastId);

	for( int i = 0; i < ROOMS; i++ )
	{
		CzmChatRoom &r = m_rooms[i];

		if( r.request && CZM_NetPoll( r.request, &status, body ))
		{
			r.request = 0;
			r.nextPoll = now + POLL_EVERY;
			if( status == 200 )
				ReadMessages( r, body.Get( ));
		}
	}

	if( CZM_OnlineReady() && !room.request && now >= room.nextPoll )
	{
		char path[96];

		snprintf( path, sizeof( path ), "/api/v1/chat/%s?after=%d", s_roomIds[m_iRoom], room.lastId );
		room.request = CZM_NetRequest( "GET", CZM_OnlineUrl( path ), CZM_OnlineKey(), "" );
		if( !room.request )
			room.nextPoll = now + POLL_EVERY;
	}

	if( m_iSendId && CZM_NetPoll( m_iSendId, &status, body ))
	{
		CzmJson j;
		bool parsed = j.Parse( body.Get( ));
		const char *error = parsed ? j.String( j.Get( 0, "error" )) : "";
		char text[160];

		m_iSendId = 0;
		if( status == 200 )
		{
			// the message comes with the next answer of the room
			room.nextPoll = 0.0;
			m_flScroll = 0.0f;
		}
		else
		{
			// the text goes back into the field
			if( !m_szInput[0] )
				Q_strncpy( m_szInput, m_szSending, sizeof( m_szInput ));

			if( !strcmp( error, "slow" ))
			{
				snprintf( text, sizeof( text ), CZM_T( "chat_slow" ), Q_max( 1, j.Int( j.Get( 0, "wait" ), 3 )));
				Toast( text );
			}
			else if( !strcmp( error, "repeat" ))
				Toast( CZM_T( "chat_repeat" ));
			else if( !strcmp( error, "banned" ))
				CZM_OnlineReadBan( j, j.Get( 0, "ban" ));
			else if( !strcmp( error, "rules" ))
				CZM_RulesRefused( j.Int( j.Get( 0, "version" )), AfterRules );
			else if( !strcmp( error, "muted" ))
			{
				char why[300];
				CZM_OnlineSetLimit( CZM_LIMIT_TEXT, j, j.Get( 0, "mute" ));
				if( CZM_OnlineLimited( CZM_LIMIT_TEXT, why, sizeof( why )))
					CZM_ShowNotice( CZM_IsRussian() ? "Чат ограничен" : "Chat limited", why );
			}
			else if( strcmp( error, "empty" ))
				Toast( CZM_T( "chat_offline" ));
		}
	}

	if( m_iReportId && CZM_NetPoll( m_iReportId, &status, body ))
	{
		m_iReportId = 0;
		Toast( CZM_T( status == 200 ? "chat_reported" : status == 429 ? "chat_report_slow" : "chat_offline" ));
	}
}

void CCzmChat::Send( void )
{
	CUtlString body;
	char path[64];
	const char *p = m_szInput;

	while( *p == ' ' )
		p++;
	if( !*p || m_iSendId || CZM_OnlineBan( NULL, NULL, NULL ))
		return;

	if( !CZM_OnlineReady( ))
	{
		Toast( CZM_T( "chat_offline" ));
		return;
	}
	if( !CZM_RulesAllow( AfterRules ))
		return;
	{
		char why[300];
		if( CZM_OnlineLimited( CZM_LIMIT_TEXT, why, sizeof( why )))
		{
			CZM_ShowNotice( CZM_IsRussian() ? "Чат ограничен" : "Chat limited", why );
			return;
		}
	}

	body.Append( "{\"text\":" );
	CZM_JsonQuote( body, p );
	body.Append( "}" );
	snprintf( path, sizeof( path ), "/api/v1/chat/%s", s_roomIds[m_iRoom] );
	Q_strncpy( m_szSending, p, sizeof( m_szSending ));
	m_iSendId = CZM_NetRequest( "POST", CZM_OnlineUrl( path ), CZM_OnlineKey(), body.Get( ));
	m_szInput[0] = 0;
}

void CCzmChat::Report( bool avatar )
{
	CzmChatRoom &room = m_rooms[m_iRoom];
	char body[64];

	if( m_iPopup < 0 || m_iPopup >= room.messages.Count() || m_iReportId )
		return;

	if( avatar )
		snprintf( body, sizeof( body ), "{\"player\":%d}", room.messages[m_iPopup].player );
	else
		snprintf( body, sizeof( body ), "{\"message\":%d}", room.messages[m_iPopup].id );
	m_iReportId = CZM_NetRequest( "POST", CZM_OnlineUrl( "/api/v1/report" ), CZM_OnlineKey(), body );
}

/*
=================
layout and input
=================
*/

bool CCzmChat::DateBefore(int index)const{
 const CzmChatRoom &room=m_rooms[m_iRoom];return index==0||!CzmConversation::SameDay(room.messages[index-1].time,room.messages[index].time);
}
int CCzmChat::MessageHeight(CzmChatMessage&m){
 const bool mine=m.player==CZM_OnlinePlayer();return CzmConversation::Layout(m_clip,0,m.text,mine?(CZM_IsRussian()?"Вы":"You"):m.nick,mine,false,m.role,m.project,m.place).height;
}
int CCzmChat::RowHeight(int index){return MessageHeight(m_rooms[m_iRoom].messages[index])+(DateBefore(index)?CzmConversation::DateHeight():0);}

int CCzmChat::ContentHeight( void )
{
	CzmChatRoom &room = m_rooms[m_iRoom];
	int total = 0;

	for( int i = 0; i < room.messages.Count(); i++ )
		total += RowHeight(i);
	return total;
}

void CCzmChat::Layout( void )
{
	HFont titleFont = CZM_Font( CZMF_PANEL_TITLE );
	HFont tabFont = CZM_Font( CZMF_TILE_STATUS );
	int margin, top, hb, x, bottom, ih, pad;

	W = ScreenWidth;
	H = ScreenHeight;
	int sheetW = Q_min( (int)( W * 0.86f ), (int)( H * 1.65f ));
	int sheetH = H * 0.76f;
	float eased = m_flOpen * m_flOpen * ( 3.0f - 2.0f * m_flOpen );
	m_sheet = CZM_Rect( ( W - sheetW ) / 2, H * 0.965f - sheetH + ( 1.0f - eased ) * ( sheetH + H * 0.04f ), sheetW, sheetH );
	pad = H * 0.025f;
	margin = m_sheet.x + pad;
	top = m_sheet.y + H * 0.055f;
	hb = H * 0.065f;
	m_handle = CZM_Rect( W / 2 - H * 0.16f, m_sheet.y, H * 0.32f, H * 0.045f );

	m_back = CZM_Rect( margin, top, hb, hb );
	x = margin + hb + H * 0.03f + CZM_TextWidth( titleFont, CZM_T( "chat_title" )) + H * 0.05f;
	for( int i = 0; i < ROOMS; i++ )
	{
		int w = CZM_TextWidth( tabFont, s_roomNames[i] ) + H * 0.07f;
		m_rooms_[i] = CZM_Rect( x, top + ( hb - H * 0.064f ) / 2, w, H * 0.064f );
		x += w;
	}

	// input at the bottom
	ih = H * 0.075f;
	bottom = m_sheet.y + m_sheet.h - pad;
	m_send = CZM_Rect( m_sheet.x + m_sheet.w - pad - ih, bottom - ih, ih, ih );
	m_input = CZM_Rect( margin, bottom - ih, m_send.x - H * 0.02f - margin, ih );

	// messages between the header and the input
	m_panel = CZM_Rect( margin, top + hb + H * 0.05f, m_sheet.w - pad * 2, 0 );
	m_panel.h = m_input.y - H * 0.025f - m_panel.y;
	m_clip = m_panel;

	m_iAvatar = H * 0.06f;
	m_iGap = H * 0.018f;
	m_iTextX = m_clip.x + m_iAvatar + H * 0.022f;
	m_iTextW = m_clip.x + m_clip.w - m_iTextX;
	if( m_bTyping ) EngFuncs::SetTextInputRect( m_input.x, m_input.y, m_input.w, m_input.h );


 // Resolve a menu by message ID: polling or pruning must not change its target.
 if(m_iPopup>=0){
  m_iPopup=-1;for(int i=0;i<m_rooms[m_iRoom].messages.Count();i++)if(m_rooms[m_iRoom].messages[i].id==m_popupId){m_iPopup=i;break;}
 }
 {
  const bool mine=m_iPopup>=0&&m_rooms[m_iRoom].messages[m_iPopup].player==CZM_OnlinePlayer();
  const int rows=m_reportConfirm?2:mine?3:4,bh=Q_max(28,(int)(H*.063f)),gap=Q_max(5,H/100),inset=Q_max(8,H/45);
  const int width=Q_min((int)(W*.90f),(int)(H*.96f)),title=Q_max(64,(int)(H*.16f)),height=inset*2+title+rows*(bh+gap);
  m_popup=CZM_Rect((W-width)/2,(H-height)/2,width,height);
  const int x=m_popup.x+inset,w=width-inset*2;int y=m_popup.y+inset+title;
  m_popupCopy=m_popupAvatar=m_popupMessage=CZM_Rect(0,0,0,0);
  if(!m_reportConfirm){m_popupCopy=CZM_Rect(x,y,w,bh);y+=bh+gap;m_popupAvatar=CZM_Rect(x,y,w,bh);y+=bh+gap;}
  if(m_reportConfirm||!mine){m_popupMessage=CZM_Rect(x,y,w,bh);y+=bh+gap;}
  m_popupCancel=CZM_Rect(x,y,w,bh);
 }

}

int CCzmChat::HitTest( void ) const
{
	const int grow = ScreenHeight * 0.012f;
	int x = uiStatic.cursorX, y = uiStatic.cursorY;


 if(m_iPopup>=0){
  if(!m_reportConfirm&&m_popupCopy.HasCursor())return HIT_POPUP_COPY;
  if(!m_reportConfirm&&m_popupAvatar.HasCursor())return HIT_POPUP_AVATAR;
  if(m_popupMessage.w&&m_popupMessage.HasCursor())return HIT_POPUP_MESSAGE;
  if(m_popupCancel.HasCursor())return HIT_POPUP_CANCEL;
  return m_popup.HasCursor()?HIT_POPUP_PANEL:HIT_BACKDROP;
 }

	if( m_back.Grown( grow ).HasCursor( ))
		return HIT_BACK;
	if( m_handle.HasCursor() )
		return HIT_HANDLE;
	if( !m_sheet.Contains( x, y ))
		return HIT_BACKDROP;
	for( int i = 0; i < ROOMS; i++ )
	{
		if( m_rooms_[i].HasCursor( ))
			return HIT_ROOM + i;
	}
	if( m_send.Grown( grow ).HasCursor( ))
		return HIT_SEND;
	if( m_input.HasCursor( ))
		return HIT_INPUT;


 if(m_clip.Contains(x,y)){
  const CzmChatRoom&room=m_rooms[m_iRoom];int bottom=m_clip.y+m_clip.h+(int)m_flScroll;
  for(int i=room.messages.Count()-1;i>=0&&bottom>m_clip.y;i--){
   const int height=((CCzmChat*)this)->RowHeight(i);bottom-=height;if(y<bottom||y>=bottom+height)continue;
   const CzmChatMessage&m=room.messages[i];const bool mine=m.player==CZM_OnlinePlayer();
   const CzmConversation::Bubble b=CzmConversation::Layout(m_clip,bottom+(DateBefore(i)?CzmConversation::DateHeight():0),m.text,mine?(CZM_IsRussian()?"Вы":"You"):m.nick,mine,false,m.role,m.project,m.place);
   if(b.menu.HasCursor())return HIT_OPTIONS+i;
   if(b.canTranslate&&b.translate.HasCursor())return HIT_TRANSLATE+i;
   if(b.avatar.HasCursor()||(b.header.HasCursor()&&x<b.menu.x-CZM_TextWidth(CZM_Font(CZMF_UI_META),"00:00")))return HIT_PROFILE+i;
   return HIT_NONE;
  }
 }

	return HIT_NONE;
}

void CCzmChat::Activate( int hit )
{
	if( m_bClosing || hit == HIT_NONE || hit == HIT_POPUP_PANEL )
		return;

 if(hit>=HIT_TRANSLATE&&hit<HIT_TRANSLATE+MAX_MESSAGES){
  const int index=hit-HIT_TRANSLATE;if(index<m_rooms[m_iRoom].messages.Count())CZM_Translate(m_rooms[m_iRoom].messages[index].text);return;
 }
 if(hit>=HIT_OPTIONS&&hit<HIT_OPTIONS+MAX_MESSAGES){
  const int index=hit-HIT_OPTIONS;if(index<m_rooms[m_iRoom].messages.Count()){EndInput();m_iPopup=index;m_popupId=m_rooms[m_iRoom].messages[index].id;m_reportConfirm=false;}return;
 }

	// The base window plays its closing sound when the slide finishes.
	bool closes = hit == HIT_BACK || hit == HIT_HANDLE
		|| (( hit == HIT_POPUP_CANCEL || hit == HIT_BACKDROP ) && m_iPopup < 0 );
	if( hit < HIT_MESSAGE && !closes )
		CZM_PlayClick();

	switch( hit )
	{
	case HIT_BACK:
	case HIT_HANDLE:
		Hide();
		return;
	case HIT_INPUT:
		if( !CZM_OnlineBan( NULL, NULL, NULL ))
			BeginInput();
		return;
	case HIT_SEND:
		Send();
		return;

 case HIT_POPUP_COPY:
  if(m_iPopup>=0&&m_iPopup<m_rooms[m_iRoom].messages.Count()){
   if(CZM_CopyText(m_rooms[m_iRoom].messages[m_iPopup].text))Toast(CZM_IsRussian()?"Сообщение скопировано":"Message copied");
  }m_iPopup=-1;return;
 case HIT_POPUP_AVATAR:
  if(m_iPopup>=0&&m_iPopup<m_rooms[m_iRoom].messages.Count()){
   const CzmChatMessage&m=m_rooms[m_iRoom].messages[m_iPopup];EndInput();CZM_OpenProfile(m.player,m.id);
  }m_iPopup=-1;return;
 case HIT_POPUP_MESSAGE:
  if(!m_reportConfirm){m_reportConfirm=true;return;}
  Report(false);m_iPopup=-1;m_reportConfirm=false;return;

	case HIT_POPUP_CANCEL:
	case HIT_BACKDROP:
		if( m_iPopup >= 0 ) m_iPopup = -1;
		else Hide();
		return;
	}

	if( hit >= HIT_ROOM && hit < HIT_ROOM + ROOMS )
	{
		m_iRoom = hit - HIT_ROOM;
		EngFuncs::CvarSetValue( "czm_chat_room", m_iRoom );
		m_flScroll = 0.0f;
		m_flVelocity = 0.0f;
		m_rooms[m_iRoom].nextPoll = 0.0;
		return;
	}


 // Only the avatar/name opens a profile; body taps leave the conversation in place.
 if(hit>=HIT_PROFILE&&hit<HIT_PROFILE+MAX_MESSAGES){
  const int index=hit-HIT_PROFILE;CzmChatRoom&room=m_rooms[m_iRoom];
  if(index>=0&&index<room.messages.Count()){EndInput();CZM_OpenProfile(room.messages[index].player,room.messages[index].id);}
 }

}

bool CCzmChat::KeyDown( int key )
{
	if( m_bClosing ) return true;
	Layout();

	if( m_bTyping )
	{
		if( UI::Key::IsBackspace( key ))
		{
			size_t len = strlen( m_szInput );
			if( len > 0 )
			{
				len--;
				while( len > 0 && ( (unsigned char)m_szInput[len] & 0xC0 ) == 0x80 )
					len--;
				m_szInput[len] = 0;
			}
			return true;
		}
		if( UI::Key::IsEnter( key ))
		{
			Send();
			return true;
		}
	}

	if( UI::Key::IsLeftMouse( key ))
	{
		int hit = HitTest();

		if( m_bTyping && hit != HIT_INPUT && hit != HIT_SEND )
			EndInput();

		m_iPressed = hit;
		m_iDownY = m_iLastMoveY = uiStatic.cursorY;
		m_flLastMoveTime = EngFuncs::DoubleTime();
		m_flScrollAtDown = m_flScroll;
		m_flVelocity = 0.0f;
		m_bScrolling = false;
		m_bHandleDrag = hit == HIT_HANDLE;
		m_bMaybeScroll = m_iPopup < 0 && m_clip.HasCursor();
		return true;
	}

	if( key == K_MWHEELDOWN || key == K_MWHEELUP )
	{
		m_flScroll += ( key == K_MWHEELUP ? 1 : -1 ) * H * 0.1f;
		return true;
	}

	if( UI::Key::IsEscape( key ))
	{
		if( m_iPopup >= 0 )
		{
			m_iPopup = -1;
			CZM_PlayClick();
		}
		else if( m_bTyping )
		{
			EndInput();
			CZM_PlayClick();
		}
		else
			Hide();
		return true;
	}

	return CMenuFramework::KeyDown( key );
}

bool CCzmChat::KeyUp( int key )
{
	if( UI::Key::IsLeftMouse( key ))
	{
		int pressed = m_iPressed;
		bool tap = !m_bScrolling;
		int hit;

		Layout();
		hit = HitTest();
		m_iPressed = HIT_NONE;
		if( m_bScrolling && EngFuncs::DoubleTime() - m_flLastMoveTime > 0.08 )
			m_flVelocity = 0.0f;
		m_bMaybeScroll = m_bScrolling = m_bHandleDrag = false;

		if( tap && hit != HIT_NONE && hit == pressed )
			Activate( hit );
		return true;
	}

	return CMenuFramework::KeyUp( key );
}

bool CCzmChat::MouseMove( int x, int y )
{
	CMenuFramework::MouseMove( x, y );
	if( m_bHandleDrag && uiStatic.cursorY - m_iDownY > ScreenHeight * 0.065f )
	{
		m_iPressed = HIT_NONE;
		Hide();
		return true;
	}

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

			// pulling down shows older messages
			m_flScroll = m_flScrollAtDown + dy;
			if( dt > 0.001 )
				m_flVelocity = m_flVelocity * 0.3f + ( uiStatic.cursorY - m_iLastMoveY ) / dt * 0.7f;
		}

		m_iLastMoveY = uiStatic.cursorY;
		m_flLastMoveTime = now;
	}

	return true;
}

void CCzmChat::Char( int ch )
{
	size_t len;

	if( !m_bTyping || ch < 32 )
		return;

	len = strlen( m_szInput );
	if( len + 4 >= sizeof( m_szInput ))
		return;
	// the limit is in letters; continuation bytes of a letter always fit
	if(( ch & 0xC0 ) != 0x80 && Utf8Chars( m_szInput ) >= INPUT_CHARS )
		return;

	m_szInput[len] = (char)ch;
	m_szInput[len + 1] = 0;
}

/*
=================
drawing
=================
*/
static unsigned int NickColor( int player, bool mine )
{
	static const unsigned int colors[6] =
	{
		PackRGBA( 125, 196, 255, 255 ), PackRGBA( 134, 239, 172, 255 ), PackRGBA( 253, 186, 116, 255 ),
		PackRGBA( 196, 181, 253, 255 ), PackRGBA( 103, 232, 249, 255 ), PackRGBA( 249, 168, 212, 255 ),
	};

	return mine ? PackRGBA( 248, 113, 113, 255 ) : colors[(unsigned int)player % 6];
}

static void FormatTime( int t, char *out, size_t size )
{
	time_t when = t, now = time( NULL );
	struct tm a, b;

	a = *localtime( &when );
	b = *localtime( &now );
	if( a.tm_yday == b.tm_yday && a.tm_year == b.tm_year )
		strftime( out, size, "%H:%M", &a );
	else
		strftime( out, size, "%d.%m %H:%M", &a );
}


void CCzmChat::DrawMessages(void)
{
 CzmChatRoom&room=m_rooms[m_iRoom];using namespace CzmStyle;
 if(!CZM_NetAvailable()||(!CZM_OnlineReady()&&!room.loaded)){
  Text(m_panel,CZM_T(CZM_NetAvailable()?"chat_connecting":"chat_offline"),CZMF_CHAT_TEXT,Muted(),QM_CENTER);return;
 }
 if(!room.loaded||!room.messages.Count()){
  Text(m_panel,CZM_T(room.loaded?"chat_empty":"chat_loading"),CZMF_CHAT_TEXT,Muted(),QM_CENTER);return;
 }
 const int maxScroll=Q_max(0,ContentHeight()-m_clip.h);m_flScroll=bound(0.0f,m_flScroll,(float)maxScroll);
 UI::Scissor::PushScissor(m_clip.x,m_clip.y,m_clip.w,m_clip.h);
 int bottom=m_clip.y+m_clip.h+(int)m_flScroll;
 for(int i=room.messages.Count()-1;i>=0&&bottom>m_clip.y;i--){
  CzmChatMessage&m=room.messages[i];bottom-=RowHeight(i);int top=bottom;if(top>m_clip.y+m_clip.h)continue;
  if(DateBefore(i)){CzmConversation::Date(m_clip,top,m.time);top+=CzmConversation::DateHeight();}
  const bool mine=m.player==CZM_OnlinePlayer();const char*nick=mine?(CZM_IsRussian()?"Вы":"You"):m.nick;
  const CzmConversation::Bubble bubble=CzmConversation::Layout(m_clip,top,m.text,nick,mine,false,m.role,m.project,m.place);
  CzmConversation::Draw(bubble,m.text,nick,CZM_AvatarFor(m.avatar,m.player),m.time,mine,false,IsPressed(HIT_OPTIONS+i),m.role,m.project,m.place);
 }
 UI::Scissor::PopScissor();
}

void CCzmChat::DrawInput( void )
{
	HFont font = CZM_Font( CZMF_TILE_STATUS );
	const CzmRect &r = m_input;
	int pad = r.h * 0.45f, textY = r.y + ( r.h - CZM_FontHeight( font )) / 2, textW = r.w - pad * 2;
	int until;
	bool forever;
	const char *reason;
	char text[256];

	if( CZM_OnlineBan( &until, &forever, &reason ))
	{
		char date[32];
		time_t t = until;

		strftime( date, sizeof( date ), "%d.%m.%Y %H:%M", localtime( &t ));
		if( forever )
			snprintf( text, sizeof( text ), "%s", CZM_T( "chat_banned_forever" ));
		else
			snprintf( text, sizeof( text ), CZM_T( "chat_banned_until" ), date );

		CZM_DrawPill( UI_DIR "button_danger.png", r.x, r.y, m_send.x + m_send.w - r.x, r.h );
		CZM_DrawText( font, r.x + pad, textY, m_send.x + m_send.w - r.x - pad * 2, text, PackRGBA( 255, 170, 170, 255 ));
		return;
	}

	CZM_DrawPill( m_bTyping ? UI_DIR "button_danger.png" : UI_DIR "button_secondary.png", r.x, r.y, r.w, r.h,
		IsPressed( HIT_INPUT ) ? PackRGBA( 200, 200, 200, 255 ) : CZM_White());

	if( m_szInput[0] )
	{
		const char *p = m_szInput;
		int w;

		// the end of a long message stays visible while typing
		while( *p && CZM_TextWidth( font, p ) > textW )
		{
			p++;
			while(( *p & 0xC0 ) == 0x80 )
				p++;
		}
		CZM_DrawText( font, r.x + pad, textY, textW, p, CZM_White());
		w = Q_min( CZM_TextWidth( font, p ), textW );
		if( m_bTyping && ( uiStatic.realTime / 500 ) % 2 == 0 )
			UI_FillRect( r.x + pad + w + 2, textY, Q_max( 2, H / 400 ), CZM_FontHeight( font ), PackRGBA( 239, 68, 68, 255 ));
	}
	else
	{
		snprintf( text, sizeof( text ), CZM_T( "chat_placeholder" ), s_roomNames[m_iRoom] );
		CZM_DrawText( font, r.x + pad, textY, textW, text, PackRGBA( 130, 136, 146, 255 ));
		if( m_bTyping && ( uiStatic.realTime / 500 ) % 2 == 0 )
			UI_FillRect( r.x + pad, textY, Q_max( 2, H / 400 ), CZM_FontHeight( font ), PackRGBA( 239, 68, 68, 255 ));
	}

	// send: red when there is something to send
	{
		int icon = m_send.h * 0.44f;
		bool ready = m_szInput[0] && !m_iSendId;

		CZM_DrawImage( ready ? UI_DIR "pill_lang_on.png" : UI_DIR "chip_round.png", m_send.x, m_send.y, m_send.w, m_send.h,
			IsPressed( HIT_SEND ) ? PackRGBA( 180, 180, 180, 255 ) : CZM_White());
		CZM_DrawImage( UI_DIR "icon_send.png", m_send.x + ( m_send.w - icon ) / 2 - icon / 12, m_send.y + ( m_send.h - icon ) / 2, icon, icon,
			ready ? CZM_White() : PackRGBA( 150, 156, 166, 255 ));
	}
}


void CCzmChat::DrawPopup(void)
{
 if(m_iPopup<0||m_iPopup>=m_rooms[m_iRoom].messages.Count()){m_iPopup=-1;return;}
 using namespace CzmStyle;const CzmChatMessage&m=m_rooms[m_iRoom].messages[m_iPopup];
 UI_FillRect(0,0,W,H,PackRGBA(0,0,0,185));Surface(m_popup,PackRGBA(16,22,32,255));
 const int inset=Q_max(8,H/45),x=m_popup.x+inset,y=m_popup.y+inset,w=m_popup.w-inset*2;
 Text(CZM_Rect(x,y,w,CZM_FontHeight(CZM_Font(CZMF_LANG))),m_reportConfirm?(CZM_IsRussian()?"Пожаловаться на сообщение?":"Report this message?"):m.nick,CZMF_LANG);
 const int quoteY=y+CZM_FontHeight(CZM_Font(CZMF_LANG))+inset/2;
 TextLines(CZM_Rect(x,quoteY,w,Q_max(0,(m_reportConfirm?m_popupMessage.y:m_popupCopy.y)-quoteY-inset/2)),m.text,CZMF_UI_LABEL,Muted());
 if(!m_reportConfirm){
  Button(m_popupCopy,CZM_IsRussian()?"Скопировать":"Copy",true,false,IsPressed(HIT_POPUP_COPY));
  Button(m_popupAvatar,CZM_IsRussian()?"Открыть профиль":"View profile",true,false,IsPressed(HIT_POPUP_AVATAR));
 }
 if(m_popupMessage.w)Button(m_popupMessage,m_reportConfirm?(CZM_IsRussian()?"Отправить жалобу":"Send report"):(CZM_IsRussian()?"Пожаловаться":"Report message"),true,m_reportConfirm,IsPressed(HIT_POPUP_MESSAGE));
 Button(m_popupCancel,CZM_IsRussian()?"Отмена":"Cancel",true,false,IsPressed(HIT_POPUP_CANCEL));
}

void CCzmChat::Draw()
{
	HFont titleFont = CZM_Font( CZMF_PANEL_TITLE );
	HFont tabFont = CZM_Font( CZMF_TILE_STATUS );
	double now = EngFuncs::DoubleTime();
	float dt = (float)bound( 0.0, now - m_flLastDraw, 0.05 );
	int icon;

	m_flLastDraw = now;
	m_flOpen = bound( 0.0f, m_flOpen + ( m_bClosing ? -1.0f : 1.0f ) * dt / 0.24f, 1.0f );
	if( m_bClosing && m_flOpen <= 0.0f )
	{
		m_bClosing = false;
		CMenuFramework::Hide();
		DisableTransition();
		return;
	}
	Layout();
	Poll();
	Layout(); // polling may prune the selected message; resolve its ID before drawing

	// fling
	if( !m_bScrolling && fabsf( m_flVelocity ) > 1.0f )
	{
		m_flScroll += m_flVelocity * dt;
		m_flVelocity *= expf( -3.5f * dt );
		if( fabsf( m_flVelocity ) < 20.0f )
			m_flVelocity = 0.0f;
	}

	// the menu behind goes dark and the sheet is solid: tiles and the logo must not show through
	UI_FillRect( 0, 0, W, H, PackRGBA( 0, 0, 0, (int)( 185 * m_flOpen )));
	CzmStyle::Surface(m_sheet,PackRGBA(13,19,28,255),PackRGBA(58,69,86,255),Q_max(8,H/45));
	CZM_DrawPill( UI_DIR "button_secondary.png", W / 2 - H * 0.055f, m_sheet.y + H * 0.018f, H * 0.11f, H * 0.008f, PackRGBA( 210, 216, 228, 210 ));

	// header: back, title, rooms
	CZM_DrawImage( UI_DIR "chip_round.png", m_back.x, m_back.y, m_back.w, m_back.h, IsPressed( HIT_BACK ) ? PackRGBA( 170, 170, 170, 255 ) : CZM_White());
	icon = m_back.h * 0.48f;
	CZM_DrawImage( UI_DIR "icon_back.png", m_back.x + ( m_back.w - icon ) / 2, m_back.y + ( m_back.h - icon ) / 2, icon, icon );
	CZM_DrawText( titleFont, m_back.x + m_back.w + H * 0.03f, m_back.y + ( m_back.h - CZM_FontHeight( titleFont )) / 2, W / 3,
		CZM_T( "chat_title" ), CZM_White());

	{
		CzmRect bar = CZM_Rect( m_rooms_[0].x, m_rooms_[0].y, m_rooms_[ROOMS - 1].x + m_rooms_[ROOMS - 1].w - m_rooms_[0].x, m_rooms_[0].h );
		int inset = bar.h * 0.09f;

		CZM_DrawPill( UI_DIR "chip_lang.png", bar.x, bar.y, bar.w, bar.h );
		for( int i = 0; i < ROOMS; i++ )
		{
			const CzmRect &r = m_rooms_[i];
			bool active = i == m_iRoom;

			if( active )
				CZM_DrawPill( UI_DIR "pill_lang_on.png", r.x + inset, r.y + inset, r.w - inset * 2, r.h - inset * 2 );
			CZM_DrawText( tabFont, r.x, r.y + ( r.h - CZM_FontHeight( tabFont )) / 2, r.w, s_roomNames[i],
				active || IsPressed( HIT_ROOM + i ) ? CZM_White() : PackRGBA( 170, 176, 186, 255 ), QM_CENTER );
			const int n=CZM_ChatUnread(i);
			if(n>0){const int bh=Q_max(16,r.h/2),bw=CZM_CountBadgeWidth(n,bh);
				CZM_DrawCountBadge(CZM_Rect(r.x+r.w-bw/2,r.y-bh/3,bw,bh),n);}
		}

		// Keep rules on their own line, including narrow screens.
		{
			HFont small = CZM_Font( CZMF_SMALL );
			CZM_DrawText( small, m_panel.x, m_panel.y - CZM_FontHeight( small ) - H * 0.012f, m_panel.w, CZM_T( "chat_rules" ),
				PackRGBA( 150, 156, 168, 255 ));
		}
	}

	DrawMessages();
	DrawInput();

	if( m_szToast[0] && now - m_flToastTime < 2.5 )
	{
		HFont font = CZM_Font( CZMF_TILE_STATUS );
		int tw = CZM_TextWidth( font, m_szToast ) + H * 0.08f, th = H * 0.07f;
		CzmRect r = CZM_Rect(( W - tw ) / 2, m_input.y - th - H * 0.03f, tw, th );

		CZM_DrawPill( UI_DIR "button_secondary.png", r.x, r.y, r.w, r.h );
		CZM_DrawText( font, r.x, r.y + ( r.h - CZM_FontHeight( font )) / 2, r.w, m_szToast, CZM_White(), QM_CENTER );
	}

	if( m_iPopup >= 0 )
		DrawPopup();
}

ADD_MENU3( menu_czmchat, CCzmChat, UI_CzmChat_Menu );

void CCzmChat::AfterRules( void )
{
	if( menu_czmchat && menu_czmchat->m_szInput[0] )
		menu_czmchat->Send();
}

void UI_CzmChat_Menu( void )
{
	menu_czmchat->Show();
}

void CZM_OpenChat( void )
{
	UI_CzmChat_Menu();
}

// a blocked player disappears at once; the service leaves him out of the next answers
void CZM_ChatHidePlayer( int player )
{
	if( !menu_czmchat || player <= 0 )
		return;
	for( int r = 0; r < ROOMS; r++ )
	{
		CUtlVector<CzmChatMessage> &messages = menu_czmchat->m_rooms[r].messages;
		for( int i = messages.Count() - 1; i >= 0; i-- )
			if( messages[i].player == player )
				messages.Remove( i );
	}
	menu_czmchat->m_iPopup = -1;
}
