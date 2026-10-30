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
#include "CzmDesign.h"
#include "../../common/czm_tab.h"

#define UI_DIR "gfx/czm/ui/"

namespace {
const char *T( const char *ru, const char *en ) { return CZM_IsRussian() ? ru : en; }
const int PROFILE_STATUS_LINES=4;
const char *s_kinds[] = { "friends", "dialogs", "followers", "following", "blocked" };
char s_key[80];
int s_epoch, s_unread, s_requests, s_friends, s_followers, s_following;
int s_newFriends,s_followingUpdates,s_chatUnread[3];
double s_countsRevision=-1;
int s_chatRead[3],s_chatWanted[3],s_chatSent[3],s_chatEpoch[3];
double s_chatRetry[3];
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
	const int version=j.Get(c,"revision");
	if(j.Type(version)==CzmJson::T_NUMBER){
		const double revision=j.Number(version);
		if(revision<s_countsRevision)return;
		s_countsRevision=revision;
	}else if(s_countsRevision>=0)return;
	s_unread = j.Int( j.Get( c, "unread" )); s_requests = j.Int( j.Get( c, "requests" ));
	s_friends = j.Int( j.Get( c, "friends" )); s_followers = j.Int( j.Get( c, "followers" ));
	s_following = j.Int( j.Get( c, "following" ));
	s_newFriends=j.Int(j.Get(c,"new_friends"));s_followingUpdates=j.Int(j.Get(c,"following_updates"));
	const char *rooms[]={"chat_global","chat_ru","chat_en"};
	for(int i=0;i<3;i++)s_chatUnread[i]=Q_max(0,j.Int(j.Get(c,rooms[i])));
}

const char *SocialError( const char *code )
{
    if( !strcmp( code, "server_blocked" )) return T( "Сервер заблокирован модерацией CZM", "CZM moderation restricted this server" );
	if( !strcmp( code, "account_required" ) || !strcmp( code, "session" )) return T( "Войдите в аккаунт, чтобы пользоваться друзьями и ЛС", "Sign in to use friends and messages" );
	if( !strcmp( code, "not_found" ) || !strcmp( code, "account_not_found" )) return T( "Игрок с таким ID не найден", "No player with this ID" );
	if( !strcmp( code, "not_friends" )) return T( "Отправлять сообщения можно только взаимным друзьям", "Messages require mutual friendship" );
	if( !strcmp( code, "unavailable" )) return T( "Действие недоступно", "Action unavailable" );
	if( !strcmp( code, "banned" )) return T( "Общение ограничено модератором", "Messaging is restricted by a moderator" );
	if( !strcmp( code, "muted" ))
	{
		static char why[220];
		return CZM_OnlineLimited( CZM_LIMIT_TEXT, why, sizeof( why )) ? why : T( "Чат ограничен модератором", "A moderator limited your chat" );
	}
	if( !strcmp( code, "slow" ) || !strcmp( code, "limit" )) return T( "Слишком часто. Попробуйте позже", "Too many requests. Try later" );
	if( !strcmp( code, "empty" )) return T( "Введите сообщение", "Enter a message" );
	return T( "Нет связи. Нажмите обновить и повторите", "Connection failed. Refresh and try again" );
}

struct Person
{
	int id, created, lastSeen, friends, followers, following, unread;
	int togetherCount, togetherSize, lobbyCount, lobbyCapacity;
    char lobbyId[64];
	bool account, online, playing, support;
	bool serverOwner; int ownedCount;
	char role[16], project[132], telegram[104];
	struct { char address[64], name[388]; } owned[5];
	int topPlace, topSeconds; // the Top 100: the exact place and the time on servers (0: no time yet)
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
	p.support = !strcmp( j.String( j.Get( item, "role" )), "support" );
	Q_strncpy(p.role,j.String(j.Get(item,"role")),sizeof(p.role));
	Q_strncpy(p.project,j.String(j.Get(item,"project")),sizeof(p.project));
	if(!p.role[0])Q_strncpy(p.telegram,j.String(j.Get(item,"telegram")),sizeof(p.telegram));
	p.serverOwner=!strcmp(p.role,"server_owner");
	const int roles=j.Get(item,"roles");
	for(int i=0;i<j.Count(roles);i++)if(!strcmp(j.String(j.At(roles,i)),"server_owner"))p.serverOwner=true;
	if(j.Count(roles))p.telegram[0]=0;
	const int servers=j.Get(item,"servers");
	for(int i=0;i<j.Count(servers)&&p.ownedCount<5;i++){
		const int server=j.At(servers,i),index=p.ownedCount++;
		Q_strncpy(p.owned[index].address,j.String(j.Get(server,"server")),sizeof(p.owned[index].address));
		Q_strncpy(p.owned[index].name,j.String(j.Get(server,"name")),sizeof(p.owned[index].name));
	}
	p.topPlace = j.Int( j.Get( j.Get( item, "top" ), "place" ));
	p.topSeconds = j.Int( j.Get( j.Get( item, "top" ), "seconds" ));
	p.account = j.Bool( j.Get( item, "account" )); p.online = j.Bool( j.Get( item, "online" )); p.playing = j.Bool( j.Get( item, "playing" ));
	p.unread = j.Int( j.Get( item, "unread" ));
	int together = j.Get( item, "together" );
	p.togetherCount = j.Int( j.Get( together, "count" ));
	p.togetherSize = j.Int( j.Get( together, "size" ));
    int lobby=j.Get(item,"lobby");
    p.lobbyCount=j.Int(j.Get(lobby,"count"));
    p.lobbyCapacity=j.Int(j.Get(lobby,"capacity"));
    Q_strncpy(p.lobbyId,j.String(j.Get(lobby,"id")),sizeof(p.lobbyId));
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
	if( p.online )
	{
		if( p.playing && p.togetherCount >= 2 && p.togetherSize >= p.togetherCount )
			snprintf( out, size, T( "В игре · Вместе %d/%d", "In game · Together %d/%d" ), p.togetherCount, p.togetherSize );
        else if(!p.playing && p.lobbyCount>0 && p.lobbyCapacity>0)
            snprintf(out,size,T("В лобби · Пати %d/%d","In lobby · Party %d/%d"),
                     p.lobbyCount,p.lobbyCapacity);
        else Q_strncpy(out,p.playing?T("В игре · Соло","In game · Solo"):
                       T("Онлайн · В меню","Online · In menu"),size);
		return;
	}
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
// a round button with an icon: back, the gear, the shield, ⋯
void Chip( const CzmRect &r, const char *icon, bool pressed, unsigned tint = 0 )
{
	CzmStyle::Surface( r, pressed ? PackRGBA( 41, 51, 67, 255 ) : PackRGBA( 28, 34, 45, 255 ), pressed && tint ? tint : CzmStyle::Border(), r.h / 2 );
	const int side = r.h * 46 / 100;
	CZM_DrawImage( icon, r.x + ( r.w - side ) / 2, r.y + ( r.h - side ) / 2, side, side, tint ? tint : CzmStyle::Ink() );
}
// the CZM button of the card: a thin edge, an icon before the words, red for the main action
void ActionButton( const CzmRect &r, const char *icon, const char *label, bool primary, bool pressed, bool enabled = true, unsigned accent = 0 )
{
	CzmStyle::Button( r, "", enabled, primary, pressed, accent );
	int font = CZMF_UI_LABEL;
	if( CZM_TextWidth( CZM_Font( font ), label ) > r.w - r.h ) font = CZMF_UI_META;
	const HFont f = CZM_Font( font );
	const int side = icon && icon[0] ? r.h * 40 / 100 : 0, space = side ? r.h / 5 : 0;
	int textW = Q_min( CZM_TextWidth( f, label ), r.w - r.h / 2 - side - space );
	const bool withIcon = side && textW + side + space <= r.w - r.h / 3;
	const int total = textW + ( withIcon ? side + space : 0 ), x = r.x + ( r.w - total ) / 2;
	const unsigned color = !enabled ? CzmStyle::Muted() : accent && !primary ? accent : CzmStyle::Ink();
	if( withIcon ) CZM_DrawImage( icon, x, r.y + ( r.h - side ) / 2, side, side, color );
	CZM_DrawText( f, x + ( withIcon ? side + space : 0 ), r.y + ( r.h - CZM_FontHeight( f )) / 2, textW + 2, label, color );
}
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
	enum { BACK=1, MINE, BLOCKED, REFRESH, FIELD, SEARCH, SEND, PREVIOUS, NEXT, PRIMARY, SECONDARY, BLOCK, REPORT, COPY, EDIT, SETTINGS, JOIN, CANCEL, CONFIRM, PEER, LOGIN, REPORT_CHAT, BACKDROP, INVITE, PARTY_INVITE, MODERATE, MORE, MORE_CLOSE, TELEGRAM, PROJECT_MANAGE, TAB=100, PICK=200, MORE_ROW=300, COUNT=400, PROJECT=500, ROW=1000 };
	enum { MORE_ROWS = 4 };
	enum { MAX_PICKS = 4 };
	enum { READ_LIST=1, READ_PROFILE, READ_DIALOG, WRITE_ACTION, WRITE_STATUS, WRITE_MESSAGE, WRITE_REPORT };
	void Layout(); void LayoutProfile(); int Hit(); void Activate( int hit ); void Navigate( int mode ); void Fetch();
	void Write( int kind, const char *path, const char *body ); void Follow( const char *action ); void Send();
	void Input( const char *value ); void EndInput(); void Notice( const char *text ); void Read( const CzmJson &j, int kind );
	void DrawList(); void DrawProfile(); void DrawMore(); void DrawDialog(); void Field( const char *placeholder );
	const char *ProfileStatusText() const;
	int MessageHeight( const Message &m );
	void BuildPicks(); void SendInvite( int index ); void DrawPicker();
	static void AfterRules(); // the message or the status waits in the field while the rules are read
	bool Pressed( int hit ) { return m_pressed == hit && Hit() == hit; }
	int m_mode, m_tab, m_target, m_returnMode, m_view, m_epoch, m_pressed, m_chatMessage;
	int m_read, m_readView, m_readKind, m_write, m_writeView, m_writeKind, m_ack;
	int m_offset, m_nextOffset, m_before, m_nextBefore, m_blocking;
	bool m_open, m_typing, m_loaded, m_canSend, m_editStatus, m_outside, m_joinPending;
	bool m_drag, m_moved; int m_downY; float m_downScroll, m_scroll;
	char m_input[1604], m_sent[1604], m_nonce[80], m_nonceText[1604], m_notice[220], m_confirm[24];
	double m_nextFetch, m_noticeUntil;
	Person m_profile; CUtlVector<Person> m_people; CUtlVector<Message> m_messages;
	CzmRect m_panel, m_back, m_mine, m_blocked, m_refresh, m_tabs[4], m_field, m_search, m_clip, m_prev, m_next;
	CzmRect m_primary, m_secondary, m_block, m_report, m_copy, m_edit, m_settings, m_join, m_peer, m_confirmPanel, m_confirmYes, m_confirmNo;
	CzmRect m_hero, m_profileStatus, m_profileInfo, m_profileCounts[3], m_profileHint, m_profileServer, m_reportChat;
	CzmRect m_telegram, m_projectPanel, m_projectTitle, m_projectManage, m_projectRows[5];
	// "invite to game": the server I play on now and the servers pinned with a heart
	bool m_pickOpen; int m_pickCount;
	char m_pickAddress[MAX_PICKS][64], m_pickProto[MAX_PICKS][4], m_pickName[MAX_PICKS][64];
	CzmRect m_moderate; // SUPPORT: the own profile opens the panel, another one the actions
	// ⋯ of another player's card: report, block, end the friendship
	CzmRect m_more, m_moreSheet, m_moreRows[MORE_ROWS]; int m_moreKind[MORE_ROWS], m_moreCount; bool m_moreOpen;
	double m_appear; // when the card's data came: it rises into place
	CzmRect m_invite, m_partyInvite, m_pickPanel, m_pick[MAX_PICKS], m_pickCancel;
	int W, H, pad;
};
static CCzmSocial *s_window;

CCzmSocial::CCzmSocial() : CMenuFramework( "CzmSocial" )
{
	s_window=this; m_mode=LIST; m_tab=m_target=m_view=m_epoch=m_pressed=m_returnMode=m_chatMessage=0;
	m_read=m_readView=m_readKind=m_write=m_writeView=m_writeKind=m_ack=0;
	m_offset=m_before=m_nextBefore=m_blocking=0; m_nextOffset=-1;
	m_open=m_typing=m_loaded=m_canSend=m_editStatus=m_outside=m_joinPending=m_drag=m_moved=false;
	m_pickOpen=false; m_pickCount=0; m_moreOpen=false; m_moreCount=0; m_appear=0;
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
	m_pickOpen=false; m_pressed=0; m_moreOpen=false;
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
	m_editStatus=false; m_confirm[0]=0; m_input[0]=0; m_notice[0]=0; m_joinPending=false; m_pickOpen=false; m_moreOpen=false;
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
	m_blocking=!strcmp(action,"block")?m_target:0;
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
	if( kind==READ_PROFILE && !m_loaded ) m_appear=EngFuncs::DoubleTime();
	Counts(j); m_loaded=true;
	if( kind==READ_LIST )
	{
		m_people.RemoveAll(); int list=j.Get(0,"people");
		for(int i=0;i<j.Count(list)&&i<40;i++){ Person p;ReadPerson(p,j,j.At(list,i));m_people.AddToTail(p); }
		m_nextOffset=j.Int(j.Get(0,"next"),-1);
		if(m_tab!=1&&m_tab<4&&!m_ack&&m_pStack->Current()==this){
			CUtlString request;request.Append("{\"kind\":");CZM_JsonQuote(request,s_kinds[m_tab]);request.Append(",\"ids\":[");
			int found=0;
			for(int i=0;i<j.Count(list)&&i<40;i++){
				int id=j.Int(j.Get(j.At(list,i),"notice"));
				if(id>0){if(found++)request.Append(",");request.AppendFormat("%d",id);}
			}
			request.Append("]}");
			if(found)m_ack=CZM_NetRequest("POST",CZM_OnlineUrl("/api/v1/social/notifications/read"),CZM_OnlineKey(),request.Get());
			else if(m_tab==2&&s_requests>0&&j.Type(j.Get(j.Get(0,"counts"),"revision"))==CzmJson::T_NULL&&!m_write)
				Write(WRITE_ACTION,"/api/v1/social/action","{\"action\":\"seen\"}");
		}
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
			if(m_writeKind==WRITE_ACTION&&m_blocking)CZM_ChatHidePlayer(m_blocking);
			m_blocking=0;
			if(m_open&&m_writeView==m_view){
				if(m_writeKind==WRITE_MESSAGE){if(!strcmp(m_input,m_sent))m_input[0]=0;m_nonce[0]=0;m_before=0;m_scroll=0;}
				if(m_writeKind==WRITE_STATUS){m_editStatus=false;EndInput();m_input[0]=0;}
				if(m_writeKind==WRITE_REPORT)Notice(T("Жалоба отправлена","Report sent"));
				m_nextFetch=0;
			}
		}else if(m_open&&m_writeView==m_view&&parsed&&!strcmp(j.String(j.Get(0,"error")),"rules")){m_blocking=0;CZM_RulesRefused(j.Int(j.Get(0,"version")),AfterRules);
		}else if(m_open&&m_writeView==m_view){m_blocking=0;Notice(SocialError(parsed?j.String(j.Get(0,"error")):""));if(status==403&&m_mode==DIALOG)m_canSend=false;}
		else m_blocking=0;
	}
	if(m_ack&&CZM_NetPoll(m_ack,&status,body)){m_ack=0;CzmJson j;if(status==200&&j.Parse(body.Get()))Counts(j);}
	if(m_open && m_pStack->Current()==this && !m_write && EngFuncs::DoubleTime()>=m_nextFetch)Fetch();
}

void CCzmSocial::LayoutProfile()
{
	// the personal card: header, the player, the status, three counters, the actions, "in CZM since"
	pad=Q_max(10,(int)(H*.026f));
	const bool project=m_loaded&&m_profile.serverOwner;
	const int width=Q_min((int)(W*(project?.94f:.92f)),(int)(H*(project?1.78f:1.08f)));
	const int gap=Q_max(6,(int)(H*.014f)),bh=Q_max(34,(int)(H*.068f));
	const int leftWidth=project?width*56/100:width,inner=leftWidth-pad*2;
	const HFont meta=CZM_Font(CZMF_UI_META),body=CZM_Font(CZMF_PANEL_TEXT);
	const bool self=m_profile.id==CZM_OnlinePlayer();
	CzmRect empty=CZM_Rect(0,0,0,0);
	m_primary=m_secondary=m_block=m_report=m_edit=m_settings=m_join=m_field=m_search=empty;
	m_copy=m_hero=m_profileStatus=m_profileInfo=m_profileHint=m_profileServer=m_partyInvite=empty;
	m_more=m_moderate=m_refresh=empty;
	m_telegram=m_projectPanel=m_projectTitle=m_projectManage=empty;
	for(int i=0;i<5;i++)m_projectRows[i]=empty;
	for(int i=0;i<3;i++)m_profileCounts[i]=empty;
	m_moreCount=0;m_moreSheet=empty;for(int i=0;i<MORE_ROWS;i++)m_moreRows[i]=empty;
	int y=pad,right=width-pad;
	m_back=CZM_Rect(pad,y,bh,bh);
	if(m_loaded&&self){m_settings=CZM_Rect(right-bh,y,bh,bh);right-=bh+gap;}
	// SUPPORT: the shield sits next to the gear and does something else
	if(CZM_OnlineSupport()&&m_loaded&&m_profile.id>0&&!(m_profile.support&&!self)){m_moderate=CZM_Rect(right-bh,y,bh,bh);right-=bh+gap;}
	if(m_loaded&&m_profile.telegram[0]&&!m_profile.role[0]){const int tw=bh*12/5;m_telegram=CZM_Rect(right-tw,y,tw,bh);right-=tw+gap;}
	m_peer=CZM_Rect(pad+bh+gap,y,right-(pad+bh+gap),bh);
	y+=bh+gap;
	const int contentY=y;
	if(!m_loaded)y+=H*.18f;
	else{
		const int avatar=Q_max(56,(int)(H*.165f));
		const int nickH=CZM_FontHeight(CZM_Font(CZMF_NICK));
		m_hero=CZM_Rect(pad,y,inner,avatar+gap*2);
		const int tx=pad+gap*2+avatar+gap*2;
		char id[32];snprintf(id,sizeof(id),"ID %d",m_profile.id);
		const int chipH=CZM_FontHeight(meta)+gap,icon=chipH*62/100;
		m_copy=CZM_Rect(tx,y+gap+nickH+gap/2,CZM_TextWidth(meta,id)+icon+gap*2+gap/2,chipH);
		y+=m_hero.h+gap;
		if(m_editStatus){
			const int half=(inner-gap)/2;
			m_field=CZM_Rect(pad,y,inner,bh);y+=bh+gap;
			m_secondary=CZM_Rect(pad,y,half,bh);m_primary=CZM_Rect(pad+half+gap,y,half,bh);y+=bh+gap;
		}else{
			int starts[PROFILE_STATUS_LINES+1];
			const int lineH=CZM_FontHeight(body)+2,iconW=self?bh/2+gap:0;
			const int lines=CZM_WrapText(body,ProfileStatusText(),inner-gap*2-iconW,starts,PROFILE_STATUS_LINES);
			m_profileStatus=CZM_Rect(pad,y,inner,Q_max(1,lines)*lineH+gap*2);
			if(self)m_edit=m_profileStatus;
			y+=m_profileStatus.h+gap;
		}
		const int cw=(inner-gap*2)/3,ch=Q_max(40,(int)(H*.088f));
		for(int i=0;i<3;i++)m_profileCounts[i]=CZM_Rect(pad+i*(cw+gap),y,cw,ch);
		y+=ch+gap;
		const bool friends=!strcmp(m_profile.relation,"friend"),following=!strcmp(m_profile.relation,"following");
		const bool blocked=!strcmp(m_profile.relation,"blocked"),unavailable=!strcmp(m_profile.relation,"unavailable");
		const bool join=m_profile.online&&friends&&(m_profile.server[0]||m_profile.lobbyId[0])&&!m_editStatus;
		if(!self&&!m_profile.account){
			int starts[3];
			const int n=CZM_WrapText(CZM_Font(CZMF_SMALL),T("Игрок пока гость. Дружба и ЛС доступны после регистрации.","This player is a guest. Friends and messages require registration."),inner,starts,2);
			m_profileHint=CZM_Rect(pad,y,inner,n*(CZM_FontHeight(CZM_Font(CZMF_SMALL))+2));y+=m_profileHint.h+gap;
		}
		if(join&&m_profile.server[0]){
			m_profileServer=CZM_Rect(pad,y,inner,m_profile.map[0]?Q_max((int)(H*.095f),2*(CZM_FontHeight(CZM_Font(CZMF_SMALL))+2)):(CZM_FontHeight(CZM_Font(CZMF_SMALL))+2));
			y+=m_profileServer.h+gap;
		}
		if(!self&&!m_editStatus){
			// one row: the main action, joining, a lobby invite, then ⋯ with report and block
			const bool invite=friends&&CZM_LobbyCanInvite();
			CzmRect *row[3];int n=0;
			if(!blocked&&!unavailable)row[n++]=&m_primary;
			else if(blocked)row[n++]=&m_block;
			if(join)row[n++]=&m_join;
			if(invite)row[n++]=&m_partyInvite;
			const int rowW=inner-bh-gap;
			const int bw=n?(rowW-gap*(n-1))/n:0;
			if(n==3&&bw<H*.24f){
				const int half=(rowW-gap)/2;
				*row[0]=CZM_Rect(pad,y,half,bh);*row[1]=CZM_Rect(pad+half+gap,y,half,bh);
				m_more=CZM_Rect(pad+inner-bh,y,bh,bh);y+=bh+gap;
				*row[2]=CZM_Rect(pad,y,inner,bh);y+=bh+gap;
			}else{
				for(int i=0;i<n;i++)*row[i]=CZM_Rect(pad+i*(bw+gap),y,bw,bh);
				m_more=n?CZM_Rect(pad+inner-bh,y,bh,bh):CZM_Rect(pad,y,inner,bh);
				y+=bh+gap;
			}
			(void)following;
		}
		m_profileInfo=CZM_Rect(pad,y,inner,CZM_FontHeight(meta)+gap/2);y+=m_profileInfo.h;
	}
	if(project){
		const int count=Q_max(1,m_profile.ownedCount),titleH=CZM_FontHeight(CZM_Font(CZMF_UI_LABEL))+gap;
		y=Q_max(y,contentY+gap+titleH+gap+count*24+(count-1)*gap+(self?bh+gap*2:gap));
		m_projectPanel=CZM_Rect(leftWidth,contentY,width-leftWidth-pad,y-contentY);
		m_projectTitle=CZM_Rect(m_projectPanel.x+gap,contentY+gap,m_projectPanel.w-gap*2,CZM_FontHeight(CZM_Font(CZMF_UI_LABEL))+gap);
		const int rowsY=m_projectTitle.y+m_projectTitle.h+gap;
		const int bottom=y-gap-(self?bh+gap:0);
		const int rowH=Q_min(bh+gap*2,Q_max(24,(bottom-rowsY-gap*(count-1))/count));
		for(int i=0;i<m_profile.ownedCount;i++)m_projectRows[i]=CZM_Rect(m_projectPanel.x+gap,rowsY+i*(rowH+gap),m_projectPanel.w-gap*2,rowH);
		if(self)m_projectManage=CZM_Rect(m_projectPanel.x+gap,y-gap-bh,m_projectPanel.w-gap*2,bh);
	}
	m_clip=CZM_Rect(pad,contentY,inner,y-contentY);
	const int height=y+pad;
	// the card rises into place once its data is there
	const double t=bound(0.0,( EngFuncs::DoubleTime()-m_appear )/0.2,1.0),ease=1.0-(1.0-t)*(1.0-t)*(1.0-t);
	m_panel=CZM_Rect((W-width)/2,(H-height)/2+(int)(( 1.0-ease )*H*.035f),width,height);
	CzmRect *rects[]={&m_back,&m_moderate,&m_peer,&m_hero,&m_copy,&m_profileStatus,&m_profileInfo,
		&m_profileCounts[0],&m_profileCounts[1],&m_profileCounts[2],&m_profileHint,&m_profileServer,
		&m_primary,&m_secondary,&m_block,&m_report,&m_edit,&m_settings,&m_join,&m_partyInvite,&m_more,&m_field,&m_clip,
		&m_telegram,&m_projectPanel,&m_projectTitle,&m_projectManage,&m_projectRows[0],&m_projectRows[1],&m_projectRows[2],&m_projectRows[3],&m_projectRows[4]};
	for(unsigned i=0;i<sizeof(rects)/sizeof(rects[0]);i++)if(rects[i]->w&&rects[i]->h){rects[i]->x+=m_panel.x;rects[i]->y+=m_panel.y;}
	if(m_moreOpen&&!self&&m_loaded){
		// ⋯: report, block or unblock, end the friendship or the request, close
		if(m_profile.account&&strcmp(m_profile.relation,"blocked"))m_moreKind[m_moreCount++]=BLOCK; // unblocking is on the card
		if(!strcmp(m_profile.relation,"friend")||!strcmp(m_profile.relation,"following"))m_moreKind[m_moreCount++]=SECONDARY;
		m_moreKind[m_moreCount++]=REPORT;
		m_moreKind[m_moreCount++]=CANCEL;
		const int sw=Q_min((int)(W*.86f),(int)(H*.80f)),title=CZM_FontHeight(CZM_Font(CZMF_UI_TITLE))+gap*2;
		const int sh=pad*2+title+m_moreCount*(bh+gap)-gap;
		m_moreSheet=CZM_Rect((W-sw)/2,(H-sh)/2,sw,sh);
		for(int i=0;i<m_moreCount;i++)m_moreRows[i]=CZM_Rect(m_moreSheet.x+pad,m_moreSheet.y+pad+title+i*(bh+gap),sw-pad*2,bh);
	}
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
	m_moderate=CZM_Rect(0,0,0,0);
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
	if(m_moreOpen&&m_mode==PROFILE){for(int i=0;i<m_moreCount;i++)if(m_moreRows[i].HasCursor())return MORE_ROW+i;return MORE_CLOSE;}
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
		const bool self=m_profile.id==CZM_OnlinePlayer();
		if(m_moderate.w&&m_moderate.HasCursor())return MODERATE;
		if(m_settings.w&&m_settings.HasCursor())return SETTINGS;
		if(m_copy.HasCursor())return COPY;
		if(m_telegram.w&&m_telegram.HasCursor())return TELEGRAM;
		if(m_projectManage.w&&m_projectManage.HasCursor())return PROJECT_MANAGE;
		for(int i=0;i<m_profile.ownedCount;i++)if(m_projectRows[i].w&&m_projectRows[i].HasCursor()&&!CZM_ServerBlocked(m_profile.owned[i].address))return PROJECT+i;
		if(m_editStatus){if(m_field.HasCursor())return FIELD;if(m_primary.HasCursor())return SEND;if(m_secondary.HasCursor())return CANCEL;return 0;}
		if(self){
			if(m_edit.w&&m_edit.HasCursor())return EDIT;
			for(int i=0;i<3;i++)if(m_profileCounts[i].HasCursor())return COUNT+i;
		}else{
			if(m_primary.w&&m_primary.HasCursor())return PRIMARY;
			if(m_block.w&&m_block.HasCursor())return BLOCK;
			if(m_join.w&&m_join.HasCursor())return JOIN;
			if(m_partyInvite.w&&m_partyInvite.HasCursor())return PARTY_INVITE;
			if(m_more.w&&m_more.HasCursor())return MORE;
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
	if(hit==TELEGRAM){CZM_CommunityShow("telegram",m_profile.id);return;}
	if(hit==PROJECT_MANAGE){CZM_CommunityShow("servers",m_profile.id);return;}
	if(hit>=PROJECT&&hit<PROJECT+5){const int i=hit-PROJECT;if(i<m_profile.ownedCount&&!CZM_ServerBlocked(m_profile.owned[i].address)){char address[64];Q_strncpy(address,m_profile.owned[i].address,sizeof(address));Hide();CZM_JoinAddress(address);}return;}
	if(hit==REFRESH){m_nextFetch=0;return;}
	if(hit==CANCEL&&m_pickOpen){m_pickOpen=false;return;}
	if(hit==CANCEL){m_confirm[0]=0;m_editStatus=false;EndInput();m_input[0]=0;return;}
	if(hit==MORE){EndInput();m_moreOpen=true;return;}
	if(hit==MORE_CLOSE){m_moreOpen=false;return;}
	if(hit>=MORE_ROW&&hit<MORE_ROW+MORE_ROWS){
		const int i=hit-MORE_ROW,kind=i<m_moreCount?m_moreKind[i]:CANCEL;
		m_moreOpen=false;
		if(kind!=CANCEL)Activate(kind);
		return;
	}
	if(hit>=COUNT&&hit<COUNT+3){static const int tabs[]={0,2,3};m_tab=tabs[hit-COUNT];Navigate(LIST);return;}
	if(hit==MODERATE){
		EndInput();
		if(m_profile.id==CZM_OnlinePlayer())CZM_ModerationOpen();
		else CZM_ModerationTarget(m_profile.id,m_profile.nick,m_chatMessage,0,"");
		return;
	}
    if(hit==PARTY_INVITE) {
        CZM_LobbyInviteFriend(m_profile.id);
        Notice(T("Отправляем приглашение в лобби","Sending lobby invite"));
        return;
    }
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
	if(hit==SEND&&(m_editStatus?m_input[0]!=0:m_input[0]&&m_canSend)&&!m_write&&!CZM_RulesAllow(AfterRules))return;
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
    if(hit==JOIN){
        if(m_profile.lobbyId[0]){
            char lobby[64];Q_strncpy(lobby,m_profile.lobbyId,sizeof(lobby));
            Hide();CZM_OpenLobbyById(lobby);
        }else{m_joinPending=true;m_nextFetch=0;}
        return;
    }
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
	if(UI::Key::IsEscape(key)){if(m_moreOpen)m_moreOpen=false;else if(m_confirm[0])m_confirm[0]=0;else if(m_typing)EndInput();else Activate(BACK);return true;}
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
	int notices[]={s_newFriends,s_unread,s_requests,s_followingUpdates};
	for(int i=0;i<4;i++){
		const CzmRect r=m_tabs[i];const int bh=Q_max(16,r.h*55/100),bw=CZM_CountBadgeWidth(notices[i],bh);
		char text[100];
		if(i==1)Q_strncpy(text,tabs[i],sizeof(text));else snprintf(text,sizeof(text),"%s  %d",tabs[i],totals[i]);
		Button(r,"",m_tab==i,Pressed(TAB+i));
		const int inset=Q_max(4,r.h/5),width=r.w-inset*2-(bw?bw+inset:0);
		const int font=CZM_TextWidth(CZM_Font(CZMF_LANG),text)<=width?CZMF_LANG:CZMF_SMALL;
		CZM_DrawText(CZM_Font(font),r.x+inset,r.y+(r.h-CZM_FontHeight(CZM_Font(font)))/2,width,text,CZM_White(),QM_CENTER);
		if(bw)CZM_DrawCountBadge(CZM_Rect(r.x+r.w-inset-bw,r.y+(r.h-bh)/2,bw,bh),notices[i]);
	}
	Field(T("Найти игрока по ID","Find player by ID"));Button(m_search,T("Найти","Find"),true,Pressed(SEARCH));
	if(!Account()){Label(CZM_Rect(m_clip.x,m_clip.y,m_clip.w,H*.09f),T("Друзья и переписка сохраняются в аккаунте","Friends and messages are saved in your account"));Button(m_prev,T("Войти","Sign in"),true);return;}
	int rh=H*.105f; m_scroll=bound(0.0f,m_scroll,(float)Q_max(0,m_people.Count()*rh-m_clip.h));
	UI::Scissor::PushScissor(m_clip.x,m_clip.y,m_clip.w,m_clip.h);
	for(int i=0;i<m_people.Count();i++){
		const Person &p=m_people[i];CzmRect r=CZM_Rect(m_clip.x,m_clip.y+i*rh-(int)m_scroll,m_clip.w,rh-pad/2);if(r.y+r.h<m_clip.y||r.y>m_clip.y+m_clip.h)continue;
		UI_FillRect(r.x,r.y,r.w,r.h,Pressed(ROW+i)?PackRGBA(69,30,41,245):PackRGBA(17,26,37,240));
		int av=r.h-pad;CZM_DrawImage(CZM_AvatarFor(p.avatar,p.id),r.x+pad/2,r.y+pad/2,av,av);
		char text[180];int tx=r.x+av+pad,tw=r.w-av-pad*2;
		if(p.role[0]){
			// nick, the tag, then the ID: the tag must not be cut away by a long nick
			const int fh=CZM_FontHeight(CZM_Font(CZMF_LANG)),tagH=fh,tagW=CZM_RoleTagWidth(p.role,tagH,p.project,tw/2);
			const int nw=Q_min(CZM_TextWidth(CZM_Font(CZMF_LANG),p.nick)+2,tw/2);
			Label(CZM_Rect(tx,r.y+pad/4,nw,r.h/2),p.nick,CZMF_LANG);
			CZM_DrawRoleTag(tx+nw+pad/2,r.y+pad/4+(r.h/2-tagH)/2,tagH,p.role,p.project,tagW);
			snprintf(text,sizeof(text),"·  ID %d%s",p.id,p.unread?"  +":"");
			const int ix=tx+nw+pad/2+tagW+pad/2;Label(CZM_Rect(ix,r.y+pad/4,tx+tw-ix,r.h/2),text,CZMF_LANG);
		}else{snprintf(text,sizeof(text),"%s  ·  ID %d%s",p.nick,p.id,p.unread?"  +":"");Label(CZM_Rect(tx,r.y+pad/4,tw,r.h/2),text,CZMF_LANG);}
		char seen[100];SeenText(p,seen,sizeof(seen));
		Label(CZM_Rect(tx,r.y+r.h/2-pad/4,tw,r.h/2),m_tab==1&&p.last[0]?p.last:seen,CZMF_SMALL,p.online?PackRGBA(112,220,161,255):CZM_Grey());
		if(p.unread){snprintf(text,sizeof(text),"%d",p.unread);CZM_DrawText(CZM_Font(CZMF_LANG),r.x+r.w-H*.08f,r.y+pad,H*.07f,text,PackRGBA(255,95,110,255),QM_RIGHT);}
	}
	if(!m_people.Count())Label(m_clip,m_tab==4?T("Заблокированных игроков нет","No blocked players"):m_loaded?T("Пока пусто","Nothing here yet"):T("Загружаем…","Loading…"),CZMF_PANEL_TEXT,CZM_Grey());
	UI::Scissor::PopScissor();
	if(m_offset>0)Button(m_prev,T("Назад","Previous"));if(m_nextOffset>=0)Button(m_next,T("Далее","Next"));
	if(m_tab==4)Label(CZM_Rect(m_prev.x+m_prev.w+pad,m_prev.y,m_next.x-m_prev.x-m_prev.w-pad*2,m_prev.h),T("Заблокированные игроки","Blocked players"),CZMF_SMALL);
}

const char *CCzmSocial::ProfileStatusText() const
{
	if(m_profile.status[0])return m_profile.status;
	if(m_profile.id!=CZM_OnlinePlayer())return T("Статус не указан","No status yet");
	return Account()?T("Добавить статус","Add a status"):T("Войдите, чтобы добавить статус","Sign in to add a status");
}

void CCzmSocial::DrawProfile()
{
	using namespace CzmStyle;
	const Person &p=m_profile;
	const bool self=p.id==CZM_OnlinePlayer();
	const int gap=Q_max(6,(int)(H*.014f));
	const HFont meta=CZM_Font(CZMF_UI_META),body=CZM_Font(CZMF_PANEL_TEXT),nickFont=CZM_Font(CZMF_NICK);
	// header: back, "Profile", the moderation shield and the gear
	Chip(m_back,UI_DIR "icon_back.png",Pressed(BACK));
	if(p.role[0]&&!p.support)CZM_DrawRoleTag(m_peer.x,m_peer.y+m_peer.h/6,m_peer.h*2/3,p.role,p.project,m_peer.w);
	else Text(m_peer,T("Профиль","Profile"),CZMF_UI_TITLE);
	if(m_moderate.w)Chip(m_moderate,UI_DIR "icon_shield.png",Pressed(MODERATE),AccentGold());
	if(m_settings.w)Chip(m_settings,UI_DIR "icon_gear.png",Pressed(SETTINGS));
	if(!m_loaded){Text(m_clip,T("Загружаем профиль…","Loading profile…"),CZMF_PANEL_TEXT,Muted(),QM_CENTER);return;}

	// the player: a soft red light behind the picture, a thin frame that slowly breathes
	Surface(m_hero,PackRGBA(22,26,34,255),p.role[0]?CZM_RoleColor(p.role,110):PackRGBA(48,55,68,255));
	const int av=Q_max(56,(int)(H*.165f)),ax=m_hero.x+gap*2,ay=m_hero.y+(m_hero.h-av)/2;
	CZM_DrawImage(UI_DIR "glow.png",ax-av*45/100,ay-av*45/100,av*190/100,av*190/100,p.role[0]?CZM_RoleColor(p.role,95):PackRGBA(229,40,58,95));
	CZM_DrawImage(CZM_AvatarFor(p.avatar,p.id),ax,ay,av,av);
	const double wave=0.5+0.5*sin(EngFuncs::DoubleTime()*2.0*M_PI/3.2);
	const int ring=Q_max(2,av/30);
	CZM_DrawImage(UI_DIR "icon_ring.png",ax-ring,ay-ring,av+ring*2,av+ring*2,CZM_RoleColor(p.role,(int)(150+70*wave)));
	const int tx=m_copy.x,tw=m_hero.x+m_hero.w-gap*2-tx;
	{
		// the nick, then the official role and the current Top 100 rank: both, independent
		const int nh=CZM_FontHeight(nickFont),tagH=nh*82/100;
		const int supportW=p.support?CZM_SupportTagWidth(tagH)+gap:0,topW=CZM_TopTagWidth(p.topPlace,tagH);
		const int tagW=supportW+(topW?topW+gap:0);
		const int nw=Q_max(0,Q_min(CZM_TextWidth(nickFont,p.nick)+2,tw-tagW));
		CZM_DrawText(nickFont,tx,m_hero.y+gap,nw,p.nick,Ink());
		int x=tx+nw+gap;
		if(p.support)x+=CZM_DrawSupportTag(x,m_hero.y+gap+(nh-tagH)/2,tagH)+gap;
		if(topW)CZM_DrawTopTag(x,m_hero.y+gap+(nh-tagH)/2,tagH,p.topPlace);
	}
	// the ID with a copy sign: the ID of this very player
	{
		char id[32];snprintf(id,sizeof(id),"ID %d",p.id);
		Surface(m_copy,Pressed(COPY)?PackRGBA(41,51,67,255):PackRGBA(30,36,46,255),Border(),m_copy.h/2);
		const int icon=m_copy.h*62/100;
		CZM_DrawText(meta,m_copy.x+gap,m_copy.y+(m_copy.h-CZM_FontHeight(meta))/2,CZM_TextWidth(meta,id)+2,id,Muted());
		CZM_DrawImage(UI_DIR "icon_copy.png",m_copy.x+m_copy.w-gap-icon,m_copy.y+(m_copy.h-icon)/2,icon,icon,Muted());
	}
	// presence, as it is: online in the menu, in a lobby, in a game, or last seen
	{
		char seen[160];SeenText(p,seen,sizeof(seen));
		const int sy=m_copy.y+m_copy.h+gap/2,dot=Q_max(7,(int)(H*.012f)),fh=CZM_FontHeight(CZM_Font(CZMF_SMALL));
		CZM_DrawImage(UI_DIR "dot.png",tx,sy+(fh-dot)/2,dot,dot,p.online?PackRGBA(66,216,137,255):PackRGBA(120,128,142,255));
		CZM_DrawText(CZM_Font(CZMF_SMALL),tx+dot+gap,sy,tw-dot-gap,seen,p.online?PackRGBA(112,220,161,255):Muted());
		// the place among all players and the time on game servers
		if(p.topSeconds>0&&p.topPlace>0){
			char time[48],line[120];CZM_FormatPlaytime(p.topSeconds,time,sizeof(time));
			if(p.topPlace<=100)snprintf(line,sizeof(line),T("№%d в Топ 100  ·  %s на серверах","#%d in the Top 100  ·  %s on servers"),p.topPlace,time);
			else snprintf(line,sizeof(line),T("Место №%d  ·  %s на серверах","Place #%d  ·  %s on servers"),p.topPlace,time);
			const int ly=sy+fh+gap/2,icon=fh;
			const unsigned color=p.topPlace<=100?CZM_TopColor(p.topPlace):Muted();
			CZM_DrawImage(CZM_TopCrown(p.topPlace),tx,ly,icon,icon,color);
			CZM_DrawText(CZM_Font(CZMF_SMALL),tx+icon+gap/2,ly,tw-icon-gap/2,line,p.topPlace<=100?color:Muted());
		}
	}
	// the status: the whole row edits it on the own card
	if(m_editStatus){
		Surface(m_field,PackRGBA(14,20,29,255),m_typing?AccentRed():Border());
		const char *visible=m_input[0]?m_input:T("Ваш статус, до 100 символов","Your status, up to 100 characters");
		if(m_input[0])while(*visible&&CZM_TextWidth(body,visible)>m_field.w-gap*3){visible++;while((*visible&0xc0)==0x80)visible++;}
		CZM_DrawText(body,m_field.x+gap*3/2,m_field.y+(m_field.h-CZM_FontHeight(body))/2,m_field.w-gap*3,visible,m_input[0]?Ink():Muted());
		if(m_typing&&((int)(EngFuncs::DoubleTime()*2)%2)==0){const int x=m_field.x+gap*3/2+(m_input[0]?CZM_TextWidth(body,visible):0);UI_FillRect(x,m_field.y+m_field.h/5,Q_max(1,H/400),m_field.h*3/5,AccentRed());}
		ActionButton(m_secondary,"",T("Отмена","Cancel"),false,Pressed(CANCEL));
		ActionButton(m_primary,UI_DIR "icon_check.png",m_write?T("Сохраняем…","Saving…"):T("Сохранить","Save"),true,Pressed(SEND),!m_write);
	}else{
		const bool down=self&&Pressed(EDIT);
		Surface(m_profileStatus,down?PackRGBA(33,42,56,255):PackRGBA(20,24,32,255),PackRGBA(44,51,63,255));
		const char *status=ProfileStatusText();
		const int iconW=self?m_back.h/2+gap:0,lineH=CZM_FontHeight(body)+2;
		int starts[PROFILE_STATUS_LINES+1];
		const int lines=CZM_WrapText(body,status,m_profileStatus.w-gap*2-iconW,starts,PROFILE_STATUS_LINES);
		for(int i=0;i<lines;i++){char line[410];CZM_WrapLine(status,starts,i,line,sizeof(line));
			CZM_DrawText(body,m_profileStatus.x+gap,m_profileStatus.y+gap+i*lineH,m_profileStatus.w-gap*2-iconW,line,p.status[0]?Ink():Muted());}
		if(self){const int icon=Q_min(m_back.h/2,m_profileStatus.h-gap);CZM_DrawImage(UI_DIR "icon_pencil.png",m_profileStatus.x+m_profileStatus.w-gap-icon,m_profileStatus.y+(m_profileStatus.h-icon)/2,icon,icon,p.status[0]?Muted():AccentRed());}
	}
	// friends, followers, following: a clear number, a calm caption; the own lists open
	if(m_telegram.w)ActionButton(m_telegram,UI_DIR "icon_chat.png","Telegram",false,Pressed(TELEGRAM),true,AccentBlue());
	if(m_projectPanel.w){
		Surface(m_projectPanel,PackRGBA(18,29,34,255),CZM_RoleColor("server_owner",100));
		Text(m_projectTitle,p.project[0]?p.project:T("Серверы проекта","Project servers"),CZMF_UI_LABEL,CZM_RoleColor("server_owner"));
		for(int i=0;i<p.ownedCount;i++){
			const CzmRect &r=m_projectRows[i];const bool available=!CZM_ServerBlocked(p.owned[i].address);
			Surface(r,Pressed(PROJECT+i)?PackRGBA(33,65,61,255):PackRGBA(23,36,43,255),Border());
			const int lh=CZM_FontHeight(CZM_Font(CZMF_UI_META)),inset=Q_max(4,gap/2);
			const bool verified=CZM_ServerOwner(p.owned[i].address)>0;
			const int shield=Q_min(r.h-inset*2,lh*3/2),cw=r.w-inset*2-gap-(verified?shield+gap:0);
			if(verified)CZM_DrawImage(UI_DIR "icon_shield.png",r.x+r.w-inset-shield,r.y+(r.h-shield)/2,shield,shield,CZM_RoleColor("server_owner"));
			CZM_DrawText(meta,r.x+inset,r.y+(r.h-lh*2-2)/2,cw,p.owned[i].name[0]?p.owned[i].name:p.owned[i].address,available?Ink():Muted());
			CZM_DrawText(meta,r.x+inset,r.y+(r.h-lh*2-2)/2+lh+2,cw,p.owned[i].address,available?CZM_RoleColor("server_owner"):Muted());
		}
		if(!p.ownedCount)Text(CZM_Rect(m_projectTitle.x,m_projectTitle.y+m_projectTitle.h+gap,m_projectTitle.w,m_back.h),T("Серверы пока не добавлены","No servers added yet"),CZMF_UI_META,Muted());
		if(m_projectManage.w)ActionButton(m_projectManage,UI_DIR "icon_gear.png",T("Управлять","Manage"),false,Pressed(PROJECT_MANAGE));
	}
	{
		const char *names[]={T("Друзья","Friends"),T("Подписчики","Followers"),T("Подписки","Following")};
		const int values[]={p.friends,p.followers,p.following};
		const HFont number=CZM_Font(CZMF_UI_TITLE);
		for(int i=0;i<3;i++){
			const CzmRect &r=m_profileCounts[i];
			Surface(r,self&&Pressed(COUNT+i)?PackRGBA(33,42,56,255):PackRGBA(24,30,40,255),PackRGBA(44,51,63,255));
			char text[24];snprintf(text,sizeof(text),"%d",values[i]);
			const int nh=CZM_FontHeight(number),mh=CZM_FontHeight(meta),top=r.y+(r.h-nh-mh-2)/2;
			CZM_DrawText(number,r.x+gap,top,r.w-gap*2,text,Ink(),QM_CENTER);
			CZM_DrawText(meta,r.x+gap,top+nh+2,r.w-gap*2,names[i],Muted(),QM_CENTER);
		}
	}
	if(m_profileHint.h){
		const char *hint=T("Игрок пока гость. Дружба и ЛС доступны после регистрации.","This player is a guest. Friends and messages require registration.");
		int starts[3];const int n=CZM_WrapText(CZM_Font(CZMF_SMALL),hint,m_profileHint.w,starts,2),h=CZM_FontHeight(CZM_Font(CZMF_SMALL))+2;
		for(int i=0;i<n;i++){char line[240];CZM_WrapLine(hint,starts,i,line,sizeof(line));CZM_DrawText(CZM_Font(CZMF_SMALL),m_profileHint.x,m_profileHint.y+i*h,m_profileHint.w,line,Muted());}
	}
	if(m_profileServer.h){
		char text[160];int sx=m_profileServer.x,sw=m_profileServer.w;
		if(p.map[0]){const int imageW=Q_min((int)(m_profileServer.h*1.7f),m_profileServer.w/3);CZM_DrawMapPreview(p.map,m_profileServer.x,m_profileServer.y,imageW,m_profileServer.h,p.server);sx+=imageW+gap;sw-=imageW+gap;}
		if(CZM_ServerOwner(p.server)){
			const int side=Q_min(m_profileServer.h,CZM_FontHeight(CZM_Font(CZMF_SMALL))*2);
			CZM_DrawImage(UI_DIR "icon_shield.png",sx+sw-side,m_profileServer.y,side,side,CZM_RoleColor("server_owner"));sw-=side+gap;
		}
		snprintf(text,sizeof(text),"%s %s",T("Сервер:","Server:"),p.server);
		const int sh=CZM_FontHeight(CZM_Font(CZMF_SMALL))+2;
		CZM_DrawText(CZM_Font(CZMF_SMALL),sx,m_profileServer.y,sw,text,Muted());
		if(p.map[0])CZM_DrawText(CZM_Font(CZMF_SMALL),sx,m_profileServer.y+sh,sw,p.map,Muted());
	}
	// another player: what the relationship allows
	if(!self&&!m_editStatus){
		const bool friends=!strcmp(p.relation,"friend"),following=!strcmp(p.relation,"following"),follower=!strcmp(p.relation,"follower");
		if(m_primary.w){
			const char *label=friends?T("Написать","Message"):following?T("Заявка отправлена","Request sent"):follower?T("Принять в друзья","Accept friend"):T("Добавить в друзья","Add friend");
			const char *icon=friends?UI_DIR "icon_chat.png":following?UI_DIR "icon_clock.png":follower?UI_DIR "icon_check.png":UI_DIR "icon_person_add.png";
			ActionButton(m_primary,icon,label,p.account&&!following,Pressed(PRIMARY),p.account);
		}
		if(m_block.w)ActionButton(m_block,UI_DIR "icon_block.png",T("Разблокировать","Unblock"),false,Pressed(BLOCK));
		if(m_join.w)ActionButton(m_join,UI_DIR "icon_play.png",T("Присоединиться","Join"),false,Pressed(JOIN),true,Success());
		if(m_partyInvite.w)ActionButton(m_partyInvite,UI_DIR "icon_users.png",T("Позвать в лобби","Invite to lobby"),false,Pressed(PARTY_INVITE));
		if(m_more.w){
			if(m_more.w>m_more.h)ActionButton(m_more,UI_DIR "icon_more.png",T("Ещё","More"),false,Pressed(MORE));
			else Chip(m_more,UI_DIR "icon_more.png",Pressed(MORE)||m_moreOpen);
		}
	}
	// "In CZM since": the date the service keeps, nothing invented
	{
		time_t stamp=p.created;struct tm date;char when[40],text[96];localtime_r(&stamp,&date);strftime(when,sizeof(when),"%d.%m.%Y",&date);
		snprintf(text,sizeof(text),"%s %s",p.account?T("В CZM с","In CZM since"):T("Гостевой профиль с","Guest since"),when);
		Text(m_profileInfo,text,CZMF_UI_META,Muted(),QM_CENTER);
	}
}

void CCzmSocial::DrawMore()
{
	using namespace CzmStyle;
	const int gap=Q_max(6,(int)(H*.014f));
	UI_FillRect(0,0,W,H,PackRGBA(2,6,12,205));
	Surface(m_moreSheet,PackRGBA(18,24,34,255),PackRGBA(58,64,78,255),Q_max(6,(int)(H*.022f)));
	const HFont title=CZM_Font(CZMF_UI_TITLE);
	CZM_DrawText(title,m_moreSheet.x+pad,m_moreSheet.y+pad,m_moreSheet.w-pad*2,m_profile.nick,Ink());
	for(int i=0;i<m_moreCount;i++){
		const int kind=m_moreKind[i];
		const bool blocked=!strcmp(m_profile.relation,"blocked");
		const char *label=kind==REPORT?T("Пожаловаться","Report"):
			kind==BLOCK?(blocked?T("Разблокировать","Unblock"):T("Заблокировать","Block")):
			kind==SECONDARY?(!strcmp(m_profile.relation,"friend")?T("Удалить из друзей","Remove friend"):T("Отменить заявку","Cancel request")):
			T("Закрыть","Close");
		const char *icon=kind==REPORT?UI_DIR "icon_flag.png":kind==BLOCK?UI_DIR "icon_block.png":kind==SECONDARY?UI_DIR "icon_close.png":"";
		ActionButton(m_moreRows[i],icon,label,false,Pressed(MORE_ROW+i),true,kind==REPORT||kind==BLOCK?AccentRed():0);
	}
	(void)gap;
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
	Layout();UI_FillRect(0,0,W,H,PackRGBA(0,0,0,150));
	if(m_mode==PROFILE){
		// a dense graphite card, readable over the bright game picture
		CzmStyle::Surface(m_panel,PackRGBA(15,18,24,252),PackRGBA(58,64,78,255),Q_max(8,(int)(H*.03f)));
		DrawProfile();
	}else{
		CZM_DrawPanel(m_panel);
		CZM_DrawImage(UI_DIR "chip_round.png",m_back.x,m_back.y,m_back.w,m_back.h);int icon=m_back.h/2;CZM_DrawImage(UI_DIR "icon_back.png",m_back.x+icon/2,m_back.y+icon/2,icon,icon);
		CZM_DrawImage(UI_DIR "icon_refresh.png",m_refresh.x+icon/2,m_refresh.y+icon/2,icon,icon);
		Label(m_peer,m_mode==LIST?T("ДРУЗЬЯ","FRIENDS"):m_profile.nick[0]?m_profile.nick:T("ЛИЧНЫЕ СООБЩЕНИЯ","PRIVATE MESSAGES"),CZMF_NICK);
		if(m_mode==LIST)DrawList();else DrawDialog();
	}
	if(m_notice[0]&&EngFuncs::DoubleTime()<m_noticeUntil){CzmRect r=CZM_Rect(W*.12f,H*.035f,W*.76f,H*.075f);CZM_DrawPill(UI_DIR "button_secondary.png",r.x,r.y,r.w,r.h);Label(CZM_Rect(r.x+pad,r.y,r.w-pad*2,r.h),m_notice,CZMF_LANG);}
	if(m_pickOpen)DrawPicker();
	if(m_moreOpen&&m_mode==PROFILE&&m_moreCount)DrawMore();
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

void CCzmSocial::AfterRules()
{
	if(s_window&&s_window->m_open)s_window->Activate(SEND);
}
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
int CZM_SocialNotifications( void ) { return Q_max(0,s_unread)+Q_max(0,s_requests)+Q_max(0,s_newFriends)+Q_max(0,s_followingUpdates); }
int CZM_ChatUnread(int room){return room>=0&&room<3?s_chatUnread[room]:s_chatUnread[0]+s_chatUnread[1]+s_chatUnread[2];}
void CZM_ChatMarkRead(int room,int through){if(Account()&&room>=0&&room<3)s_chatWanted[room]=Q_max(s_chatWanted[room],through);}

void CZM_SocialFrame( void )
{
	if(strcmp(s_key,CZM_OnlineKey())||s_identity!=CZM_OnlineIdentity()){
		Q_strncpy(s_key,CZM_OnlineKey(),sizeof(s_key));s_identity=CZM_OnlineIdentity();s_epoch++;s_sessionInvalid=false;
		s_unread=s_requests=s_friends=s_followers=s_following=s_newFriends=s_followingUpdates=0;s_countsRevision=-1;
		for(int i=0;i<3;i++){Abandon(s_chatRead[i]);s_chatUnread[i]=s_chatWanted[i]=s_chatSent[i]=0;s_chatRetry[i]=0;}
		s_nextPresence=0;s_connection[0]=0;Abandon(s_presence);
	}
	char self[24];snprintf(self,sizeof(self),"%d",CZM_OnlinePlayer());if(strcmp(EngFuncs::GetCvarString("czm_profile_id"),self))EngFuncs::CvarSetString("czm_profile_id",self);
	int status;CUtlString body;for(int i=s_abandoned.Count()-1;i>=0;i--)if(CZM_NetPoll(s_abandoned[i],&status,body))s_abandoned.Remove(i);
	if(s_presence&&CZM_NetPoll(s_presence,&status,body)){s_presence=0;CzmJson j;if(s_presenceEpoch==s_epoch&&status==200&&j.Parse(body.Get()))Counts(j);else if(status==401&&!s_sessionInvalid){s_sessionInvalid=true;s_epoch++;s_unread=s_requests=0;}}
	if(CZM_OnlineReady()){
		CzmTab::State state;bool playing=CL_IsActive()&&CzmTab::Parse(EngFuncs::GetCvarString("czm_tab_state"),state);
		const char *map=playing?EngFuncs::GetCvarString("czm_current_map"):"";char connection[160];snprintf(connection,sizeof(connection),"%s|%s",playing?state.server:"",map);
		if(strcmp(connection,s_connection)){Q_strncpy(s_connection,connection,sizeof(s_connection));s_nextPresence=0;}
		if(!s_presence&&EngFuncs::DoubleTime()>=s_nextPresence){CUtlString request;request.Append("{\"server\":");CZM_JsonQuote(request,playing?state.server:"");request.Append(",\"map\":");CZM_JsonQuote(request,map);request.Append("}");s_presence=CZM_NetRequest("POST",CZM_OnlineUrl("/api/v1/social/presence"),CZM_OnlineKey(),request.Get());s_presenceEpoch=s_epoch;s_nextPresence=EngFuncs::DoubleTime()+(CL_IsActive()?30:10);}
	}
	if(s_window)s_window->Frame();
	const char *rooms[]={"global","ru","en"};
	for(int i=0;i<3;i++){
		if(s_chatRead[i]&&CZM_NetPoll(s_chatRead[i],&status,body)){
			s_chatRead[i]=0;CzmJson j;
			if(s_chatEpoch[i]==s_epoch&&status==200&&j.Parse(body.Get()))Counts(j);
			else{s_chatSent[i]=0;s_chatRetry[i]=EngFuncs::DoubleTime()+5;}
		}
		if(Account()&&!s_chatRead[i]&&s_chatWanted[i]>s_chatSent[i]&&EngFuncs::DoubleTime()>=s_chatRetry[i]){
			char path[100],payload[64];snprintf(path,sizeof(path),"/api/v1/chat/%s/read",rooms[i]);snprintf(payload,sizeof(payload),"{\"through\":%d}",s_chatWanted[i]);
			s_chatRead[i]=CZM_NetRequest("POST",CZM_OnlineUrl(path),CZM_OnlineKey(),payload);
			if(s_chatRead[i]){s_chatSent[i]=s_chatWanted[i];s_chatEpoch[i]=s_epoch;}
		}
	}
}
