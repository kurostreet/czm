/* Flat community feed: the same geometry drives painting and message actions. */
#pragma once
#include <time.h>
#include "CzmDesign.h"
#include "CzmTranslation.h"

namespace CzmCommunityChat {
enum { Lines = 128 };
inline bool SameDay( int a, int b ) {
    time_t x = a, y = b; struct tm first, second;
    localtime_r( &x, &first ); localtime_r( &y, &second );
    return first.tm_year == second.tm_year && first.tm_yday == second.tm_yday;
}
inline int DateHeight() { return CZM_FontHeight( CZM_Font( CZMF_UI_META )) + Q_max( 6, ScreenHeight / 110 ); }
inline void Date( const CzmRect &clip, int y, int stamp ) {
    time_t value = stamp; struct tm day; localtime_r( &value, &day );
    char label[40]; strftime( label, sizeof( label ), "%d.%m.%Y", &day );
    const int height = DateHeight(), width = CZM_TextWidth( CZM_Font( CZMF_UI_META ), label ) + height;
    const int lineY = y + height / 2, middle = clip.x + clip.w / 2;
    UI_FillRect( clip.x, lineY, Q_max( 0, middle - width / 2 - clip.x ), 1, CzmStyle::Border() );
    UI_FillRect( middle + width / 2, lineY, Q_max( 0, clip.x + clip.w - middle - width / 2 ), 1, CzmStyle::Border() );
    CzmStyle::Text( CZM_Rect( middle - width / 2, y, width, height ), label, CZMF_UI_META, CzmStyle::Muted(), QM_CENTER );
}
inline const char *TranslateLabel( const CzmTranslationView &view ) {
    if( view.state == 1 ) return CZM_IsRussian() ? "Переводим…" : "Translating…";
    if( view.state == 3 ) return CZM_IsRussian() ? "Повторить перевод" : "Retry translation";
    if( view.state == 2 && view.shown ) return CZM_IsRussian() ? "Скрыть перевод" : "Hide translation";
    return CZM_IsRussian() ? "Перевести с Google" : "Translate with Google";
}
struct Row {
    CzmRect frame, avatar, name, roleTag, topTag, time, menu, body, translate, result, credit;
    int height, originalLines, resultLines, starts[Lines + 1], translatedStarts[Lines + 1];
    bool grouped, canTranslate;
    CzmTranslationView translation;
};
inline Row Layout( const CzmRect &clip, int top, const char *text, const char *nick,
                   bool grouped = false, const char *role = "", const char *project = "", int place = 0 ) {
    Row row = {};
    const int H = ScreenHeight, pad = Q_max( 2, H / 230 ), gap = Q_max( 2, H / 300 );
    const HFont bodyFont = CZM_Font( CZMF_CHAT_TEXT ), nameFont = CZM_Font( CZMF_UI_LABEL ), meta = CZM_Font( CZMF_UI_META );
    const int line = CZM_FontHeight( bodyFont ) + Q_max( 1, H / 600 );
    const int avatar = Q_max( 22, H * 45 / 1000 ), menu = Q_max( 20, H * 36 / 1000 );
    const int textX = clip.x + avatar + Q_max( 7, H / 80 );
    const int right = clip.x + clip.w, timeWidth = CZM_TextWidth( meta, "00:00" ) + gap;
    row.grouped = grouped;
    row.menu = CZM_Rect( right - menu, top + pad, menu, menu );
    row.time = CZM_Rect( row.menu.x - timeWidth - gap, top + pad, timeWidth, CZM_FontHeight( meta ));
    const int textWidth = Q_max( 1, row.time.x - gap * 2 - textX );
    int y = top + pad;
    if( !grouped ) {
        const int tagHeight = Q_max( 10, CZM_FontHeight( meta ) + 2 );
        const int header = Q_max( CZM_FontHeight( nameFont ), tagHeight );
        const int tagLimit = Q_max( 0, textWidth / 3 );
        const int roleWidth = role && role[0] ? CZM_RoleTagWidth( role, tagHeight, project, tagLimit ) : 0;
        const int topWidth = CZM_TopTagWidth( place, tagHeight );
        const int tags = ( roleWidth ? roleWidth + gap : 0 ) + ( topWidth ? topWidth + gap : 0 );
        const int nameWidth = Q_min( CZM_TextWidth( nameFont, nick ), Q_max( 1, textWidth - tags ));
        row.name = CZM_Rect( textX, y, nameWidth, header );
        int tagX = textX + nameWidth + gap;
        if( roleWidth ) { row.roleTag = CZM_Rect( tagX, y + ( header - tagHeight ) / 2, roleWidth, tagHeight ); tagX += roleWidth + gap; }
        if( topWidth ) row.topTag = CZM_Rect( tagX, y + ( header - tagHeight ) / 2, topWidth, tagHeight );
        row.avatar = CZM_Rect( clip.x, y, avatar, avatar );
        y += header + gap;
    }
    row.originalLines = CZM_WrapText( bodyFont, text, textWidth, row.starts, Lines );
    row.body = CZM_Rect( textX, y, textWidth, row.originalLines * line ); y += row.body.h;
    row.canTranslate = CZM_CanTranslate( text );
    row.translation = row.canTranslate ? CZM_TranslationGet( text ) : CzmTranslationView{ 0, false, "" };
    if( row.canTranslate ) {
        y += gap;
        row.translate = CZM_Rect( textX, y, textWidth, Q_max( 12, CZM_FontHeight( meta ) + gap ));
        y += row.translate.h;
    }
    if( row.translation.state == 2 && row.translation.shown ) {
        y += gap * 2;
        row.resultLines = CZM_WrapText( bodyFont, row.translation.text, textWidth, row.translatedStarts, Lines );
        row.result = CZM_Rect( textX, y, textWidth, row.resultLines * line ); y += row.result.h + gap;
        const int creditWidth = Q_min( textWidth, Q_max( 88, H * 20 / 100 ));
        row.credit = CZM_Rect( textX, y, creditWidth, Q_max( 8, creditWidth * 32 / 352 )); y += row.credit.h;
    }
    const int end = Q_max( y, Q_max( row.menu.y + row.menu.h, row.avatar.y + row.avatar.h ));
    row.frame = CZM_Rect( clip.x, top, clip.w, end + pad - top );
    row.height = row.frame.h;
    return row;
}
inline void Draw( const Row &row, const char *text, const char *nick, unsigned nickColor,
                  const char *avatar, int stamp, bool menuPressed = false,
                  const char *role = "", const char *project = "", int place = 0 ) {
    using namespace CzmStyle;
    const int line = CZM_FontHeight( CZM_Font( CZMF_CHAT_TEXT )) + Q_max( 1, ScreenHeight / 600 );
    if( !row.grouped ) {
        CZM_DrawImage( avatar, row.avatar.x, row.avatar.y, row.avatar.w, row.avatar.h );
        Text( row.name, nick, CZMF_UI_LABEL, nickColor );
        if( row.roleTag.w ) CZM_DrawRoleTag( row.roleTag.x, row.roleTag.y, row.roleTag.h, role, project, row.roleTag.w );
        if( row.topTag.w ) CZM_DrawTopTag( row.topTag.x, row.topTag.y, row.topTag.h, place );
    }
    time_t value = stamp; struct tm date; localtime_r( &value, &date );
    char when[20]; strftime( when, sizeof( when ), "%H:%M", &date );
    Text( row.time, when, CZMF_UI_META, Muted(), QM_RIGHT );
    if( menuPressed ) Round( row.menu, PackRGBA( 57, 66, 82, 255 ));
    Icon( row.menu, "gfx/czm/ui/icon_more.png", Muted() );
    for( int i = 0; i < row.originalLines; i++ ) {
        char part[1604]; CZM_WrapLine( text, row.starts, i, part, sizeof( part ));
        CZM_DrawText( CZM_Font( CZMF_CHAT_TEXT ), row.body.x, row.body.y + i * line, row.body.w, part, Ink() );
    }
    if( row.canTranslate ) Text( row.translate, TranslateLabel( row.translation ), CZMF_UI_META, row.translation.state == 3 ? AccentGold() : AccentBlue() );
    if( row.resultLines ) {
        UI_FillRect( row.result.x, row.result.y - Q_max( 2, ScreenHeight / 300 ), row.result.w, 1, Border() );
        for( int i = 0; i < row.resultLines; i++ ) {
            char part[6404]; CZM_WrapLine( row.translation.text, row.translatedStarts, i, part, sizeof( part ));
            CZM_DrawText( CZM_Font( CZMF_CHAT_TEXT ), row.result.x, row.result.y + i * line, row.result.w, part, PackRGBA( 186, 216, 247, 255 ));
        }
        // Official, unmodified Google Translate attribution asset.
        CZM_DrawImage( "gfx/czm/ui/google_translate.png", row.credit.x, row.credit.y, row.credit.w, row.credit.h );
    }
    UI_FillRect( row.body.x, row.frame.y + row.frame.h - 1, row.frame.x + row.frame.w - row.body.x, 1, PackRGBA( 39, 48, 61, 255 ));
}
} // namespace CzmCommunityChat
