/*
CzmMapVote.cpp -- the next-map vote window of our servers. GPL-3.0-or-later.

czm_mapvote.amxx (1.1.0) asks clients for czm_mapvote_ui; ours answer 1 and get the whole
ballot in CzmVote messages instead of a numbered menu. The HUD keeps it in the czm_vote cvar
(common/czm_vote.h). Every map of the server with its picture, most votes first: a tap shows
a map on the right, the red button votes for it. A map keeps its number for the whole vote,
so a list that moves under the finger never turns a tap into a vote for another map.
The list scrolls like our server list (common/czm_scroll.h): it follows the finger without
a jump, keeps a flick going, never reorders under the finger and lets rows glide to new places.
*/

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "extdll_menu.h"
#include "BaseMenu.h"
#include "BaseClientWindow.h"
#include "keydefs.h"
#include "CzmMenu.h"
#include "CzmDesign.h"
#include "Scissor.h"
#include "../../common/czm_vote.h"
#include "../../common/czm_scroll.h"

#define UI_DIR "gfx/czm/ui/"

class CCzmVoteWindow : public CMenuBaseClientWindow
{
public:
	typedef CMenuBaseClientWindow BaseClass;
	CCzmVoteWindow();

	void Open( const CzmVote::Ballot &ballot );
	void Update( const CzmVote::Ballot &ballot );
	void Close( void );

	void Show() override;
	void Hide() override;
	void Draw() override;
	bool KeyDown( int key ) override;
	bool KeyUp( int key ) override;
	bool MouseMove( int x, int y ) override;

private:
	// rows are hit by their map number: HIT_ROW + number
	enum { HIT_NONE = 0, HIT_CLOSE, HIT_VOTE, HIT_BAR, HIT_ROW = 1000 };

	void Layout( int shift );
	int HitTest( void ) const;
	bool IsPressed( int hit ) const { return m_pressed == hit && !m_scroller.dragging && HitTest() == hit; }
	void Activate( int hit );
	void Vote( void );
	void Step( int direction );
	void RevealSelected( void );
	void TakeOrder( void );
	int ViewIndex( int number ) const;
	void BarTo( int y );
	bool Sending( void ) const;
	int Seconds( void ) const;
	int RowStep( void ) const { return m_rowH + m_gap; }
	CzmRect RowRect( int number ) const;
	void DrawRow( int number, int a );
	void DrawPreview( int a );

	CzmVote::Ballot m_ballot;
	int m_view[CzmVote::MAX_ROWS], m_viewCount; // the order shown: kept while a finger is on the list
	float m_glide[256];                          // where each map's row is drawn, in rows
	bool m_placed[256];
	bool m_orderWaiting, m_revealWaiting;
	CzmScroll::List m_scroller;
	double m_lastFrame;

	int m_selected;              // the map number shown on the right
	int m_sent, m_sentTime;      // a vote on its way to the server
	int m_receivedAt;            // when m_ballot.seconds was the server's
	int m_openTime, m_pressed;
	bool m_closing, m_barDrag;
	int m_barGrab;
	int W, H, m_rowH, m_gap;
	CzmRect m_win, m_close, m_list, m_bar, m_barHit, m_thumb, m_shot, m_stats, m_vote, m_foot;
	int m_pad, m_titleY, m_subY;
};

CCzmVoteWindow::CCzmVoteWindow() : BaseClass( "CzmVoteWindow" )
{
	m_viewCount = 0;
	memset( m_view, 0, sizeof( m_view ));
	memset( m_glide, 0, sizeof( m_glide ));
	memset( m_placed, 0, sizeof( m_placed ));
	m_orderWaiting = m_revealWaiting = false;
	m_lastFrame = 0;
	m_selected = m_sent = -1;
	m_sentTime = m_receivedAt = m_openTime = 0;
	m_pressed = HIT_NONE;
	m_closing = m_barDrag = false;
	m_barGrab = 0;
	W = H = m_rowH = m_gap = m_pad = m_titleY = m_subY = 0;
	memset( &m_win, 0, sizeof( m_win ));
	m_close = m_list = m_bar = m_barHit = m_thumb = m_shot = m_stats = m_vote = m_foot = m_win;
}

// The shown order follows the ballot; maps new to the list appear in place, the rest glide.
void CCzmVoteWindow::TakeOrder( void )
{
	m_viewCount = m_ballot.count;
	for( int i = 0; i < m_viewCount; i++ )
	{
		const int number = m_ballot.rows[i].number & 255;
		m_view[i] = number;
		if( !m_placed[number] ) { m_glide[number] = i; m_placed[number] = true; }
	}
	m_orderWaiting = false;
}

int CCzmVoteWindow::ViewIndex( int number ) const
{
	for( int i = 0; i < m_viewCount; i++ )
		if( m_view[i] == number ) return i;
	return -1;
}

void CCzmVoteWindow::Open( const CzmVote::Ballot &ballot )
{
	m_ballot = ballot;
	m_receivedAt = m_openTime = uiStatic.realTime;
	m_lastFrame = EngFuncs::DoubleTime();
	m_selected = ballot.own >= 0 && CzmVote::Find( ballot, ballot.own ) >= 0 ? ballot.own : ballot.rows[0].number;
	m_sent = -1;
	m_pressed = HIT_NONE;
	m_closing = m_barDrag = false;
	m_scroller = CzmScroll::List();
	memset( m_placed, 0, sizeof( m_placed ));
	TakeOrder();
	CZM_KeepClientMenu( this );
	Show();
	Layout( 0 );
	// the own vote or the first map, already in view when the window appears
	const int index = ViewIndex( m_selected );
	if( index >= 0 )
	{
		m_scroller.Reveal( index * RowStep(), index * RowStep() + m_rowH, m_list.h );
		if( m_scroller.aiming ) { m_scroller.pos = m_scroller.target; m_scroller.aiming = false; }
	}
}

void CCzmVoteWindow::Update( const CzmVote::Ballot &ballot )
{
	const int ownBefore = m_ballot.own;
	m_ballot = ballot;
	m_receivedAt = uiStatic.realTime;
	if( CzmVote::Find( m_ballot, m_selected ) < 0 )
		m_selected = m_ballot.rows[0].number;
	if( m_sent >= 0 && m_ballot.own == m_sent )
		m_sent = -1;
	// never reorder under the finger: the new order waits until it lifts
	m_orderWaiting = true;
	// the map just voted for rises: the list follows it
	if( m_ballot.own != ownBefore && m_ballot.own == m_selected )
		m_revealWaiting = true;
}

void CCzmVoteWindow::Close( void )
{
	Hide();
}

void CCzmVoteWindow::Show()
{
	EngFuncs::KEY_SetDest( KEY_MENU );
	EngFuncs::ClientCmd( true, "touch_setclientonly 1" );
	BaseClass::Show();
}

// the stock way, on the next frame, like our other windows over the game
void CCzmVoteWindow::Hide()
{
	if( m_closing )
		return;
	m_closing = true;
	CZM_CloseClientMenuSoon( this );
}

bool CCzmVoteWindow::Sending( void ) const
{
	return m_sent >= 0 && m_ballot.own != m_sent && uiStatic.realTime - m_sentTime < 1500;
}

int CCzmVoteWindow::Seconds( void ) const
{
	return Q_max( 0, m_ballot.seconds - ( uiStatic.realTime - m_receivedAt ) / 1000 );
}

void CCzmVoteWindow::Layout( int shift )
{
	W = ScreenWidth; H = ScreenHeight;
	const int winW = Q_min( (int)( W * .94f ), (int)( H * 1.82f )), winH = H * .90f;
	m_win = CZM_Rect(( W - winW ) / 2, ( H - winH ) / 2 + shift, winW, winH );
	m_pad = Q_max( 8, (int)( H * .040f ));
	const int top = m_win.y + H * .034f;
	const int metaH = CZM_FontHeight( CZM_Font( CZMF_UI_META )), titleH = CZM_FontHeight( CZM_Font( CZMF_UI_TITLE ));
	const int side = H * .062f;
	m_close = CZM_Rect( m_win.x + m_win.w - m_pad * 9 / 10 - side, m_win.y + H * .032f, side, side );
	m_titleY = top + metaH + H * .010f;
	m_subY = m_titleY + titleH + H * .008f;
	const int bodyY = m_subY + metaH + H * .028f, bodyH = m_win.y + m_win.h - m_pad * 8 / 10 - bodyY;
	const int inner = m_win.w - m_pad * 2, listW = inner * .47f, gap = H * .038f;

	m_rowH = Q_max( 24, (int)( H * .111f ));
	m_gap = Q_max( 3, (int)( H * .015f ));
	const int barW = Q_max( 3, (int)( H * .007f ));
	m_bar = CZM_Rect( m_win.x + m_pad + listW - barW, bodyY, barW, bodyH );
	m_list = CZM_Rect( m_win.x + m_pad, bodyY, listW - barW - H * .016f, bodyH );
	// the slider is taken from the gap beside the list, never from the rows
	const int barLeft = m_list.x + m_list.w + 1;
	m_barHit = CZM_Rect( barLeft, bodyY, m_bar.x + m_bar.w + H * .018f - barLeft, bodyH );
	const int content = m_viewCount * RowStep() - m_gap;
	m_scroller.slop = Q_max( 6, (int)( H * .022f ));
	m_scroller.SetMax( (float)( content - m_list.h ));
	if( m_scroller.max > 0 )
	{
		const int thumbH = Q_max( (int)( H * .06f ), m_bar.h * m_list.h / Q_max( 1, content ));
		m_thumb = CZM_Rect( m_bar.x, m_bar.y + (int)(( m_bar.h - thumbH ) * m_scroller.pos / m_scroller.max ), m_bar.w, thumbH );
	}
	else m_thumb = CZM_Rect( 0, 0, 0, 0 );

	const int px = m_win.x + m_pad + listW + gap, pw = m_win.x + m_win.w - m_pad - px;
	const int footH = metaH, voteH = Q_max( 24, (int)( H * .098f )), statsH = Q_max( metaH, (int)( H * .045f ));
	m_foot = CZM_Rect( px, bodyY + bodyH - footH, pw, footH );
	m_vote = CZM_Rect( px, m_foot.y - H * .012f - voteH, pw, voteH );
	const int shotH = Q_max( 1, m_vote.y - H * .022f - statsH - H * .018f - bodyY );
	m_shot = CZM_Rect( px, bodyY, pw, shotH );
	m_stats = CZM_Rect( px, m_shot.y + m_shot.h + H * .018f, pw, statsH );
}

CzmRect CCzmVoteWindow::RowRect( int number ) const
{
	return CZM_Rect( m_list.x, m_list.y + (int)( m_glide[number & 255] * RowStep() - m_scroller.pos ), m_list.w, m_rowH );
}

int CCzmVoteWindow::HitTest( void ) const
{
	const int x = uiStatic.cursorX, y = uiStatic.cursorY;
	if( m_close.Grown( H / 80 ).Contains( x, y )) return HIT_CLOSE;
	if( m_vote.Contains( x, y )) return HIT_VOTE;
	if( m_scroller.max > 0 && m_barHit.Contains( x, y )) return HIT_BAR;
	if( !m_list.Contains( x, y )) return HIT_NONE;
	// the row drawn last is on top while rows glide past each other
	for( int i = m_viewCount - 1; i >= 0; i-- )
		if( RowRect( m_view[i] ).Contains( x, y ))
			return HIT_ROW + m_view[i];
	return HIT_NONE;
}

void CCzmVoteWindow::RevealSelected( void )
{
	const int index = ViewIndex( m_selected );
	if( index >= 0 )
		m_scroller.Reveal( index * RowStep(), index * RowStep() + m_rowH, m_list.h );
}

void CCzmVoteWindow::BarTo( int y )
{
	if( m_scroller.max <= 0 ) return;
	const int travel = Q_max( 1, m_bar.h - m_thumb.h );
	m_scroller.velocity = 0;
	m_scroller.aiming = false;
	m_scroller.pos = m_scroller.Bound( (float)( y - m_barGrab - m_bar.y ) * m_scroller.max / travel );
}

void CCzmVoteWindow::Vote( void )
{
	if( CzmVote::Find( m_ballot, m_selected ) < 0 || m_selected == m_ballot.own || Seconds() <= 0
		|| ( Sending() && m_sent == m_selected ))
		return;
	CZM_PlayClick();
	m_sent = m_selected;
	m_sentTime = uiStatic.realTime;
	EngFuncs::ClientCmdF( false, "czm_vote_map %d\n", m_selected );
}

void CCzmVoteWindow::Step( int direction )
{
	const int index = bound( 0, ViewIndex( m_selected ) + direction, m_viewCount - 1 );
	if( index < 0 || index >= m_viewCount ) return;
	m_selected = m_view[index];
	RevealSelected();
}

void CCzmVoteWindow::Activate( int hit )
{
	if( hit == HIT_CLOSE ) { CZM_PlayClick(); Close(); return; }
	if( hit == HIT_VOTE ) { Vote(); return; }
	if( hit >= HIT_ROW && CzmVote::Find( m_ballot, hit - HIT_ROW ) >= 0 )
	{
		CZM_PlayClick();
		m_selected = hit - HIT_ROW;
		RevealSelected();
	}
}

bool CCzmVoteWindow::KeyDown( int key )
{
	if( UI::Key::IsEscape( key )) { Close(); return true; }
	if( UI::Key::IsEnter( key )) { Vote(); return true; }
	if( key == K_UPARROW || key == K_DOWNARROW ) { Step( key == K_UPARROW ? -1 : 1 ); return true; }
	if( key == K_MWHEELUP || key == K_MWHEELDOWN )
	{
		m_scroller.Wheel(( key == K_MWHEELUP ? -1 : 1 ) * RowStep());
		return true;
	}
	if( UI::Key::IsLeftMouse( key ))
	{
		m_pressed = HitTest();
		m_barDrag = m_pressed == HIT_BAR;
		if( m_barDrag )
		{
			// a finger on the thumb keeps its grip; elsewhere on the track the thumb comes to it
			const int y = uiStatic.cursorY;
			m_barGrab = y >= m_thumb.y && y < m_thumb.y + m_thumb.h ? y - m_thumb.y : m_thumb.h / 2;
			BarTo( y );
		}
		else if( m_list.Contains( uiStatic.cursorX, uiStatic.cursorY ))
			m_scroller.Press( (float)uiStatic.cursorY, EngFuncs::DoubleTime());
	}
	return true;
}

bool CCzmVoteWindow::KeyUp( int key )
{
	if( UI::Key::IsLeftMouse( key ))
	{
		const int pressed = m_pressed;
		bool tap = !m_barDrag;
		if( m_scroller.down )
			tap = m_scroller.Release( EngFuncs::DoubleTime()) && tap;
		const int hit = HitTest();
		m_pressed = HIT_NONE;
		m_barDrag = false;
		if( tap && hit == pressed && hit != HIT_NONE && hit != HIT_BAR )
			Activate( hit );
	}
	return true;
}

bool CCzmVoteWindow::MouseMove( int x, int y )
{
	BaseClass::MouseMove( x, y );
	if( m_barDrag ) BarTo( uiStatic.cursorY );
	else if( m_scroller.down )
	{
		m_scroller.Move( (float)uiStatic.cursorY, EngFuncs::DoubleTime());
		if( m_scroller.dragging ) m_pressed = HIT_NONE;
	}
	return true;
}

static int MostVotes( const CzmVote::Ballot &b )
{
	int most = 0;
	for( int i = 0; i < b.count; i++ ) most = Q_max( most, b.rows[i].votes );
	return most;
}

void CCzmVoteWindow::DrawRow( int number, int a )
{
	const int row = CzmVote::Find( m_ballot, number );
	if( row < 0 ) return;
	const CzmVote::Row &r = m_ballot.rows[row];
	const CzmRect card = RowRect( number );
	if( card.y + card.h <= m_list.y || card.y >= m_list.y + m_list.h ) return;
	const bool ru = CZM_IsRussian(), own = r.number == m_ballot.own, selected = r.number == m_selected;
	const bool pressed = IsPressed( HIT_ROW + number );
	CzmStyle::Surface( card, selected ? PackRGBA( 34, 23, 29, a ) : pressed ? PackRGBA( 30, 39, 52, a ) : PackRGBA( 24, 32, 43, a ),
		selected ? PackRGBA( 229, 63, 77, a ) : PackRGBA( 40, 49, 64, a ), Q_max( 4, H / 60 ));

	const int inset = Q_max( 3, (int)( H * .011f ));
	const int picH = card.h - inset * 2, picW = Q_min( (int)( picH * 2.26f ), card.w * 36 / 100 );
	const CzmRect pic = CZM_Rect( card.x + inset, card.y + inset, picW, picH );
	const int top = Q_max( pic.y, m_list.y ), bottom = Q_min( pic.y + pic.h, m_list.y + m_list.h );
	// A photo is clipped by the list; the placeholder of a missing one is a fill, so a row
	// half out of the list gets it only inside the list.
	if( CZM_MapPreview( r.map ) || ( top == pic.y && bottom == pic.y + pic.h )) CzmStyle::MapPreview( pic, r.map );
	else if( bottom > top ) CzmStyle::MapPreview( CZM_Rect( pic.x, top, pic.w, bottom - top ), r.map );

	char votes[16];
	snprintf( votes, sizeof( votes ), "%d", r.votes );
	const HFont badgeFont = CZM_Font( CZMF_UI_LABEL );
	const int badgeH = Q_max( 12, (int)( H * .047f )), badgeW = Q_max( (int)( H * .058f ), CZM_TextWidth( badgeFont, votes ) + badgeH * 2 / 3 );
	const CzmRect badge = CZM_Rect( card.x + card.w - H * .024f - badgeW, card.y + ( card.h - badgeH ) / 2, badgeW, badgeH );
	const int most = MostVotes( m_ballot );
	const bool hot = r.votes > 0 && r.votes * 2 >= most;
	CzmStyle::Round( badge, hot ? PackRGBA( 255, 211, 107, a ) : PackRGBA( 35, 44, 57, a ), badgeH / 2 );
	CzmStyle::Text( badge, votes, CZMF_UI_LABEL, hot ? PackRGBA( 27, 20, 4, a ) : PackRGBA( 199, 208, 220, a ), QM_CENTER );

	const int tx = card.x + inset + picW + H * .024f, tw = badge.x - tx - H * .016f;
	const HFont name = CZM_Font( CZMF_UI_LABEL ), meta = CZM_Font( CZMF_UI_META );
	const int nameH = CZM_FontHeight( name ), metaH = CZM_FontHeight( meta ), gap = H * .004f;
	const int ty = card.y + ( card.h - nameH - gap - metaH ) / 2;
	CZM_DrawText( name, tx, ty, tw, r.map, CZM_White( a ));
	const char *note = own ? ( ru ? "✓ Твой голос" : "✓ Your vote" ) : selected ? ( ru ? "Смотришь сейчас" : "Viewing now" ) : "";
	if( note[0] )
		CZM_DrawText( meta, tx, ty + nameH + gap, tw, note, own ? PackRGBA( 70, 217, 139, a ) : PackRGBA( 163, 174, 189, a ));
}

void CCzmVoteWindow::DrawPreview( int a )
{
	const bool ru = CZM_IsRussian();
	const int row = CzmVote::Find( m_ballot, m_selected );
	if( row < 0 ) return;
	const CzmVote::Row &r = m_ballot.rows[row];

	CzmStyle::Surface( m_shot, PackRGBA( 12, 16, 22, a ), PackRGBA( 49, 59, 75, a ), Q_max( 4, H / 52 ));
	const int line = Q_max( 1, H / 450 );
	const CzmRect photo = CZM_Rect( m_shot.x + line, m_shot.y + line, m_shot.w - line * 2, m_shot.h - line * 2 );
	CzmStyle::MapPreview( photo, r.map );
	const HFont title = CZM_Font( CZMF_UI_TITLE );
	const int capH = CZM_FontHeight( title ) + H * .045f;
	// a dark caption over the bottom of the picture, darker towards the edge
	for( int i = 0; i < 4; i++ )
		UI_FillRect( photo.x, photo.y + photo.h - capH * ( 4 - i ) / 4, photo.w, capH * ( 4 - i ) / 4, PackRGBA( 6, 9, 14, a * ( 40 + i * 30 ) / 255 ));
	CZM_DrawText( title, photo.x + H * .026f, photo.y + photo.h - capH + ( capH - CZM_FontHeight( title )) / 2, photo.w - H * .052f, r.map, CZM_White( a ));

	char votes[48], voted[64];
	snprintf( votes, sizeof( votes ), ru ? "Голосов: %d" : "Votes: %d", r.votes );
	snprintf( voted, sizeof( voted ), ru ? "Проголосовало: %d из %d" : "Voted: %d of %d", m_ballot.voters, Q_max( m_ballot.voters, m_ballot.players ));
	const HFont meta = CZM_Font( CZMF_UI_META );
	const int ty = m_stats.y + ( m_stats.h - CZM_FontHeight( meta )) / 2;
	CZM_DrawText( meta, m_stats.x, ty, m_stats.w / 2, votes, PackRGBA( 163, 174, 189, a ));
	CZM_DrawText( meta, m_stats.x + CZM_TextWidth( meta, votes ) + H * .045f, ty, m_stats.w / 2, voted, PackRGBA( 163, 174, 189, a ));

	char label[96];
	const bool own = r.number == m_ballot.own, sending = Sending() && m_sent == r.number, over = Seconds() <= 0;
	if( own ) snprintf( label, sizeof( label ), ru ? "✓ Твой голос за %s" : "✓ You voted for %s", r.map );
	else if( sending ) snprintf( label, sizeof( label ), "%s", ru ? "Отправляем голос…" : "Sending your vote…" );
	else snprintf( label, sizeof( label ), ru ? "Голосовать за %s" : "Vote for %s", r.map );
	const bool active = !own && !sending && !over;
	const bool pressed = IsPressed( HIT_VOTE ) && active;
	const unsigned fill = !active ? PackRGBA( 26, 33, 44, a ) : pressed ? PackRGBA( 170, 30, 38, a ) : PackRGBA( 217, 37, 46, a );
	CzmStyle::Surface( m_vote, fill, own ? PackRGBA( 70, 217, 139, a ) : active ? PackRGBA( 229, 63, 77, a ) : PackRGBA( 51, 62, 78, a ), m_vote.h / 2 );
	CzmStyle::Text( CZM_Rect( m_vote.x + m_vote.h / 3, m_vote.y, m_vote.w - m_vote.h * 2 / 3, m_vote.h ), label, CZMF_UI_ACTION,
		own ? PackRGBA( 70, 217, 139, a ) : active ? CZM_White( a ) : PackRGBA( 155, 166, 184, a ), QM_CENTER );

	CZM_DrawText( meta, m_foot.x, m_foot.y, m_foot.w, ru ? "Окно можно закрыть: /votemap откроет его снова"
		: "You can close this window: /votemap opens it again", PackRGBA( 130, 143, 161, a ), QM_CENTER );
}

void CCzmVoteWindow::Draw()
{
	if( m_closing )
		return;
	if( !CL_IsActive() ) { Close(); return; }
	const float t = Q_min( 1.0f, ( uiStatic.realTime - m_openTime ) / 170.0f ), ease = 1 - ( 1 - t ) * ( 1 - t );
	const int a = 255 * ease;
	const double now = EngFuncs::DoubleTime(), dt = now - m_lastFrame;
	m_lastFrame = now;
	// the list moves only between touches: a new order, then the voted map into view
	if( !m_scroller.down && !m_barDrag )
	{
		if( m_orderWaiting ) TakeOrder();
		Layout( 0 );
		if( m_revealWaiting ) { RevealSelected(); m_revealWaiting = false; }
	}
	for( int i = 0; i < m_viewCount; i++ )
		m_glide[m_view[i]] = CzmScroll::Glide( m_glide[m_view[i]], (float)i, dt );
	m_scroller.Step( dt );
	Layout(( 1 - ease ) * H * .025f );
	UI_FillRect( 0, 0, ScreenWidth, ScreenHeight, PackRGBA( 3, 5, 9, a * 165 / 255 ));
	CzmStyle::Surface( m_win, PackRGBA( 18, 24, 33, a ), PackRGBA( 43, 52, 66, a ), Q_max( 6, H / 34 ));
	UI_FillRect( m_win.x + m_pad, m_win.y, Q_max( 1, (int)( m_win.w * .13f )), Q_max( 2, H / 240 ), PackRGBA( 229, 63, 77, a ));

	const bool ru = CZM_IsRussian();
	const HFont meta = CZM_Font( CZMF_UI_META ), title = CZM_Font( CZMF_UI_TITLE );
	CZM_DrawText( meta, m_win.x + m_pad, m_win.y + H * .034f, m_win.w / 2, CZM_OnSurvivalServer() ? "CZM | SURVIVAL" : "CZM | SERVER",
		PackRGBA( 229, 63, 77, a ));
	char clock[16];
	CzmVote::Clock( Seconds(), clock, sizeof( clock ));
	const int clockW = CZM_TextWidth( title, "0:00" ) + 4, clockX = m_close.x - H * .035f - clockW;
	CZM_DrawText( title, clockX, m_titleY, clockW, clock, PackRGBA( 255, 211, 107, a ), QM_RIGHT );
	CZM_DrawText( title, m_win.x + m_pad, m_titleY, clockX - m_win.x - m_pad - H * .02f,
		ru ? "Голосование за следующую карту" : "Vote for the next map", CZM_White( a ));
	CZM_DrawText( meta, m_win.x + m_pad, m_subY, m_close.x - m_win.x - m_pad,
		ru ? "Нажми на карту, чтобы посмотреть её, и проголосуй. Голос можно поменять до конца."
		   : "Tap a map to look at it, then vote. You can change your vote until the end.", PackRGBA( 163, 174, 189, a ));
	CzmStyle::Surface( m_close, PackRGBA( 27, 34, 44, a ), IsPressed( HIT_CLOSE ) ? PackRGBA( 229, 63, 77, a ) : PackRGBA( 43, 52, 66, a ), H / 80 );
	const int icon = m_close.w * .42f;
	CZM_DrawImage( UI_DIR "icon_close.png", m_close.x + ( m_close.w - icon ) / 2, m_close.y + ( m_close.h - icon ) / 2, icon, icon, CZM_White( a ));

	UI::Scissor::PushScissor( m_list.x, m_list.y, m_list.w, m_list.h );
	for( int i = 0; i < m_viewCount; i++ )
		DrawRow( m_view[i], a );
	UI::Scissor::PopScissor();
	if( m_scroller.max > 0 )
	{
		CzmStyle::Round( m_bar, PackRGBA( 35, 44, 57, a ), m_bar.w / 2 );
		CzmStyle::Round( m_thumb, m_barDrag ? PackRGBA( 229, 63, 77, a ) : PackRGBA( 155, 166, 184, a ), m_thumb.w / 2 );
	}
	DrawPreview( a );
}

ADD_MENU3( menu_czmvote, CCzmVoteWindow, UI_CzmVote_Menu );

void UI_CzmVote_Menu( void )
{
}

/*
Each frame: the window follows the ballot. It opens by itself once for a new vote (when the
player's popup setting allows) and again whenever the player asks for it with /votemap; it
waits while another of our windows or the main menu is in front.
*/
void CZM_VoteFrame( void )
{
	static CzmVote::Opening opening;
	static CzmVote::Ballot ballot;
	static char last[CzmVote::MAX_ROWS * 48 + 128];
	static bool has, pending;
	if( !menu_czmvote )
		return;
	const char *value = EngFuncs::GetCvarString( "czm_vote" );
	if( !value ) value = "";
	const bool changed = strncmp( value, last, sizeof( last ) - 1 ) != 0;
	if( changed )
	{
		Q_strncpy( last, value, sizeof( last ));
		has = CzmVote::Parse( value, ballot );
		if( has && opening.Next( ballot )) pending = true;
	}
	const bool open = CZM_ClientMenuOpen( menu_czmvote );
	if( !has || !CL_IsActive() )
	{
		pending = false;
		if( open ) menu_czmvote->Close();
		return;
	}
	if( open )
	{
		if( changed ) menu_czmvote->Update( ballot );
		pending = false;
		return;
	}
	if( pending && !uiStatic.menu.IsActive() && !uiStatic.client.IsActive() )
	{
		pending = false;
		menu_czmvote->Open( ballot );
	}
}
