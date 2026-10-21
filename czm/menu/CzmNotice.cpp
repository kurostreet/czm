/* Counter Zombie Mobile: branded alerts and explicit connection recovery. GPL-3.0-or-later. */
#include <ctype.h>
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

#define UI_DIR "gfx/czm/ui/"

int CZM_DiagnosticsMode( void )
{
	return bound( 0, (int)EngFuncs::GetCvarFloat( "czm_diagnostics" ), 2 );
}

void CZM_SetDiagnosticsMode( int mode )
{
	mode = bound( 0, mode, 2 );
	EngFuncs::CvarSetValue( "czm_diagnostics", mode );
	EngFuncs::CvarSetValue( "developer", mode );
	// Save before retrying: Android can stop the process without a clean exit.
	EngFuncs::ClientCmd( true, "host_writeconfig\n" );
}

bool CZM_DiagnosticsRequired( const char *reason )
{
	if( !reason ) return false;
	for( const char *p = reason; *p; p++ )
	{
		if( p != reason && ( isalnum( (unsigned char)p[-1] ) || p[-1] == '_' )) continue;
		const char *word = "developer", *q = p;
		while( *q && *word && tolower( (unsigned char)*q ) == *word ) q++, word++;
		if( *word || !( isspace( (unsigned char)*q ) || *q == '=' )) continue;
		while( isspace( (unsigned char)*q ) || *q == '=' ) q++;
		char quote = ( *q == '"' || *q == '\'' ) ? *q++ : 0;
		if( *q++ != '0' ) continue;
		if( quote ) { if( *q != quote ) continue; q++; }
		if( !isalnum( (unsigned char)*q ) && *q != '_' && *q != '.' ) return true;
	}
	return false;
}

static bool SafeRetry( const char *address, const char *protocol )
{
	// Engine-owned values contain numeric IPv4/IPv6 addresses. No server text is executed.
	return address && protocol && address[0] && strlen( address ) < 128 && strchr( address, ':' )
		&& strspn( address, "0123456789abcdefABCDEF.:[]" ) == strlen( address )
		&& ( !strcmp( protocol, "gs" ) || !strcmp( protocol, "49" ));
}

class CCzmNotice : public CMenuFramework
{
public:
	CCzmNotice();
	void Open( const char *title, const char *text, const char *details, bool diagnostics );
	void Hide() override;
	void Draw() override;
	bool IsRoot() const override { return false; }
	bool KeyDown( int key ) override;
	bool KeyUp( int key ) override;
	bool MouseMove( int x, int y ) override;
private:
	enum { CLOSE=1, RETRY, DETAILS, BODY };
	void Layout();
	int Hit();
	void Activate( int hit );
	bool CanRetry() const { return m_diagnostics && SafeRetry( m_address, m_protocol ); }
	bool Pressed( int hit ) { return m_pressed == hit && Hit() == hit; }
	char m_title[192], m_text[1024], m_details[1024], m_body[2100], m_address[128], m_protocol[4];
	bool m_open, m_diagnostics, m_expanded, m_drag, m_moved;
	int m_pressed, m_scroll, m_downScroll, m_downY, m_maxScroll, m_lines, m_starts[130];
	CzmRect m_panel, m_clip, m_close, m_retry, m_detail;
};

CCzmNotice::CCzmNotice() : CMenuFramework( "CzmNotice" )
{
	m_open=m_diagnostics=m_expanded=m_drag=m_moved=false;
	m_pressed=m_scroll=m_maxScroll=0;
	m_title[0]=m_text[0]=m_details[0]=m_address[0]=m_protocol[0]=0;
}

void CCzmNotice::Open( const char *title, const char *text, const char *details, bool diagnostics )
{
	Q_strncpy( m_title, title ? title : "", sizeof( m_title ));
	Q_strncpy( m_text, text ? text : "", sizeof( m_text ));
	Q_strncpy( m_details, details ? details : "", sizeof( m_details ));
	m_address[0]=m_protocol[0]=0;
	if( diagnostics )
	{
		Q_strncpy( m_address, EngFuncs::GetCvarString( "czm_retry_address" ), sizeof( m_address ));
		Q_strncpy( m_protocol, EngFuncs::GetCvarString( "czm_retry_protocol" ), sizeof( m_protocol ));
	}
	m_diagnostics=diagnostics; m_expanded=false; m_scroll=m_pressed=0; m_drag=m_moved=false;
	// The engine and loading teardown may report the same error in one frame.
	if( !m_open || m_pStack->Current() != this ) CMenuFramework::Show();
	m_open=true;
}

void CCzmNotice::Hide()
{
	m_open=false; m_pressed=0; m_drag=false;
	CMenuFramework::Hide();
}

void CCzmNotice::Layout()
{
	const int W=ScreenWidth, H=ScreenHeight;
	int pad=Q_max( 12, (int)( H*.038f )), gap=Q_max( 8, (int)( H*.018f ));
	int width=Q_min( (int)( W*.90f ), (int)( H*1.60f ));
	int button=Q_max( 36, (int)( H*.082f )), line=CZM_FontHeight( CZM_Font( CZMF_PANEL_TEXT ))+gap/2;
	snprintf( m_body, sizeof( m_body ), "%s%s%s", m_text, m_expanded && m_details[0] ? "\n\n" : "", m_expanded ? m_details : "" );
	m_lines=CZM_WrapText( CZM_Font( CZMF_PANEL_TEXT ), m_body, width-pad*2, m_starts, 128 );
	int heading=CZM_FontHeight( CZM_Font( CZMF_PANEL_TITLE ))+gap*2;
	int controls=button+( CanRetry() ? button+gap : 0 )+( m_details[0] ? button+gap : 0 );
	int height=Q_min( (int)( H*.90f ), pad*2+heading+m_lines*line+gap+controls );
	m_panel=CZM_Rect( (W-width)/2, (H-height)/2, width, height );
	m_clip=CZM_Rect( m_panel.x+pad, m_panel.y+pad+heading, width-pad*2, height-pad*2-heading-controls-gap );
	m_maxScroll=Q_max( 0, m_lines*line-m_clip.h ); m_scroll=bound( 0, m_scroll, m_maxScroll );
	int y=m_panel.y+height-pad-button;
	m_close=CZM_Rect( m_panel.x+pad,y,width-pad*2,button );
	m_retry=CZM_Rect( 0,0,0,0 ); m_detail=CZM_Rect( 0,0,0,0 );
	if( CanRetry() ) { y-=button+gap; m_retry=CZM_Rect( m_panel.x+pad,y,width-pad*2,button ); }
	if( m_details[0] ) { y-=button+gap; m_detail=CZM_Rect( m_panel.x+pad,y,width-pad*2,button ); }
}

int CCzmNotice::Hit()
{
	if( m_close.HasCursor() ) return CLOSE;
	if( m_retry.HasCursor() ) return RETRY;
	if( m_detail.HasCursor() ) return DETAILS;
	return m_clip.HasCursor() ? BODY : 0;
}

void CCzmNotice::Activate( int hit )
{
	if( !m_open ) return;
	if( hit==DETAILS ) { m_expanded=!m_expanded; m_scroll=0; CZM_PlayClick(); return; }
	if( hit==CLOSE ) { CZM_PlayClick(); Hide(); return; }
	if( hit!=RETRY || !CanRetry() || !CZM_OnlinePlayAllowed() ) return;
	char address[128], protocol[4];
	Q_strncpy( address,m_address,sizeof(address) ); Q_strncpy( protocol,m_protocol,sizeof(protocol) );
	CZM_SetDiagnosticsMode( 0 );
	CZM_PlayClick(); Hide();
	EngFuncs::ClientCmdF( false, "connect \"%s\" %s\n", address, protocol );
}

bool CCzmNotice::KeyDown( int key )
{
	Layout();
	if( UI::Key::IsEscape( key ) || UI::Key::IsEnter( key )) { Activate( CLOSE ); return true; }
	if( key==K_MWHEELUP || key==K_MWHEELDOWN ) { m_scroll=bound( 0,m_scroll+(key==K_MWHEELUP?-1:1)*ScreenHeight/10,m_maxScroll ); return true; }
	if( UI::Key::IsLeftMouse( key ))
	{
		m_pressed=Hit(); m_drag=m_pressed==BODY; m_moved=false; m_downY=uiStatic.cursorY; m_downScroll=m_scroll;
	}
	return true;
}

bool CCzmNotice::KeyUp( int key )
{
	if( UI::Key::IsLeftMouse( key ))
	{
		Layout(); int hit=Hit();
		if( !m_moved && m_pressed && m_pressed==hit ) Activate( hit );
		m_pressed=0; m_drag=false;
	}
	return true;
}

bool CCzmNotice::MouseMove( int x, int y )
{
	CMenuFramework::MouseMove( x,y );
	if( m_drag )
	{
		int dy=uiStatic.cursorY-m_downY;
		if( abs( dy )>ScreenHeight*.018f ) m_moved=true;
		if( m_moved ) m_scroll=bound( 0,m_downScroll-dy,m_maxScroll );
	}
	return true;
}

void CCzmNotice::Draw()
{
	Layout();
	UI_FillRect( 0,0,ScreenWidth,ScreenHeight,PackRGBA(0,0,0,170) );
	CZM_DrawPanel( m_panel );
	int pad=m_clip.x-m_panel.x, gap=Q_max( 8,(int)(ScreenHeight*.018f) );
	CZM_DrawImage( UI_DIR "white.png",m_clip.x,m_panel.y+pad,m_clip.w, Q_max(2,ScreenHeight/200),PackRGBA(230,38,38,255) );
	CZM_DrawText( CZM_Font(CZMF_PANEL_TITLE),m_clip.x,m_panel.y+pad+gap,m_clip.w,m_title,CZM_White() );
	UI::Scissor::PushScissor( m_clip.x,m_clip.y,m_clip.w,m_clip.h );
	int line=CZM_FontHeight(CZM_Font(CZMF_PANEL_TEXT))+gap/2;
	for( int i=0;i<m_lines;i++ )
	{
		char text[2100]; CZM_WrapLine(m_body,m_starts,i,text,sizeof(text));
		CZM_DrawText( CZM_Font(CZMF_PANEL_TEXT),m_clip.x,m_clip.y+i*line-m_scroll,m_clip.w,text,CZM_White() );
	}
	UI::Scissor::PopScissor();
	if( m_maxScroll )
	{
		int thumb=Q_max( 12,m_clip.h*m_clip.h/(m_clip.h+m_maxScroll) );
		UI_FillRect(m_panel.x+m_panel.w-pad/2,m_clip.y+(m_clip.h-thumb)*m_scroll/m_maxScroll,3,thumb,CZM_White(140));
	}
	if( m_details[0] ) CZM_DrawButton( UI_DIR "button_secondary.png",m_detail,CZM_T(m_expanded?"notice_less":"notice_details"),CZM_Grey(),Pressed(DETAILS),CZMF_SMALL );
	if( CanRetry() ) CZM_DrawButton( UI_DIR "button_primary.png",m_retry,CZM_T(CZM_DiagnosticsMode()?"diag_retry":"diag_retry_only"),CZM_White(),Pressed(RETRY),CZMF_PANEL_TEXT );
	CZM_DrawButton( CanRetry()?UI_DIR "button_secondary.png":UI_DIR "button_primary.png",m_close,CZM_T("notice_close"),CZM_White(),Pressed(CLOSE),CZMF_PANEL_TEXT );
}

ADD_MENU3( menu_czmnotice, CCzmNotice, UI_CzmNotice_Menu );

void UI_CzmNotice_Menu( void )
{
	CZM_ShowNotice( CZM_T("notice_title"), "" );
}

void CZM_ShowNotice( const char *title, const char *text, const char *details, bool diagnostics )
{
	if( menu_czmnotice ) menu_czmnotice->Open( title,text,details,diagnostics );
}

void CZM_ShowMessage( const char *text )
{
	CZM_ShowNotice( CZM_T("notice_title"), text );
}
