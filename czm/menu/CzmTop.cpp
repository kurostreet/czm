/* Counter Zombie Mobile: the Top 100 by time on game servers. GPL-3.0-or-later. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
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
The service ranks players by the time the game was really connected to a game server (playtime.py):
the three first get cards on top, the rest a list, and the player's own place stays pinned at the
bottom, outside the hundred too. A tap on anyone opens the profile.
*/
#define UI_DIR "gfx/czm/ui/"
#define TOP_ROWS 100

namespace
{
const char *T( const char *ru, const char *en ) { return CZM_IsRussian() ? ru : en; }

struct TopRow
{
	int place, id, seconds;
	bool online, support;
	char nick[100], avatar[32];
};
}

class CCzmTop : public CMenuFramework
{
public:
	CCzmTop();
	void Open();
	void Hide() override;
	void Draw() override;
	bool IsRoot() const override { return false; }
	bool KeyDown( int key ) override;
	bool KeyUp( int key ) override;
	bool MouseMove( int x, int y ) override;
	void Poll();
	bool m_open;

	enum { BACK = 1, REFRESH, PODIUM = 10, ROW = 100, ME = 300 };
	void Layout();
	int Hit();
	void Activate( int hit );
	bool Pressed( int hit ) { return m_pressed == hit && Hit() == hit; }
	void Load();
	void DrawPodium( int i, const CzmRect &r );
	void DrawRow( int i, const CzmRect &r );
	void DrawMe();
	int ListCount() const { return m_count > 3 ? m_count - 3 : 0; }
	CzmRect RowRect( int i ) const;

	TopRow m_rows[TOP_ROWS];
	int m_count, m_players;
	bool m_loaded, m_failed, m_hasMe;
	int m_mePlace, m_meSeconds, m_meBehind;
	int m_request, m_pressed, m_scroll, m_maxScroll, m_downScroll, m_downY;
	bool m_drag, m_moved;
	double m_nextLoad, m_openedAt;
	CzmRect m_panel, m_back, m_refresh, m_podium[3], m_clip, m_me;
	int W, H, pad, gap, rowH;
};

CCzmTop::CCzmTop() : CMenuFramework( "CzmTop" )
{
	m_open = m_loaded = m_failed = m_hasMe = m_drag = m_moved = false;
	m_count = m_players = m_mePlace = m_meSeconds = m_meBehind = 0;
	m_request = m_pressed = m_scroll = m_maxScroll = m_downScroll = m_downY = 0;
	m_nextLoad = m_openedAt = 0;
	memset( m_rows, 0, sizeof( m_rows ));
	W = H = pad = gap = rowH = 0;
}

void CCzmTop::Open()
{
	m_scroll = 0; m_pressed = 0; m_drag = m_moved = false;
	if( !m_open || m_pStack->Current() != this ) CMenuFramework::Show();
	m_open = true;
	m_openedAt = EngFuncs::DoubleTime();
	m_nextLoad = 0;
	Load();
}

void CCzmTop::Hide()
{
	m_open = false; m_pressed = 0; m_drag = false;
	CMenuFramework::Hide();
}

void CCzmTop::Load()
{
	if( m_request || !CZM_OnlineReady() ) return;
	m_request = CZM_NetRequest( "GET", CZM_OnlineUrl( "/api/v1/top" ), CZM_OnlineKey(), "" );
	m_nextLoad = EngFuncs::DoubleTime() + 60.0;
	if( !m_request ) m_failed = true;
}

void CCzmTop::Poll()
{
	int status = 0;
	CUtlString body;
	if( m_request && CZM_NetPoll( m_request, &status, body ))
	{
		m_request = 0;
		CzmJson j;
		if( status != 200 || !j.Parse( body.Get() ))
		{
			m_failed = !m_loaded;
			return;
		}
		const int list = j.Get( 0, "top" );
		m_count = 0;
		for( int i = 0; i < j.Count( list ) && m_count < TOP_ROWS; i++ )
		{
			const int item = j.At( list, i );
			TopRow &r = m_rows[m_count++];
			memset( &r, 0, sizeof( r ));
			r.place = j.Int( j.Get( item, "place" ));
			r.id = j.Int( j.Get( item, "id" ));
			r.seconds = j.Int( j.Get( item, "seconds" ));
			r.online = j.Bool( j.Get( item, "online" ));
			r.support = !strcmp( j.String( j.Get( item, "role" )), "support" );
			Q_strncpy( r.nick, j.String( j.Get( item, "nick" )), sizeof( r.nick ));
			Q_strncpy( r.avatar, j.String( j.Get( item, "avatar" )), sizeof( r.avatar ));
		}
		m_players = j.Int( j.Get( 0, "players" ));
		const int me = j.Get( 0, "me" );
		m_hasMe = j.Type( me ) == CzmJson::T_OBJECT;
		m_mePlace = j.Int( j.Get( me, "place" ));
		m_meSeconds = j.Int( j.Get( me, "seconds" ));
		m_meBehind = j.Int( j.Get( me, "behind" ));
		m_loaded = true;
		m_failed = false;
	}
	if( m_open && !m_request && EngFuncs::DoubleTime() >= m_nextLoad ) Load();
}

/*
 * layout
 */
CzmRect CCzmTop::RowRect( int i ) const
{
	return CZM_Rect( m_clip.x, m_clip.y + i * rowH - m_scroll, m_clip.w, rowH - gap / 2 );
}

void CCzmTop::Layout()
{
	W = ScreenWidth; H = ScreenHeight;
	pad = Q_max( 10, (int)( H * .028f )); gap = Q_max( 6, (int)( H * .014f ));
	const int bh = Q_max( 34, (int)( H * .068f ));
	const int pw = Q_min( W - pad * 2, (int)( H * 1.72f )), ph = Q_min( H - gap * 2, (int)( H * .94f ));
	m_panel = CZM_Rect(( W - pw ) / 2, ( H - ph ) / 2, pw, ph );
	const int left = m_panel.x + pad, inner = pw - pad * 2;
	int y = m_panel.y + pad;
	m_back = CZM_Rect( left, y, bh, bh );
	m_refresh = CZM_Rect( left + inner - bh, y, bh, bh );
	y += bh + gap;
	// the three first: the winner in the middle, a little higher
	const int cardW = ( inner - gap * 2 ) / 3, cardH = Q_max( 90, (int)( H * .25f )), lift = H * .02f;
	const int order[3] = { 1, 0, 2 }; // left: 2nd, middle: 1st, right: 3rd
	for( int k = 0; k < 3; k++ )
	{
		const int i = order[k];
		m_podium[i] = CZM_Rect( left + k * ( cardW + gap ), y + ( i == 0 ? 0 : lift ), cardW, cardH - ( i == 0 ? 0 : lift ));
	}
	y += cardH + gap;
	const int meH = Q_max( 44, (int)( H * .095f ));
	m_me = CZM_Rect( left, m_panel.y + ph - pad - meH, inner, meH );
	rowH = Q_max( 40, (int)( H * .085f ));
	m_clip = CZM_Rect( left, y, inner, m_me.y - gap - y );
	m_maxScroll = Q_max( 0, ListCount() * rowH - m_clip.h );
	m_scroll = bound( 0, m_scroll, m_maxScroll );
}

int CCzmTop::Hit()
{
	if( !m_panel.HasCursor() ) return BACK; // a tap next to the window closes it
	if( m_back.HasCursor() ) return BACK;
	if( m_refresh.HasCursor() ) return REFRESH;
	for( int i = 0; i < 3 && i < m_count; i++ ) if( m_podium[i].HasCursor() ) return PODIUM + i;
	if( m_me.HasCursor() ) return ME;
	if( m_clip.HasCursor() )
	{
		const int i = ( uiStatic.cursorY - m_clip.y + m_scroll ) / Q_max( 1, rowH );
		if( i >= 0 && i < ListCount() ) return ROW + i;
	}
	return 0;
}

void CCzmTop::Activate( int hit )
{
	if( !hit ) return;
	CZM_PlayClick();
	if( hit == BACK ) { Hide(); return; }
	if( hit == REFRESH ) { Load(); return; }
	int index = -1;
	if( hit >= PODIUM && hit < PODIUM + 3 ) index = hit - PODIUM;
	else if( hit >= ROW && hit < ROW + TOP_ROWS ) index = 3 + hit - ROW;
	if( index >= 0 && index < m_count ) { CZM_OpenProfile( m_rows[index].id ); return; }
	if( hit == ME && CZM_OnlinePlayer() > 0 ) CZM_OpenProfile( CZM_OnlinePlayer() );
}

bool CCzmTop::KeyDown( int key )
{
	Layout();
	if( UI::Key::IsEscape( key )) { Hide(); return true; }
	if( key == K_MWHEELUP || key == K_MWHEELDOWN )
	{
		m_scroll = bound( 0, m_scroll + ( key == K_MWHEELUP ? -1 : 1 ) * rowH * 2, m_maxScroll );
		return true;
	}
	if( UI::Key::IsLeftMouse( key ))
	{
		m_pressed = Hit();
		m_drag = m_clip.HasCursor();
		m_moved = false; m_downY = uiStatic.cursorY; m_downScroll = m_scroll;
		return true;
	}
	return CMenuFramework::KeyDown( key );
}

bool CCzmTop::KeyUp( int key )
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

bool CCzmTop::MouseMove( int x, int y )
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

/*
 * drawing
 */
static void Chip( const CzmRect &r, const char *icon, bool pressed, unsigned tint = 0 )
{
	CzmStyle::Surface( r, pressed ? PackRGBA( 41, 51, 67, 255 ) : PackRGBA( 28, 34, 45, 255 ), CzmStyle::Border(), r.h / 2 );
	const int side = r.h * 46 / 100;
	CZM_DrawImage( icon, r.x + ( r.w - side ) / 2, r.y + ( r.h - side ) / 2, side, side, tint ? tint : CzmStyle::Ink() );
}

static unsigned Fade( unsigned color, int alpha )
{
	return ( color & 0x00FFFFFF ) | ((unsigned)alpha << 24 );
}

void CCzmTop::DrawPodium( int i, const CzmRect &r )
{
	using namespace CzmStyle;
	const TopRow &p = m_rows[i];
	const unsigned color = CZM_TopColor( p.place );
	const bool mine = p.id == CZM_OnlinePlayer(), down = Pressed( PODIUM + i );
	Surface( r, down ? PackRGBA( 34, 40, 52, 255 ) : PackRGBA( 22, 26, 34, 255 ), Fade( color, mine ? 255 : 150 ), Q_max( 6, r.h / 10 ));
	UI_FillRect( r.x + r.w / 4, r.y + 1, r.w / 2, Q_max( 2, H / 300 ), color );
	// the picture with its own light and crown
	const int av = Q_min( r.w * 40 / 100, r.h * 44 / 100 ), ax = r.x + ( r.w - av ) / 2, ay = r.y + r.h * 20 / 100;
	const double wave = 0.5 + 0.5 * sin( EngFuncs::DoubleTime() * 2.0 * M_PI / ( 2.6 + i * 0.4 ));
	CZM_DrawImage( UI_DIR "glow.png", ax - av * 45 / 100, ay - av * 45 / 100, av * 190 / 100, av * 190 / 100, Fade( color, (int)( 70 + 50 * wave )));
	CZM_DrawImage( CZM_AvatarFor( p.avatar, p.id ), ax, ay, av, av );
	const int ring = Q_max( 2, av / 28 );
	CZM_DrawImage( UI_DIR "icon_ring.png", ax - ring, ay - ring, av + ring * 2, av + ring * 2, color );
	const int crown = av * 46 / 100;
	CZM_DrawImage( CZM_TopCrown( p.place ), ax + ( av - crown ) / 2, ay - crown * 80 / 100, crown, crown, color );
	if( p.online )
	{
		const int dot = Q_max( 7, av / 6 );
		CZM_DrawImage( UI_DIR "dot.png", ax + av - dot, ay + av - dot, dot, dot, PackRGBA( 66, 216, 137, 255 ));
	}
	const HFont nick = CZM_Font( CZMF_UI_LABEL ), meta = CZM_Font( CZMF_UI_META );
	int y = ay + av + gap / 2;
	{
		// the nick and, for the official account, its SUPPORT tag: one centred group
		const int tagH = CZM_FontHeight( meta ) + 4, tagW = p.support ? CZM_SupportTagWidth( tagH ) + gap / 2 : 0;
		const int nickW = Q_max( 0, Q_min( CZM_TextWidth( nick, p.nick ) + 2, r.w - gap * 2 - tagW ));
		const int x = r.x + ( r.w - nickW - tagW ) / 2;
		CZM_DrawText( nick, x, y, nickW, p.nick, Ink() );
		if( p.support ) CZM_DrawSupportTag( x + nickW + gap / 2, y + ( CZM_FontHeight( nick ) - tagH ) / 2, tagH );
	}
	y += CZM_FontHeight( nick ) + 2;
	char time[48], line[80];
	CZM_FormatPlaytime( p.seconds, time, sizeof( time ));
	snprintf( line, sizeof( line ), "TOP %d  ·  %s", p.place, time );
	CZM_DrawText( meta, r.x + gap, y, r.w - gap * 2, line, color, QM_CENTER );
}

void CCzmTop::DrawRow( int i, const CzmRect &r )
{
	using namespace CzmStyle;
	const TopRow &p = m_rows[3 + i];
	const unsigned color = CZM_TopColor( p.place );
	const bool mine = p.id == CZM_OnlinePlayer(), down = Pressed( ROW + i );
	Surface( r, down ? PackRGBA( 34, 42, 56, 255 ) : mine ? PackRGBA( 44, 26, 32, 255 ) : PackRGBA( 20, 25, 33, 255 ),
		mine ? AccentRed() : PackRGBA( 40, 47, 58, 255 ));
	const HFont label = CZM_Font( CZMF_UI_LABEL ), meta = CZM_Font( CZMF_UI_META );
	const int placeW = CZM_TextWidth( label, "100" ) + gap * 2;
	char text[48];
	snprintf( text, sizeof( text ), "%d", p.place );
	CZM_DrawText( label, r.x + gap, r.y + ( r.h - CZM_FontHeight( label )) / 2, placeW - gap, text, color, QM_CENTER );
	const int av = r.h - gap, ax = r.x + placeW + gap / 2, ay = r.y + gap / 2;
	CZM_DrawImage( CZM_AvatarFor( p.avatar, p.id ), ax, ay, av, av );
	if( p.online )
	{
		const int dot = Q_max( 6, av / 4 );
		CZM_DrawImage( UI_DIR "dot.png", ax + av - dot, ay + av - dot, dot, dot, PackRGBA( 66, 216, 137, 255 ));
	}
	CZM_FormatPlaytime( p.seconds, text, sizeof( text ));
	const int timeW = CZM_TextWidth( label, text ) + 2, right = r.x + r.w - gap;
	CZM_DrawText( label, right - timeW, r.y + ( r.h - CZM_FontHeight( label )) / 2, timeW, text, Ink() );
	int x = ax + av + gap;
	const int room = right - timeW - gap - x, tagH = Q_max( 12, CZM_FontHeight( meta ) + 4 );
	const int tagW = CZM_TopTagWidth( p.place, tagH ) + ( p.support ? CZM_SupportTagWidth( tagH ) + gap / 2 : 0 );
	const int nickW = Q_max( 0, Q_min( CZM_TextWidth( label, p.nick ) + 2, room - tagW - gap ));
	CZM_DrawText( label, x, r.y + ( r.h - CZM_FontHeight( label )) / 2, nickW, p.nick, Ink() );
	x += nickW + gap / 2;
	if( x + tagW <= right - timeW - gap / 2 )
	{
		x += CZM_DrawTopTag( x, r.y + ( r.h - tagH ) / 2, tagH, p.place ) + gap / 2;
		if( p.support ) CZM_DrawSupportTag( x, r.y + ( r.h - tagH ) / 2, tagH );
	}
}

void CCzmTop::DrawMe()
{
	using namespace CzmStyle;
	const bool down = Pressed( ME );
	const unsigned edge = m_hasMe && m_mePlace <= 100 ? CZM_TopColor( m_mePlace ) : AccentRed();
	Surface( m_me, down ? PackRGBA( 44, 30, 36, 255 ) : PackRGBA( 34, 22, 28, 255 ), edge, Q_max( 6, m_me.h / 5 ));
	const HFont label = CZM_Font( CZMF_UI_LABEL ), meta = CZM_Font( CZMF_UI_META );
	const int x = m_me.x + pad, w = m_me.w - pad * 2;
	if( !m_loaded )
		return;
	if( !m_hasMe )
	{
		Text( CZM_Rect( x, m_me.y, w, m_me.h ), T( "Ваше место появится после первой игры на любом сервере",
			"Your place appears after your first game on any server" ), CZMF_UI_LABEL, Muted() );
		return;
	}
	char time[48], line[200];
	CZM_FormatPlaytime( m_meSeconds, time, sizeof( time ));
	char nick[64];
	CZM_CleanName( EngFuncs::GetCvarString( "name" ), nick, sizeof( nick ));
	if( nick[0] )
		snprintf( line, sizeof( line ), T( "Ваше место  №%d  ·  %s  ·  %s", "Your place  #%d  ·  %s  ·  %s" ), m_mePlace, nick, time );
	else
		snprintf( line, sizeof( line ), T( "Ваше место  №%d  ·  %s", "Your place  #%d  ·  %s" ), m_mePlace, time );
	const int lh = CZM_FontHeight( label ), mh = CZM_FontHeight( meta );
	const bool second = m_mePlace > 100 && m_meBehind > 0;
	const int top = m_me.y + ( m_me.h - lh - ( second ? mh + 2 : 0 )) / 2;
	const int tagH = Q_max( 12, mh + 4 ), tagW = CZM_TopTagWidth( m_mePlace, tagH );
	CZM_DrawText( label, x, top, w - ( tagW ? tagW + pad : 0 ), line, Ink() );
	if( tagW ) CZM_DrawTopTag( m_me.x + m_me.w - pad - tagW, m_me.y + ( m_me.h - tagH ) / 2, tagH, m_mePlace );
	if( second )
	{
		char behind[48];
		CZM_FormatPlaytime( m_meBehind, behind, sizeof( behind ));
		snprintf( line, sizeof( line ), T( "До 100-го места сейчас: %s", "To the 100th place now: %s" ), behind );
		CZM_DrawText( meta, x, top + lh + 2, w, line, Muted() );
	}
}

void CCzmTop::Draw()
{
	Poll();
	if( !m_open ) return;
	Layout();
	using namespace CzmStyle;
	UI_FillRect( 0, 0, W, H, PackRGBA( 0, 0, 0, 170 ));
	Surface( m_panel, PackRGBA( 15, 18, 24, 252 ), PackRGBA( 58, 64, 78, 255 ), Q_max( 8, (int)( H * .03f )));
	Chip( m_back, UI_DIR "icon_back.png", Pressed( BACK ));
	Chip( m_refresh, UI_DIR "icon_refresh.png", Pressed( REFRESH ), m_request ? Muted() : 0 );
	{
		const HFont title = CZM_Font( CZMF_UI_TITLE ), meta = CZM_Font( CZMF_UI_META );
		const int tx = m_back.x + m_back.w + gap, tw = m_refresh.x - gap - tx;
		const int titleW = Q_min( CZM_TextWidth( title, T( "Топ 100", "Top 100" )) + 2, tw );
		CZM_DrawText( title, tx, m_back.y + ( m_back.h - CZM_FontHeight( title )) / 2, titleW, T( "Топ 100", "Top 100" ), Ink() );
		CZM_DrawText( meta, tx + titleW + gap, m_back.y + ( m_back.h - CZM_FontHeight( meta )) / 2, tw - titleW - gap,
			T( "время на игровых серверах  ·  за всё время", "time on game servers  ·  all time" ), Muted() );
	}
	if( !m_loaded || !m_count )
	{
		const char *text = m_failed ? T( "Нет связи. Нажмите обновить", "No connection. Tap refresh" )
			: !m_loaded ? T( "Загружаем…", "Loading…" )
			: T( "Пока никто не играл на серверах. Время считается с первой игры", "Nobody has played yet. Time counts from the first game" );
		Text( CZM_Rect( m_panel.x + pad, m_podium[0].y, m_panel.w - pad * 2, m_me.y - m_podium[0].y ), text, CZMF_PANEL_TEXT, Muted(), QM_CENTER );
		DrawMe();
		return;
	}
	// the first three rise into place one after another when the window opens
	const double since = EngFuncs::DoubleTime() - m_openedAt;
	for( int i = 0; i < 3 && i < m_count; i++ )
	{
		const double t = bound( 0.0, ( since - i * 0.06 ) / 0.22, 1.0 ), ease = 1.0 - ( 1.0 - t ) * ( 1.0 - t ) * ( 1.0 - t );
		CzmRect r = m_podium[i];
		r.y += (int)(( 1.0 - ease ) * H * .04f );
		DrawPodium( i, r );
	}
	UI::Scissor::PushScissor( m_clip.x, m_clip.y, m_clip.w, m_clip.h );
	for( int i = 0; i < ListCount(); i++ )
	{
		const CzmRect r = RowRect( i );
		if( r.y + r.h < m_clip.y || r.y > m_clip.y + m_clip.h ) continue;
		DrawRow( i, r );
	}
	UI::Scissor::PopScissor();
	if( m_maxScroll )
	{
		const int thumb = Q_max( 12, m_clip.h * m_clip.h / ( m_clip.h + m_maxScroll ));
		UI_FillRect( m_panel.x + m_panel.w - pad / 2, m_clip.y + ( m_clip.h - thumb ) * m_scroll / m_maxScroll, 3, thumb, CZM_White( 140 ));
	}
	DrawMe();
}

ADD_MENU3( menu_czmtop, CCzmTop, UI_CzmTop_Menu );

void UI_CzmTop_Menu( void )
{
	CZM_OpenTop();
}

void CZM_OpenTop( void )
{
	if( menu_czmtop ) menu_czmtop->Open();
}
