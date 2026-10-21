#!/usr/bin/env python3
"""Prepare branded menu sources without modifying the pinned upstream submodule."""

import argparse
from pathlib import Path


def replace_once(source, old, new, filename):
    if source.count(old) != 1:
        raise RuntimeError(f"Upstream menu changed: expected one branding anchor in {filename}")
    return source.replace(old, new, 1)


def brand_background(source):
    filename = "controls/BackgroundBitmap.cpp"
    source = replace_once(source, '#include "BaseWindow.h"\n', '#include "BaseWindow.h"\n#include "CzmMenu.h"\n', filename)
    source = replace_once(
        source,
        "\tif( FBitSet( ui_prefer_won_background->flags, FCVAR_CHANGED ))",
        '''\t// Owner-supplied art fills the screen, a dark fade keeps the menu readable.
\t// The version is shown in the About panel of the main screen.
\tif( CZM_DrawMenuBackground( m_scPos, m_scSize ))
\t\treturn;

\tif( FBitSet( ui_prefer_won_background->flags, FCVAR_CHANGED ))''',
        filename,
    )
    source = replace_once(source, "char version[32];", "char version[128];", filename)
    source = replace_once(
        source,
        'snprintf( version, 32, "cs16-client build %s",',
        'snprintf( version, sizeof( version ), "Counter Zombie Mobile 32 players build %s",',
        filename,
    )
    return source.replace("// print CS16Client version", "// print application version")


def brand_base_menu(source):
    filename = "BaseMenu.cpp"
    source = replace_once(source, '#include "FontManager.h"\n', '#include "FontManager.h"\n#include "CzmMenu.h"\n', filename)
    source = replace_once(
        source,
        "\t// advance global time\n\tuiStatic.realTime = flTime * 1000;\n",
        "\t// advance global time\n\tuiStatic.realTime = flTime * 1000;\n\n"
        "\tCZM_MenuAudioFrame();\n\n"
        "\t// our loading screen replaces the console while the engine connects\n"
        "\tif( CZM_DrawLoadingScreen( ))\n\t\treturn;\n\n"
        "\t// server menus as cards over the game\n"
        "\tCZM_DrawGameOverlay();\n\n"
        "\t// answers of our service: hello, news, chat avatars\n"
        "\tCZM_OnlineFrame();\n",
        filename,
    )
    source = replace_once(
        source,
        'EngFuncs::PlayBackgroundTrack( "media/gamestartup", "media/gamestartup" );',
        'CZM_MenuAudioFrame();',
        filename,
    )
    start = source.index("static void UI_LoadSounds( void )\n{")
    end = source.index("\n}\n", start) + 3
    source = source[:start] + '''static void UI_LoadSounds( void )
{
\tmemset( uiStatic.sounds, 0, sizeof( uiStatic.sounds ) );
\tfor( int i = 0; i < SND_COUNT; i++ )
\t{
\t\t// Scrolling and pointer hover stay quiet; button actions use the same tap.
\t\tif( i != SND_MOVE && i != SND_ROLLOVER && i != SND_NULL )
\t\t\tQ_strncpy( uiStatic.sounds[i], "czm/tapscroll.wav", sizeof( uiStatic.sounds[i] ));
\t}
}
''' + source[end:]
    # A cut line ends with "...": cut before the whole UTF-8 character, not after its first byte
    # (a Russian letter cut in half was drawn as a wrong letter, e.g. «режЮ..»).
    source = replace_once(
        source,
        "\t\tutfstate_t state;\n\n\t\twhile( string[j] )\n",
        "\t\tutfstate_t state;\n\t\tint charStart = j; // first byte of the character being read\n\n\t\twhile( string[j] )\n",
        filename,
    )
    source = replace_once(
        source,
        "\t\t\tline[len] = string[j];\n\n\t\t\tuint32_t uch = state.Decode((uint8_t)string[j] );\n",
        "\t\t\tline[len] = string[j];\n\n"
        "\t\t\tif((( uint8_t )string[j] & 0xC0 ) != 0x80 )\n\t\t\t\tcharStart = j;\n\n"
        "\t\t\tuint32_t uch = state.Decode((uint8_t)string[j] );\n",
        filename,
    )
    source = replace_once(
        source,
        "\t\t\t\t\tif( pixelWide + ellipsisWide < w && j > 0 )\n\t\t\t\t\t{\n"
        "\t\t\t\t\t\tsave_pixelWide = pixelWide;\n\t\t\t\t\t\tsave_j = j;\n",
        "\t\t\t\t\tif( pixelWide + ellipsisWide < w && charStart > 0 )\n\t\t\t\t\t{\n"
        "\t\t\t\t\t\tsave_pixelWide = pixelWide;\n\t\t\t\t\t\tsave_j = charStart;\n",
        filename,
    )
    return replace_once(
        source,
        "uiStatic.renderPicbuttonText = gMenu.m_gameinfo.flags & GFL_RENDER_PICBUTTON_TEXT;",
        "uiStatic.renderPicbuttonText = true; // Avoid branded text baked into external cache bitmaps.",
        filename,
    )


def brand_font_manager(source):
    filename = "font/FontManager.cpp"
    source = replace_once(source, '#include "FontManager.h"\n', '#include "FontManager.h"\n#include "CzmMenu.h"\n', filename)
    source = replace_once(
        source,
        "bool CFontManager::FindFontDataFile( const char *name, int tall, int weight, int flags, char *dataFile, size_t dataFileChars )\n{\n",
        "bool CFontManager::FindFontDataFile( const char *name, int tall, int weight, int flags, char *dataFile, size_t dataFileChars )\n{\n"
        "\tif( CZM_FindFontFile( name, dataFile, dataFileChars ))\n\t\treturn true;\n\n",
        filename,
    )
    return replace_once(source, "\t\tprevScale = scale;\n", "\t\tCZM_CreateFonts( scale );\n\t\tprevScale = scale;\n", filename)


def brand_main_menu(source):
    filename = "menus/Main.cpp"
    source = replace_once(
        source,
        'multiPlayer.SetNameAndStatus( L( "GameUI_Multiplayer" ), L( "StringsList_198" ) );',
        'multiPlayer.SetNameAndStatus( "Play online", L( "StringsList_198" ) );',
        filename,
    )
    source = replace_once(
        source,
        'previews.SetNameAndStatus( L( "Previews" ), L( "StringsList_400" ) );',
        'previews.SetNameAndStatus( "Project", L( "StringsList_400" ) );',
        filename,
    )
    old_banner = '''\tif( FBitSet( gMenu.m_gameinfo.flags, GFL_ANIMATED_TITLE ))
\t{
\t\tif( animatedBanner.TryLoad())
\t\t\tAddItem( animatedBanner );
\t}
\telse
\t{
\t\tAddItem( movieBanner );
\t}'''
    source = replace_once(source, old_banner, "\t// The background draws our logo instead of the external cache title movie.", filename)
    source = replace_once(source, "\tAddItem( readme );", "\t// Upstream readme button has no action; project information is available below.", filename)
    # Our main screen (czm/menu/CzmMain.cpp) owns UI_Main_Menu, the stock one stays for debugging.
    source = replace_once(
        source,
        "ADD_MENU( menu_main, CMenuMain, UI_Main_Menu );",
        "ADD_MENU( menu_stockmain, CMenuMain, UI_StockMain_Menu );",
        filename,
    )
    # The upstream menu draws all help text over the logo when QMF_NOTIFY is set.
    return source.replace(".iFlags |= QMF_NOTIFY;", ".iFlags &= ~QMF_NOTIFY;")


def brand_server_browser(source):
    filename = "menus/ServerBrowser.cpp"
    source = replace_once(source, '#include "DropDown.h"\n', '#include "DropDown.h"\n#include "CzmMenu.h"\n', filename)
    # server info goes to the mode tiles and our server list first
    source = replace_once(
        source,
        "void UI_AddServerToList( netadr_t adr, const char *info )\n{\n",
        "void UI_AddServerToList( netadr_t adr, const char *info )\n{\n"
        "\tif( CZM_OnServerInfo( adr, info ))\n\t\treturn;\n\n",
        filename,
    )
    # the engine sent the queries for the master list: pings count from now
    return replace_once(
        source,
        "void UI_MenuResetPing_f( void )\n{\n",
        "void UI_MenuResetPing_f( void )\n{\n\tCZM_ServerListResetPing();\n\n",
        filename,
    )


def brand_connection_progress(source):
    filename = "menus/ConnectionProgress.cpp"
    # after a failed connection go back to the main screen, the game has no server browser
    return replace_once(
        source,
        "\t\t\tUI_Main_Menu();\n\t\t\tUI_ServerBrowser_Menu();\n"
        "\t\t\tif( m_iSource == SOURCE_CREATEGAME )\n\t\t\t\tUI_CreateGame_Menu();\n",
        "\t\t\tUI_Main_Menu();\n",
        filename,
    )


def brand_udll_int(source):
    filename = "udll_int.cpp"
    source = replace_once(source, '#include "Utils.h"\n', '#include "Utils.h"\n#include "CzmMenu.h"\n', filename)
    # buy menus open our shop (wheel or grid), the stock ones stay for "czm_shop 0"
    return replace_once(
        source,
        "\t\tEngFuncs::KEY_ClearStates();\n\n\t\tswitch( menuType )\n",
        "\t\tEngFuncs::KEY_ClearStates();\n\n"
        "\t\tif( CZM_ShopShow( menuType, param2 ))\n\t\t\treturn;\n\n"
        "\t\tswitch( menuType )\n",
        filename,
    )


def brand_message_box(source):
    filename = "controls/YesNoMessageBox.cpp"
    source = replace_once(source, '#include "Utils.h"\n', '#include "Utils.h"\n#include "CzmMenu.h"\n', filename)
    source = replace_once(source, '\tstatic CMenuYesNoMessageBox msgBox( true );\n', '', filename)
    # Keep the upstream input-device recovery action; other engine alerts use our card.
    return replace_once(source, '\tmsgBox.SetMessage( msg );\n\tmsgBox.Show();',
                        '\tCZM_ShowMessage( msg );', filename)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("upstream", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    transforms = {
        "BaseMenu.cpp": brand_base_menu,
        "controls/BackgroundBitmap.cpp": brand_background,
        "menus/Main.cpp": brand_main_menu,
        "font/FontManager.cpp": brand_font_manager,
        "menus/ServerBrowser.cpp": brand_server_browser,
        "menus/ConnectionProgress.cpp": brand_connection_progress,
        "udll_int.cpp": brand_udll_int,
        "controls/YesNoMessageBox.cpp": brand_message_box,
    }
    for filename, transform in transforms.items():
        content = transform((args.upstream / filename).read_text())
        target = args.output / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.read_text() != content:
            target.write_text(content)
    print("Prepared Counter Zombie Mobile menu sources")


if __name__ == "__main__":
    main()
