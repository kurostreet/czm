"""Geometry of the chat block and the frame of server messages stays on any screen."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

HARNESS = r'''
#include "czm_hud_layout.h"
#include <cassert>
#include <cmath>
#include <cstdlib>
static void Inside( const CzmHud::Rect &r, float sw, float sh )
{
	assert( std::isfinite( r.x + r.y + r.w + r.h ));
	assert( r.x >= -0.5f && r.y >= -0.5f && r.x + r.w <= sw + 0.5f && r.y + r.h <= sh + 0.5f );
}
int main()
{
	const float screens[][2] = { { 640, 360 }, { 1600, 720 }, { 2340, 1080 }, { 2000, 1200 } };
	const float places[] = { -5, 0, 0.01f, 0.5f, 0.99f, 1, 7, NAN };
	const float scales[] = { 0, 0.6f, 1, 1.6f, 9, NAN };
	for( auto &s : screens ) for( float x : places ) for( float y : places ) for( float k : scales )
	{
		Inside( CzmHud::ChatLayout( s[0], s[1], x, y, k, 1, s[1] * 0.034f ), s[0], s[1] );
		Inside( CzmHud::MessageFrame( s[0], s[1], x, y, k, 1 ), s[0], s[1] );
	}
	// by default server messages keep the whole screen: nothing moves for players who never open the editor
	CzmHud::Rect full = CzmHud::MessageFrame( 2340, 1080, CzmHud::defaults[CzmHud::MESSAGES][0], CzmHud::defaults[CzmHud::MESSAGES][1], 1, 1 );
	assert( full.x == 0 && full.y == 0 && full.w == 2340 && full.h == 1080 );
	// a smaller frame stays centred around its place
	CzmHud::Rect small = CzmHud::MessageFrame( 2340, 1080, 0.5f, 0.5f, 0.8f, 1 );
	assert( fabsf( small.x + small.w / 2 - 1170 ) < 1 && fabsf( small.w - 1872 ) < 1 );
	// the chat starts bottom left, five lines tall, half the screen wide
	CzmHud::Rect chat = CzmHud::ChatLayout( 2340, 1080, CzmHud::defaults[CzmHud::CHAT][0], CzmHud::defaults[CzmHud::CHAT][1], 1, 1, 36 );
	assert( chat.x < 2340 * 0.03f && chat.w == 1170 && chat.h == 36 * CzmHud::chatLines && chat.y + chat.h < 1080 * 0.95f );
	return 0;
}
'''


class HudMessagesTests(unittest.TestCase):
    def test_chat_and_message_frame_geometry(self):
        if not shutil.which("g++"):
            self.skipTest("g++ required")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path / "main.cpp").write_text(HARNESS)
            subprocess.run(["g++", "-std=c++11", "-I" + str(ROOT / "common"), str(path / "main.cpp"), "-o", str(path / "run")], check=True)
            subprocess.run([str(path / "run")], check=True)

    def test_client_reads_the_editor_blocks(self):
        saytext = (ROOT / "cl_dll/saytext.cpp").read_text()
        message = (ROOT / "cl_dll/message.cpp").read_text()
        self.assertIn("CzmHud::ChatLayout", saytext)
        self.assertIn('CZM_HudValue( CzmHud::CHAT, "hidden", 0 )', saytext)
        self.assertIn("CzmHud::MessageFrame", message)
        self.assertIn("if ( !s_framesHidden )", message)


if __name__ == "__main__":
    unittest.main()
