/* CZM radar: three plates (gfx/czm/radar, scripts/make_czm_radar.py), marks tinted on top.
   Place, size, opacity and style come from the editor (czm_hud_radar_*). GPL-2.0-or-later. */
#include "hud.h"
#include "cl_util.h"
#include "czm_hud.h"
#include "triangleapi.h"
#include <cmath>
#include <cstdio>

static int s_plates[CzmHud::RADAR_STYLES], s_marks[CZM_MARKS];

void CZM_RadarVidInit()
{
	static const char *const plates[CzmHud::RADAR_STYLES] = { "classic", "tactical", "minimal" };
	static const char *const marks[CZM_MARKS] = { "dot", "up", "down", "x" };
	char path[64];

	for( int i = 0; i < CzmHud::RADAR_STYLES; i++ )
	{
		snprintf( path, sizeof( path ), "gfx/czm/radar/radar_%s.png", plates[i] );
		s_plates[i] = gRenderAPI.GL_LoadTexture( path, NULL, 0, TF_CLAMP );
	}
	for( int i = 0; i < CZM_MARKS; i++ )
	{
		snprintf( path, sizeof( path ), "gfx/czm/radar/mark_%s.png", marks[i] );
		s_marks[i] = gRenderAPI.GL_LoadTexture( path, NULL, 0, TF_CLAMP );
	}
}

// a textured square in HUD units, tinted
static void Picture( int texture, float x, float y, float w, float h, int r, int g, int b, float alpha )
{
	const float s = gHUD.m_flScale;

	if( !texture || w <= 0 || h <= 0 )
		return;
	gRenderAPI.GL_SelectTexture( 0 );
	gRenderAPI.GL_Bind( 0, texture );
	gEngfuncs.pTriAPI->RenderMode( kRenderTransAlpha );
	gEngfuncs.pTriAPI->Color4f( r / 255.f, g / 255.f, b / 255.f, alpha );
	gEngfuncs.pTriAPI->Begin( TRI_QUADS );
	gEngfuncs.pTriAPI->TexCoord2f( 0, 0 ); gEngfuncs.pTriAPI->Vertex3f( x * s, y * s, 0 );
	gEngfuncs.pTriAPI->TexCoord2f( 0, 1 ); gEngfuncs.pTriAPI->Vertex3f( x * s, ( y + h ) * s, 0 );
	gEngfuncs.pTriAPI->TexCoord2f( 1, 1 ); gEngfuncs.pTriAPI->Vertex3f(( x + w ) * s, ( y + h ) * s, 0 );
	gEngfuncs.pTriAPI->TexCoord2f( 1, 0 ); gEngfuncs.pTriAPI->Vertex3f(( x + w ) * s, y * s, 0 );
	gEngfuncs.pTriAPI->End();
	gEngfuncs.pTriAPI->Color4f( 1, 1, 1, 1 );
}

bool CZM_RadarDraw( float yaw, const CzmRadarMark *marks, int count, int *labelX, int *labelY )
{
	int style;
	float cx, cy, inner, size;
	CzmHud::Rect p;

	if( !CZM_HudReady() || !s_plates[0] || !s_marks[CZM_MARK_DOT] )
		return false;

	*labelX = *labelY = -1;
	if( CZM_HudValue( CzmHud::RADAR, "hidden", 0 ) > .5f )
		return true; // taken off the screen in the editor

	style = (int)CzmHud::Clamp( gEngfuncs.pfnGetCvarFloat( "czm_hud_radar_style" ), 0, CzmHud::RADAR_STYLES - 1, 0 );
	p = CzmHud::RadarLayout( ScreenWidth, ScreenHeight,
		CZM_HudValue( CzmHud::RADAR, "x", CzmHud::defaults[CzmHud::RADAR][0] ),
		CZM_HudValue( CzmHud::RADAR, "y", CzmHud::defaults[CzmHud::RADAR][1] ),
		CZM_HudValue( CzmHud::RADAR, "scale", CzmHud::defaultScale[CzmHud::RADAR] ), CZM_HudValue( CzmHud::RADAR, "opacity", 1 ));

	Picture( s_plates[style] ? s_plates[style] : s_plates[0], p.x, p.y, p.w, p.h, 255, 255, 255, p.opacity );

	cx = p.x + p.w * 0.5f;
	cy = p.y + p.h * 0.5f;
	inner = p.w * 0.5f * CzmHud::RadarInner( style );

	// the tactical radar has a compass that turns with the view: N is the world +y, E the world +x
	if( style == CzmHud::RADAR_TACTICAL )
	{
		static const char *const letters[4] = { "N", "E", "S", "W" };
		static const float angles[4] = { 90.f, 0.f, -90.f, 180.f };
		float h = p.h * 0.07f, radius = inner * 0.93f;

		for( int i = 0; i < 4; i++ )
		{
			float offset = ( yaw - angles[i] ) * 0.0174532925f;
			float x = cx + radius * sinf( offset ), y = cy - radius * cosf( offset );
			bool north = i == 0;

			CZM_HudText( x - h * 0.325f, y - h * 0.5f, h, letters[i], north ? 224 : 147, north ? 37 : 159, north ? 50 : 180, 1.f );
		}
	}

	// players and the bomb stay fully visible at any plate opacity
	size = p.h * 0.085f;
	if( size < 7 )
		size = 7;
	for( int i = 0; i < count; i++ )
	{
		const CzmRadarMark &m = marks[i];
		int kind = m.kind >= 0 && m.kind < CZM_MARKS ? m.kind : CZM_MARK_DOT;
		float s = kind == CZM_MARK_X ? size * 1.25f : size;
		// a mark at the edge stays whole inside the radar, even on a tiny one
		float reach = p.w * 0.5f - s * 0.5f < inner ? p.w * 0.5f - s * 0.5f : inner;
		float x = cx + m.x * reach, y = cy + m.y * reach;

		Picture( s_marks[kind] ? s_marks[kind] : s_marks[CZM_MARK_DOT], x - s * 0.5f, y - s * 0.5f, s, s, m.r, m.g, m.b, 1.f );
	}

	// the place name under the radar, over it near the bottom of the screen
	*labelX = (int)cx;
	*labelY = (int)( p.y + p.h + 4 );
	if( *labelY > ScreenHeight - 24 )
		*labelY = (int)p.y - 20;
	return true;
}
