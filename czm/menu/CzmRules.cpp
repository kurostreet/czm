/* Counter Zombie Mobile: community rules, accepted once before posting anything others see. GPL-3.0-or-later. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
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
The service tells in hello which version of the rules is current and whether this player
accepted it. Chat, private messages, the profile status and photo, lobby rooms, their chat
and microphone ask CZM_RulesAllow first: without the rules a player still plays, reads
and listens. The service refuses posts of a game that announced the rules (403 "rules"),
so a stale state here only costs one extra window.
*/
#define UI_DIR "gfx/czm/ui/"
#define RULES_URL "https://counter-zombie.ru/rules"

static struct
{
	int version;          // 0: the service does not ask for rules (an older server)
	bool accepted;
	char url[128];
	void ( *then )( void ); // the post the player was making when the window opened
} s_rules;

static const char *T( const char *ru, const char *en ) { return CZM_IsRussian() ? ru : en; }

enum { RULE_HEAD, RULE_TEXT, RULE_ITEM, RULE_NOTE };
static const struct { int kind; const char *ru, *en; } s_text[] =
{
	{ RULE_TEXT, "В игре общаются живые люди. Эти правила действуют в чате, личных сообщениях, лобби и профиле. Без них можно играть, читать чат и слушать лобби.",
		"Real people talk in this game. These rules apply to the chat, private messages, lobbies and profiles. Without them you can still play, read the chat and listen in lobbies." },
	{ RULE_HEAD, "Запрещено", "Not allowed" },
	{ RULE_ITEM, "Оскорблять, травить и запугивать игроков, угрожать им.", "Insulting, harassing, intimidating or threatening players." },
	{ RULE_ITEM, "Разжигать ненависть по национальности, расе, религии, полу, ориентации, инвалидности и другим признакам.",
		"Hate against people for their nationality, race, religion, gender, sexual orientation, disability or other traits." },
	{ RULE_ITEM, "Публиковать сексуальный и откровенный контент. Такие материалы с участием несовершеннолетних — блокировка навсегда и передача в правоохранительные органы.",
		"Sexual or explicit content. Such content involving minors means a permanent ban and a report to law enforcement." },
	{ RULE_ITEM, "Призывать к насилию, терроризму или самоповреждению, показывать жестокость.", "Calls for violence, terrorism or self-harm, and gore." },
	{ RULE_ITEM, "Спамить, рекламировать, мошенничать, выманивать пароли и коды из писем, продавать читы и аккаунты.",
		"Spam, advertising, scams, asking for passwords or email codes, selling cheats or accounts." },
	{ RULE_ITEM, "Публиковать чужие адреса, телефоны, документы и фото без согласия.", "Posting other people's addresses, phone numbers, documents or photos without consent." },
	{ RULE_ITEM, "Выдавать себя за администрацию игры или другого игрока.", "Pretending to be the game's staff or another player." },
	{ RULE_HEAD, "Как защититься", "Staying safe" },
	{ RULE_ITEM, "Нажмите на сообщение, игрока или лобби и выберите «Пожаловаться». Нарушитель не узнает, кто пожаловался. Каждую жалобу проверяет человек.",
		"Tap a message, a player or a lobby and choose \"Report\". The player never learns who reported them. A person reviews every report." },
	{ RULE_ITEM, "«Заблокировать» в профиле игрока скрывает его сообщения и голос, он больше не сможет писать вам и приглашать вас.",
		"\"Block\" in a player's profile hides their messages and voice, and they can no longer write to or invite you." },
	{ RULE_ITEM, "Администрация никогда не спрашивает пароль и коды из писем.", "Staff never ask for your password or email codes." },
	{ RULE_ITEM, "Роли назначает главный администратор. Moderator управляет чатом; Tester отправляет обращения; Server owner показывает до пяти серверов проекта. За действия модератора отвечает отдельная проверка. Роль не означает, что CZM владеет указанным сервером.",
		"The head administrator assigns roles. Moderators manage chat, testers submit tickets, and server owners list up to five project servers. Moderator actions are reviewed. A role does not mean CZM owns the listed server." },
	{ RULE_ITEM, "На сервер можно пожаловаться из его карточки или меню в игре. С подтверждённой почты — одна жалоба на один сервер раз в 30 дней. Модератор видит ваш ник, ID аккаунта и число обращений. Решение о блокировке сервера принимается после проверки; его можно пересмотреть.",
		"Report a server from its card or the in-game menu. Verified email: one report per server every 30 days. Moderators see your nickname, account ID and report counts. A server restriction follows a review and can be reconsidered." },
	{ RULE_HEAD, "За нарушения", "Consequences" },
	{ RULE_ITEM, "Удаляем сообщения, сбрасываем аватар и статус, закрываем лобби.", "We delete messages, reset avatars and statuses, and close lobbies." },
	{ RULE_ITEM, "Отключаем чат, лобби и личные сообщения на неделю, месяц или навсегда — для аккаунта и устройства.",
		"We ban chat, lobbies and private messages for a week, a month or forever, on the account and the device." },
	{ RULE_NOTE, "Полная версия: counter-zombie.ru/rules. Вопросы и обжалование: kuro.street.inc@gmail.com",
		"Full version: counter-zombie.ru/rules. Questions and appeals: kuro.street.inc@gmail.com" },
};
#define RULE_BLOCKS ( sizeof( s_text ) / sizeof( s_text[0] ))
#define RULE_LINES 160

class CCzmRules : public CMenuFramework
{
public:
	CCzmRules();
	void Open( bool readOnly );
	void Hide() override;
	void Draw() override;
	bool IsRoot() const override { return false; }
	bool KeyDown( int key ) override;
	bool KeyUp( int key ) override;
	bool MouseMove( int x, int y ) override;
	void Poll();

	enum { CHECK=1, LATER, ACCEPT, SITE, BODY };
	void Layout();
	int Hit();
	void Activate( int hit );
	bool Pressed( int hit ) { return m_pressed == hit && Hit() == hit; }
	const char *Text( int block ) const { return CZM_IsRussian() ? s_text[block].ru : s_text[block].en; }
	int Font( int block ) const { return s_text[block].kind == RULE_HEAD ? CZMF_UI_LABEL : s_text[block].kind == RULE_NOTE ? CZMF_SMALL : CZMF_PANEL_TEXT; }

	bool m_open, m_readOnly, m_checked, m_failed, m_drag, m_moved;
	int m_request, m_pressed, m_scroll, m_downScroll, m_downY, m_maxScroll, m_lines, m_indent;
	struct { short block, from, to; int y; } m_line[RULE_LINES];
	CzmRect m_panel, m_clip, m_check, m_later, m_accept, m_site;
};

CCzmRules::CCzmRules() : CMenuFramework( "CzmRules" )
{
	m_open=m_readOnly=m_checked=m_failed=m_drag=m_moved=false;
	m_request=m_pressed=m_scroll=m_downScroll=m_downY=m_maxScroll=m_lines=m_indent=0;
}

void CCzmRules::Open( bool readOnly )
{
	m_readOnly=readOnly; m_failed=false; m_scroll=m_pressed=0; m_drag=m_moved=false;
	if( !m_request ) m_checked=false;
	if( !m_open || m_pStack->Current() != this ) CMenuFramework::Show();
	m_open=true;
}

void CCzmRules::Hide()
{
	m_open=false; m_pressed=0; m_drag=false;
	CMenuFramework::Hide();
}

void CCzmRules::Layout()
{
	const int W=ScreenWidth, H=ScreenHeight;
	const int pad=Q_max( 12, (int)( H*.038f )), gap=Q_max( 8, (int)( H*.018f ));
	// a readable column: about 90 characters a line on a phone in landscape
	const int width=Q_min( (int)( W*.90f ), (int)( H*1.32f )), height=Q_min( H-gap*2, (int)( H*.92f ));
	const int button=Q_max( 36, (int)( H*.082f )), inner=width-pad*2;
	const int heading=CZM_FontHeight( CZM_Font( CZMF_PANEL_TITLE ))+gap*2;
	m_panel=CZM_Rect( (W-width)/2, (H-height)/2, width, height );

	// footer: the agreement and the two buttons share a row when the panel is wide enough
	const HFont label=CZM_Font( CZMF_PANEL_TEXT );
	const int box=button*62/100;
	const int buttonW=Q_min( (int)( H*.30f ), ( inner-gap )/2 );
	const int agreement=box+gap+CZM_TextWidth( label, T( "Я прочитал и принимаю правила", "I have read and accept the rules" ));
	const bool oneRow=agreement+gap*2+buttonW*2+gap<=inner;
	const int footer=oneRow ? button : button*2+gap;
	const int bottom=m_panel.y+height-pad;
	m_accept=CZM_Rect( m_panel.x+width-pad-buttonW, bottom-button, buttonW, button );
	m_later=CZM_Rect( m_accept.x-gap-buttonW, m_accept.y, buttonW, button );
	m_site=m_readOnly ? m_later : CZM_Rect( 0,0,0,0 );
	if( m_readOnly ) m_later=CZM_Rect( 0,0,0,0 );
	m_check=CZM_Rect( m_panel.x+pad, oneRow ? m_accept.y : m_accept.y-gap-button, oneRow ? m_later.x-gap-m_panel.x-pad : inner, button );
	if( m_readOnly ) m_check.w=( m_site.x-gap )-m_check.x;

	m_clip=CZM_Rect( m_panel.x+pad, m_panel.y+pad+heading, inner, height-pad*2-heading-footer-gap );

	// the text: headings, paragraphs and items with a red marker, wrapped to the panel
	m_indent=Q_max( 10, (int)( H*.032f ));
	int y=0; m_lines=0;
	for( int b=0; b<(int)RULE_BLOCKS && m_lines<RULE_LINES; b++ )
	{
		const HFont f=CZM_Font( Font( b ));
		const int kind=s_text[b].kind, lineH=CZM_FontHeight( f )+gap/3;
		const char *text=Text( b );
		int starts[24], count;
		if( kind==RULE_HEAD && b ) y+=gap;
		if( kind==RULE_NOTE ) y+=gap;
		count=CZM_WrapText( f, text, m_clip.w-( kind==RULE_ITEM ? m_indent : 0 ), starts, 23 );
		for( int l=0; l<count && m_lines<RULE_LINES; l++, m_lines++ )
		{
			m_line[m_lines].block=b; m_line[m_lines].from=starts[l];
			m_line[m_lines].to=l+1<count ? starts[l+1] : (short)strlen( text );
			m_line[m_lines].y=y; y+=lineH;
		}
		y+=kind==RULE_ITEM ? gap/2 : kind==RULE_HEAD ? gap/4 : gap/2;
	}
	m_maxScroll=Q_max( 0, y-m_clip.h ); m_scroll=bound( 0, m_scroll, m_maxScroll );
}

int CCzmRules::Hit()
{
	if( m_accept.HasCursor() ) return ACCEPT;
	if( m_later.w && m_later.HasCursor() ) return LATER;
	if( m_site.w && m_site.HasCursor() ) return SITE;
	if( !m_readOnly && m_check.HasCursor() ) return CHECK;
	return m_clip.HasCursor() ? BODY : 0;
}

void CCzmRules::Activate( int hit )
{
	if( !m_open ) return;
	if( hit==SITE ) { CZM_PlayClick(); EngFuncs::ShellExecute( s_rules.url[0] ? s_rules.url : RULES_URL, NULL, false ); return; }
	if( m_readOnly ) { if( hit==ACCEPT ) { CZM_PlayClick(); Hide(); } return; }
	if( m_request ) return; // the answer decides
	if( hit==CHECK ) { CZM_PlayClick(); m_checked=!m_checked; m_failed=false; return; }
	if( hit==LATER ) { CZM_PlayClick(); s_rules.then=NULL; Hide(); return; }
	if( hit!=ACCEPT || !m_checked ) return;
	char body[48]; snprintf( body, sizeof( body ), "{\"version\":%d}", s_rules.version>0 ? s_rules.version : 1 );
	CZM_PlayClick(); m_failed=false;
	m_request=CZM_OnlineKey()[0] ? CZM_NetRequest( "POST", CZM_OnlineUrl( "/api/v1/rules/accept" ), CZM_OnlineKey(), body ) : 0;
	if( !m_request ) m_failed=true;
}

void CCzmRules::Poll()
{
	int status=0; CUtlString body;
	if( !m_request || !CZM_NetPoll( m_request, &status, body )) return;
	m_request=0;
	CzmJson j;
	if( status==200 && j.Parse( body.Get() ) && j.Bool( j.Get( j.Get( 0, "rules" ), "accepted" )))
	{
		s_rules.accepted=true;
		void ( *then )( void )=s_rules.then; s_rules.then=NULL;
		if( m_open ) Hide();
		if( then ) then(); // the message, the room or the photo goes on as the player asked
		return;
	}
	m_failed=true;
}

bool CCzmRules::KeyDown( int key )
{
	Layout();
	if( UI::Key::IsEscape( key )) { Activate( m_readOnly ? ACCEPT : LATER ); return true; }
	if( UI::Key::IsEnter( key )) { Activate( ACCEPT ); return true; }
	if( key==K_MWHEELUP || key==K_MWHEELDOWN ) { m_scroll=bound( 0, m_scroll+( key==K_MWHEELUP ? -1 : 1 )*ScreenHeight/10, m_maxScroll ); return true; }
	if( UI::Key::IsLeftMouse( key ))
	{
		m_pressed=Hit(); m_drag=m_pressed==BODY; m_moved=false; m_downY=uiStatic.cursorY; m_downScroll=m_scroll;
	}
	return true;
}

bool CCzmRules::KeyUp( int key )
{
	if( UI::Key::IsLeftMouse( key ))
	{
		Layout(); int hit=Hit();
		if( !m_moved && m_pressed && m_pressed==hit ) Activate( hit );
		m_pressed=0; m_drag=false;
	}
	return true;
}

bool CCzmRules::MouseMove( int x, int y )
{
	CMenuFramework::MouseMove( x, y );
	if( m_drag )
	{
		int dy=uiStatic.cursorY-m_downY;
		if( abs( dy )>ScreenHeight*.018f ) m_moved=true;
		if( m_moved ) m_scroll=bound( 0, m_downScroll-dy, m_maxScroll );
	}
	return true;
}

void CCzmRules::Draw()
{
	Poll();
	Layout();
	using namespace CzmStyle;
	const int H=ScreenHeight, pad=m_clip.x-m_panel.x, gap=Q_max( 8, (int)( H*.018f ));
	UI_FillRect( 0, 0, ScreenWidth, ScreenHeight, PackRGBA( 0, 0, 0, 180 ));
	CZM_DrawPanel( m_panel );
	CZM_DrawImage( UI_DIR "white.png", m_clip.x, m_panel.y+pad, m_clip.w, Q_max( 2, H/200 ), PackRGBA( 230, 38, 38, 255 ));
	CZM_DrawText( CZM_Font( CZMF_PANEL_TITLE ), m_clip.x, m_panel.y+pad+gap, m_clip.w, T( "Правила сообщества", "Community rules" ), CZM_White() );

	UI::Scissor::PushScissor( m_clip.x, m_clip.y, m_clip.w, m_clip.h );
	for( int i=0; i<m_lines; i++ )
	{
		const int b=m_line[i].block, kind=s_text[b].kind, y=m_clip.y+m_line[i].y-m_scroll;
		const HFont f=CZM_Font( Font( b ));
		const int fh=CZM_FontHeight( f );
		if( y+fh<m_clip.y || y>m_clip.y+m_clip.h ) continue;
		char text[512]; const int range[2]={ m_line[i].from, m_line[i].to };
		CZM_WrapLine( Text( b ), range, 0, text, sizeof( text ));
		const bool first=i==0 || m_line[i-1].block!=b;
		if( kind==RULE_ITEM && first )
		{
			const int dot=Q_max( 4, H/110 );
			UI_FillRect( m_clip.x+dot/2, y+( fh-dot )/2, dot, dot, AccentRed() );
		}
		CZM_DrawText( f, m_clip.x+( kind==RULE_ITEM ? m_indent : 0 ), y, m_clip.w, text,
			kind==RULE_HEAD ? AccentRed() : kind==RULE_NOTE ? Muted() : kind==RULE_TEXT ? Muted() : Ink() );
	}
	UI::Scissor::PopScissor();
	// the text fades out where more of it waits above or below
	const int fade=Q_max( 8, H/24 ), bands=8;
	for( int i=0; i<bands; i++ )
	{
		const int y0=i*fade/bands, y1=( i+1 )*fade/bands, alpha=255*( bands-i )/( bands+1 );
		if( m_scroll<m_maxScroll ) UI_FillRect( m_clip.x, m_clip.y+m_clip.h-y1, m_clip.w, y1-y0, PackRGBA( 11, 13, 19, alpha ));
		if( m_scroll>0 ) UI_FillRect( m_clip.x, m_clip.y+y0, m_clip.w, y1-y0, PackRGBA( 11, 13, 19, alpha ));
	}
	if( m_maxScroll )
	{
		const int thumb=Q_max( 12, m_clip.h*m_clip.h/( m_clip.h+m_maxScroll ));
		UI_FillRect( m_panel.x+m_panel.w-pad/2, m_clip.y+( m_clip.h-thumb )*m_scroll/m_maxScroll, 3, thumb, CZM_White( 140 ));
	}

	// footer
	const HFont label=CZM_Font( CZMF_PANEL_TEXT );
	const int box=m_check.h*62/100, boxY=m_check.y+( m_check.h-box )/2, textX=m_check.x+box+gap;
	if( m_readOnly )
	{
		if( s_rules.accepted )
		{
			CZM_DrawImage( UI_DIR "icon_check.png", m_check.x, boxY, box, box, Success() );
			CZM_DrawText( label, textX, m_check.y+( m_check.h-CZM_FontHeight( label ))/2, m_check.w-box-gap,
				T( "Вы приняли правила", "You accepted the rules" ), Success() );
		}
		Button( m_site, T( "На сайте", "On the website" ), true, false, Pressed( SITE ));
		Button( m_accept, T( "Закрыть", "Close" ), true, true, Pressed( ACCEPT ));
		return;
	}
	Surface( CZM_Rect( m_check.x, boxY, box, box ), m_checked ? PackRGBA( 190, 43, 60, 255 ) : Base(),
		m_checked || Pressed( CHECK ) ? AccentRed() : Muted(), Q_max( 3, box/5 ));
	if( m_checked ) CZM_DrawImage( UI_DIR "icon_check.png", m_check.x+box/5, boxY+box/5, box*3/5, box*3/5, Ink() );
	const char *line=m_failed ? T( "Не удалось сохранить. Проверьте интернет", "Could not save. Check the connection" )
		: T( "Я прочитал и принимаю правила", "I have read and accept the rules" );
	CZM_DrawText( label, textX, m_check.y+( m_check.h-CZM_FontHeight( label ))/2, m_check.x+m_check.w-textX, line,
		m_failed ? AccentRed() : Ink() );
	Button( m_later, T( "Не сейчас", "Not now" ), !m_request, false, Pressed( LATER ));
	Button( m_accept, m_request ? T( "Сохраняем…", "Saving…" ) : m_failed ? T( "Повторить", "Retry" ) : T( "Принять", "Accept" ),
		m_checked && !m_request, true, Pressed( ACCEPT ));
}

ADD_MENU3( menu_czmrules, CCzmRules, UI_CzmRules_Menu );

void UI_CzmRules_Menu( void )
{
	CZM_RulesShow();
}

void CZM_RulesSetState( int version, bool accepted, const char *url )
{
	s_rules.version=version>0 ? version : 0;
	s_rules.accepted=accepted;
	Q_strncpy( s_rules.url, url && !strncmp( url, "https://", 8 ) ? url : RULES_URL, sizeof( s_rules.url ));
}

bool CZM_RulesAccepted( void )
{
	return !s_rules.version || s_rules.accepted;
}

bool CZM_RulesConfirmed( void )
{
	return s_rules.version && s_rules.accepted;
}

bool CZM_RulesAllow( void ( *then )( void ))
{
	if( CZM_RulesAccepted() ) return true;
	s_rules.then=then;
	if( menu_czmrules ) menu_czmrules->Open( false );
	return false;
}

void CZM_RulesRefused( int version, void ( *then )( void ))
{
	// the service knows better: a newer version, or acceptance made on another phone was reset
	if( version>0 ) s_rules.version=version;
	else if( !s_rules.version ) s_rules.version=1;
	s_rules.accepted=false;
	CZM_RulesAllow( then );
}

void CZM_RulesShow( void )
{
	if( !menu_czmrules ) return;
	s_rules.then=NULL;
	menu_czmrules->Open( CZM_RulesAccepted() );
}

void CZM_RulesFrame( void )
{
	// an answer that arrives after the window was closed by the game still counts
	if( menu_czmrules && !menu_czmrules->m_open ) menu_czmrules->Poll();
}
