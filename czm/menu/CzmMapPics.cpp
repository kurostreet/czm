/* Shared map previews. GPL-3.0-or-later. */
#include "extdll_menu.h"
#include "BaseMenu.h"
#include "CzmMenu.h"
#include <map>
#include <string>
#include <stdio.h>
#include <string.h>

namespace {
struct Picture {
	HIMAGE image;
	int request;
	double next;
	bool missing;
	Picture() : image( 0 ), request( 0 ), next( 0 ), missing( false ) {}
};
std::map<std::string, Picture> pictures;
bool Name( const char *src, char *out )
{
	if( !src || !*src || strlen( src ) > 63 || strstr( src, ".." )) return false;
	int i = 0;
	for( ; src[i]; i++ )
	{
		unsigned char c = src[i];
		if( c >= 'A' && c <= 'Z' ) c += 'a' - 'A';
		if( !( c >= 'a' && c <= 'z' ) && !( c >= '0' && c <= '9' ) && c != '_' && c != '-' && c != '.' ) return false;
		out[i] = c;
	}
	out[i] = 0;
	return ( out[0] >= 'a' && out[0] <= 'z' ) || ( out[0] >= '0' && out[0] <= '9' );
}
void CachePath( const char *map, char *out, size_t size )
{
	snprintf( out, size, "czm_cache/maps/%s.png", map );
}
}

HIMAGE CZM_MapPreview( const char *name )
{
	char map[64], path[160];
	if( !Name( name, map )) return 0;
	Picture &p = pictures[map];
	if( p.image ) return p.image;
	const double now = EngFuncs::DoubleTime();
	if( p.request || now < p.next ) return 0;
	// Bundled image, phone image, then the shared service. No overview-as-photo.
	snprintf( path, sizeof( path ), "gfx/czm/maps/%s.png", map );
	if( EngFuncs::FileExists( path, false )) p.image = EngFuncs::PIC_Load( path );
	CachePath( map, path, sizeof( path ));
	if( !p.image && EngFuncs::FileExists( path, true )) p.image = EngFuncs::PIC_Load( path );
	if( !p.image )
	{
		snprintf( path, sizeof( path ), "levelshots/%s_16x9.bmp", map );
		if( EngFuncs::FileExists( path, false )) p.image = EngFuncs::PIC_Load( path );
	}
	if( !p.image )
	{
		snprintf( path, sizeof( path ), "levelshots/%s_4x3.bmp", map );
		if( EngFuncs::FileExists( path, false )) p.image = EngFuncs::PIC_Load( path );
	}
	if( !p.image && CZM_NetAvailable() )
	{
		char url[128];
		CachePath( map, path, sizeof( path ));
		snprintf( url, sizeof( url ), "/mappics/%s.png", map );
		p.request = CZM_NetDownload( CZM_OnlineUrl( url ), path );
		p.next = now + 30;
	}
	return p.image;
}

bool CZM_MapInstalled( const char *name )
{
	char map[64], path[96];
	if( !Name( name, map )) return false;
	snprintf( path, sizeof( path ), "maps/%s.bsp", map );
	// The engine search paths include cstrike_downloads/maps.
	return EngFuncs::FileExists( path, false );
}

// plain fills go through a picture: the engine clips pictures to a scrolling list, not rectangles
static void Fill( int x, int y, int w, int h, unsigned int color )
{
	CZM_DrawImage( "gfx/czm/ui/white.png", x, y, w, h, color );
}

void CZM_DrawMapPreview( const char *map, int x, int y, int w, int h, const char *server )
{
	HIMAGE image = CZM_MapPreview( map );
	HFont small = CZM_Font( CZMF_SMALL );
	int sh = CZM_FontHeight( small );

	if( w <= 0 || h <= 0 )
		return;

	if( image )
		CZM_DrawCover( image, x, y, w, h );
	else
	{
		// nobody has a picture of this map yet: the art of its mode, dimmed, with a question mark
		HIMAGE art = CZM_Image( CZM_MapModeArt( map, server ));
		int side = Q_min( w, h );
		int chip = bound( sh + 6, (int)( side * 0.36f ), (int)( side * 0.6f ));
		bool plate = h >= chip + sh * 3;
		int cx = x + w / 2, cy = y + ( plate ? ( h - sh - 8 ) / 2 : h / 2 );
		HFont mark = CZM_Font( CZMF_PANEL_TITLE );

		if( art )
			CZM_DrawCover( art, x, y, w, h );
		else
			Fill( x, y, w, h, PackRGBA( 20, 24, 33, 255 ));
		Fill( x, y, w, h, PackRGBA( 8, 10, 16, 150 ));

		if( CZM_FontHeight( mark ) > chip * 0.9f )
			mark = CZM_Font( CZMF_TILE_STATUS );
		CZM_DrawImage( "gfx/czm/ui/glow.png", cx - chip, cy - chip, chip * 2, chip * 2, PackRGBA( 0, 0, 0, 120 ));
		CZM_DrawImage( "gfx/czm/ui/chip_round.png", cx - chip / 2, cy - chip / 2, chip, chip );
		CZM_DrawText( mark, cx - chip / 2, cy - CZM_FontHeight( mark ) / 2, chip, "?", PackRGBA( 240, 242, 246, 255 ), QM_CENTER );

		if( plate )
		{
			int bh = sh + 8;
			Fill( x, y + h - bh, w, bh, PackRGBA( 6, 10, 17, 200 ));
			CZM_DrawText( small, x + 4, y + h - bh + 4, w - 8, CZM_T( "map_not_loaded" ), PackRGBA( 200, 206, 216, 255 ), QM_CENTER );
		}
		return;
	}

	if( map && *map && !CZM_MapInstalled( map ))
	{
		int bh = sh + 6;
		Fill( x, y + h - bh, w, bh, PackRGBA( 6, 10, 17, 205 ));
		CZM_DrawText( small, x + 3, y + h - bh + 3, w - 6, CZM_T( "map_not_downloaded" ), CZM_White(), QM_CENTER );
	}
}

void CZM_MapPicturesFrame( void )
{
	const double now = EngFuncs::DoubleTime();
	for( auto &entry : pictures )
	{
		Picture &p = entry.second;
		int status;
		CUtlString body;
		if( !p.request || !CZM_NetPoll( p.request, &status, body )) continue;
		p.request = 0;
		p.missing = status == 404;
		p.next = now + ( p.missing ? 300 : 30 );
		if( status == 200 )
		{
			char path[160];
			CachePath( entry.first.c_str(), path, sizeof( path ));
			p.image = EngFuncs::PIC_Load( path );
		}
	}
	static int visit = -1, attempts = 0, upload = 0;
	static double retry;
	static char uploading[64];
	if( upload )
	{
		int status;
		CUtlString body;
		if( CZM_NetPoll( upload, &status, body ))
		{
			upload = 0;
			if( status == 201 || status == 409 )
			{
				Picture &p = pictures[uploading];
				p.next = 0;
				p.missing = false;
				CZM_MapPreview( uploading );
			}
			retry = now + 15;
		}
	}
	int current = (int)EngFuncs::GetCvarFloat( "czm_map_visit" );
	if( current != visit ) { visit = current; attempts = 0; retry = 0; }
	char map[64];
	if( !Name( EngFuncs::GetCvarString( "czm_current_map" ), map )) return;
	CZM_MapPreview( map );
	Picture &p = pictures[map];
	if( upload || !CZM_OnlineReady() || !CZM_OnlineKey()[0] ) return;
	int state = (int)EngFuncs::GetCvarFloat( "czm_mapshot_state" );
	if( state == 2 )
	{
		char path[160], url[128];
		snprintf( path, sizeof( path ), "czm_cache/maps/%s_capture.png", map );
		snprintf( url, sizeof( url ), "/api/v1/mappic/%s", map );
		Q_strncpy( uploading, map, sizeof( uploading ));
		upload = CZM_NetUpload( CZM_OnlineUrl( url ), CZM_OnlineKey(), path, "image/png" );
		EngFuncs::CvarSetValue( "czm_mapshot_state", 0 );
		retry = now + 15;
	}
	else if( state == 3 )
	{
		EngFuncs::CvarSetValue( "czm_mapshot_state", 0 );
		retry = now + 15;
	}
	else if( state == 0 && !p.image && p.missing && !p.request && attempts < 3 && now >= retry
		&& EngFuncs::GetCvarFloat( "czm_mapshot_ready" ) != 0 )
	{
		attempts++;
		EngFuncs::CvarSetValue( "czm_mapshot_state", 1 );
	}
}
