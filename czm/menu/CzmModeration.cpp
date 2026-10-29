/* Counter Zombie Mobile: moderation by the official SUPPORT account. GPL-3.0-or-later. */
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
#include "CzmMenu.h"
#include "CzmDesign.h"
#include "CzmJson.h"

/*
The entries to this window are shown only to the player the service names SUPPORT in hello,
and the service checks the role again on every request: the window itself grants nothing.
Each action carries a nonce, so a retry after a lost answer is never applied twice.

Two ways in: the panel (open reports, active restrictions, the journal) from the own profile,
and a player straight from a chat message, a profile or a lobby. Both end on the same steps:
action, duration, reason, a check of everything, then the request.
*/
#define UI_DIR "gfx/czm/ui/"

namespace
{
const char *T( const char *ru, const char *en ) { return CZM_IsRussian() ? ru : en; }

enum { TAB_REPORTS, TAB_SANCTIONS, TAB_HISTORY, TAB_COUNT };
enum { PAGE_PANEL, PAGE_TARGET, PAGE_DURATION, PAGE_REASON, PAGE_CONFIRM };
enum { NEED_MESSAGE = 1, NEED_REPORT = 2, NEED_LOBBY = 4 };

struct ModAction { const char *code, *ru, *en; int need; bool sanction, danger; };
const ModAction s_actions[] =
{
	{ "delete_message", "Удалить сообщение", "Delete message", NEED_MESSAGE, false, false },
	{ "warn", "Предупредить", "Warn", 0, false, false },
	{ "remove_avatar", "Сбросить аватар", "Reset avatar", 0, false, false },
	{ "mute_text", "Отключить чат", "Mute chat", 0, true, true },
	{ "mute_voice", "Отключить голос", "Mute voice", 0, true, true },
	{ "restrict_photo", "Запретить фото", "Restrict photo", 0, true, true },
	{ "close_lobby", "Закрыть лобби", "Close lobby", NEED_LOBBY, false, true },
	{ "dismiss", "Отклонить жалобу", "Dismiss report", NEED_REPORT, false, false },
	{ "ban", "Заблокировать", "Ban", 0, true, true },
};
#define MOD_ACTIONS (int)( sizeof( s_actions ) / sizeof( s_actions[0] ))

const struct { int minutes; const char *ru, *en; } s_durations[] =
{
	{ 60, "1 час", "1 hour" }, { 1440, "1 день", "1 day" }, { 10080, "7 дней", "7 days" },
	{ 43200, "30 дней", "30 days" }, { 0, "Навсегда", "Forever" },
};
#define MOD_DURATIONS 5

const struct { const char *ru, *en; } s_reasons[] =
{
	{ "Оскорбления", "Insults" }, { "Угрозы", "Threats" }, { "Спам и реклама", "Spam and ads" },
	{ "Сексуальный контент", "Sexual content" }, { "Нацистская пропаганда", "Nazi propaganda" },
	{ "Своя причина", "Other reason" },
};
#define MOD_REASONS 6
#define MOD_OWN_REASON ( MOD_REASONS - 1 )

struct ModPerson { int id; char nick[100], avatar[32]; };
struct ModRow
{
	int id, created, until, reportsWeek;
	bool forever;
	ModPerson target;
	char kind[24], text[600], context[200], moderator[100];
};

void ReadModPerson( ModPerson &p, const CzmJson &j, int node )
{
	p.id = j.Int( j.Get( node, "id" ));
	Q_strncpy( p.nick, j.String( j.Get( node, "nick" )), sizeof( p.nick ));
	Q_strncpy( p.avatar, j.String( j.Get( node, "avatar" )), sizeof( p.avatar ));
}

void Stamp( int stamp, char *out, size_t size )
{
	time_t t = stamp;
	struct tm date;
	localtime_r( &t, &date );
	strftime( out, size, "%d.%m %H:%M", &date );
}

// "до 01.11 12:00" or "навсегда"
void Term( int until, bool forever, char *out, size_t size )
{
	if( forever ) { Q_strncpy( out, T( "навсегда", "for good" ), size ); return; }
	char when[24];
	Stamp( until, when, sizeof( when ));
	snprintf( out, size, T( "до %s", "until %s" ), when );
}

const char *ReportKind( const char *kind )
{
	if( !strcmp( kind, "chat" )) return T( "Сообщение в чате", "Chat message" );
	if( !strcmp( kind, "private" )) return T( "Личное сообщение", "Private message" );
	if( !strcmp( kind, "lobby_message" )) return T( "Сообщение в лобби", "Lobby message" );
	if( !strcmp( kind, "lobby_member" )) return T( "Поведение в лобби", "Behaviour in a lobby" );
	if( !strcmp( kind, "lobby" )) return T( "Название лобби", "Lobby name" );
	return T( "Профиль", "Profile" );
}

bool MessageReport( const char *kind )
{
	return !strcmp( kind, "chat" ) || !strcmp( kind, "private" ) || !strcmp( kind, "lobby_message" );
}

const char *SanctionKind( const char *kind )
{
	if( !strcmp( kind, "text" )) return T( "Чат отключён", "Chat muted" );
	if( !strcmp( kind, "voice" )) return T( "Голос отключён", "Voice muted" );
	if( !strcmp( kind, "photo" )) return T( "Фото запрещено", "Photo restricted" );
	return T( "Блокировка", "Ban" );
}

const char *ActionName( const char *code )
{
	if( !strcmp( code, "lift" )) return T( "Снять ограничение", "Lift restriction" );
	for( int i = 0; i < MOD_ACTIONS; i++ )
		if( !strcmp( code, s_actions[i].code ))
			return CZM_IsRussian() ? s_actions[i].ru : s_actions[i].en;
	return code;
}

// what the toast says once the service did it
const char *ActionDone( const char *code )
{
	static const struct { const char *code, *ru, *en; } done[] =
	{
		{ "delete_message", "Сообщение удалено", "Message deleted" },
		{ "warn", "Предупреждение отправлено", "Warning sent" },
		{ "remove_avatar", "Аватар сброшен", "Avatar reset" },
		{ "mute_text", "Чат отключён", "Chat muted" },
		{ "mute_voice", "Голос отключён", "Voice muted" },
		{ "restrict_photo", "Фото запрещено", "Photo restricted" },
		{ "close_lobby", "Лобби закрыто", "Lobby closed" },
		{ "dismiss", "Жалоба отклонена", "Report dismissed" },
		{ "ban", "Игрок заблокирован", "Player banned" },
		{ "lift", "Ограничение снято", "Restriction lifted" },
	};
	for( unsigned i = 0; i < sizeof( done ) / sizeof( done[0] ); i++ )
		if( !strcmp( code, done[i].code ))
			return CZM_IsRussian() ? done[i].ru : done[i].en;
	return T( "Готово", "Done" );
}

const char *ErrorText( const char *code, int status )
{
	if( !strcmp( code, "forbidden" )) return T( "У аккаунта нет доступа к этому действию", "This account cannot perform this action" );
	if( !strcmp( code, "moderator_paused" )) return T( "Права приостановлены до проверки главным администратором", "The main administrator must review your suspended permissions" );
	if( !strcmp( code, "moderator_action" )) return T( "Это действие доступно только SUPPORT", "Only SUPPORT can perform this action" );
	if( !strcmp( code, "staff" )) return T( "Нельзя применить к сотруднику", "Staff cannot be moderated" );
	if( !strcmp( code, "self" )) return T( "Нельзя применить к себе", "Not on yourself" );
	if( !strcmp( code, "target" )) return T( "Жалоба или сообщение о другом игроке", "The report or message is about someone else" );
	if( !strcmp( code, "not_found" )) return T( "Не найдено. Обновите список", "Not found. Refresh the list" );
	if( !strcmp( code, "minutes" )) return T( "Выберите срок", "Choose a duration" );
	if( !strcmp( code, "reason" )) return T( "Укажите причину", "Give a reason" );
	if( !strcmp( code, "message" ) || !strcmp( code, "lobby" ) || !strcmp( code, "report" ))
		return T( "Это уже недоступно. Обновите", "No longer available. Refresh" );
	if( !strcmp( code, "nonce" )) return T( "Это действие уже выполнено", "Already done" );
	if( !strcmp( code, "slow" ) || status == 429 ) return T( "Слишком часто. Подождите", "Too fast. Wait a moment" );
	if( status == 401 || !strcmp( code, "account_required" ) || !strcmp( code, "session" )) return T( "Войдите в аккаунт", "Sign in first" );
	return T( "Нет связи. Повторите", "Connection failed. Try again" );
}

int Letters( const char *text ) { int n = 0; for( ; *text; text++ ) if(( *text & 0xc0 ) != 0x80 ) n++; return n; }
}

class CCzmModeration : public CMenuFramework
{
public:
	CCzmModeration();
	void OpenPanel();
	void OpenTarget( int player, const char *nick, int message, int lobbyMessage, const char *quote,
		int report = 0, const char *reportKind = "", const char *context = "", bool fromPanel = false );
	void Hide() override;
	void Draw() override;
	bool IsRoot() const override { return false; }
	bool KeyDown( int key ) override;
	bool KeyUp( int key ) override;
	bool MouseMove( int x, int y ) override;
	void Char( int key ) override;
	void Poll();
	bool m_open;

private:
	enum { BACK = 1, REFRESH, FIELD, NEXT, CONFIRM, CANCEL, BODY, TAB = 100, ROW = 200, LIFT = 1000, ACTION = 1800, DURATION = 1900, REASON = 2000 };
	enum { READ_SUMMARY = 1, READ_LIST, READ_PLAYER };
	enum { WRITE_ACT = 1, WRITE_LIFT };

	void Layout();
	int Hit();
	void Activate( int hit );
	bool Pressed( int hit ) { return m_pressed == hit && Hit() == hit; }
	void Go( int page );
	void Back();
	void LoadList( bool more );
	void LoadSummary();
	void LoadPlayer();
	void Act();
	void Lift( int row );
	void Toast( const char *text, bool error = false );
	void Abandon();
	void StartInput();
	void StopInput();
	void Visible();
	int RowHeight() const;
	int Rows() const { return m_rows.Count() + ( m_next >= 0 ? 1 : 0 ); }
	CzmRect RowRect( int i ) const;
	CzmRect LiftRect( const CzmRect &row ) const;
	bool NeedsReason() const;
	bool ForeverAllowed() const;
	const ModAction &Current() const { return s_actions[m_action]; }

	void DrawHeader( const char *title );
	void DrawPanelPage();
	void DrawTargetPage();
	void DrawChoicePage();
	void DrawConfirmPage();
	void DrawRow( int i, const CzmRect &r );

	int m_page, m_tab, m_counts[2];
	CUtlVector<ModRow> m_rows;
	int m_next, m_listTab;
	bool m_loaded;

	// the player the steps are about
	ModPerson m_target;
	int m_message, m_lobbyMessage, m_report, m_reportsWeek;
	bool m_fromPanel, m_targetLoaded, m_targetStaff, m_messageGone;
	char m_reportKind[24], m_quote[600], m_context[200], m_limits[220];

	int m_visible[MOD_ACTIONS], m_visibleCount;
	int m_action, m_minutes, m_reasonIndex;
	char m_reason[256], m_nonce[80];
	bool m_typing, m_armed;
	int m_liftArmed;

	int m_read, m_readKind, m_readView, m_write, m_writeKind, m_writeView, m_view, m_pending;
	int m_stale[4]; // reads of a page left behind: their answers are collected and dropped
	int m_pressed, m_scroll, m_maxScroll, m_downScroll, m_downY;
	bool m_drag, m_moved;
	char m_toast[240];
	bool m_toastError;
	double m_toastUntil;

	CzmRect m_panel, m_back, m_refresh, m_tabs[TAB_COUNT], m_clip, m_card, m_quoteRect;
	CzmRect m_actionRects[MOD_ACTIONS], m_choice[MOD_REASONS], m_field, m_nextRect, m_confirm, m_cancel;
	int W, H, pad, gap, bh;
};

static CCzmModeration *s_moderation;

CCzmModeration::CCzmModeration() : CMenuFramework( "CzmModeration" )
{
	s_moderation = this;
	m_open = false;
	m_page = PAGE_PANEL; m_tab = TAB_REPORTS; m_counts[0] = m_counts[1] = -1;
	m_next = -1; m_listTab = -1; m_loaded = false;
	memset( &m_target, 0, sizeof( m_target ));
	m_message = m_lobbyMessage = m_report = m_reportsWeek = 0;
	m_fromPanel = m_targetLoaded = m_targetStaff = m_messageGone = false;
	m_reportKind[0] = m_quote[0] = m_context[0] = m_limits[0] = 0;
	m_visibleCount = 0; m_action = 0; m_minutes = -1; m_reasonIndex = -1;
	m_reason[0] = m_nonce[0] = 0; m_typing = m_armed = false; m_liftArmed = 0;
	m_read = m_readKind = m_readView = m_write = m_writeKind = m_writeView = m_view = m_pending = 0;
	memset( m_stale, 0, sizeof( m_stale ));
	m_pressed = m_scroll = m_maxScroll = m_downScroll = m_downY = 0;
	m_drag = m_moved = false;
	m_toast[0] = 0; m_toastError = false; m_toastUntil = 0;
	W = H = pad = gap = bh = 0;
}

// a new page must not wait for the answer to the one before it
void CCzmModeration::Abandon()
{
	m_pending = 0;
	if( !m_read ) return;
	for( int i = 0; i < 4; i++ )
		if( !m_stale[i] ) { m_stale[i] = m_read; m_read = 0; return; }
}

void CCzmModeration::OpenPanel()
{
	StopInput();
	Abandon();
	m_page = PAGE_PANEL; m_scroll = 0; m_liftArmed = 0; m_pressed = 0;
	m_view++;
	if( !m_open || m_pStack->Current() != this ) CMenuFramework::Show();
	m_open = true;
	m_listTab = -1;
	LoadSummary();
}

void CCzmModeration::OpenTarget( int player, const char *nick, int message, int lobbyMessage, const char *quote,
	int report, const char *reportKind, const char *context, bool fromPanel )
{
	if( player <= 0 ) return;
	StopInput();
	Abandon();
	memset( &m_target, 0, sizeof( m_target ));
	m_target.id = player;
	Q_strncpy( m_target.nick, nick && nick[0] ? nick : "", sizeof( m_target.nick ));
	m_message = Q_max( 0, message ); m_lobbyMessage = Q_max( 0, lobbyMessage ); m_report = Q_max( 0, report );
	Q_strncpy( m_reportKind, reportKind ? reportKind : "", sizeof( m_reportKind ));
	Q_strncpy( m_quote, quote ? quote : "", sizeof( m_quote ));
	Q_strncpy( m_context, context ? context : "", sizeof( m_context ));
	m_fromPanel = fromPanel; m_targetLoaded = m_targetStaff = m_messageGone = false;
	m_reportsWeek = 0; m_limits[0] = 0;
	m_view++;
	if( !m_open || m_pStack->Current() != this ) CMenuFramework::Show();
	m_open = true;
	Go( PAGE_TARGET );
	LoadPlayer();
}

void CCzmModeration::Hide()
{
	StopInput();
	m_open = false; m_pressed = 0; m_drag = false; m_armed = false; m_liftArmed = 0;
	m_view++;
	CMenuFramework::Hide();
}

void CCzmModeration::Toast( const char *text, bool error )
{
	Q_strncpy( m_toast, text ? text : "", sizeof( m_toast ));
	m_toastError = error;
	m_toastUntil = EngFuncs::DoubleTime() + ( error ? 5 : 3 );
}

void CCzmModeration::StartInput()
{
	m_typing = true;
	EngFuncs::SetTextInputRect( m_field.x, m_field.y, m_field.w, m_field.h );
	UI_EnableTextInput( true );
}

void CCzmModeration::StopInput()
{
	if( m_typing ) UI_EnableTextInput( false );
	m_typing = false;
}

void CCzmModeration::Go( int page )
{
	StopInput();
	m_page = page; m_pressed = 0; m_armed = false; m_scroll = 0;
	if( page == PAGE_TARGET ) { m_action = 0; m_minutes = -1; m_reasonIndex = -1; m_reason[0] = 0; }
	if( page == PAGE_CONFIRM ) CZM_NetNewKey( m_nonce, sizeof( m_nonce ));
}

void CCzmModeration::Back()
{
	if( m_write ) return; // the answer decides where we go
	switch( m_page )
	{
	case PAGE_CONFIRM:
		if( !strcmp( Current().code, "dismiss" )) Go( PAGE_TARGET );
		else Go( PAGE_REASON );
		break;
	case PAGE_REASON:
		if( Current().sanction ) Go( PAGE_DURATION );
		else Go( PAGE_TARGET );
		break;
	case PAGE_DURATION: Go( PAGE_TARGET ); break;
	case PAGE_TARGET:
		if( m_fromPanel ) { Go( PAGE_PANEL ); m_listTab = -1; LoadSummary(); }
		else Hide();
		break;
	default: Hide(); break;
	}
}

bool CCzmModeration::NeedsReason() const
{
	return Current().sanction || !strcmp( Current().code, "warn" ) || !strcmp( CZM_OnlineRole(), "moderator" );
}

bool CCzmModeration::ForeverAllowed() const
{
	return !strcmp( Current().code, "ban" ) || !strcmp( Current().code, "restrict_photo" );
}

// the actions that make sense for what we have: a message, a report, a room
void CCzmModeration::Visible()
{
	const bool message = !m_messageGone && ( m_message || m_lobbyMessage || ( m_report && MessageReport( m_reportKind )));
	m_visibleCount = 0;
	if( m_targetStaff ) return;
	for( int i = 0; i < MOD_ACTIONS; i++ )
	{
		if( !strcmp( CZM_OnlineRole(), "moderator" ) && ( !strcmp( s_actions[i].code, "remove_avatar" ) || !strcmp( s_actions[i].code, "restrict_photo" ) || !strcmp( s_actions[i].code, "close_lobby" ))) continue;
		const int need = s_actions[i].need;
		if(( need & NEED_MESSAGE ) && !message ) continue;
		if(( need & NEED_REPORT ) && !m_report ) continue;
		if(( need & NEED_LOBBY ) && !( m_report && !strcmp( m_reportKind, "lobby" ))) continue;
		m_visible[m_visibleCount++] = i;
	}
}

/*
 * requests
 */
void CCzmModeration::LoadSummary()
{
	if( m_read ) { m_pending |= 1; return; }
	m_readKind = READ_SUMMARY; m_readView = m_view;
	m_read = CZM_NetRequest( "GET", CZM_OnlineUrl( "/api/v1/moderation/summary" ), CZM_OnlineKey(), "" );
}

void CCzmModeration::LoadList( bool more )
{
	if( m_read ) return; // Poll starts it once the current read is answered
	char path[96];
	const int offset = more ? Q_max( 0, m_next ) : 0;
	if( !more ) { m_rows.RemoveAll(); m_next = -1; m_loaded = false; m_scroll = 0; m_liftArmed = 0; }
	m_listTab = m_tab;
	if( m_tab == TAB_REPORTS ) snprintf( path, sizeof( path ), "/api/v1/moderation/reports?offset=%d", offset );
	else if( m_tab == TAB_SANCTIONS ) Q_strncpy( path, "/api/v1/moderation/sanctions", sizeof( path ));
	else snprintf( path, sizeof( path ), "/api/v1/moderation/history?offset=%d", offset );
	m_readKind = READ_LIST; m_readView = m_view;
	m_read = CZM_NetRequest( "GET", CZM_OnlineUrl( path ), CZM_OnlineKey(), "" );
	if( !m_read ) { m_loaded = true; Toast( ErrorText( "", 0 ), true ); }
}

void CCzmModeration::LoadPlayer()
{
	if( m_read ) { m_pending |= 4; return; }
	char path[128];
	snprintf( path, sizeof( path ), "/api/v1/moderation/player/%d?message=%d&lobby_message=%d", m_target.id,
		m_messageGone ? 0 : m_message, m_messageGone ? 0 : m_lobbyMessage );
	m_readKind = READ_PLAYER; m_readView = m_view;
	m_read = CZM_NetRequest( "GET", CZM_OnlineUrl( path ), CZM_OnlineKey(), "" );
	if( !m_read ) Toast( ErrorText( "", 0 ), true );
}

void CCzmModeration::Act()
{
	if( m_write ) return;
	const ModAction &a = Current();
	CUtlString body;
	char number[96];
	snprintf( number, sizeof( number ), "{\"target\":%d,\"action\":", m_target.id );
	body.Append( number );
	CZM_JsonQuote( body, a.code );
	if( a.sanction ) { snprintf( number, sizeof( number ), ",\"minutes\":%d", Q_max( 0, m_minutes )); body.Append( number ); }
	body.Append( ",\"reason\":" );
	CZM_JsonQuote( body, m_reason );
	if( m_report ) { snprintf( number, sizeof( number ), ",\"report\":%d", m_report ); body.Append( number ); }
	else if( !m_messageGone && m_message ) { snprintf( number, sizeof( number ), ",\"message\":%d", m_message ); body.Append( number ); }
	else if( !m_messageGone && m_lobbyMessage ) { snprintf( number, sizeof( number ), ",\"lobby_message\":%d", m_lobbyMessage ); body.Append( number ); }
	body.Append( ",\"nonce\":" );
	CZM_JsonQuote( body, m_nonce );
	body.Append( "}" );
	m_writeKind = WRITE_ACT; m_writeView = m_view;
	m_write = CZM_NetRequest( "POST", CZM_OnlineUrl( "/api/v1/moderation/act" ), CZM_OnlineKey(), body.Get() );
	if( !m_write ) Toast( ErrorText( "", 0 ), true );
}

void CCzmModeration::Lift( int row )
{
	if( m_write || row < 0 || row >= m_rows.Count() ) return;
	char path[96], body[120];
	snprintf( path, sizeof( path ), "/api/v1/moderation/sanctions/%d/lift", m_rows[row].id );
	CZM_NetNewKey( m_nonce, sizeof( m_nonce ));
	snprintf( body, sizeof( body ), "{\"nonce\":\"%s\"}", m_nonce );
	m_writeKind = WRITE_LIFT; m_writeView = m_view;
	m_write = CZM_NetRequest( "POST", CZM_OnlineUrl( path ), CZM_OnlineKey(), body );
	if( !m_write ) Toast( ErrorText( "", 0 ), true );
}

void CCzmModeration::Poll()
{
	int status = 0;
	CUtlString body;
	for( int i = 0; i < 4; i++ )
		if( m_stale[i] && CZM_NetPoll( m_stale[i], &status, body )) m_stale[i] = 0;
	if( m_read && CZM_NetPoll( m_read, &status, body ))
	{
		const int kind = m_readKind;
		const bool current = m_open && m_readView == m_view;
		CzmJson j;
		const bool parsed = j.Parse( body.Get() );
		m_read = 0;
		if( current && ( status != 200 || !parsed ))
		{
			Toast( ErrorText( parsed ? j.String( j.Get( 0, "error" )) : "", status ), true );
			if( kind == READ_LIST ) m_loaded = true;
		}
		else if( current && kind == READ_SUMMARY )
		{
			m_counts[0] = j.Int( j.Get( 0, "reports_open" ), -1 );
			m_counts[1] = j.Int( j.Get( 0, "sanctions_active" ), -1 );
		}
		else if( current && kind == READ_LIST && m_listTab == m_tab )
		{
			const char *names[TAB_COUNT] = { "reports", "sanctions", "history" };
			const int list = j.Get( 0, names[m_tab] );
			for( int i = 0; i < j.Count( list ) && m_rows.Count() < 600; i++ )
			{
				const int item = j.At( list, i );
				ModRow r;
				memset( &r, 0, sizeof( r ));
				r.id = j.Int( j.Get( item, "id" ));
				r.created = j.Int( j.Get( item, "created" ));
				r.until = j.Int( j.Get( item, "until" ));
				r.forever = j.Bool( j.Get( item, "forever" ));
				r.reportsWeek = j.Int( j.Get( item, "reports_week" ));
				ReadModPerson( r.target, j, j.Get( item, "target" ));
				Q_strncpy( r.kind, j.String( j.Get( item, m_tab == TAB_HISTORY ? "action" : "kind" )), sizeof( r.kind ));
				Q_strncpy( r.text, j.String( j.Get( item, m_tab == TAB_REPORTS ? "evidence" : "reason" )), sizeof( r.text ));
				Q_strncpy( r.context, j.String( j.Get( item, "context" )), sizeof( r.context ));
				if( m_tab == TAB_HISTORY )
				{
					Q_strncpy( r.moderator, j.String( j.Get( j.Get( item, "moderator" ), "nick" )), sizeof( r.moderator ));
					if( !strcmp( r.kind, "lift" )) Q_strncpy( r.text, SanctionKind( j.String( j.Get( item, "reason" ))), sizeof( r.text ));
				}
				m_rows.AddToTail( r );
			}
			m_next = m_tab == TAB_SANCTIONS ? -1 : j.Int( j.Get( 0, "next" ), -1 );
			m_loaded = true;
		}
		else if( current && kind == READ_PLAYER )
		{
			ModPerson p;
			ReadModPerson( p, j, j.Get( 0, "target" ));
			if( p.id == m_target.id ) m_target = p;
			m_targetStaff = j.Get( 0, "protected" ) >= 0 ? j.Bool( j.Get( 0, "protected" )) : j.String( j.Get( 0, "role" ))[0] != 0;
			m_reportsWeek = j.Int( j.Get( 0, "reports_week" ));
			const int quote = j.Get( 0, "quote" );
			if( j.Type( quote ) == CzmJson::T_OBJECT )
			{
				Q_strncpy( m_quote, j.String( j.Get( quote, "text" )), sizeof( m_quote ));
				Q_strncpy( m_context, j.String( j.Get( quote, "context" )), sizeof( m_context ));
			}
			else if(( m_message || m_lobbyMessage ) && !m_report ) m_messageGone = true; // deleted meanwhile
			// what he is under now, in one line
			m_limits[0] = 0;
			const int moderation = j.Get( 0, "moderation" );
			const char *kinds[] = { "text", "voice", "photo" };
			for( int k = 0; k < 4; k++ )
			{
				const int node = k < 3 ? j.Get( moderation, kinds[k] ) : j.Get( 0, "ban" );
				if( j.Type( node ) != CzmJson::T_OBJECT ) continue;
				char term[48], part[96];
				Term( j.Int( j.Get( node, "until" )), j.Bool( j.Get( node, "forever" )), term, sizeof( term ));
				snprintf( part, sizeof( part ), "%s%s %s", m_limits[0] ? "  ·  " : "", SanctionKind( k < 3 ? kinds[k] : "ban" ), term );
				const size_t used = strlen( m_limits );
				Q_strncpy( m_limits + used, part, sizeof( m_limits ) - used );
			}
			m_targetLoaded = true;
		}
	}

	if( m_write && CZM_NetPoll( m_write, &status, body ))
	{
		const int kind = m_writeKind;
		const bool current = m_open && m_writeView == m_view;
		CzmJson j;
		const bool parsed = j.Parse( body.Get() );
		m_write = 0;
		if( !current ) { /* closed meanwhile: the journal keeps it */ }
		else if( status != 200 || !parsed )
		{
			Toast( ErrorText( parsed ? j.String( j.Get( 0, "error" )) : "", status ), true );
			m_armed = false; m_liftArmed = 0;
		}
		else if( kind == WRITE_LIFT )
		{
			Toast( ActionDone( "lift" ));
			m_liftArmed = 0; m_listTab = -1;
			LoadSummary();
		}
		else
		{
			Toast( ActionDone( Current().code ));
			if( !strcmp( Current().code, "delete_message" )) { m_messageGone = true; m_quote[0] = 0; }
			if( m_report && m_fromPanel )
			{
				// the report is resolved by any action: back to the list without it
				Go( PAGE_PANEL ); m_report = 0; m_listTab = -1;
				LoadSummary();
			}
			else
			{
				m_report = 0; // resolved
				Go( PAGE_TARGET );
				LoadPlayer();
			}
		}
	}

	if( !m_open ) { m_pending = 0; return; }
	// one read at a time: the card first, then the counters, then the list
	if( !m_read && ( m_pending & 4 )) { m_pending &= ~4; LoadPlayer(); }
	if( !m_read && ( m_pending & 1 )) { m_pending &= ~1; LoadSummary(); }
	if( !m_read && m_page == PAGE_PANEL && m_listTab != m_tab ) LoadList( false );
}

/*
 * layout
 */
int CCzmModeration::RowHeight() const
{
	return m_tab == TAB_REPORTS ? Q_max( 64, (int)( H * .165f )) : Q_max( 52, (int)( H * .125f ));
}

CzmRect CCzmModeration::RowRect( int i ) const
{
	const int rh = RowHeight();
	return CZM_Rect( m_clip.x, m_clip.y + i * rh - m_scroll, m_clip.w, rh - gap / 2 );
}

CzmRect CCzmModeration::LiftRect( const CzmRect &row ) const
{
	const int w = Q_max( 80, (int)( H * .2f )), h = Q_min( bh, row.h - gap );
	return CZM_Rect( row.x + row.w - gap - w, row.y + ( row.h - h ) / 2, w, h );
}

void CCzmModeration::Layout()
{
	W = ScreenWidth; H = ScreenHeight;
	pad = Q_max( 10, (int)( H * .03f )); gap = Q_max( 6, (int)( H * .016f )); bh = Q_max( 32, (int)( H * .07f ));
	const int pw = Q_min( W - pad * 2, (int)( H * 1.62f )), ph = Q_min( H - gap * 2, (int)( H * .92f ));
	m_panel = CZM_Rect(( W - pw ) / 2, ( H - ph ) / 2, pw, ph );
	const int left = m_panel.x + pad, inner = pw - pad * 2, header = bh;
	int y = m_panel.y + pad;
	m_back = CZM_Rect( left, y, header, header );
	m_refresh = m_page == PAGE_PANEL || m_page == PAGE_TARGET ? CZM_Rect( left + inner - header, y, header, header ) : CZM_Rect( 0, 0, 0, 0 );
	y += header + gap;
	const int bottom = m_panel.y + ph - pad;
	for( int i = 0; i < TAB_COUNT; i++ ) m_tabs[i] = CZM_Rect( 0, 0, 0, 0 );
	for( int i = 0; i < MOD_ACTIONS; i++ ) m_actionRects[i] = CZM_Rect( 0, 0, 0, 0 );
	for( int i = 0; i < MOD_REASONS; i++ ) m_choice[i] = CZM_Rect( 0, 0, 0, 0 );
	m_card = m_quoteRect = m_field = m_nextRect = m_confirm = m_cancel = CZM_Rect( 0, 0, 0, 0 );
	m_clip = CZM_Rect( left, y, inner, bottom - y );

	if( m_page == PAGE_PANEL )
	{
		const int tw = ( inner - gap * ( TAB_COUNT - 1 )) / TAB_COUNT;
		for( int i = 0; i < TAB_COUNT; i++ ) m_tabs[i] = CZM_Rect( left + i * ( tw + gap ), y, tw, bh );
		y += bh + gap;
		m_clip = CZM_Rect( left, y, inner, bottom - y );
		m_maxScroll = Q_max( 0, Rows() * RowHeight() - m_clip.h );
		m_scroll = bound( 0, m_scroll, m_maxScroll );
		return;
	}
	if( m_page == PAGE_TARGET )
	{
		const int avatar = Q_max( 44, (int)( H * .13f ));
		m_card = CZM_Rect( left, y, inner, avatar + gap * 2 );
		y += m_card.h + gap;
		if( m_quote[0] || m_messageGone )
		{
			const int lineH = CZM_FontHeight( CZM_Font( CZMF_PANEL_TEXT ));
			int starts[4];
			const int lines = m_quote[0] ? CZM_WrapText( CZM_Font( CZMF_PANEL_TEXT ), m_quote, inner - gap * 2, starts, 3 ) : 1;
			m_quoteRect = CZM_Rect( left, y, inner, gap + CZM_FontHeight( CZM_Font( CZMF_UI_META )) + gap / 2 + Q_max( 1, lines ) * lineH + gap );
			y += m_quoteRect.h + gap;
		}
		const int columns = 3, rows = ( m_visibleCount + columns - 1 ) / columns;
		const int cw = ( inner - gap * ( columns - 1 )) / columns;
		const int ah = rows ? Q_min( bh, ( bottom - y - gap * ( rows - 1 )) / rows ) : bh;
		for( int i = 0; i < m_visibleCount; i++ )
			m_actionRects[i] = CZM_Rect( left + ( i % columns ) * ( cw + gap ), y + ( i / columns ) * ( ah + gap ), cw, ah );
		return;
	}
	// the steps: a heading line, then the choices or the summary
	y += CZM_FontHeight( CZM_Font( CZMF_PANEL_TEXT )) + gap;
	if( m_page == PAGE_DURATION )
	{
		const int count = ForeverAllowed() ? MOD_DURATIONS : MOD_DURATIONS - 1;
		const int cw = ( inner - gap * ( count - 1 )) / count;
		for( int i = 0; i < count; i++ ) m_choice[i] = CZM_Rect( left + i * ( cw + gap ), y, cw, bh );
	}
	else if( m_page == PAGE_REASON )
	{
		const int columns = 3, cw = ( inner - gap * ( columns - 1 )) / columns;
		for( int i = 0; i < MOD_REASONS; i++ )
			m_choice[i] = CZM_Rect( left + ( i % columns ) * ( cw + gap ), y + ( i / columns ) * ( bh + gap ), cw, bh );
		y += 2 * ( bh + gap );
		if( m_reasonIndex == MOD_OWN_REASON )
		{
			const int next = Q_max( 90, (int)( H * .22f ));
			m_field = CZM_Rect( left, y, inner - next - gap, bh );
			m_nextRect = CZM_Rect( left + inner - next, y, next, bh );
		}
	}
	else if( m_page == PAGE_CONFIRM )
	{
		const int w = Q_min(( inner - gap ) / 2, (int)( H * .42f ));
		m_confirm = CZM_Rect( left + inner - w, bottom - bh, w, bh );
		m_cancel = CZM_Rect( m_confirm.x - gap - w, m_confirm.y, w, bh );
	}
	if( m_typing ) EngFuncs::SetTextInputRect( m_field.x, m_field.y, m_field.w, m_field.h );
}

int CCzmModeration::Hit()
{
	if( !m_panel.HasCursor() ) return 0;
	if( m_back.HasCursor() ) return BACK;
	if( m_refresh.w && m_refresh.HasCursor() ) return REFRESH;
	if( m_page == PAGE_PANEL )
	{
		for( int i = 0; i < TAB_COUNT; i++ ) if( m_tabs[i].HasCursor() ) return TAB + i;
		if( !m_clip.HasCursor() ) return 0;
		const int i = ( uiStatic.cursorY - m_clip.y + m_scroll ) / Q_max( 1, RowHeight() );
		if( i < 0 || i >= Rows() || i >= 600 ) return BODY;
		if( m_tab == TAB_SANCTIONS && i < m_rows.Count() && LiftRect( RowRect( i )).HasCursor() ) return LIFT + i;
		return ROW + i;
	}
	if( m_page == PAGE_TARGET )
	{
		for( int i = 0; i < m_visibleCount; i++ ) if( m_actionRects[i].HasCursor() ) return ACTION + i;
		return 0;
	}
	if( m_page == PAGE_DURATION || m_page == PAGE_REASON )
	{
		for( int i = 0; i < MOD_REASONS; i++ ) if( m_choice[i].w && m_choice[i].HasCursor() ) return ( m_page == PAGE_DURATION ? DURATION : REASON ) + i;
		if( m_field.w && m_field.HasCursor() ) return FIELD;
		if( m_nextRect.w && m_nextRect.HasCursor() ) return NEXT;
		return 0;
	}
	if( m_confirm.HasCursor() ) return CONFIRM;
	if( m_cancel.HasCursor() ) return CANCEL;
	return 0;
}

void CCzmModeration::Activate( int hit )
{
	if( !hit || hit == BODY ) return;
	CZM_PlayClick();
	if( hit == BACK || hit == CANCEL ) { Back(); return; }
	if( hit == REFRESH )
	{
		if( m_page == PAGE_PANEL ) { LoadSummary(); m_listTab = -1; }
		else LoadPlayer();
		return;
	}
	if( hit >= TAB && hit < TAB + TAB_COUNT )
	{
		if( m_tab != hit - TAB ) { m_tab = hit - TAB; m_rows.RemoveAll(); m_loaded = false; m_listTab = -1; m_scroll = 0; }
		return;
	}
	if( hit >= LIFT && hit < LIFT + 600 )
	{
		const int i = hit - LIFT;
		if( m_write || i >= m_rows.Count() ) return;
		if( m_liftArmed != m_rows[i].id ) { m_liftArmed = m_rows[i].id; return; } // the second tap lifts it
		Lift( i );
		return;
	}
	if( hit >= ROW && hit < ROW + 600 )
	{
		const int i = hit - ROW;
		m_liftArmed = 0;
		if( i >= m_rows.Count() ) { if( m_next >= 0 && !m_read ) LoadList( true ); return; }
		const ModRow &r = m_rows[i];
		if( m_tab == TAB_REPORTS )
		{
			char context[220];
			snprintf( context, sizeof( context ), "%s%s%s", ReportKind( r.kind ), r.context[0] ? "  ·  " : "", r.context );
			OpenTarget( r.target.id, r.target.nick, 0, 0, r.text, r.id, r.kind, context, true );
		}
		else OpenTarget( r.target.id, r.target.nick, 0, 0, "", 0, "", "", true );
		return;
	}
	if( hit >= ACTION && hit < ACTION + m_visibleCount )
	{
		if( !m_targetLoaded ) return;
		m_action = m_visible[hit - ACTION];
		m_minutes = -1; m_reasonIndex = -1; m_reason[0] = 0;
		if( Current().sanction ) Go( PAGE_DURATION );
		else if( !strcmp( Current().code, "dismiss" ) && !NeedsReason() ) Go( PAGE_CONFIRM );
		else Go( PAGE_REASON );
		return;
	}
	if( hit >= DURATION && hit < DURATION + MOD_DURATIONS )
	{
		m_minutes = s_durations[hit - DURATION].minutes;
		Go( PAGE_REASON );
		return;
	}
	if( hit >= REASON && hit < REASON + MOD_REASONS )
	{
		m_reasonIndex = hit - REASON;
		if( m_reasonIndex == MOD_OWN_REASON ) { m_reason[0] = 0; Layout(); StartInput(); return; }
		Q_strncpy( m_reason, CZM_IsRussian() ? s_reasons[m_reasonIndex].ru : s_reasons[m_reasonIndex].en, sizeof( m_reason ));
		Go( PAGE_CONFIRM );
		return;
	}
	if( hit == FIELD ) { StartInput(); return; }
	if( hit == NEXT )
	{
		if( NeedsReason() && Letters( m_reason ) < 3 ) { Toast( T( "Опишите причину, хотя бы 3 буквы", "Describe the reason, 3 letters at least" ), true ); return; }
		Go( PAGE_CONFIRM );
		return;
	}
	if( hit == CONFIRM )
	{
		if( m_write ) return;
		const bool forever = Current().sanction && m_minutes == 0;
		if(( forever || !strcmp( Current().code, "ban" )) && !m_armed ) { m_armed = true; return; } // asked twice
		Act();
	}
}

/*
 * input
 */
bool CCzmModeration::KeyDown( int key )
{
	Layout();
	if( m_typing && UI::Key::IsBackspace( key ))
	{
		size_t n = strlen( m_reason );
		if( n ) { n--; while( n && ((unsigned char)m_reason[n] & 0xc0 ) == 0x80 ) n--; m_reason[n] = 0; }
		return true;
	}
	if( m_typing && UI::Key::IsEnter( key )) { Activate( NEXT ); return true; }
	if( UI::Key::IsEscape( key )) { if( m_typing ) StopInput(); else Back(); return true; }
	if( key == K_MWHEELUP || key == K_MWHEELDOWN )
	{
		m_scroll = bound( 0, m_scroll + ( key == K_MWHEELUP ? -1 : 1 ) * H / 10, m_maxScroll );
		return true;
	}
	if( UI::Key::IsLeftMouse( key ))
	{
		m_pressed = Hit();
		m_drag = m_page == PAGE_PANEL && m_clip.HasCursor();
		m_moved = false; m_downY = uiStatic.cursorY; m_downScroll = m_scroll;
		if( m_typing && m_pressed != FIELD && m_pressed != NEXT ) StopInput();
		return true;
	}
	return CMenuFramework::KeyDown( key );
}

bool CCzmModeration::KeyUp( int key )
{
	if( UI::Key::IsLeftMouse( key ))
	{
		Layout();
		const int hit = Hit();
		if( !m_moved && hit && hit == m_pressed ) Activate( hit );
		m_pressed = 0; m_drag = false;
		return true;
	}
	return CMenuFramework::KeyUp( key );
}

bool CCzmModeration::MouseMove( int x, int y )
{
	CMenuFramework::MouseMove( x, y );
	if( m_drag )
	{
		const int dy = uiStatic.cursorY - m_downY;
		if( abs( dy ) > H * .02f ) m_moved = true;
		if( m_moved ) m_scroll = bound( 0, m_downScroll - dy, m_maxScroll );
	}
	return true;
}

void CCzmModeration::Char( int key )
{
	if( !m_typing || key < 32 || key == 127 ) return;
	const size_t n = strlen( m_reason );
	if( n + 4 >= sizeof( m_reason ) || (( key & 0xc0 ) != 0x80 && Letters( m_reason ) >= 120 )) return;
	m_reason[n] = (char)key; m_reason[n + 1] = 0;
}

/*
 * drawing
 */
void CCzmModeration::DrawHeader( const char *title )
{
	using namespace CzmStyle;
	const bool backDown = m_pressed == BACK && m_back.HasCursor();
	CZM_DrawImage( UI_DIR "chip_round.png", m_back.x, m_back.y, m_back.w, m_back.h, backDown ? PackRGBA( 200, 200, 200, 255 ) : 0xFFFFFFFF );
	const int icon = m_back.h / 2;
	CZM_DrawImage( m_page == PAGE_PANEL || ( m_page == PAGE_TARGET && !m_fromPanel ) ? UI_DIR "icon_close.png" : UI_DIR "icon_back.png",
		m_back.x + icon / 2, m_back.y + icon / 2, icon, icon );
	if( m_refresh.w )
	{
		const bool down = m_pressed == REFRESH && m_refresh.HasCursor();
		CZM_DrawImage( UI_DIR "chip_round.png", m_refresh.x, m_refresh.y, m_refresh.w, m_refresh.h, down ? PackRGBA( 200, 200, 200, 255 ) : 0xFFFFFFFF );
		CZM_DrawImage( UI_DIR "icon_refresh.png", m_refresh.x + icon / 2, m_refresh.y + icon / 2, icon, icon, m_read ? Muted() : Ink() );
	}
	const HFont f = CZM_Font( CZMF_UI_TITLE );
	const int tx = m_back.x + m_back.w + gap, right = m_refresh.w ? m_refresh.x - gap : m_panel.x + m_panel.w - pad;
	const int tagH = Q_max( 14, CZM_FontHeight( f ) * 80 / 100 ), tagW = CZM_SupportTagWidth( tagH );
	const int tw = Q_min( CZM_TextWidth( f, title ) + 2, right - tx - tagW - gap );
	CZM_DrawText( f, tx, m_back.y + ( m_back.h - CZM_FontHeight( f )) / 2, tw, title, Ink() );
	CZM_DrawSupportTag( tx + tw + gap, m_back.y + ( m_back.h - tagH ) / 2, tagH );
}

void CCzmModeration::DrawRow( int i, const CzmRect &r )
{
	using namespace CzmStyle;
	const bool down = m_pressed == ROW + i && Hit() == ROW + i;
	if( i >= m_rows.Count() )
	{
		Surface( r, down ? PackRGBA( 33, 44, 60, 255 ) : PackRGBA( 22, 30, 42, 255 ));
		Text( r, m_read ? T( "Загружаем…", "Loading…" ) : T( "Показать ещё", "Show more" ), CZMF_UI_LABEL, AccentBlue(), QM_CENTER );
		return;
	}
	const ModRow &row = m_rows[i];
	Surface( r, down ? PackRGBA( 33, 44, 60, 255 ) : PackRGBA( 22, 30, 42, 255 ));
	const int inset = Q_max( 5, gap * 3 / 4 ), av = Q_min( r.h - inset * 2, (int)( H * .1f ));
	CZM_DrawImage( CZM_AvatarFor( row.target.avatar, row.target.id ), r.x + inset, r.y + inset, av, av );
	const int tx = r.x + inset * 2 + av;
	int tw = r.x + r.w - inset - tx;
	const HFont label = CZM_Font( CZMF_UI_LABEL ), meta = CZM_Font( CZMF_UI_META ), body = CZM_Font( CZMF_PANEL_TEXT );
	const int lh = CZM_FontHeight( label ), mh = CZM_FontHeight( meta );
	char line[720], when[24];
	Stamp( row.created, when, sizeof( when ));

	if( m_tab == TAB_SANCTIONS )
	{
		const CzmRect lift = LiftRect( r );
		tw = lift.x - gap - tx;
		snprintf( line, sizeof( line ), "%s  ·  ID %d", row.target.nick[0] ? row.target.nick : T( "Игрок", "Player" ), row.target.id );
		CZM_DrawText( label, tx, r.y + inset, tw, line, Ink() );
		char term[48];
		Term( row.until, row.forever, term, sizeof( term ));
		snprintf( line, sizeof( line ), "%s %s", SanctionKind( row.kind ), term );
		CZM_DrawText( meta, tx, r.y + inset + lh + 2, tw, line, !strcmp( row.kind, "ban" ) ? AccentRed() : AccentGold() );
		CZM_DrawText( meta, tx, r.y + inset + lh + mh + 4, tw, row.text, Muted() );
		const bool armed = m_liftArmed == row.id, liftDown = m_pressed == LIFT + i && Hit() == LIFT + i;
		Button( lift, armed ? T( "Точно снять?", "Lift it?" ) : T( "Снять", "Lift" ), !m_write, armed, liftDown, armed ? 0 : Success() );
		return;
	}
	if( m_tab == TAB_HISTORY )
	{
		snprintf( line, sizeof( line ), "%s  ·  %s", ActionName( row.kind ), row.target.nick[0] ? row.target.nick : T( "Игрок", "Player" ));
		CZM_DrawText( label, tx, r.y + inset, tw - CZM_TextWidth( meta, when ) - gap, line, Ink() );
		CZM_DrawText( meta, tx, r.y + inset + ( lh - mh ) / 2, tw, when, Muted(), QM_RIGHT );
		snprintf( line, sizeof( line ), "%s%s%s", row.moderator, row.text[0] ? "  ·  " : "", row.text );
		CZM_DrawText( meta, tx, r.y + inset + lh + 4, tw, line, Muted() );
		return;
	}
	// a report: who, what kind and where, the reported words
	snprintf( line, sizeof( line ), "%s  ·  ID %d", row.target.nick[0] ? row.target.nick : T( "Игрок", "Player" ), row.target.id );
	CZM_DrawText( label, tx, r.y + inset, tw - CZM_TextWidth( meta, when ) - gap, line, Ink() );
	CZM_DrawText( meta, tx, r.y + inset + ( lh - mh ) / 2, tw, when, Muted(), QM_RIGHT );
	snprintf( line, sizeof( line ), "%s%s%s", ReportKind( row.kind ), row.context[0] ? "  ·  " : "", row.context );
	int y = r.y + inset + lh + 2;
	if( row.reportsWeek > 1 )
	{
		char count[48];
		snprintf( count, sizeof( count ), T( "жалоб за неделю: %d", "%d reports this week" ), row.reportsWeek );
		const int cw = CZM_TextWidth( meta, count );
		CZM_DrawText( meta, tx + tw - cw, y, cw, count, AccentRed() );
		CZM_DrawText( meta, tx, y, tw - cw - gap, line, AccentBlue() );
	}
	else CZM_DrawText( meta, tx, y, tw, line, AccentBlue() );
	y += mh + 3;
	if( row.text[0] )
	{
		int starts[3];
		const int lines = CZM_WrapText( body, row.text, tw, starts, Q_max( 1, ( r.y + r.h - inset - y ) / Q_max( 1, CZM_FontHeight( body ))));
		for( int l = 0; l < lines; l++ )
		{
			char text[620];
			CZM_WrapLine( row.text, starts, l, text, sizeof( text ));
			CZM_DrawText( body, tx, y + l * CZM_FontHeight( body ), tw, text, Ink() );
		}
	}
}

void CCzmModeration::DrawPanelPage()
{
	using namespace CzmStyle;
	DrawHeader( T( "Модерация", "Moderation" ));
	const char *names[TAB_COUNT] = { T( "Жалобы", "Reports" ), T( "Наказания", "Restrictions" ), T( "История", "History" ) };
	for( int i = 0; i < TAB_COUNT; i++ )
	{
		const CzmRect &r = m_tabs[i];
		const bool on = m_tab == i;
		Surface( r, on ? PackRGBA( 44, 33, 22, 255 ) : Pressed( TAB + i ) ? PackRGBA( 33, 44, 60, 255 ) : PackRGBA( 22, 30, 42, 255 ),
			on ? AccentGold() : Border());
		const int count = i < 2 ? m_counts[i] : -1, bhh = Q_max( 14, r.h * 52 / 100 ), bw = count > 0 ? CZM_CountBadgeWidth( count, bhh ) : 0;
		const HFont f = CZM_Font( CZMF_UI_LABEL );
		const int textW = CZM_TextWidth( f, names[i] ), total = textW + ( bw ? bw + gap / 2 : 0 );
		const int x = r.x + ( r.w - total ) / 2;
		CZM_DrawText( f, x, r.y + ( r.h - CZM_FontHeight( f )) / 2, textW + 2, names[i], on ? AccentGold() : Ink() );
		if( bw ) CZM_DrawCountBadge( CZM_Rect( x + textW + gap / 2, r.y + ( r.h - bhh ) / 2, bw, bhh ), count );
	}
	UI::Scissor::PushScissor( m_clip.x, m_clip.y, m_clip.w, m_clip.h );
	for( int i = 0; i < Rows(); i++ )
	{
		const CzmRect r = RowRect( i );
		if( r.y + r.h < m_clip.y || r.y > m_clip.y + m_clip.h ) continue;
		DrawRow( i, r );
	}
	UI::Scissor::PopScissor();
	if( !m_rows.Count() )
	{
		const char *empty = !m_loaded ? T( "Загружаем…", "Loading…" )
			: m_tab == TAB_REPORTS ? T( "Открытых жалоб нет", "No open reports" )
			: m_tab == TAB_SANCTIONS ? T( "Активных ограничений нет", "No active restrictions" )
			: T( "Журнал пуст", "The journal is empty" );
		Text( m_clip, empty, CZMF_PANEL_TEXT, Muted(), QM_CENTER );
	}
	if( m_maxScroll )
	{
		const int thumb = Q_max( 12, m_clip.h * m_clip.h / ( m_clip.h + m_maxScroll ));
		UI_FillRect( m_panel.x + m_panel.w - pad / 2, m_clip.y + ( m_clip.h - thumb ) * m_scroll / m_maxScroll, 3, thumb, CZM_White( 140 ));
	}
}

void CCzmModeration::DrawTargetPage()
{
	using namespace CzmStyle;
	DrawHeader( T( "Модерация", "Moderation" ));
	// the card: avatar, nick, ID, reports, current restrictions
	Surface( m_card, PackRGBA( 22, 30, 42, 255 ));
	const int av = m_card.h - gap * 2;
	CZM_DrawImage( CZM_AvatarFor( m_target.avatar, m_target.id ), m_card.x + gap, m_card.y + gap, av, av );
	const int tx = m_card.x + gap * 2 + av, tw = m_card.x + m_card.w - gap - tx;
	const HFont title = CZM_Font( CZMF_UI_TITLE ), meta = CZM_Font( CZMF_UI_META );
	int y = m_card.y + gap;
	CZM_DrawText( title, tx, y, tw, m_target.nick[0] ? m_target.nick : T( "Игрок", "Player" ), Ink() );
	y += CZM_FontHeight( title ) + 2;
	char line[260];
	if( m_targetLoaded ) snprintf( line, sizeof( line ), T( "ID %d  ·  жалоб за неделю: %d", "ID %d  ·  reports this week: %d" ), m_target.id, m_reportsWeek );
	else snprintf( line, sizeof( line ), T( "ID %d  ·  загружаем…", "ID %d  ·  loading…" ), m_target.id );
	CZM_DrawText( meta, tx, y, tw, line, Muted() );
	y += CZM_FontHeight( meta ) + 3;
	if( m_targetLoaded )
	{
		if( m_targetStaff ) CZM_DrawText( meta, tx, y, tw, T( "Сотрудник: действия недоступны", "Staff: no actions" ), AccentGold() );
		else if( m_limits[0] ) CZM_DrawText( meta, tx, y, tw, m_limits, AccentRed() );
		else CZM_DrawText( meta, tx, y, tw, T( "Ограничений нет", "No restrictions" ), Success() );
	}
	// what it is about
	if( m_quoteRect.h )
	{
		Surface( m_quoteRect, PackRGBA( 16, 22, 32, 255 ));
		UI_FillRect( m_quoteRect.x + 1, m_quoteRect.y + gap / 2, Q_max( 2, H / 300 ), m_quoteRect.h - gap, AccentRed() );
		const int qx = m_quoteRect.x + gap, qw = m_quoteRect.w - gap * 2;
		int qy = m_quoteRect.y + gap / 2;
		CZM_DrawText( meta, qx, qy, qw, m_context[0] ? m_context : m_report ? ReportKind( m_reportKind ) : T( "Сообщение", "Message" ), Muted() );
		qy += CZM_FontHeight( meta ) + gap / 2;
		if( m_messageGone && !m_quote[0] ) CZM_DrawText( CZM_Font( CZMF_PANEL_TEXT ), qx, qy, qw, T( "Сообщение удалено", "Message deleted" ), Muted() );
		else
		{
			const HFont body = CZM_Font( CZMF_PANEL_TEXT );
			int starts[4];
			const int lines = CZM_WrapText( body, m_quote, qw, starts, 3 );
			for( int l = 0; l < lines; l++ )
			{
				char text[620];
				CZM_WrapLine( m_quote, starts, l, text, sizeof( text ));
				CZM_DrawText( body, qx, qy + l * CZM_FontHeight( body ), qw, text, Ink() );
			}
		}
	}
	for( int i = 0; i < m_visibleCount; i++ )
	{
		const ModAction &a = s_actions[m_visible[i]];
		const bool ban = !strcmp( a.code, "ban" );
		Button( m_actionRects[i], CZM_IsRussian() ? a.ru : a.en, m_targetLoaded && !m_write, ban, Pressed( ACTION + i ),
			a.danger && !ban ? AccentRed() : 0 );
	}
}

void CCzmModeration::DrawChoicePage()
{
	using namespace CzmStyle;
	DrawHeader( ActionName( Current().code ));
	const HFont text = CZM_Font( CZMF_PANEL_TEXT );
	char line[260];
	if( m_page == PAGE_DURATION )
		snprintf( line, sizeof( line ), T( "%s  ·  на какой срок?", "%s  ·  for how long?" ), m_target.nick );
	else
		snprintf( line, sizeof( line ), "%s  ·  %s", m_target.nick, NeedsReason()
			? T( "причина, её увидит игрок", "the reason the player will see" )
			: T( "причина для журнала", "the reason for the journal" ));
	CZM_DrawText( text, m_clip.x, m_clip.y, m_clip.w, line, Muted() );
	if( m_page == PAGE_DURATION )
	{
		for( int i = 0; i < MOD_DURATIONS; i++ )
			if( m_choice[i].w )
				Button( m_choice[i], CZM_IsRussian() ? s_durations[i].ru : s_durations[i].en, true, false, Pressed( DURATION + i ),
					s_durations[i].minutes == 0 ? AccentRed() : 0 );
		return;
	}
	for( int i = 0; i < MOD_REASONS; i++ )
		Button( m_choice[i], CZM_IsRussian() ? s_reasons[i].ru : s_reasons[i].en, true, false, Pressed( REASON + i ),
			i == m_reasonIndex ? AccentGold() : 0 );
	if( m_field.w )
	{
		Surface( m_field, PackRGBA( 14, 20, 29, 255 ), m_typing ? AccentGold() : Border());
		const HFont f = CZM_Font( CZMF_PANEL_TEXT );
		const char *visible = m_reason[0] ? m_reason : T( "Опишите нарушение", "Describe the violation" );
		if( m_reason[0] ) while( *visible && CZM_TextWidth( f, visible ) > m_field.w - gap * 2 ) { visible++; while(( *visible & 0xc0 ) == 0x80 ) visible++; }
		CZM_DrawText( f, m_field.x + gap, m_field.y + ( m_field.h - CZM_FontHeight( f )) / 2, m_field.w - gap * 2, visible, m_reason[0] ? Ink() : Muted() );
		if( m_typing && ((int)( EngFuncs::DoubleTime() * 2 ) % 2 ) == 0 )
		{
			const int x = m_field.x + gap + ( m_reason[0] ? CZM_TextWidth( f, visible ) : 0 );
			UI_FillRect( x, m_field.y + m_field.h / 5, Q_max( 1, H / 400 ), m_field.h * 3 / 5, AccentGold() );
		}
		Button( m_nextRect, T( "Далее", "Next" ), Letters( m_reason ) >= 3, true, Pressed( NEXT ));
	}
}

void CCzmModeration::DrawConfirmPage()
{
	using namespace CzmStyle;
	DrawHeader( T( "Проверьте", "Check" ));
	const ModAction &a = Current();
	const HFont label = CZM_Font( CZMF_UI_META ), value = CZM_Font( CZMF_PANEL_TEXT );
	const int keyW = Q_max( CZM_TextWidth( label, T( "Действие", "Action" )), CZM_TextWidth( label, T( "Причина", "Reason" ))) + gap * 2;
	int y = m_clip.y;
	auto row = [&]( const char *key, const char *text, unsigned color )
	{
		const int lh = CZM_FontHeight( value );
		CZM_DrawText( label, m_clip.x, y + ( lh - CZM_FontHeight( label )) / 2, keyW, key, Muted() );
		int starts[4];
		const int lines = CZM_WrapText( value, text, m_clip.w - keyW, starts, 3 );
		for( int l = 0; l < lines; l++ )
		{
			char part[300];
			CZM_WrapLine( text, starts, l, part, sizeof( part ));
			CZM_DrawText( value, m_clip.x + keyW, y + l * lh, m_clip.w - keyW, part, color );
		}
		y += Q_max( 1, lines ) * lh + gap;
	};
	char text[300];
	row( T( "Действие", "Action" ), CZM_IsRussian() ? a.ru : a.en, a.danger ? AccentRed() : Ink() );
	snprintf( text, sizeof( text ), "%s  ·  ID %d", m_target.nick[0] ? m_target.nick : T( "Игрок", "Player" ), m_target.id );
	row( T( "Игрок", "Player" ), text, Ink() );
	if( a.sanction )
	{
		const char *term = T( "навсегда", "for good" );
		for( int i = 0; i < MOD_DURATIONS; i++ )
		{
			if( s_durations[i].minutes == m_minutes )
				term = CZM_IsRussian() ? s_durations[i].ru : s_durations[i].en;
		}
		row( T( "Срок", "Duration" ), term, m_minutes == 0 ? AccentRed() : Ink() );
	}
	if( m_reason[0] ) row( T( "Причина", "Reason" ), m_reason, Ink() );
	if( m_report )
	{
		snprintf( text, sizeof( text ), T( "№%d будет закрыта", "#%d will be closed" ), m_report );
		row( T( "Жалоба", "Report" ), text, Muted() );
	}
	if( !strcmp( a.code, "ban" ))
		row( "", T( "Закроет чат, ЛС, лобби и онлайн-функции на аккаунте и устройстве", "Closes chat, messages, lobbies and online features on the account and the phone" ), Muted() );
	if( m_armed )
		row( "", m_minutes == 0 ? T( "Это навсегда. Нажмите ещё раз, чтобы подтвердить", "This is for good. Tap again to confirm" )
			: T( "Нажмите ещё раз, чтобы подтвердить", "Tap again to confirm" ), AccentGold() );
	Button( m_cancel, T( "Назад", "Back" ), !m_write, false, Pressed( CANCEL ));
	Button( m_confirm, m_write ? T( "Отправляем…", "Sending…" ) : m_armed ? ( m_minutes == 0 ? T( "Да, навсегда", "Yes, for good" ) : T( "Да, применить", "Yes, apply" ))
		: T( "Подтвердить", "Confirm" ), !m_write, true, Pressed( CONFIRM ));
}

void CCzmModeration::Draw()
{
	Poll();
	if( !m_open ) return;
	if( !CZM_OnlineSupport() && CZM_OnlineReady() ) { Hide(); return; } // the role went away
	if( m_page == PAGE_TARGET ) Visible();
	Layout();
	UI_FillRect( 0, 0, W, H, PackRGBA( 0, 0, 0, 180 ));
	CZM_DrawPanel( m_panel );
	if( m_page == PAGE_PANEL ) DrawPanelPage();
	else if( m_page == PAGE_TARGET ) DrawTargetPage();
	else if( m_page == PAGE_CONFIRM ) DrawConfirmPage();
	else DrawChoicePage();
	if( m_toast[0] && EngFuncs::DoubleTime() < m_toastUntil )
	{
		using namespace CzmStyle;
		const HFont f = CZM_Font( CZMF_UI_META );
		const int height = Q_max( 22, (int)( H * .05f )), width = Q_min( m_panel.w - pad * 2, CZM_TextWidth( f, m_toast ) + pad * 2 );
		const CzmRect toast = CZM_Rect(( W - width ) / 2, Q_max( 2, m_panel.y - height - gap / 2 ), width, height );
		Surface( toast, PackRGBA( 25, 36, 51, 255 ), m_toastError ? AccentRed() : Success());
		Text( CZM_Rect( toast.x + pad / 2, toast.y, toast.w - pad, toast.h ), m_toast, CZMF_UI_META, Ink(), QM_CENTER );
	}
}

ADD_MENU3( menu_czmmoderation, CCzmModeration, UI_CzmModeration_Menu );

void UI_CzmModeration_Menu( void )
{
	CZM_ModerationOpen();
}

void CZM_ModerationOpen( void )
{
	if( !menu_czmmoderation || !CZM_OnlineSupport() ) return;
	menu_czmmoderation->OpenPanel();
}

void CZM_ModerationTarget( int player, const char *nick, int message, int lobbyMessage, const char *quote )
{
	if( !menu_czmmoderation || !CZM_OnlineSupport() || player <= 0 ) return;
	if( player == CZM_OnlinePlayer() ) { CZM_ModerationOpen(); return; }
	menu_czmmoderation->OpenTarget( player, nick, message, lobbyMessage, quote );
}

void CZM_ModerationFrame( void )
{
	// an answer that arrives after the window was closed is still collected
	if( menu_czmmoderation && !menu_czmmoderation->m_open ) menu_czmmoderation->Poll();
}
