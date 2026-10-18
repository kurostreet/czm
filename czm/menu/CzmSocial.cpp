/* Account profiles, friends and private messages. GPL-3.0-or-later. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <math.h>
#include "extdll_menu.h"
#include "BaseMenu.h"
#include "Utils.h"
#include "Framework.h"
#include "Scissor.h"
#include "keydefs.h"
#include "CzmMenu.h"
#include "CzmJson.h"
#include "../../common/czm_tab.h"

#define UI_DIR "gfx/czm/ui/"

namespace {
const char *T( const char *ru, const char *en ) { return CZM_IsRussian() ? ru : en; }
const int PROFILE_STATUS_LINES=4;
const char *s_kinds[] = { "friends", "dialogs", "followers", "following", "blocked" };
char s_key[80];
int s_epoch, s_unread, s_requests, s_friends, s_followers, s_following;
int s_identity=-1;
bool s_sessionInvalid;
int s_presence, s_presenceEpoch;
double s_nextPresence;
char s_connection[160];
CUtlVector<int> s_abandoned;

bool Account() { return !s_sessionInvalid && CZM_OnlineAccount(); }
void Abandon( int &id ) { if( id ) s_abandoned.AddToTail( id ); id = 0; }
void Counts( const CzmJson &j )
{
	int c = j.Get( 0, "counts" );
	if( j.Type( c ) != CzmJson::T_OBJECT ) return;
	s_unread = j.Int( j.Get( c, "unread" )); s_requests = j.Int( j.Get( c, "requests" ));
	s_friends = j.Int( j.Get( c, "friends" )); s_followers = j.Int( j.Get( c, "followers" ));
	s_following = j.Int( j.Get( c, "following" ));
}

const char *SocialError( const char *code )
{
	if( !strcmp( code, "account_required" ) || !strcmp( code, "session" )) return T( "Войдите в аккаунт, чтобы пользоваться друзьями и ЛС", "Sign in to use friends and messages" );
	if( !strcmp( code, "not_found" ) || !strcmp( code, "account_not_found" )) return T( "Игрок с таким ID не найден", "No player with this ID" );
	if( !strcmp( code, "not_friends" )) return T( "Отправлять сообщения можно только взаимным друзьям", "Messages require mutual friendship" );
	if( !strcmp( code, "unavailable" )) return T( "Действие недоступно", "Action unavailable" );
	if( !strcmp( code, "banned" )) return T( "Общение ограничено модератором", "Messaging is restricted by a moderator" );
	if( !strcmp( code, "slow" ) || !strcmp( code, "limit" )) return T( "Слишком часто. Попробуйте позже", "Too many requests. Try later" );
	if( !strcmp( code, "empty" )) return T( "Введите сообщение", "Enter a message" );
	return T( "Нет связи. Нажмите обновить и повторите", "Connection failed. Refresh and try again" );
}

struct Person
{
	int id, created, lastSeen, friends, followers, following, unread;
	bool account, online, playing;
	char nick[100], avatar[32], status[404], relation[24], server[64], map[65], last[1604];
};
struct Message { int id, player, time; bool deleted; char text[1604]; };

/*
A game invite as the service stores it: "czm:invite gs 1.2.3.4:27015 Server name".
Only the invite request makes this text; typed messages have their addresses masked.
*/
bool ParseInvite( const char *text, char *proto, char *address, char *name, size_t nameSize )
{
	if( strncmp( text, "czm:invite ", 11 )) return false;
	const char *p = text + 11;
	if( strncmp( p, "gs ", 3 ) && strncmp( p, "49 ", 3 )) return false;
	memcpy( proto, p, 2 ); proto[2] = 0; p += 3;
	size_t n = strcspn( p, " " );
	if( !n || n >= 22 ) return false;
	memcpy( address, p, n ); address[n] = 0;
	if( strspn( address, "0123456789.:" ) != n || !strchr( address, ':' )) return false;
	p += n; while( *p == ' ' ) p++;
	Q_strncpy( name, *p ? p : address, nameSize );
	return true;
}

void ReadPerson( Person &p, const CzmJson &j, int item )
{
	memset( &p, 0, sizeof( p ));
	p.id = j.Int( j.Get( item, "id" )); p.created = j.Int( j.Get( item, "created" )); p.lastSeen = j.Int( j.Get( item, "last_seen" ));
	p.account = j.Bool( j.Get( item, "account" )); p.online = j.Bool( j.Get( item, "online" )); p.playing = j.Bool( j.Get( item, "playing" ));
	p.unread = j.Int( j.Get( item, "unread" ));
	Q_strncpy( p.nick, j.String( j.Get( item, "nick" )), sizeof( p.nick ));
	Q_strncpy( p.avatar, j.String( j.Get( item, "avatar" )), sizeof( p.avatar ));
	Q_strncpy( p.status, j.String( j.Get( item, "status" )), sizeof( p.status ));
	Q_strncpy( p.relation, j.String( j.Get( item, "relation" )), sizeof( p.relation ));
	Q_strncpy( p.server, j.String( j.Get( item, "server" )), sizeof( p.server ));
	Q_strncpy( p.map, j.String( j.Get( item, "map" )), sizeof( p.map ));
	int c = j.Get( item, "counts" );
	p.friends = j.Int( j.Get( c, "friends" )); p.followers = j.Int( j.Get( c, "followers" )); p.following = j.Int( j.Get( c, "following" ));
	int last = j.Get( item, "last" );
	Q_strncpy( p.last, j.Bool( j.Get( last, "deleted" )) ? T( "Сообщение удалено модератором", "Message removed by a moderator" ) : j.String( j.Get( last, "t" )), sizeof( p.last ));
}

void SeenText( const Person &p, char *out, size_t size )
{
	if( p.online ) { Q_strncpy( out, p.playing ? T( "Онлайн · В игре", "Online · In game" ) : T( "Онлайн · В меню", "Online · In menu" ), size ); return; }
	if( !p.lastSeen ) { Q_strncpy( out, T( "Офлайн", "Offline" ), size ); return; }
	time_t value = p.lastSeen, current = time( NULL ); struct tm then, today;
	localtime_r( &value, &then ); localtime_r( &current, &today );
	char when[40];
	strftime( when, sizeof( when ), then.tm_year == today.tm_year && then.tm_yday == today.tm_yday ? "%H:%M" : "%H:%M %d.%m.%Y", &then );
	snprintf( out, size, "%s %s", T( "Последний заход", "Last seen" ), when );
}

void Label( const CzmRect &r, const char *text, int font = CZMF_PANEL_TEXT, unsigned color = 0 )
{
	HFont f = CZM_Font( font ); CZM_DrawText( f, r.x, r.y + ( r.h - CZM_FontHeight( f )) / 2, r.w, text, color ? color : CZM_White() );
}
void Button( const CzmRect &r, const char *text, bool primary = false, bool pressed = false, bool enabled = true )
{
	int font = CZMF_LANG;
	if( CZM_TextWidth( CZM_Font( font ), text ) > r.w-r.h/2 ) font = CZMF_PANEL_TEXT;
	if( CZM_TextWidth( CZM_Font( font ), text ) > r.w-r.h/2 ) font = CZMF_SMALL;
	CZM_DrawButton( primary ? UI_DIR "button_primary.png" : UI_DIR "button_secondary.png", r, text, enabled ? CZM_White() : CZM_Grey(), pressed && enabled, font );
}
int Letters( const char *text ) { int n=0; for( ; *text; text++ ) if( ( *text & 0xc0 ) != 0x80 ) n++; return n; }
}

class CCzmSocial : public CMenuFramework
{
public:
	CCzmSocial();
	void Show() override;
	void Hide() override;
	void Forget();
	void Draw() override;
	bool IsRoot() const override { return false; }
	bool KeyDown( int key ) override;
	bool KeyUp( int key ) override;
	bool MouseMove( int x, int y ) override;
	void Char( int key ) override;
	void OpenProfile( int id, bool outside, int chatMessage = 0 );
	void Frame();
private:
	enum { LIST, PROFILE, DIALOG };
	enum { BACK=1, MINE, BLOCKED, REFRESH, FIELD, SEARCH, SEND, PREVIOUS, NEXT, PRIMARY, SECONDARY, BLOCK, REPORT, COPY, EDIT, SETTINGS, JOIN, CANCEL, CONFIRM, PEER, LOGIN, REPORT_CHAT, BACKDROP, INVITE, TAB=100, PICK=200, ROW=1000 };
	enum { MAX_PICKS = 4 };
	enum { READ_LIST=1, READ_PROFILE, READ_DIALOG, WRITE_ACTION, WRITE_STATUS, WRITE_MESSAGE, WRITE_REPORT };
	void Layout(); void LayoutProfile(); int Hit(); void Activate( int hit ); void Navigate( int mode ); void Fetch();
	void Write( int kind, const char *path, const char *body ); void Follow( const char *action ); void Send();
	void Input( const char *value ); void EndInput(); void Notice( const char *text ); void Read( const CzmJson &j, int kind );
	void DrawList(); void DrawProfile(); void DrawDialog(); void Field( const char *placeholder );
	int MessageHeight( const Message &m );
	void BuildPicks(); void SendInvite( int index ); void DrawPicker();
	bool Pressed( int hit ) { return m_pressed == hit && Hit() == hit; }
	int m_mode, m_tab, m_target, m_returnMode, m_view, m_epoch, m_pressed, m_chatMessage;
	int m_read, m_readView, m_readKind, m_write, m_writeView, m_writeKind, m_ack;
	int m_offset, m_nextOffset, m_before, m_nextBefore;
	bool m_open, m_typing, m_loaded, m_canSend, m_editStatus, m_outside, m_joinPending;
	bool m_drag, m_moved; int m_downY; float m_downScroll, m_scroll;
	char m_input[1604], m_sent[1604], m_nonce[80], m_nonceText[1604], m_notice[220], m_confirm[24];
	double m_nextFetch, m_noticeUntil;
	Person m_profile; CUtlVector<Person> m_people; CUtlVector<Message> m_messages;
	CzmRect m_panel, m_back, m_mine, m_blocked, m_refresh, m_tabs[4], m_field, m_search, m_clip, m_prev, m_next;
	CzmRect m_primary, m_secondary, m_block, m_report, m_copy, m_edit, m_settings, m_join, m_peer, m_confirmPanel, m_confirmYes, m_confirmNo;
	CzmRect m_hero, m_profileStatus, m_profileInfo, m_profileCounts[3], m_profileHint, m_profileServer, m_reportChat;
	// "invite to game": the server I play on now and the servers pinned with a heart
	bool m_pickOpen; int m_pickCount;
	char m_pickAddress[MAX_PICKS][64], m_pickProto[MAX_PICKS][4], m_pickName[MAX_PICKS][64];
	CzmRect m_invite, m_pickPanel, m_pick[MAX_PICKS], m_pickCancel;
	int W, H, pad;
};
static CCzmSocial *s_window;

CCzmSocial::CCzmSocial() : CMenuFramework( "CzmSocial" )
{
	s_window=this; m_mode=LIST; m_tab=m_target=m_view=m_epoch=m_pressed=m_returnMode=m_chatMessage=0;
	m_read=m_readView=m_readKind=m_write=m_writeView=m_writeKind=m_ack=0;
	m_offset=m_before=m_nextBefore=0; m_nextOffset=-1;
	m_open=m_typing=m_loaded=m_canSend=m_editStatus=m_outside=m_joinPending=m_drag=m_moved=false;
	m_pickOpen=false; m_pickCount=0;
	m_scroll=m_downScroll=0; m_downY=0; m_nextFetch=m_noticeUntil=0; W=H=pad=0;
	m_input[0]=m_sent[0]=m_nonce[0]=m_nonceText[0]=m_notice[0]=m_confirm[0]=0;
	memset( &m_profile,0,sizeof( m_profile ));
}

// The window keeps being drawn while its closing animation plays, so what was on screen stays
// until the next opening: clearing it in Hide() flashed an empty guest profile with its buttons.
void CCzmSocial::Forget()
{
	m_people.RemoveAll(); m_messages.RemoveAll(); memset( &m_profile,0,sizeof( m_profile ));
}
void CCzmSocial::Show()
{
	CZM_Init(); m_epoch=s_epoch; m_mode=LIST; m_tab=0; m_outside=false; m_target=0;
	if( !m_open ) { Forget(); CMenuFramework::Show(); } m_open=true; Navigate( LIST );
}
void CCzmSocial::Hide()
{
	EndInput(); m_open=false; m_chatMessage=0; m_confirm[0]=0; m_input[0]=m_sent[0]=m_nonce[0]=m_nonceText[0]=0;
	m_pickOpen=false; m_pressed=0;
	m_view++; CMenuFramework::Hide();
}
void CCzmSocial::OpenProfile( int id, bool outside, int chatMessage )
{
	if( id<=0 ) return;
	if( !m_open ) { Forget(); CMenuFramework::Show(); m_open=true; m_epoch=s_epoch; }
	m_outside=outside; m_returnMode=m_mode==DIALOG?DIALOG:LIST; m_target=id; Navigate( PROFILE );
	m_chatMessage=chatMessage;
}
void CCzmSocial::Navigate( int mode )
{
	EndInput(); m_mode=mode; m_view++; m_loaded=false; m_scroll=0; m_nextFetch=0; m_pressed=0;
	m_chatMessage=0;
	m_editStatus=false; m_confirm[0]=0; m_input[0]=0; m_notice[0]=0; m_joinPending=false; m_pickOpen=false;
	if( mode==LIST ) { m_offset=0; m_people.RemoveAll(); }
	if( mode==DIALOG ) { m_before=m_nextBefore=0; m_messages.RemoveAll(); m_canSend=false; if(m_profile.id!=m_target)memset(&m_profile,0,sizeof(m_profile)); }
	if( mode==PROFILE ) memset( &m_profile,0,sizeof( m_profile ));
}
void CCzmSocial::Notice( const char *text ) { Q_strncpy( m_notice,text,sizeof( m_notice )); m_noticeUntil=EngFuncs::DoubleTime()+4; }
void CCzmSocial::Input( const char *value )
{
	if( value != m_input ) Q_strncpy( m_input,value,sizeof( m_input ));
	m_typing=true;
	EngFuncs::SetTextInputRect( m_field.x,m_field.y,m_field.w,m_field.h ); UI_EnableTextInput( true );
}
void CCzmSocial::EndInput() { if( m_typing ) UI_EnableTextInput( false ); m_typing=false; }

void CCzmSocial::Fetch()
{
	if( m_read || !CZM_OnlineReady() ) return;
	if( m_mode!=PROFILE && !Account() ) return;
	char path[160];
	if( m_mode==LIST ) { m_readKind=READ_LIST;
		if( m_tab==1 ) snprintf( path,sizeof(path),"/api/v1/social/dialogs?offset=%d",m_offset );
		else snprintf( path,sizeof(path),"/api/v1/social/people/%s?offset=%d",s_kinds[m_tab],m_offset ); }
	else if( m_mode==PROFILE ) { m_readKind=READ_PROFILE; snprintf( path,sizeof(path),"/api/v1/social/profile/%d",m_target ); }
	else { m_readKind=READ_DIALOG; snprintf( path,sizeof(path),"/api/v1/social/dialog/%d?before=%d",m_target,m_before ); }
	m_readView=m_view; m_read=CZM_NetRequest("GET",CZM_OnlineUrl(path),CZM_OnlineKey(),"");
	m_nextFetch=EngFuncs::DoubleTime()+(m_mode==DIALOG?3:10);
}
void CCzmSocial::Write( int kind,const char *path,const char *body )
{
	if( m_write ) return;
	m_writeKind=kind; m_writeView=m_view;
	m_write=CZM_NetRequest("POST",CZM_OnlineUrl(path),CZM_OnlineKey(),body);
	if( !m_write ) Notice( SocialError( "" ));
}
void CCzmSocial::Follow( const char *action )
{
	if( !Account() ) { CZM_AccountShow(CZM_OnlineKey(),EngFuncs::GetCvarString("name")); return; }
	char body[128]; snprintf(body,sizeof(body),"{\"target\":%d,\"action\":\"%s\"}",m_target,action);
	Write(WRITE_ACTION,"/api/v1/social/action",body);
}
void CCzmSocial::Send()
{
	if( m_write || !m_canSend || !m_input[0] ) return;
	if( strcmp(m_input,m_nonceText) || !m_nonce[0] ) { CZM_NetNewKey(m_nonce,sizeof(m_nonce)); Q_strncpy(m_nonceText,m_input,sizeof(m_nonceText)); }
	CUtlString body; body.Append("{\"text\":"); CZM_JsonQuote(body,m_input); body.Append(",\"nonce\":"); CZM_JsonQuote(body,m_nonce); body.Append("}");
	Q_strncpy(m_sent,m_input,sizeof(m_sent)); char path[100]; snprintf(path,sizeof(path),"/api/v1/social/dialog/%d",m_target);
	Write(WRITE_MESSAGE,path,body.Get());
}

void CCzmSocial::Read( const CzmJson &j,int kind )
{
	Counts(j); m_loaded=true;
	if( kind==READ_LIST )
	{
		m_people.RemoveAll(); int list=j.Get(0,"people");
		for(int i=0;i<j.Count(list)&&i<40;i++){ Person p;ReadPerson(p,j,j.At(list,i));m_people.AddToTail(p); }
		m_nextOffset=j.Int(j.Get(0,"next"),-1);
		if(m_tab==2 && s_requests>0 && !m_write) Write(WRITE_ACTION,"/api/v1/social/action","{\"action\":\"seen\"}");
	}
	else
	{
		ReadPerson(m_profile,j,j.Get(0,"profile"));
		if(kind==READ_DIALOG)
		{
			m_canSend=j.Bool(j.Get(0,"can_send"));m_nextBefore=j.Int(j.Get(0,"before"));
			m_messages.RemoveAll();int list=j.Get(0,"messages");
			for(int i=0;i<j.Count(list)&&i<50;i++){
				int item=j.At(list,i);Message m;memset(&m,0,sizeof(m));m.id=j.Int(j.Get(item,"id"));m.player=j.Int(j.Get(item,"p"));m.time=j.Int(j.Get(item,"ts"));m.deleted=j.Bool(j.Get(item,"deleted"));
				Q_strncpy(m.text,m.deleted?T("Сообщение удалено модератором","Message removed by a moderator"):j.String(j.Get(item,"t")),sizeof(m.text));m_messages.AddToTail(m);
			}
			if(!m_ack && m_messages.Count() && !m_before && m_scroll<=1 && m_pStack->Current()==this){char path[110],body[64];snprintf(path,sizeof(path),"/api/v1/social/dialog/%d/read",m_target);snprintf(body,sizeof(body),"{\"through\":%d}",m_messages.Tail().id);m_ack=CZM_NetRequest("POST",CZM_OnlineUrl(path),CZM_OnlineKey(),body);}
		}
		if(m_joinPending){m_joinPending=false;if(m_profile.online && !strcmp(m_profile.relation,"friend") && m_profile.server[0]) {char address[64];Q_strncpy(address,m_profile.server,sizeof(address));Hide();CZM_JoinAddress(address);}else Notice(T("Друг уже вышел с сервера","Your friend has left the server"));}
	}
}

void CCzmSocial::Frame()
{
	if(m_epoch!=s_epoch){Abandon(m_read);Abandon(m_write);Abandon(m_ack);if(m_open)Hide();Forget();m_epoch=s_epoch;return;} // another account: nothing of the old one stays
	int status;CUtlString body;
	if(m_read && CZM_NetPoll(m_read,&status,body)){
		m_read=0;CzmJson j;bool parsed=j.Parse(body.Get());
		if(m_open && m_readView==m_view){if(status==200&&parsed)Read(j,m_readKind);else {m_joinPending=false;Notice(SocialError(parsed?j.String(j.Get(0,"error")):""));}}
	}
	if(m_write && CZM_NetPoll(m_write,&status,body)){
		m_write=0;CzmJson j;bool parsed=j.Parse(body.Get());
		if(status==200&&parsed){Counts(j);s_nextPresence=0;
			if(m_open&&m_writeView==m_view){
				if(m_writeKind==WRITE_MESSAGE){if(!strcmp(m_input,m_sent))m_input[0]=0;m_nonce[0]=0;m_before=0;m_scroll=0;}
				if(m_writeKind==WRITE_STATUS){m_editStatus=false;EndInput();m_input[0]=0;}
				if(m_writeKind==WRITE_REPORT)Notice(T("Жалоба отправлена","Report sent"));
				m_nextFetch=0;
			}
		}else if(m_open&&m_writeView==m_view){Notice(SocialError(parsed?j.String(j.Get(0,"error")):""));if(status==403&&m_mode==DIALOG)m_canSend=false;}
	}
	if(m_ack&&CZM_NetPoll(m_ack,&status,body)){m_ack=0;CzmJson j;if(status==200&&j.Parse(body.Get()))Counts(j);}
	if(m_open && m_pStack->Current()==this && !m_write && EngFuncs::DoubleTime()>=m_nextFetch)Fetch();
}

void CCzmSocial::LayoutProfile()
{
	pad=Q_max(8,(int)(H*.018f));
	const int width=Q_min((int)(W*.90f),(int)(H*.94f));
	const int gap=Q_max(5,(int)(H*.011f)),bh=Q_max(32,(int)(H*.06f));
	const int inner=width-pad*2,half=(inner-gap)/2;
	CzmRect empty=CZM_Rect(0,0,0,0);
	m_primary=m_secondary=m_block=m_report=m_edit=m_settings=m_join=m_field=m_search=empty;
	m_copy=m_hero=m_profileStatus=m_profileInfo=m_profileHint=m_profileServer=empty;
	for(int i=0;i<3;i++)m_profileCounts[i]=empty;
	int y=pad;
	m_back=CZM_Rect(pad,y,bh,bh);m_refresh=CZM_Rect(width-pad-bh,y,bh,bh);
	m_peer=CZM_Rect(pad+bh+gap,y,inner-bh*2-gap*2,bh);
	y+=bh+gap;
	int contentY=y;
	if(!m_loaded)y+=H*.14f;
	else {
		m_hero=CZM_Rect(pad,y,inner,H*.12f);
		int avatar=m_hero.h-gap*2,tx=pad+avatar+gap*2;
		m_copy=CZM_Rect(tx,y+gap+CZM_FontHeight(CZM_Font(CZMF_NICK)),width-pad-tx,CZM_FontHeight(CZM_Font(CZMF_SMALL))+gap/2);
		y+=m_hero.h+gap;
		int starts[PROFILE_STATUS_LINES+1],lineH=CZM_FontHeight(CZM_Font(CZMF_PANEL_TEXT))+2;
		const char *status=m_profile.status[0]?m_profile.status:m_profile.id==CZM_OnlinePlayer()?T("Нажмите, чтобы задать статус","Tap to add a status"):T("Статус не указан","No status yet");
		int lines=CZM_WrapText(CZM_Font(CZMF_PANEL_TEXT),status,inner,starts,PROFILE_STATUS_LINES);
		m_profileStatus=CZM_Rect(pad,y,inner,Q_max(1,lines)*lineH);y+=m_profileStatus.h+gap/2;
		m_profileInfo=CZM_Rect(pad,y,inner,CZM_FontHeight(CZM_Font(CZMF_SMALL))+gap);y+=m_profileInfo.h+gap/2;
		int cw=(inner-gap*2)/3;
		for(int i=0;i<3;i++)m_profileCounts[i]=CZM_Rect(pad+i*(cw+gap),y,cw,H*.075f);
		y+=m_profileCounts[0].h+gap;
		bool self=m_profile.id==CZM_OnlinePlayer();
		bool friends=!strcmp(m_profile.relation,"friend"),following=!strcmp(m_profile.relation,"following");
		bool blocked=!strcmp(m_profile.relation,"blocked"),unavailable=!strcmp(m_profile.relation,"unavailable");
		bool join=m_profile.online&&friends&&m_profile.server[0]&&!m_editStatus;
		if(!self&&!m_profile.account){
			int n=CZM_WrapText(CZM_Font(CZMF_SMALL),T("Игрок пока гость. Дружба и ЛС доступны после регистрации.","This player is a guest. Friends and messages require registration."),inner,starts,2);
			m_profileHint=CZM_Rect(pad,y,inner,n*(CZM_FontHeight(CZM_Font(CZMF_SMALL))+2));y+=m_profileHint.h+gap;
		}
		if(join){m_profileServer=CZM_Rect(pad,y,inner,(m_profile.map[0]?2:1)*(CZM_FontHeight(CZM_Font(CZMF_SMALL))+2));y+=m_profileServer.h+gap;}
		if(m_editStatus){
			m_field=CZM_Rect(pad,y,inner,H*.064f);y+=m_field.h+gap;
			m_primary=CZM_Rect(pad,y,half,bh);m_secondary=CZM_Rect(pad+half+gap,y,half,bh);y+=bh;
		}else if(self){
			m_edit=CZM_Rect(pad,y,half,bh);m_settings=CZM_Rect(pad+half+gap,y,half,bh);y+=bh;
		}else if(!m_profile.account){
			m_primary=CZM_Rect(pad,y,half,bh);m_report=CZM_Rect(pad+half+gap,y,half,bh);y+=bh;
		}else if(blocked||unavailable){
			if(blocked)m_block=CZM_Rect(pad,y,half,bh);
			m_report=CZM_Rect(blocked?pad+half+gap:pad,y,blocked?half:inner,bh);y+=bh;
		}else{
			m_primary=CZM_Rect(pad,y,join?half:inner,bh);
			if(join)m_join=CZM_Rect(pad+half+gap,y,half,bh);
			y+=bh+gap;
			int n=friends||following?3:2,bw=(inner-gap*(n-1))/n,x=pad;
			if(n==3){m_secondary=CZM_Rect(x,y,bw,bh);x+=bw+gap;}
			m_block=CZM_Rect(x,y,bw,bh);m_report=CZM_Rect(x+bw+gap,y,bw,bh);y+=bh;
		}
	}
	m_clip=CZM_Rect(pad,contentY,inner,y-contentY);
	m_panel=CZM_Rect((W-width)/2,(H-y-pad)/2,width,y+pad);
	CzmRect *rects[]={&m_back,&m_refresh,&m_peer,&m_hero,&m_copy,&m_profileStatus,&m_profileInfo,
		&m_profileCounts[0],&m_profileCounts[1],&m_profileCounts[2],&m_profileHint,&m_profileServer,
		&m_primary,&m_secondary,&m_block,&m_report,&m_edit,&m_settings,&m_join,&m_field,&m_clip};
	for(unsigned i=0;i<sizeof(rects)/sizeof(rects[0]);i++)if(rects[i]->w&&rects[i]->h){rects[i]->x+=m_panel.x;rects[i]->y+=m_panel.y;}
}

void CCzmSocial::Layout()
{
	W=ScreenWidth;H=ScreenHeight;pad=Q_max(8,(int)(H*.018f));
	int pw=Q_min((int)(W*.90f),(int)(H*1.55f)),ph=H*.82f;
	m_panel=CZM_Rect((W-pw)/2,(H-ph)/2,pw,ph);
	int x=m_panel.x+pad,y=m_panel.y+pad,bh=H*.07f,right=m_panel.x+m_panel.w-pad;
	m_back=CZM_Rect(x,y,bh,bh);m_refresh=CZM_Rect(right-bh,y,bh,bh);
	m_mine=CZM_Rect(right-H*.61f,y,H*.25f,bh);m_blocked=CZM_Rect(right-H*.34f,y,H*.24f,bh);
	m_peer=CZM_Rect(x+bh+pad,y,m_panel.w-H*.8f,bh);
	int tabsY=y+bh+pad;
	for(int i=0;i<4;i++)m_tabs[i]=CZM_Rect(x+i*(right-x)/4,tabsY,(right-x)/4-pad/2,bh);
	m_search=CZM_Rect(right-H*.18f,tabsY+bh+pad,H*.18f,bh);
	m_field=CZM_Rect(x,m_search.y,right-x-H*.18f-pad,bh);
	m_prev=CZM_Rect(x,m_panel.y+m_panel.h-pad-bh,H*.29f,bh);
	m_next=CZM_Rect(right-H*.29f,m_prev.y,H*.29f,bh);
	m_clip=CZM_Rect(x,m_field.y+bh+pad,right-x,m_prev.y-pad-(m_field.y+bh+pad));
	m_invite=CZM_Rect(right-bh-pad-H*.34f,y,H*.34f,bh);
	if(m_pickOpen){
		int pw2=Q_min((int)(W*.8f),(int)(H*.9f)),rowH=H*.085f,title=CZM_FontHeight(CZM_Font(CZMF_NICK))+pad;
		int ph2=pad*2+title+m_pickCount*(rowH+pad/2)+pad+bh;
		m_pickPanel=CZM_Rect((W-pw2)/2,(H-ph2)/2,pw2,ph2);
		for(int i=0;i<m_pickCount;i++)m_pick[i]=CZM_Rect(m_pickPanel.x+pad,m_pickPanel.y+pad+title+i*(rowH+pad/2),pw2-pad*2,rowH);
		m_pickCancel=CZM_Rect(m_pickPanel.x+pad,m_pickPanel.y+ph2-pad-bh,pw2-pad*2,bh);
	}
	if(m_mode==DIALOG){m_field=CZM_Rect(x,m_prev.y,right-x-H*.18f-pad,bh);m_search=CZM_Rect(right-H*.18f,m_prev.y,H*.18f,bh);m_clip=CZM_Rect(x,tabsY+bh+pad,right-x,m_field.y-pad-(tabsY+bh+pad));}
	int gap=pad,bw=(right-x-gap*2)/3;
	m_primary=CZM_Rect(x,m_prev.y-bh-pad,bw,bh);m_secondary=CZM_Rect(x+bw+gap,m_primary.y,bw,bh);m_block=CZM_Rect(x+(bw+gap)*2,m_primary.y,bw,bh);
	m_report=CZM_Rect(m_block.x,m_prev.y,bw,bh);m_edit=CZM_Rect(x,m_prev.y,bw,bh);m_settings=CZM_Rect(m_secondary.x,m_prev.y,bw,bh);m_join=CZM_Rect(x,tabsY+H*.48f,right-x,bh);
	m_copy=CZM_Rect(x+H*.19f+pad,tabsY+H*.08f,H*.4f,bh*.7f);
	if(m_mode==PROFILE)LayoutProfile();
	int confirmW=Q_min((int)(W*.88f),(int)(H*.94f)),confirmH=H*(!strcmp(m_confirm,"report_choice")?.29f:.25f);
	m_confirmPanel=CZM_Rect((W-confirmW)/2,(H-confirmH)/2,confirmW,confirmH);
	m_confirmNo=CZM_Rect(m_confirmPanel.x+pad,m_confirmPanel.y+m_confirmPanel.h-pad-bh,(m_confirmPanel.w-pad*3)/2,bh);
	m_confirmYes=CZM_Rect(m_confirmNo.x+m_confirmNo.w+pad,m_confirmNo.y,m_confirmNo.w,bh);
	m_reportChat=CZM_Rect(m_confirmNo.x,m_confirmNo.y-bh-pad,m_confirmPanel.w-pad*2,bh);
	if(m_typing)EngFuncs::SetTextInputRect(m_field.x,m_field.y,m_field.w,m_field.h);
}

int CCzmSocial::Hit()
{
	if(m_pickOpen){for(int i=0;i<m_pickCount;i++)if(m_pick[i].HasCursor())return PICK+i;return m_pickCancel.HasCursor()||!m_pickPanel.HasCursor()?CANCEL:0;}
	if(m_confirm[0]){if(m_confirmYes.HasCursor())return CONFIRM;if(m_confirmNo.HasCursor())return CANCEL;if(!strcmp(m_confirm,"report_choice")&&m_reportChat.HasCursor())return REPORT_CHAT;return 0;}
	if(!m_panel.HasCursor())return BACKDROP; // a tap next to the window closes it, as in the chat and the profile
	if(m_back.HasCursor())return BACK;if(m_refresh.HasCursor())return REFRESH;
	if(m_mode==LIST){
		if(!Account()&&m_prev.HasCursor())return LOGIN;
		if(m_mine.HasCursor())return MINE;if(m_blocked.HasCursor())return BLOCKED;
		for(int i=0;i<4;i++)if(m_tabs[i].HasCursor())return TAB+i;
		if(m_field.HasCursor())return FIELD;if(m_search.HasCursor())return SEARCH;
		if(m_prev.HasCursor()&&m_offset>0)return PREVIOUS;if(m_next.HasCursor()&&m_nextOffset>=0)return NEXT;
		if(m_clip.HasCursor()){int i=(uiStatic.cursorY-m_clip.y+(int)m_scroll)/(int)(H*.105f);if(i>=0&&i<m_people.Count())return ROW+i;}
	}else if(m_mode==PROFILE&&m_loaded){
		if(m_copy.HasCursor())return COPY;
		if(m_editStatus){if(m_field.HasCursor())return FIELD;if(m_primary.HasCursor())return SEND;if(m_secondary.HasCursor())return CANCEL;return 0;}
		if(m_profile.id==CZM_OnlinePlayer()){if(m_edit.HasCursor()||m_profileStatus.HasCursor())return EDIT;if(m_settings.HasCursor())return SETTINGS;}
		else{
			if(m_primary.HasCursor())return PRIMARY;if(m_secondary.HasCursor())return SECONDARY;if(m_block.HasCursor())return BLOCK;if(m_report.HasCursor())return REPORT;
			if(m_profile.online&&!strcmp(m_profile.relation,"friend")&&m_profile.server[0]&&m_join.HasCursor())return JOIN;
		}
	}else if(m_mode==DIALOG){
		if(m_peer.HasCursor())return PEER;
		if(m_canSend&&m_invite.HasCursor())return INVITE;
		if(m_field.HasCursor()&&m_canSend)return FIELD;if(m_search.HasCursor()&&m_canSend)return SEND;
		if(m_tabs[0].HasCursor()&&m_nextBefore)return PREVIOUS;if(m_tabs[1].HasCursor()&&m_before)return NEXT;
		if(m_clip.HasCursor()){
			int bottom=m_clip.y+m_clip.h+(int)m_scroll;
			for(int i=m_messages.Count()-1;i>=0&&bottom>m_clip.y;i--){int h=MessageHeight(m_messages[i]);if(uiStatic.cursorY>=bottom-h&&m_messages[i].player!=CZM_OnlinePlayer())return ROW+i;bottom-=h;}
		}
	}
	return 0;
}

void CCzmSocial::Activate( int hit )
{
	if(hit==BACKDROP){Hide();return;}
	if(hit==BACK){if(m_mode==PROFILE&&!m_outside){Navigate(m_returnMode);return;}if(m_mode==DIALOG){Navigate(LIST);return;}Hide();return;}
	CZM_PlayClick();
	if(hit==REFRESH){m_nextFetch=0;return;}
	if(hit==CANCEL&&m_pickOpen){m_pickOpen=false;return;}
	if(hit==CANCEL){m_confirm[0]=0;m_editStatus=false;EndInput();m_input[0]=0;return;}
	if(hit==INVITE){EndInput();BuildPicks();if(m_pickCount)m_pickOpen=true;else Notice(T("Закрепи сервер сердечком или зайди на сервер, чтобы позвать друга","Pin a server with a heart or join one to invite a friend"));return;}
	if(hit>=PICK&&hit<PICK+MAX_PICKS){SendInvite(hit-PICK);m_pickOpen=false;return;}
	if(hit==CONFIRM){
		char body[72];
		if(!strncmp(m_confirm,"report:",7)){snprintf(body,sizeof(body),"{\"private_message\":%d}",atoi(m_confirm+7));Write(WRITE_REPORT,"/api/v1/report",body);}
		else if(!strcmp(m_confirm,"profile_report")||!strcmp(m_confirm,"report_choice")){snprintf(body,sizeof(body),"{\"player\":%d}",m_target);Write(WRITE_REPORT,"/api/v1/report",body);}
		else if(m_confirm[0])Follow(m_confirm);
		m_confirm[0]=0;return;
	}
	if(hit==REPORT_CHAT&&m_chatMessage>0&&!strcmp(m_confirm,"report_choice")){char body[64];snprintf(body,sizeof(body),"{\"message\":%d}",m_chatMessage);Write(WRITE_REPORT,"/api/v1/report",body);m_confirm[0]=0;return;}
	if(hit==FIELD){if(!m_write)Input(m_input);return;}
	if(hit==MINE){OpenProfile(CZM_OnlinePlayer(),false);return;}
	if(hit==LOGIN){CZM_AccountShow(CZM_OnlineKey(),EngFuncs::GetCvarString("name"));return;}
	if(hit==BLOCKED){m_tab=4;Navigate(LIST);return;}
	if(hit>=TAB&&hit<TAB+4){m_tab=hit-TAB;Navigate(LIST);return;}
	if(hit==SEARCH){char *end;long id=strtol(m_input,&end,10);if(id>0&&id<=2147483647L&&!*end)OpenProfile((int)id,false);else Notice(T("Введите числовой ID игрока","Enter a numeric player ID"));return;}
	if(hit==COPY){char id[24];snprintf(id,sizeof(id),"%d",m_profile.id);if(CZM_CopyText(id))Notice(T("ID скопирован","ID copied"));return;}
	if(hit==PEER){OpenProfile(m_target,false);return;}
	if(hit==PREVIOUS||hit==NEXT){
		if(m_mode==LIST)m_offset=hit==NEXT?m_nextOffset:Q_max(0,m_offset-40);
		else m_before=hit==PREVIOUS?m_nextBefore:0;
		m_view++;m_loaded=false;m_scroll=0;m_nextFetch=0;return;
	}
	if(hit==EDIT){if(!Account()){CZM_AccountShow(CZM_OnlineKey(),EngFuncs::GetCvarString("name"));return;}m_editStatus=true;Layout();Input(m_profile.status);return;}
	if(hit==SETTINGS){CZM_OpenSettings(CZM_TAB_PROFILE);return;}
	if(hit==SEND){if(m_editStatus){CUtlString body;body.Append("{\"text\":");CZM_JsonQuote(body,m_input);body.Append("}");Write(WRITE_STATUS,"/api/v1/social/status",body.Get());}else Send();return;}
	if(hit==PRIMARY){
		if(!m_profile.account){Notice(T("Игроку нужно зарегистрироваться, чтобы добавить его в друзья","This player needs to register before you can add them"));return;}
		if(!Account()){CZM_AccountShow(CZM_OnlineKey(),EngFuncs::GetCvarString("name"));return;}
		if(!strcmp(m_profile.relation,"friend")){Navigate(DIALOG);return;}
		if(!strcmp(m_profile.relation,"none")||!strcmp(m_profile.relation,"follower"))Follow("follow");
		else if(!strcmp(m_profile.relation,"following"))Notice(T("Заявка уже отправлена. Ждём ответа игрока","Request sent. Waiting for the player to accept"));
		return;
	}
	if(hit==SECONDARY){if(!strcmp(m_profile.relation,"friend")||!strcmp(m_profile.relation,"following"))Q_strncpy(m_confirm,"unfollow",sizeof(m_confirm));return;}
	if(hit==BLOCK){if(!strcmp(m_profile.relation,"blocked"))Follow("unblock");else if(m_profile.account)Q_strncpy(m_confirm,"block",sizeof(m_confirm));return;}
	if(hit==JOIN){m_joinPending=true;m_nextFetch=0;return;}
	if(hit==REPORT){EndInput();Q_strncpy(m_confirm,m_chatMessage>0?"report_choice":"profile_report",sizeof(m_confirm));return;}
	if(hit>=ROW){int i=hit-ROW;if(m_mode==LIST&&i<m_people.Count()){
		m_target=m_people[i].id;if(m_tab==1){m_outside=false;Navigate(DIALOG);}else OpenProfile(m_target,false);
	}else if(m_mode==DIALOG&&i<m_messages.Count()&&!m_messages[i].deleted){
		char proto[4],address[64],name[96];
		// a friend's invite: straight to the server card, which checks the server and joins
		if(ParseInvite(m_messages[i].text,proto,address,name,sizeof(name))){EndInput();CZM_JoinAddress(address);return;}
		snprintf(m_confirm,sizeof(m_confirm),"report:%d",m_messages[i].id);EndInput();} }
}

bool CCzmSocial::KeyDown( int key )
{
	Layout();
	if(m_typing&&UI::Key::IsBackspace(key)){size_t n=strlen(m_input);if(n){n--;while(n&&((unsigned char)m_input[n]&0xc0)==0x80)n--;m_input[n]=0;}return true;}
	if(m_typing&&UI::Key::IsEnter(key)){Activate(m_mode==LIST?SEARCH:SEND);return true;}
	if(UI::Key::IsEscape(key)){if(m_confirm[0])m_confirm[0]=0;else if(m_typing)EndInput();else Activate(BACK);return true;}
	if(UI::Key::IsLeftMouse(key)){m_pressed=Hit();m_drag=m_mode!=PROFILE&&m_clip.HasCursor()&&!m_confirm[0];m_moved=false;m_downY=uiStatic.cursorY;m_downScroll=m_scroll;if(m_typing&&m_pressed!=FIELD&&m_pressed!=SEND)EndInput();return true;}
	if(key==K_MWHEELUP||key==K_MWHEELDOWN){m_scroll+=(key==K_MWHEELUP?1:-1)*H*.10f*(m_mode==LIST?-1:1);return true;}
	return CMenuFramework::KeyDown(key);
}
bool CCzmSocial::KeyUp( int key )
{
	if(UI::Key::IsLeftMouse(key)){int hit=Hit();if(!m_moved&&hit&&hit==m_pressed)Activate(hit);m_pressed=0;m_drag=false;return true;}return CMenuFramework::KeyUp(key);
}
bool CCzmSocial::MouseMove( int x,int y )
{
	CMenuFramework::MouseMove(x,y);if(m_drag){int d=uiStatic.cursorY-m_downY;if(abs(d)>H*.02f)m_moved=true;if(m_moved)m_scroll=m_downScroll+d*(m_mode==LIST?-1:1);}return true;
}
void CCzmSocial::Char( int key )
{
	if(!m_typing||m_write||key<32||key==127)return;
	if(m_mode==LIST&&(key<'0'||key>'9'))return;
	size_t n=strlen(m_input);int limit=m_mode==LIST?10:m_editStatus?100:400;
	if(n+4>=sizeof(m_input)||((key&0xc0)!=0x80&&Letters(m_input)>=limit))return;
	m_input[n]=(char)key;m_input[n+1]=0;
}

void CCzmSocial::Field( const char *placeholder )
{
	CZM_DrawPill(UI_DIR "button_secondary.png",m_field.x,m_field.y,m_field.w,m_field.h);
	const char *visible = m_input[0] ? m_input : placeholder;
	if( m_input[0] ) while( *visible && CZM_TextWidth( CZM_Font( CZMF_PANEL_TEXT ), visible ) > m_field.w-pad*2 ) { visible++; while((*visible & 0xc0)==0x80)visible++; }
	Label(CZM_Rect(m_field.x+pad,m_field.y,m_field.w-pad*2,m_field.h),visible,CZMF_PANEL_TEXT,m_input[0]?CZM_White():CZM_Grey());
	if(m_typing && ((int)(EngFuncs::DoubleTime()*2)%2)==0){int x=m_field.x+pad+CZM_TextWidth(CZM_Font(CZMF_PANEL_TEXT),m_input[0]?visible:"");UI_FillRect(x,m_field.y+m_field.h*.2f,Q_max(1,H/400),m_field.h*.6f,PackRGBA(245,83,104,255));}
}
void CCzmSocial::DrawList()
{
	Button(m_mine,T("Мой профиль","My profile"));Button(m_blocked,T("Блокировки","Blocked"));
	const char *tabs[]={T("Друзья","Friends"),T("Сообщения","Messages"),T("Подписчики","Followers"),T("Подписки","Following")};
	int totals[]={s_friends,s_unread,s_followers,s_following};
	for(int i=0;i<4;i++){char text[100];snprintf(text,sizeof(text),"%s  %d",tabs[i],totals[i]);Button(m_tabs[i],text,m_tab==i,Pressed(TAB+i));}
	Field(T("Найти игрока по ID","Find player by ID"));Button(m_search,T("Найти","Find"),true,Pressed(SEARCH));
	if(!Account()){Label(CZM_Rect(m_clip.x,m_clip.y,m_clip.w,H*.09f),T("Друзья и переписка сохраняются в аккаунте","Friends and messages are saved in your account"));Button(m_prev,T("Войти","Sign in"),true);return;}
	int rh=H*.105f; m_scroll=bound(0.0f,m_scroll,(float)Q_max(0,m_people.Count()*rh-m_clip.h));
	UI::Scissor::PushScissor(m_clip.x,m_clip.y,m_clip.w,m_clip.h);
	for(int i=0;i<m_people.Count();i++){
		const Person &p=m_people[i];CzmRect r=CZM_Rect(m_clip.x,m_clip.y+i*rh-(int)m_scroll,m_clip.w,rh-pad/2);if(r.y+r.h<m_clip.y||r.y>m_clip.y+m_clip.h)continue;
		UI_FillRect(r.x,r.y,r.w,r.h,Pressed(ROW+i)?PackRGBA(69,30,41,245):PackRGBA(17,26,37,240));
		int av=r.h-pad;CZM_DrawImage(CZM_AvatarFor(p.avatar,p.id),r.x+pad/2,r.y+pad/2,av,av);
		char text[180];int tx=r.x+av+pad,tw=r.w-av-pad*2;
		snprintf(text,sizeof(text),"%s  ·  ID %d%s",p.nick,p.id,p.unread?"  +":"");Label(CZM_Rect(tx,r.y+pad/4,tw,r.h/2),text,CZMF_LANG);
		char seen[100];SeenText(p,seen,sizeof(seen));
		Label(CZM_Rect(tx,r.y+r.h/2-pad/4,tw,r.h/2),m_tab==1&&p.last[0]?p.last:seen,CZMF_SMALL,p.online?PackRGBA(112,220,161,255):CZM_Grey());
		if(p.unread){snprintf(text,sizeof(text),"%d",p.unread);CZM_DrawText(CZM_Font(CZMF_LANG),r.x+r.w-H*.08f,r.y+pad,H*.07f,text,PackRGBA(255,95,110,255),QM_RIGHT);}
	}
	if(!m_people.Count())Label(m_clip,m_tab==4?T("Заблокированных игроков нет","No blocked players"):m_loaded?T("Пока пусто","Nothing here yet"):T("Загружаем…","Loading…"),CZMF_PANEL_TEXT,CZM_Grey());
	UI::Scissor::PopScissor();
	if(m_offset>0)Button(m_prev,T("Назад","Previous"));if(m_nextOffset>=0)Button(m_next,T("Далее","Next"));
	if(m_tab==4)Label(CZM_Rect(m_prev.x+m_prev.w+pad,m_prev.y,m_next.x-m_prev.x-m_prev.w-pad*2,m_prev.h),T("Заблокированные игроки","Blocked players"),CZMF_SMALL);
}

void CCzmSocial::DrawProfile()
{
	if(!m_loaded){Label(m_clip,T("Загружаем профиль…","Loading profile…"));return;}
	const Person &p=m_profile;
	bool self=p.id==CZM_OnlinePlayer(),friends=!strcmp(p.relation,"friend"),following=!strcmp(p.relation,"following");
	bool follower=!strcmp(p.relation,"follower"),blocked=!strcmp(p.relation,"blocked");
	int gap=Q_max(5,(int)(H*.011f)),av=m_hero.h-gap*2;
	UI_FillRect(m_hero.x,m_hero.y,m_hero.w,m_hero.h,PackRGBA(18,28,42,240));
	UI_FillRect(m_hero.x,m_hero.y,Q_max(2,H/250),m_hero.h,PackRGBA(232,45,65,255));
	CZM_DrawImage(CZM_AvatarFor(p.avatar,p.id),m_hero.x+gap,m_hero.y+gap,av,av);
	Label(CZM_Rect(m_copy.x,m_hero.y+gap,m_copy.w,CZM_FontHeight(CZM_Font(CZMF_NICK))),p.nick,CZMF_NICK);
	char text[220];snprintf(text,sizeof(text),"ID %d  ·  %s",p.id,T("Копировать","Copy"));Label(m_copy,text,CZMF_SMALL,CZM_Grey());
	SeenText(p,text,sizeof(text));int sy=m_copy.y+m_copy.h+1,dot=Q_max(7,(int)(H*.011f));
	CZM_DrawImage(UI_DIR "dot.png",m_copy.x,sy+(CZM_FontHeight(CZM_Font(CZMF_SMALL))-dot)/2,dot,dot,p.online?PackRGBA(66,216,137,255):PackRGBA(242,77,94,255));
	Label(CZM_Rect(m_copy.x+dot+gap,sy,m_copy.w-dot-gap,CZM_FontHeight(CZM_Font(CZMF_SMALL))),text,CZMF_SMALL,p.online?PackRGBA(112,220,161,255):CZM_Grey());
	const char *status=p.status[0]?p.status:self?T("Нажмите, чтобы задать статус","Tap to add a status"):T("Статус не указан","No status yet");int starts[PROFILE_STATUS_LINES+1];
	int lines=CZM_WrapText(CZM_Font(CZMF_PANEL_TEXT),status,m_profileStatus.w,starts,PROFILE_STATUS_LINES),lh=CZM_FontHeight(CZM_Font(CZMF_PANEL_TEXT))+2;
	for(int i=0;i<lines;i++){char line[410];CZM_WrapLine(status,starts,i,line,sizeof(line));Label(CZM_Rect(m_profileStatus.x,m_profileStatus.y+i*lh,m_profileStatus.w,lh),line,CZMF_PANEL_TEXT,p.status[0]?CZM_White():CZM_Grey());}
	time_t timestamp=p.created;struct tm date;char when[40];localtime_r(&timestamp,&date);strftime(when,sizeof(when),"%d.%m.%Y",&date);
	snprintf(text,sizeof(text),"%s %s",p.account?T("В CZM с","Joined CZM"):T("Гостевой профиль с","Guest since"),when);Label(m_profileInfo,text,CZMF_SMALL,CZM_Grey());
	const char *names[]={T("Друзья","Friends"),T("Подписчики","Followers"),T("Подписки","Following")};int values[]={p.friends,p.followers,p.following};
	for(int i=0;i<3;i++){
		const CzmRect &r=m_profileCounts[i];UI_FillRect(r.x,r.y,r.w,r.h,PackRGBA(25,35,49,245));
		snprintf(text,sizeof(text),"%d",values[i]);Label(CZM_Rect(r.x+gap,r.y+gap/2,r.w-gap*2,r.h/2),text,CZMF_LANG);
		Label(CZM_Rect(r.x+gap,r.y+r.h/2,r.w-gap*2,r.h/2-gap/2),names[i],CZMF_SMALL,CZM_Grey());
	}
	if(m_profileHint.h){
		const char *hint=T("Игрок пока гость. Дружба и ЛС доступны после регистрации.","This player is a guest. Friends and messages require registration.");
		int n=CZM_WrapText(CZM_Font(CZMF_SMALL),hint,m_profileHint.w,starts,2),h=CZM_FontHeight(CZM_Font(CZMF_SMALL))+2;
		for(int i=0;i<n;i++){char line[240];CZM_WrapLine(hint,starts,i,line,sizeof(line));Label(CZM_Rect(m_profileHint.x,m_profileHint.y+i*h,m_profileHint.w,h),line,CZMF_SMALL,CZM_Grey());}
	}
	if(m_profileServer.h){
		snprintf(text,sizeof(text),"%s %s",T("Сервер:","Server:"),p.server);Label(CZM_Rect(m_profileServer.x,m_profileServer.y,m_profileServer.w,CZM_FontHeight(CZM_Font(CZMF_SMALL))+2),text,CZMF_SMALL,CZM_Grey());
		if(p.map[0])Label(CZM_Rect(m_profileServer.x,m_profileServer.y+CZM_FontHeight(CZM_Font(CZMF_SMALL))+2,m_profileServer.w,CZM_FontHeight(CZM_Font(CZMF_SMALL))+2),p.map,CZMF_SMALL,CZM_Grey());
	}
	if(m_editStatus){Field(T("Ваш статус, до 100 символов","Your status, up to 100 characters"));Button(m_primary,T("Сохранить","Save"),true);Button(m_secondary,T("Отмена","Cancel"));}
	else if(self){Button(m_edit,Account()?T("Изменить статус","Edit status"):T("Войти","Sign in"));Button(m_settings,T("Редактировать профиль","Edit profile"));}
	else{
		if(m_primary.w)Button(m_primary,friends?T("Написать","Message"):following?T("Заявка отправлена","Request sent"):follower?T("Принять в друзья","Accept friend"):T("Добавить в друзья","Add friend"),p.account&&!following,Pressed(PRIMARY),p.account);
		if(m_join.w)Button(m_join,T("Присоединиться","Join"),true,Pressed(JOIN));
		if(m_secondary.w)Button(m_secondary,friends?T("Удалить друга","Remove friend"):T("Отписаться","Unfollow"));
		if(m_block.w)Button(m_block,blocked?T("Разблокировать","Unblock"):T("Заблокировать","Block"));
		if(m_report.w)Button(m_report,T("Пожаловаться","Report"));
	}
}

void CCzmSocial::BuildPicks()
{
	m_pickCount=0;
	auto add=[this](const char *address,const char *proto,const char *name){
		if(m_pickCount>=MAX_PICKS||!address||!address[0]||strlen(address)>=22||strspn(address,"0123456789.:")!=strlen(address)||!strchr(address,':'))return;
		for(int i=0;i<m_pickCount;i++)if(!strcmp(m_pickAddress[i],address))return;
		Q_strncpy(m_pickAddress[m_pickCount],address,sizeof(m_pickAddress[0]));
		Q_strncpy(m_pickProto[m_pickCount],!strcmp(proto,"49")?"49":"gs",sizeof(m_pickProto[0]));
		CZM_CleanName(name&&name[0]?name:address,m_pickName[m_pickCount],sizeof(m_pickName[0]));
		if(!m_pickName[m_pickCount][0])Q_strncpy(m_pickName[m_pickCount],address,sizeof(m_pickName[0]));
		m_pickCount++;
	};
	// the server of the match that is going on now, then the hearts of the main screen
	if(CL_IsActive())add(EngFuncs::GetCvarString("czm_connect_adr"),"gs",EngFuncs::GetCvarString("czm_connect_name"));
	for(int i=0;i<CZM_ServerCount();i++){CzmServer *server=CZM_Server(i);if(server)add(server->address,server->prot,server->name);}
}

void CCzmSocial::SendInvite( int index )
{
	if(index<0||index>=m_pickCount||m_write)return;
	char nonce[80];CZM_NetNewKey(nonce,sizeof(nonce));
	CUtlString body;body.Append("{\"server\":");CZM_JsonQuote(body,m_pickAddress[index]);body.Append(",\"proto\":");CZM_JsonQuote(body,m_pickProto[index]);
	body.Append(",\"name\":");CZM_JsonQuote(body,m_pickName[index]);body.Append(",\"nonce\":");CZM_JsonQuote(body,nonce);body.Append("}");
	char path[100];snprintf(path,sizeof(path),"/api/v1/social/invite/%d",m_target);
	m_sent[0]=0; // the text the player is typing stays in the field
	Write(WRITE_MESSAGE,path,body.Get());
}

void CCzmSocial::DrawPicker()
{
	UI_FillRect(0,0,W,H,PackRGBA(0,0,0,190));CZM_DrawPanel(m_pickPanel);
	CZM_DrawText(CZM_Font(CZMF_NICK),m_pickPanel.x+pad,m_pickPanel.y+pad,m_pickPanel.w-pad*2,T("Позвать друга на сервер","Invite your friend to a server"),CZM_White(),QM_CENTER);
	for(int i=0;i<m_pickCount;i++){
		const CzmRect &r=m_pick[i];bool now=i==0&&CL_IsActive();
		CZM_DrawSliced(UI_DIR "card.png",r.x,r.y,r.w,r.h,30,(int)(H*.02f),Pressed(PICK+i)?PackRGBA(200,200,200,255):CZM_White());
		CZM_DrawImage(now?UI_DIR "icon_play.png":UI_DIR "icon_heart_on.png",r.x+pad,r.y+(r.h-H*.034f)/2,H*.034f,H*.034f,now?PackRGBA(74,222,128,255):PackRGBA(244,63,94,255));
		int tx=r.x+pad*2+H*.034f;
		CZM_DrawText(CZM_Font(CZMF_LANG),tx,r.y+(r.h-CZM_FontHeight(CZM_Font(CZMF_LANG)))/2,r.w*.62f,m_pickName[i],CZM_White());
		CZM_DrawText(CZM_Font(CZMF_SMALL),r.x+r.w*.66f,r.y+(r.h-CZM_FontHeight(CZM_Font(CZMF_SMALL)))/2,r.w*.34f-pad,now?T("играю сейчас","playing now"):m_pickAddress[i],CZM_Grey(),QM_RIGHT);
	}
	Button(m_pickCancel,T("Отмена","Cancel"),false,Pressed(CANCEL));
}

int CCzmSocial::MessageHeight( const Message &m )
{
	char proto[4],address[64],name[96];
	if(!m.deleted&&ParseInvite(m.text,proto,address,name,sizeof(name)))return (int)(H*.17f)+pad;
	int starts[14];int lines=CZM_WrapText(CZM_Font(CZMF_PANEL_TEXT),m.text,m_clip.w*.78f-pad*2,starts,12);
	return Q_max((int)(H*.105f),lines*CZM_FontHeight(CZM_Font(CZMF_PANEL_TEXT))+(int)(H*.045f))+pad;
}
void CCzmSocial::DrawDialog()
{
	Button(m_tabs[0],m_nextBefore?T("Старые сообщения","Older messages"):T("Начало переписки","Conversation"));if(m_before)Button(m_tabs[1],T("К новым сообщениям","Latest messages"));
	char seen[160];SeenText(m_profile,seen,sizeof(seen));Label(CZM_Rect(m_tabs[2].x,m_tabs[2].y,m_tabs[2].w*2,m_tabs[2].h),seen,CZMF_SMALL,CZM_Grey());
	int total=0;for(int i=0;i<m_messages.Count();i++)total+=MessageHeight(m_messages[i]);m_scroll=bound(0.0f,m_scroll,(float)Q_max(0,total-m_clip.h));
	UI::Scissor::PushScissor(m_clip.x,m_clip.y,m_clip.w,m_clip.h);int bottom=m_clip.y+m_clip.h+(int)m_scroll;
	for(int i=m_messages.Count()-1;i>=0&&bottom>m_clip.y;i--){const Message &m=m_messages[i];int h=MessageHeight(m);bottom-=h;bool mine=m.player==CZM_OnlinePlayer();int width=m_clip.w*.8f;CzmRect r=CZM_Rect(mine?m_clip.x+m_clip.w-width:m_clip.x,bottom,width,h-pad);
		char proto[4],address[64],name[96];
		if(!m.deleted&&ParseInvite(m.text,proto,address,name,sizeof(name))){
			// invite card: who calls, the server, and a big join button for the friend
			HFont nameFont=CZM_Font(CZMF_LANG),small=CZM_Font(CZMF_SMALL);
			int icon=r.h*.46f,ix=r.x+pad,iy=r.y+(r.h-icon)/2,tx=ix+icon+pad,bw=mine?0:(int)(H*.26f),tw=r.x+r.w-pad-tx-(bw?bw+pad:0);
			UI_FillRect(r.x,r.y,r.w,r.h,mine?PackRGBA(64,28,41,245):PackRGBA(40,18,24,250));
			UI_FillRect(r.x,r.y,Q_max(3,pad/3),r.h,PackRGBA(239,68,68,255));
			CZM_DrawImage(UI_DIR "glow.png",ix-icon/3,iy-icon/3,icon*5/3,icon*5/3,PackRGBA(239,40,52,110));
			CZM_DrawImage(UI_DIR "dot.png",ix,iy,icon,icon,PackRGBA(220,38,38,255));
			CZM_DrawImage(UI_DIR "icon_play.png",ix+icon*3/10,iy+icon/4,icon/2,icon/2);
			CZM_DrawText(small,tx,r.y+pad/2,tw,mine?T("Ты зовёшь в игру","You invited to play"):T("Зовёт тебя в игру","Invites you to play"),PackRGBA(252,165,165,255));
			CZM_DrawText(nameFont,tx,r.y+pad/2+CZM_FontHeight(small)+2,tw,name,CZM_White());
			CZM_DrawText(small,tx,r.y+pad/2+CZM_FontHeight(small)+CZM_FontHeight(nameFont)+4,tw,address,CZM_Grey());
			if(bw)Button(CZM_Rect(r.x+r.w-pad-bw,r.y+(r.h-H*.07f)/2,bw,H*.07f),T("Зайти","Join"),true,Pressed(ROW+i));
			time_t timestamp=m.time;struct tm date;char when[40];localtime_r(&timestamp,&date);strftime(when,sizeof(when),"%H:%M %d.%m",&date);
			CZM_DrawText(small,r.x+pad,r.y+r.h-CZM_FontHeight(small)-pad/4,r.w-pad*2-(bw?bw+pad:0),when,CZM_Grey(),QM_RIGHT);
			continue;
		}
		UI_FillRect(r.x,r.y,r.w,r.h,mine?PackRGBA(64,28,41,245):PackRGBA(19,32,46,245));
		int starts[14];int lines=CZM_WrapText(CZM_Font(CZMF_PANEL_TEXT),m.text,r.w-pad*2,starts,12);
		for(int n=0;n<lines;n++){char line[1604];CZM_WrapLine(m.text,starts,n,line,sizeof(line));CZM_DrawText(CZM_Font(CZMF_PANEL_TEXT),r.x+pad,r.y+pad/2+n*CZM_FontHeight(CZM_Font(CZMF_PANEL_TEXT)),r.w-pad*2,line,m.deleted?CZM_Grey():CZM_White());}
		time_t timestamp=m.time;struct tm date;char when[40];localtime_r(&timestamp,&date);strftime(when,sizeof(when),"%H:%M %d.%m",&date);CZM_DrawText(CZM_Font(CZMF_SMALL),r.x+pad,r.y+r.h-CZM_FontHeight(CZM_Font(CZMF_SMALL))-pad/4,r.w-pad*2,when,CZM_Grey(),QM_RIGHT);
	}
	if(!m_messages.Count())Label(m_clip,m_loaded?T("Напишите первое сообщение другу","Send your friend the first message"):T("Загружаем переписку…","Loading messages…"),CZMF_PANEL_TEXT,CZM_Grey());
	UI::Scissor::PopScissor();
	if(m_canSend)Button(m_invite,T("Позвать в игру","Invite to game"),true,Pressed(INVITE));
	if(m_canSend){Field(T("Сообщение другу…","Message your friend…"));Button(m_search,m_write?"…":T("Отправить","Send"),true,Pressed(SEND));}
	else Label(CZM_Rect(m_field.x,m_field.y,m_field.w+m_search.w+pad,m_field.h),T("История доступна. Новые ЛС — только взаимным друзьям","History is available. New messages require mutual friendship"),CZMF_SMALL,CZM_Grey());
}

void CCzmSocial::Draw()
{
	Layout();UI_FillRect(0,0,W,H,PackRGBA(0,0,0,150));CZM_DrawPanel(m_panel);
	CZM_DrawImage(UI_DIR "chip_round.png",m_back.x,m_back.y,m_back.w,m_back.h);int icon=m_back.h/2;CZM_DrawImage(UI_DIR "icon_back.png",m_back.x+icon/2,m_back.y+icon/2,icon,icon);
	CZM_DrawImage(UI_DIR "icon_refresh.png",m_refresh.x+icon/2,m_refresh.y+icon/2,icon,icon);
	Label(m_peer,m_mode==LIST?T("ДРУЗЬЯ","FRIENDS"):m_mode==PROFILE?T("ПРОФИЛЬ ИГРОКА","PLAYER PROFILE"):m_profile.nick[0]?m_profile.nick:T("ЛИЧНЫЕ СООБЩЕНИЯ","PRIVATE MESSAGES"),m_mode==PROFILE?CZMF_LANG:CZMF_NICK);
	if(m_mode==LIST)DrawList();else if(m_mode==PROFILE)DrawProfile();else DrawDialog();
	if(m_notice[0]&&EngFuncs::DoubleTime()<m_noticeUntil){CzmRect r=CZM_Rect(W*.12f,H*.035f,W*.76f,H*.075f);CZM_DrawPill(UI_DIR "button_secondary.png",r.x,r.y,r.w,r.h);Label(CZM_Rect(r.x+pad,r.y,r.w-pad*2,r.h),m_notice,CZMF_LANG);}
	if(m_pickOpen)DrawPicker();
	if(m_confirm[0]){
		UI_FillRect(0,0,W,H,PackRGBA(0,0,0,190));CZM_DrawPanel(m_confirmPanel);
		bool choice=!strcmp(m_confirm,"report_choice"),profileReport=!strcmp(m_confirm,"profile_report");
		const char *text=choice?T("На что пожаловаться?","What would you like to report?"):
			profileReport?T("Отправить жалобу на профиль игрока?","Report this player's profile?"):
			!strncmp(m_confirm,"report:",7)?T("Отправить жалобу на это сообщение? Его текст увидит модератор.","Report this message? Its text will be shared with a moderator."):
			!strcmp(m_confirm,"block")?T("Заблокировать игрока? Дружба будет прекращена.","Block this player? Your friendship will end."):
			!strcmp(m_profile.relation,"friend")?T("Удалить друга? Он останется вашим подписчиком. Новые ЛС будут недоступны.","Remove friend? They will remain your follower. New messages will be unavailable."):
			T("Отменить подписку на игрока?","Unfollow this player?");
		int starts[8],n=CZM_WrapText(CZM_Font(CZMF_PANEL_TEXT),text,m_confirmPanel.w-pad*2,starts,6);
		for(int i=0;i<n;i++){char line[300];CZM_WrapLine(text,starts,i,line,sizeof(line));CZM_DrawText(CZM_Font(CZMF_PANEL_TEXT),m_confirmPanel.x+pad,m_confirmPanel.y+pad+i*CZM_FontHeight(CZM_Font(CZMF_PANEL_TEXT)),m_confirmPanel.w-pad*2,line,CZM_White());}
		if(choice)Button(m_reportChat,T("На сообщение","Report message"),true);
		Button(m_confirmNo,T("Отмена","Cancel"));Button(m_confirmYes,choice?T("На профиль","Report profile"):T("Подтвердить","Confirm"),!choice);
	}
}

ADD_MENU3( menu_czmsocial, CCzmSocial, UI_CzmSocial_Menu );
void UI_CzmSocial_Menu( void )
{
	int player=atoi(EngFuncs::GetCvarString("czm_open_profile"));
	if(player>0){EngFuncs::CvarSetString("czm_open_profile","0");menu_czmsocial->OpenProfile(player,true);}
	else menu_czmsocial->Show();
}
void CZM_OpenFriends( void ) { UI_CzmSocial_Menu(); }
void CZM_OpenProfile( int player, int chatMessage ) { if(menu_czmsocial)menu_czmsocial->OpenProfile(player,true,chatMessage); }
int CZM_SocialUnread( void ) { return s_unread; }
int CZM_SocialRequests( void ) { return s_requests; }

void CZM_SocialFrame( void )
{
	if(strcmp(s_key,CZM_OnlineKey())||s_identity!=CZM_OnlineIdentity()){Q_strncpy(s_key,CZM_OnlineKey(),sizeof(s_key));s_identity=CZM_OnlineIdentity();s_epoch++;s_sessionInvalid=false;s_unread=s_requests=s_friends=s_followers=s_following=0;s_nextPresence=0;s_connection[0]=0;Abandon(s_presence);}
	char self[24];snprintf(self,sizeof(self),"%d",CZM_OnlinePlayer());if(strcmp(EngFuncs::GetCvarString("czm_profile_id"),self))EngFuncs::CvarSetString("czm_profile_id",self);
	int status;CUtlString body;for(int i=s_abandoned.Count()-1;i>=0;i--)if(CZM_NetPoll(s_abandoned[i],&status,body))s_abandoned.Remove(i);
	if(s_presence&&CZM_NetPoll(s_presence,&status,body)){s_presence=0;CzmJson j;if(s_presenceEpoch==s_epoch&&status==200&&j.Parse(body.Get()))Counts(j);else if(status==401&&!s_sessionInvalid){s_sessionInvalid=true;s_epoch++;s_unread=s_requests=0;}}
	if(CZM_OnlineReady()){
		CzmTab::State state;bool playing=CL_IsActive()&&CzmTab::Parse(EngFuncs::GetCvarString("czm_tab_state"),state);
		const char *map=playing?EngFuncs::GetCvarString("czm_current_map"):"";char connection[160];snprintf(connection,sizeof(connection),"%s|%s",playing?state.server:"",map);
		if(strcmp(connection,s_connection)){Q_strncpy(s_connection,connection,sizeof(s_connection));s_nextPresence=0;}
		if(!s_presence&&EngFuncs::DoubleTime()>=s_nextPresence){CUtlString request;request.Append("{\"server\":");CZM_JsonQuote(request,playing?state.server:"");request.Append(",\"map\":");CZM_JsonQuote(request,map);request.Append("}");s_presence=CZM_NetRequest("POST",CZM_OnlineUrl("/api/v1/social/presence"),CZM_OnlineKey(),request.Get());s_presenceEpoch=s_epoch;s_nextPresence=EngFuncs::DoubleTime()+30;}
	}
	if(s_window)s_window->Frame();
}
