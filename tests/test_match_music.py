"""Run the engine's real background-track rules: server music belongs to the match.

The server starts music with "mp3 play" (vote cues, round music). The engine used to tie a
track to the screen that was open when it started: music started while our shop or server
menu was open then played only in menus, and music started in game paused in every menu.
Needs the patched engine (CI applies patches/xash3d-fwgs first).
"""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ENGINE = Path(os.environ.get("CZM_ENGINE", ROOT / "3rdparty/xash3d-fwgs")) / "engine"


def function(source, signature):
    start = source.index(signature)
    opening = source.index("{", start)
    end, depth = opening + 1, 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


class MatchMusicTests(unittest.TestCase):
    def test_server_music_plays_in_game_and_over_our_menus(self):
        stream = (ENGINE / "client/sound/s_stream.c").read_text()
        start = function(stream, "void S_StartBackgroundTrack(")
        play = function(stream, "void S_StreamBackgroundTrack(")
        source = re.search(r"^\s*s_bgTrack\.source = .*;$", start, re.M).group(0)
        gate = play[play.index("if( !cl.background )"):]
        gate = gate[gate.index("{") + 1:gate.index("}")]
        rules = "\n".join(line.replace("return;", "return 0;") for line in gate.splitlines()
                          if line.strip().startswith("if(") and "s_bgTrack.source" in line)
        self.assertEqual(rules.count("return 0;"), 2)
        program = r'''
#include <assert.h>
enum { key_console, key_game, key_menu, key_message };
enum { ca_disconnected, ca_connecting, ca_connected, ca_validate, ca_active };
static struct { int state, key_dest; } cls;
static struct { int background; } cl;
static struct { int source; } s_bgTrack;
static void Start( int state, int screen ) { cls.state = state; cls.key_dest = screen;
''' + source + r'''
}
static int Plays( int screen ) { cls.key_dest = screen;
''' + rules + r'''
	return 1; }
int main( void )
{
	/* The server starts music while our shop or server menu is open: it belongs to the match. */
	Start( ca_active, key_menu );
	assert( Plays( key_menu ) && Plays( key_game ));
	/* Started in game: it keeps playing when a menu opens over the match. */
	Start( ca_active, key_game );
	assert( Plays( key_game ) && Plays( key_menu ));
	/* Main menu music outside a match: menus only, as before. */
	Start( ca_disconnected, key_menu );
	assert( Plays( key_menu ));
	cls.state = ca_active; assert( !Plays( key_game ));
	/* A match track left after leaving the server stays silent in menus. */
	Start( ca_active, key_game ); cls.state = ca_disconnected;
	assert( !Plays( key_menu ));
	return 0;
}
'''
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "music.c"
            path.write_text(program)
            subprocess.run(["cc", "-std=c99", "-Wall", "-Werror", str(path), "-o", str(Path(folder) / "music")], check=True)
            subprocess.run([str(Path(folder) / "music")], check=True)


if __name__ == "__main__":
    unittest.main()
