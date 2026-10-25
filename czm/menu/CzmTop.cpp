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
The service ranks players by the time the game was really connected to a game server (playtime.py).
The window is a compact sheet that grows with the board: the three first stand on a podium (empty
places stay visible as free pedestals), the rest are a plain list, and the player's own place is
pinned at the bottom, outside the hundred too. A tap on anyone opens the profile.
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

unsigned Fade( unsigned color, int alpha )
{
	return ( color & 0x00FFFFFF ) | ((unsigned)bound( 0, alpha, 255 ) << 24 );
}

double EaseOut( double t )
{
	t = bound( 0.0, t, 1.0 );
	return 1.0 - ( 1.0 - t ) * ( 1.0 - t ) * ( 1.0 - t );
}
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
	void DrawHeader();
	void DrawPodium( int i, double rise );
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
	CzmRect m_panel, m_back, m_refresh, m_stage, m_podium[3], m_clip, m_me;
	int W, H, pad, gap, rowH, m_avatar[3], m_base[3];
};

CCzmTop::CCzmTop() : CMenuFramework( "CzmTop" )
{
	m_open = m_loaded = m_failed = m_hasMe = m_drag = m_moved = false;
	m_count = m_players = m_mePlace = m_meSeconds = m_meBehind = 0;
	m_request = m_pressed = m_scroll = m_maxScroll = m_downScroll = m_downY = 0;
	m_nextLoad = m_openedAt = 0;
	memset( m_rows, 0, sizeof( m_rows ));
	W = H = pad = gap = rowH = 0;
	memset( m_avatar, 0, sizeof( m_avatar ));
	memset( m_base, 0, sizeof( m_base ));
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
		if( !m_loaded ) m_openedAt = EngFuncs::DoubleTime(); // the podium rises when there is something on it
		m_loaded = true;
		m_failed = false;
	}
	if( m_open && !m_request && EngFuncs::DoubleTime() >= m_nextLoad ) Load();
}

/*
 * layout: a sheet as tall as its content, centred on the screen
 */
CzmRect CCzmTop::RowRect( int i ) const
{
	return CZM_Rect( m_clip.x, m_clip.y + i * rowH - m_scroll, m_clip.w, rowH );
}

void CCzmTop::Layout()
{
	W = ScreenWidth; H = ScreenHeight;
	pad = Q_max( 10, (int)( H * .026f )); gap = Q_max( 6, (int)( H * .013f ));
	const int bh = Q_max( 32, (int)( H * .062f ));
	const int pw = Q_min( W - pad * 2, (int)( H * 1.2f )), inner = pw - pad * 2;
	const int nickH = CZM_FontHeight( CZM_Font( CZMF_UI_LABEL )), metaH = CZM_FontHeight( CZM_Font( CZMF_UI_META ));
	// the podium: the winner is bigger and stands higher; the second on the left, the third on the right
	m_avatar[0] = Q_max( 30, (int)( H * .112f ));
	m_avatar[1] = m_avatar[2] = Q_max( 24, (int)( H * .084f ));
	m_base[0] = Q_max( 22, (int)( H * .068f ));
	m_base[1] = m_base[0] * 72 / 100;
	m_base[2] = m_base[0] * 54 / 100;
	const int above = gap / 2 + metaH + 2 + nickH + gap / 3; // the time, the nick and the space under the picture
	int columnH[3];
	for( int i = 0; i < 3; i++ )
		columnH[i] = m_base[i] + above + m_avatar[i] + m_avatar[i] * ( i ? 30 : 36 ) / 100; // the crown peeks over the picture
	const int stageH = columnH[0] + gap / 2;
	rowH = Q_max( 30, (int)( H * .06f ));
	const int meH = Q_max( 38, (int)( H * .078f ));
	const int list = m_loaded ? ListCount() * rowH : 0;
	const int fixed = pad + bh + gap + stageH + gap + meH + pad + ( list ? gap : 0 );
	const int ph = Q_min( H - gap * 2, fixed + list );
	m_panel = CZM_Rect(( W - pw ) / 2, ( H - ph ) / 2, pw, ph );
	const int left = m_panel.x + pad;
	int y = m_panel.y + pad;
	m_back = CZM_Rect( left, y, bh, bh );
	m_refresh = CZM_Rect( left + inner - bh, y, bh, bh );
	y += bh + gap;
	const int stageW = Q_min( inner, (int)( H * .98f )), seam = Q_max( 2, gap / 3 );
	m_stage = CZM_Rect( left + ( inner - stageW ) / 2, y, stageW, stageH );
	const int columnW = ( stageW - seam * 2 ) / 3, floor = y + stageH;
	const int order[3] = { 1, 0, 2 };
	for( int k = 0; k < 3; k++ )
	{
		const int i = order[k];
		m_podium[i] = CZM_Rect( m_stage.x + k * ( columnW + seam ), floor - columnH[i], columnW, columnH[i] );
	}
	m_me = CZM_Rect( left, m_panel.y + ph - pad - meH, inner, meH );
	y = floor + gap;
	m_clip = CZM_Rect( left, y, inner, Q_max( 0, m_me.y - gap - y ));
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
	CzmStyle::Surface( r, pressed ? PackRGBA( 41, 51, 67, 255 ) : PackRGBA( 26, 31, 41, 255 ), PackRGBA( 46, 54, 68, 255 ), r.h / 2 );
	const int side = r.h * 44 / 100;
	CZM_DrawImage( icon, r.x + ( r.w - side ) / 2, r.y + ( r.h - side ) / 2, side, side, tint ? tint : CzmStyle::Ink() );
}

static void Picture( const char *image, int x, int y, int side, unsigned ring, bool online )
{
	CZM_DrawImage( image, x, y, side, side );
	const int line = Q_max( 2, side / 26 );
	CZM_DrawImage( UI_DIR "icon_ring.png", x - line, y - line, side + line * 2, side + line * 2, ring );
	if( online )
	{
		const int dot = Q_max( 6, side / 5 );
		CZM_DrawImage( UI_DIR "dot.png", x + side - dot, y + side - dot, dot, dot, PackRGBA( 15, 18, 24, 255 ));
		const int in = Q_max( 1, dot / 6 );
		CZM_DrawImage( UI_DIR "dot.png", x + side - dot + in, y + side - dot + in, dot - in * 2, dot - in * 2, PackRGBA( 66, 216, 137, 255 ));
	}
}

static const char *Players( int n )
{
	if( !CZM_IsRussian()) return n == 1 ? "player" : "players";
	const int d = n % 10, h = n % 100;
	return d == 1 && h != 11 ? "игрок" : d >= 2 && d <= 4 && ( h < 12 || h > 14 ) ? "игрока" : "игроков";
}

void CCzmTop::DrawHeader()
{
	using namespace CzmStyle;
	Chip( m_back, UI_DIR "icon_back.png", Pressed( BACK ));
	Chip( m_refresh, UI_DIR "icon_refresh.png", Pressed( REFRESH ), m_request ? Muted() : 0 );
	const HFont title = CZM_Font( CZMF_UI_TITLE ), meta = CZM_Font( CZMF_UI_META );
	const char *name = T( "Топ 100", "Top 100" );
	const int tx = m_back.x + m_back.w + gap, tw = m_refresh.x - gap - tx;
	const int titleW = Q_min( CZM_TextWidth( title, name ) + 2, tw );
	CZM_DrawText( title, tx, m_back.y + ( m_back.h - CZM_FontHeight( title )) / 2, titleW, name, Ink() );
	char line[96];
	if( m_loaded && m_players > 0 )
		snprintf( line, sizeof( line ), T( "по времени на серверах  ·  %d %s", "by time on servers  ·  %d %s" ), m_players, Players( m_players ));
	else
		Q_strncpy( line, T( "по времени на серверах", "by time on servers" ), sizeof( line ));
	CZM_DrawText( meta, tx + titleW + gap, m_back.y + ( m_back.h - CZM_FontHeight( meta )) / 2 + CZM_FontHeight( title ) / 10,
		tw - titleW - gap, line, Muted() );
}

// one place of the podium: a pedestal with its number and, standing on it, the player or a free spot
void CCzmTop::DrawPodium( int i, double rise )
{
	using namespace CzmStyle;
	const CzmRect &r = m_podium[i];
	const bool taken = i < m_count, down = taken && Pressed( PODIUM + i );
	const unsigned color = CZM_TopColor( i + 1 );
	const int floor = r.y + r.h, base = (int)( m_base[i] * rise ), top = floor - base;
	const int radius = Q_max( 3, H / 120 );
	// the pedestal lights up from its top edge
	const CzmRect block = CZM_Rect( r.x, top, r.w, base + radius );
	UI::Scissor::PushScissor( r.x, top, r.w, base );
	Round( block, taken ? Fade( color, down ? 62 : 34 ) : PackRGBA( 255, 255, 255, 9 ), radius );
	if( base > 0 )
		CZM_DrawImage( UI_DIR "fade_top.png", r.x, top, r.w, base, taken ? Fade( color, 70 ) : PackRGBA( 255, 255, 255, 12 ));
	UI::Scissor::PopScissor();
	if( base > 2 )
	{
		UI_FillRect( r.x + radius, top, r.w - radius * 2, Q_max( 2, H / 360 ), taken ? color : PackRGBA( 255, 255, 255, 34 ));
		// one size for all three numbers: the largest that fits the lowest pedestal
		const HFont number = CZM_Font( m_base[2] >= CZM_FontHeight( CZM_Font( CZMF_UI_ACTION )) ? CZMF_UI_ACTION : CZMF_UI_LABEL );
		char text[16];
		snprintf( text, sizeof( text ), "%d", i + 1 );
		UI::Scissor::PushScissor( r.x, top, r.w, base );
		CZM_DrawText( number, r.x, top + ( m_base[i] - CZM_FontHeight( number )) / 2, r.w, text,
			taken ? Fade( color, 235 ) : PackRGBA( 255, 255, 255, 60 ), QM_CENTER );
		UI::Scissor::PopScissor();
	}
	// the player rides up with the pedestal and fades in
	const int alpha = (int)( 255 * bound( 0.0, rise * 1.4 - 0.2, 1.0 ));
	if( alpha <= 0 ) return;
	const HFont label = CZM_Font( CZMF_UI_LABEL ), meta = CZM_Font( CZMF_UI_META );
	const int av = m_avatar[i], ax = r.x + ( r.w - av ) / 2;
	const int timeY = top - gap / 2 - CZM_FontHeight( meta ), nickY = timeY - 2 - CZM_FontHeight( label ), ay = nickY - gap / 3 - av;
	if( !taken )
	{
		Round( CZM_Rect( ax, ay, av, av ), PackRGBA( 255, 255, 255, alpha * 8 / 255 ), av / 2 );
		CZM_DrawImage( UI_DIR "icon_ring.png", ax, ay, av, av, PackRGBA( 255, 255, 255, alpha * 40 / 255 ));
		const int icon = av * 42 / 100;
		CZM_DrawImage( UI_DIR "icon_user.png", ax + ( av - icon ) / 2, ay + ( av - icon ) / 2, icon, icon, PackRGBA( 155, 166, 184, alpha * 90 / 255 ));
		CZM_DrawText( label, r.x + gap, nickY, r.w - gap * 2, T( "Свободно", "Free" ), Fade( Muted(), alpha * 150 / 255 ), QM_CENTER );
		return;
	}
	const TopRow &p = m_rows[i];
	if( i == 0 )
	{
		const double wave = 0.5 + 0.5 * sin( EngFuncs::DoubleTime() * 2.0 * M_PI / 2.8 );
		const int glow = av * 210 / 100;
		CZM_DrawImage( UI_DIR "glow.png", ax + ( av - glow ) / 2, ay + ( av - glow ) / 2, glow, glow, Fade( color, (int)(( 46 + 34 * wave ) * alpha / 255 )));
	}
	Picture( CZM_AvatarFor( p.avatar, p.id ), ax, ay, av, Fade( color, alpha ), p.online );
	const int crown = av * ( i ? 40 : 50 ) / 100;
	CZM_DrawImage( CZM_TopCrown( p.place ), ax + ( av - crown ) / 2, ay - crown * ( i ? 74 : 72 ) / 100, crown, crown, Fade( color, alpha ));
	{
		// the nick and, for the official account, its SUPPORT tag: one centred group
		const int tagH = Q_max( 12, CZM_FontHeight( meta ) + 4 ), tagW = p.support ? CZM_SupportTagWidth( tagH ) + gap / 2 : 0;
		const int nickW = Q_max( 0, Q_min( CZM_TextWidth( label, p.nick ) + 2, r.w - gap * 2 - tagW ));
		const int x = r.x + ( r.w - nickW - tagW ) / 2;
		CZM_DrawText( label, x, nickY, nickW, p.nick, Fade( Ink(), alpha ));
		if( p.support ) CZM_DrawSupportTag( x + nickW + gap / 2, nickY + ( CZM_FontHeight( label ) - tagH ) / 2, tagH );
	}
	char time[48];
	CZM_FormatPlaytime( p.seconds, time, sizeof( time ));
	CZM_DrawText( meta, r.x + gap, timeY, r.w - gap * 2, time, Fade( color, alpha * 220 / 255 ), QM_CENTER );
}

void CCzmTop::DrawRow( int i, const CzmRect &r )
{
	using namespace CzmStyle;
	const TopRow &p = m_rows[3 + i];
	const unsigned color = CZM_TopColor( p.place );
	const bool mine = p.id == CZM_OnlinePlayer(), down = Pressed( ROW + i );
	const int inset = Q_max( 2, rowH / 14 ), radius = Q_max( 3, rowH / 4 );
	const CzmRect band = CZM_Rect( r.x, r.y + inset / 2, r.w, r.h - inset );
	if( down || mine || i % 2 == 0 )
		Round( band, down ? PackRGBA( 255, 255, 255, 22 ) : mine ? PackRGBA( 229, 63, 77, 34 ) : PackRGBA( 255, 255, 255, 6 ), radius );
	if( mine ) UI_FillRect( band.x, band.y + radius, Q_max( 2, H / 360 ), band.h - radius * 2, AccentRed());
	const HFont label = CZM_Font( CZMF_UI_LABEL ), meta = CZM_Font( CZMF_UI_META );
	const int placeW = CZM_TextWidth( label, "100" ) + gap * 2, mid = band.y + band.h / 2;
	char text[48];
	snprintf( text, sizeof( text ), "%d", p.place );
	CZM_DrawText( label, band.x + gap / 2, mid - CZM_FontHeight( label ) / 2, placeW - gap, text, color, QM_CENTER );
	const int av = band.h - inset * 2, ax = band.x + placeW, ay = band.y + inset;
	Picture( CZM_AvatarFor( p.avatar, p.id ), ax, ay, av, Fade( color, 150 ), p.online );
	CZM_FormatPlaytime( p.seconds, text, sizeof( text ));
	const int timeW = CZM_TextWidth( label, text ) + 2, right = band.x + band.w - gap;
	CZM_DrawText( label, right - timeW, mid - CZM_FontHeight( label ) / 2, timeW, text, Ink() );
	const int x = ax + av + gap, tagH = Q_max( 12, CZM_FontHeight( meta ) + 4 );
	const int tagW = p.support ? CZM_SupportTagWidth( tagH ) + gap / 2 : 0;
	const int nickW = Q_max( 0, Q_min( CZM_TextWidth( label, p.nick ) + 2, right - timeW - gap * 2 - x - tagW ));
	CZM_DrawText( label, x, mid - CZM_FontHeight( label ) / 2, nickW, p.nick, Ink() );
	if( p.support && nickW > 0 ) CZM_DrawSupportTag( x + nickW + gap / 2, mid - tagH / 2, tagH );
}

// the own place, always at the bottom: a calm strip, not a warning
void CCzmTop::DrawMe()
{
	using namespace CzmStyle;
	const bool down = Pressed( ME ), ranked = m_hasMe && m_mePlace > 0, inTop = ranked && m_mePlace <= 100;
	const int radius = Q_max( 4, m_me.h / 4 );
	Round( m_me, down ? PackRGBA( 36, 43, 56, 255 ) : PackRGBA( 25, 30, 40, 255 ), radius );
	if( !m_loaded ) return;
	const unsigned color = inTop ? CZM_TopColor( m_mePlace ) : Muted();
	if( inTop ) UI_FillRect( m_me.x, m_me.y + radius, Q_max( 2, H / 360 ), m_me.h - radius * 2, color );
	const HFont label = CZM_Font( CZMF_UI_LABEL ), meta = CZM_Font( CZMF_UI_META );
	const int inset = Q_max( 5, m_me.h / 6 ), av = m_me.h - inset * 2, ax = m_me.x + inset + gap / 2;
	Picture( CZM_CurrentAvatarImage(), ax, m_me.y + inset, av, inTop ? color : PackRGBA( 70, 80, 98, 255 ), false );
	// the arrow says the strip opens the own profile
	const int arrowW = CZM_TextWidth( label, "›" ) + gap, right = m_me.x + m_me.w - gap;
	CZM_DrawText( label, right - arrowW, m_me.y + ( m_me.h - CZM_FontHeight( label )) / 2, arrowW, "›", Muted(), QM_CENTER );
	const int tagH = Q_max( 12, CZM_FontHeight( meta ) + 4 ), tagW = inTop ? CZM_TopTagWidth( m_mePlace, tagH ) : 0;
	if( tagW ) CZM_DrawTopTag( right - arrowW - gap / 2 - tagW, m_me.y + ( m_me.h - tagH ) / 2, tagH, m_mePlace );
	const int x = ax + av + gap, w = right - arrowW - ( tagW ? tagW + gap : 0 ) - gap / 2 - x;
	const int lh = CZM_FontHeight( label ), mh = CZM_FontHeight( meta ), top = m_me.y + ( m_me.h - lh - mh - 2 ) / 2;
	char line[160], time[48];
	if( !ranked )
	{
		CZM_DrawText( label, x, top, w, T( "Вас пока нет в рейтинге", "You are not on the board yet" ), Ink() );
		CZM_DrawText( meta, x, top + lh + 2, w, T( "Время идёт, пока вы играете на сервере", "Time counts while you play on a server" ), Muted() );
		return;
	}
	const char *head = T( "Ваше место", "Your place" );
	const int headW = Q_min( CZM_TextWidth( label, head ) + 2, w );
	CZM_DrawText( label, x, top, headW, head, Ink() );
	snprintf( line, sizeof( line ), "%d", m_mePlace );
	CZM_DrawText( label, x + headW + gap / 2, top, Q_max( 0, w - headW - gap / 2 ), line, inTop ? color : Ink() );
	CZM_FormatPlaytime( m_meSeconds, time, sizeof( time ));
	if( m_mePlace > 100 && m_meBehind > 0 )
	{
		char behind[48];
		CZM_FormatPlaytime( m_meBehind, behind, sizeof( behind ));
		snprintf( line, sizeof( line ), T( "%s на серверах  ·  до 100-го места %s", "%s on servers  ·  %s to the 100th place" ), time, behind );
	}
	else
		snprintf( line, sizeof( line ), T( "%s на серверах", "%s on servers" ), time );
	CZM_DrawText( meta, x, top + lh + 2, w, line, Muted() );
}

void CCzmTop::Draw()
{
	Poll();
	if( !m_open ) return;
	Layout();
	using namespace CzmStyle;
	UI_FillRect( 0, 0, W, H, PackRGBA( 0, 0, 0, 170 ));
	Surface( m_panel, PackRGBA( 15, 18, 24, 252 ), PackRGBA( 46, 53, 66, 255 ), Q_max( 8, (int)( H * .028f )));
	// a warm light over the podium
	{
		const int gw = m_stage.w * 110 / 100, gh = m_stage.h * 150 / 100;
		CZM_DrawImage( UI_DIR "glow.png", m_stage.x + ( m_stage.w - gw ) / 2, m_stage.y - gh / 3, gw, gh, PackRGBA( 255, 196, 84, 20 ));
	}
	DrawHeader();
	if( !m_loaded )
	{
		const char *text = m_failed ? T( "Нет связи. Нажмите обновить", "No connection. Tap refresh" ) : T( "Загружаем…", "Loading…" );
		Text( m_stage, text, CZMF_PANEL_TEXT, Muted(), QM_CENTER );
		DrawMe();
		return;
	}
	// the pedestals grow one after another when the board arrives: the third, the second, the winner
	const double since = EngFuncs::DoubleTime() - m_openedAt;
	const double delay[3] = { 0.16, 0.08, 0.0 };
	for( int i = 0; i < 3; i++ )
		DrawPodium( i, EaseOut(( since - delay[i] ) / 0.34 ));
	UI_FillRect( m_stage.x, m_stage.y + m_stage.h - gap / 2, m_stage.w, 1, PackRGBA( 255, 255, 255, 16 ));
	if( ListCount())
	{
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
			UI_FillRect( m_panel.x + m_panel.w - pad / 2, m_clip.y + ( m_clip.h - thumb ) * m_scroll / m_maxScroll, 3, thumb, CZM_White( 110 ));
		}
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
