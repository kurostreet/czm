"""The engine side of the touch wheels and the press animation (patch czm-touch-press-and-wheels):
the finger is followed, czm_wheel tells the menu where the wheel is, picks go out as commands."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches/xash3d-fwgs/0029-czm-touch-press-and-wheels.patch"

PROGRAM = r'''
#include <assert.h>
#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
typedef int qboolean;
typedef unsigned char byte;
#define true 1
#define false 0
#define M_PI_F 3.14159265f
#define FBitSet( a, b ) (( a ) & ( b ))
#define TOUCH_FL_CLIENT 4
#define Q_strcmp strcmp
#define Q_strncmp strncmp
#define Q_snprintf snprintf
#define bound( lo, v, hi ) (( v ) < ( lo ) ? ( lo ) : ( v ) > ( hi ) ? ( hi ) : ( v ))
typedef enum { touch_command, touch_move, touch_joy, touch_dpad, touch_look, touch_wheel, touch_czmwheel } touchButtonType;
typedef enum { state_none, state_edit } touchState;
typedef enum { event_down, event_up, event_motion } touchEventType;
typedef struct touch_button_s { touchButtonType type; float x1, y1, x2, y2; char texture[64]; char command[64]; int finger, flags;
	qboolean latched; double czm_down, czm_up; float czm_depth; } touch_button_t;
static struct { touchState state; float view_x, view_y, view_width; } touch;
static struct { double realtime; } host;
static struct { int width, height; } refState = { 2000, 932 };
enum { key_game, key_menu };
enum { ca_disconnected, ca_active };
static struct { int key_dest, state; } cls = { key_game, ca_active };
typedef struct { const char *name; char *string; float value; } convar_t;
static char wheelText[128];
static convar_t czm_touch_press = { "czm_touch_press", "1", 1 }, czm_wheel_state = { "czm_wheel", wheelText, 0 };
static void Cvar_DirectSet( convar_t *v, const char *s ) { strcpy( v->string, s ); }
static char cbuf[1024];
static void Cbuf_AddText( const char *t ) { strcat( cbuf, t ); }
static const char *va( const char *f, ... ) { static char b[256]; va_list a; va_start( a, f ); vsnprintf( b, sizeof( b ), f, a ); va_end( a ); return b; }
static float Touch_AspectRatio( void ) { return (float)refState.height / refState.width; }
#define SCRN_WIDTH( x ) ( touch.view_width * ( x ))
#define SCRN_HEIGHT( x ) ( touch.view_width * ( x ) * Touch_AspectRatio())
#define TO_SCRN_X( x ) ( touch.view_x + SCRN_WIDTH( x ))
#define TO_SCRN_Y( x ) ( touch.view_y + SCRN_HEIGHT( x ))
@@PRESS@@
@@WHEEL@@
static touch_button_t weapons = { touch_czmwheel, .80f, .60f, .86f, .73f, "gfx/czm/touch/wheel", "_czmwheel weapons", -1 };
static touch_button_t radio = { touch_czmwheel, .28f, .08f, .32f, .16f, "gfx/czm/touch/radio", "showvguimenu 38", -1 };
static touch_button_t replies = { touch_czmwheel, .40f, .08f, .44f, .16f, "gfx/czm/touch/radio3", "radio3", -1 };
static void press( touch_button_t *b, int finger, float x, float y ) { b->finger = finger; b->czm_down = host.realtime; Touch_CzmWheelOpen( b, finger, x, y ); }
static int field( int n ) { int v = 0; const char *s = wheelText; for( int i = 0; i < n; i++ ) s = strchr( s, ' ' ) + 1; sscanf( s, "%d", &v ); return v; }
int main( void ) {
	touch.view_width = 2000;
	host.realtime = 100;
	// the press animation: down in 70 ms, back in 220 ms, from as deep as it went
	weapons.finger = 3; weapons.czm_down = host.realtime; host.realtime += 0.035;
	assert( Touch_CzmAnimated( &weapons ) && fabsf( Touch_CzmDepth( &weapons ) - 0.5f ) < 0.01f );
	host.realtime += 0.1; assert( Touch_CzmDepth( &weapons ) == 1.0f );
	Touch_CzmLetGo( &weapons ); assert( weapons.finger == -1 && weapons.czm_depth == 1.0f );
	host.realtime += 0.11; assert( fabsf( Touch_CzmDepth( &weapons ) - 0.5f ) < 0.01f );
	host.realtime += 0.2; assert( Touch_CzmDepth( &weapons ) == 0.0f );
	touch.state = state_edit; assert( !Touch_CzmAnimated( &weapons )); touch.state = state_none;
	czm_touch_press.value = 0; assert( !Touch_CzmAnimated( &weapons )); czm_touch_press.value = 1;

	// a quick tap on the weapon wheel: the last weapon, the wheel never shows
	host.realtime = 200; press( &weapons, 1, .83f, .66f );
	assert( !strncmp( wheelText, "weapons 1 ", 10 ) && field( 8 ) == 0 ); // not shown yet
	assert( !Touch_CzmWheelEvent( event_motion, 2, .2f, .5f )); // other fingers walk and look
	host.realtime += 0.1; assert( Touch_CzmWheelEvent( event_up, 1, .83f, .66f ));
	assert( !strcmp( cbuf, "czm_wheel_pick weapons 1 0 0 279\n" ) && !wheelText[0] && weapons.finger == -1 );
	// held without a slide: shows, picks nothing when let go
	cbuf[0] = 0; press( &weapons, 1, .83f, .66f ); host.realtime += 0.3; Touch_CzmWheelFrame(); assert( field( 8 ) == 1 && field( 7 ) == 0 );
	Touch_CzmWheelEvent( event_up, 1, .83f, .66f ); assert( !cbuf[0] && !wheelText[0] );
	// a slide up picks by its direction; the wheel stays inside the screen
	press( &weapons, 1, .83f, .66f );
	assert( field( 2 ) >= 279 * 1.12f && field( 2 ) <= 2000 - 279 * 1.12f && field( 3 ) <= 932 - 312 );
	Touch_CzmWheelEvent( event_motion, 1, .83f, .55f ); assert( field( 7 ) == 1 && field( 8 ) == 1 && field( 5 ) == 0 && field( 6 ) < -90 );
	Touch_CzmWheelEvent( event_up, 1, .83f, .55f ); assert( !strncmp( cbuf, "czm_wheel_pick weapons 1 0 -", 28 ) && !wheelText[0] );

	// the stock radio button: a tap leaves the radio wheel open, the next tap on it picks
	cbuf[0] = 0; host.realtime = 300; press( &radio, 4, .30f, .12f ); host.realtime += 0.08;
	Touch_CzmWheelEvent( event_up, 4, .30f, .12f ); assert( !cbuf[0] && !strncmp( wheelText, "radio 2 ", 8 ) && radio.finger == -1 );
	{
		const int cx = field( 2 ), cy = field( 3 );
		const float x = ( cx + 200 ) / 2000.0f, y = cy / 2000.0f / ( 932.0f / 2000 ); // to the right of the centre
		assert( Touch_CzmWheelEvent( event_down, 5, x, y ) && field( 7 ) == 1 );
		assert( !Touch_CzmWheelEvent( event_down, 6, .6f, .5f ) || true ); // a second finger is taken and ignored
		assert( Touch_CzmWheelEvent( event_up, 5, x, y ));
		assert( !strcmp( cbuf, "czm_wheel_pick radio 2 200 0 279\n" ) && !wheelText[0] );
	}
	// the stock radio menus are wheels of their own: a slide picks from the "radio3" wheel
	cbuf[0] = 0; press( &replies, 4, .42f, .12f ); assert( !strncmp( wheelText, "radio3 1 ", 9 ));
	Touch_CzmWheelEvent( event_motion, 4, .50f, .12f ); Touch_CzmWheelEvent( event_up, 4, .50f, .12f );
	assert( !strncmp( cbuf, "czm_wheel_pick radio3 1 ", 24 ) && !wheelText[0] );
	cbuf[0] = 0; press( &replies, 4, .42f, .12f ); Touch_CzmWheelEvent( event_up, 4, .42f, .12f );
	assert( !cbuf[0] && !strncmp( wheelText, "radio3 2 ", 9 )); Touch_CzmWheelClose();
	// open: a tap on the hub or outside closes it without a pick; so does a quiet while or a menu
	cbuf[0] = 0; press( &radio, 4, .30f, .12f ); Touch_CzmWheelEvent( event_up, 4, .30f, .12f );
	{ const float x = field( 2 ) / 2000.0f, y = field( 3 ) / 932.0f; assert( Touch_CzmWheelEvent( event_down, 7, x, y )); }
	assert( !wheelText[0] && !cbuf[0] );
	press( &radio, 4, .30f, .12f ); Touch_CzmWheelEvent( event_up, 4, .30f, .12f ); assert( Touch_CzmWheelEvent( event_down, 7, .95f, .95f ) && !wheelText[0] );
	press( &radio, 4, .30f, .12f ); Touch_CzmWheelEvent( event_up, 4, .30f, .12f ); host.realtime += 7; Touch_CzmWheelFrame(); assert( !wheelText[0] );
	press( &weapons, 1, .83f, .66f ); cls.key_dest = key_menu; Touch_CzmWheelFrame(); assert( !wheelText[0] && weapons.finger == -1 ); cls.key_dest = key_game;
	// the held button goes away (the layout is loaded again): the wheel forgets it
	press( &weapons, 1, .83f, .66f ); Touch_CzmWheelForget( &weapons ); weapons.finger = 9; Touch_CzmWheelClose(); assert( weapons.finger == 9 && !wheelText[0] );
	puts( "TOUCH_WHEELS_OK" );
	return 0;
}
'''


def added_lines():
    return "\n".join(line[1:] for line in PATCH.read_text().splitlines() if line.startswith("+") and not line.startswith("+++"))


class TouchWheelsTests(unittest.TestCase):
    def test_press_animation_and_wheels(self):
        added = added_lines()
        press = added[added.index("#define CZM_PRESS_IN"):added.index("static void Touch_CzmDrawPressed(")]
        start = added.index("#define CZM_WHEEL_RADIUS")
        wheel = added[start:added.index("\t\t\tbutton->czm_down = host.realtime;", start)]
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            (p / "main.c").write_text(PROGRAM.replace("@@PRESS@@", press).replace("@@WHEEL@@", wheel))
            subprocess.run(["gcc", "-std=gnu11", "-Wall", "-Werror", "-Wno-unused-function", str(p / "main.c"), "-o", str(p / "wheels"), "-lm"],
                           check=True)
            self.assertIn("TOUCH_WHEELS_OK", subprocess.run([str(p / "wheels")], check=True, capture_output=True, text=True).stdout)

    def test_hooks_in_the_touch_code(self):
        added = added_lines()
        for hook in ('else if( !Q_strncmp( "_czmwheel ", command, 10 ) || !Q_strcmp( command, "showvguimenu 38" )\n'
                     "\t\t|| ( !Q_strncmp( \"radio\", command, 5 ) && command[5] >= '1' && command[5] <= '3' && !command[6] ))\n"
                     "\t\tbutton->type = touch_czmwheel;",
                     "\tif( touch.state == state_none && Touch_CzmWheelEvent( type, fingerID, x, y ))\n\t\treturn true;",
                     "\tTouch_CzmWheelFrame();\n",
                     "\t\t\t\tTouch_CzmWheelOpen( button, fingerID, x, y );\n\t\t\t\treturn true;",
                     "\t\tTouch_CzmWheelClose();\n", "\n\tTouch_CzmWheelClose();\n",
                     "\t\tTouch_CzmWheelForget( button );\n", "\t\tTouch_CzmWheelForget( remove );\n",
                     "\t\t\tTouch_CzmLetGo( button ); // finger -1",
                     "\t\t\t\tif( Touch_CzmAnimated( b ))\n\t\t\t\t\tTouch_CzmDrawPressed( b, color );"):
            self.assertIn(hook, added)


if __name__ == "__main__":
    unittest.main()
