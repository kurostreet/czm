"""Scope modes and fire on release on a touch screen (cl_dll/input/czm_shooting.cpp), with a server
that takes one zoom step per +attack2 at most every 0.3 s and reports the zoom after the ping."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

HUD = r'''
#pragma once
#include <cstdio>
#include <cstring>
#define FCVAR_ARCHIVE 1
#define MAX_WEAPONS 32
struct cvar_t { const char *name; float value; };
static cvar_t cvars[] = { { "czm_scope_mode", 0 }, { "czm_sniper_release", 0 }, { "czm_fire_left", 0 }, { "default_fov", 90 } };
static float clientTime;
static cvar_t *FindCvar( const char *name ) { for( auto &c : cvars ) if( !strcmp( c.name, name )) return &c; return nullptr; }
struct Engine {
 cvar_t *( *pfnRegisterVariable )( const char *, const char *, int );
 cvar_t *( *pfnGetCvarPointer )( const char * );
 float ( *GetClientTime )( void );
};
static Engine gEngfuncs = { []( const char *n, const char *, int ) { return FindCvar( n ); }, FindCvar, []() { return clientTime; } };
static int weaponInHands;
struct Ammo { int CurrentWeaponId( void ) const { return weaponInHands; } };
struct Hud { Ammo m_Ammo; };
static Hud gHUD;
'''

SCENARIOS = r'''
#include <cassert>
#include <deque>
// the server: one zoom step per +attack2 at most every 0.3 s, the new zoom reaches the client after the ping
static float serverFov = 90, nextZoom, clientFov = 90, ping = 0.05f, boltUntil;
static int lastZoom; static bool resume;
static std::deque<std::pair<float, float>> replies;
static bool dead;
static int shots, steps;
float HUD_GetFOV( void ) { return clientFov; }
bool CL_IsDead( void ) { return dead; }
static void Levels( int weapon, int *first, int *second ) {
 *first = weapon == WEAPON_AUG || weapon == WEAPON_SG552 ? 55 : 40;
 *second = weapon == WEAPON_AWP ? 10 : weapon == WEAPON_AUG || weapon == WEAPON_SG552 ? 0 : 15;
}
static void SetServerFov( float fov ) { serverFov = fov; replies.push_back( { clientTime + ping, fov } ); }
// one frame: the client makes a command from the held buttons, the server runs it
static int Frame( int held = 0, float dt = 0.02f ) {
 clientTime += dt;
 while( !replies.empty() && replies.front().first <= clientTime ) { clientFov = replies.front().second; replies.pop_front(); }
 int buttons = CZM_ShootingButtons( held );
 if( ( buttons & IN_ATTACK2 ) && clientTime >= nextZoom ) {
  int first, second; Levels( weaponInHands, &first, &second ); steps++;
  SetServerFov( serverFov == 90 ? first : serverFov == first && second ? second : 90 );
  nextZoom = clientTime + 0.3f;
 }
 if( ( buttons & IN_ATTACK ) && clientTime >= boltUntil ) {
  shots++;
  if( weaponInHands == WEAPON_AWP || weaponInHands == WEAPON_SCOUT ) {
   boltUntil = clientTime + 1.45f;
   if( serverFov != 90 ) { lastZoom = serverFov; resume = true; SetServerFov( 90 ); }
  }
 }
 if( resume && clientTime >= boltUntil ) { resume = false; SetServerFov( lastZoom ); }
 return buttons;
}
static void Run( float seconds, int held = 0 ) { for( float t = 0; t < seconds; t += 0.02f ) Frame( held ); }
static void Reset( int weapon, int mode, int release = 0 ) {
 Run( 3.5f ); weaponInHands = weapon; Run( 0.2f );
 FindCvar( "czm_scope_mode" )->value = mode; FindCvar( "czm_sniper_release" )->value = release;
 serverFov = clientFov = 90; replies.clear(); resume = false; Run( 3.5f ); shots = steps = 0;
}
// the view the player sees and whether a shot can go out
static bool Hidden( void ) { return CZM_ScopeHidden(); }

int main() {
 CZM_ShootingInit();
 // tap: the stock button, nothing is taken over
 Reset( WEAPON_AWP, 0 );
 assert( !CZM_ScopeDown() && !CZM_ScopeUp() && !CZM_FireDown() && !CZM_FireUp() );

 // hold with AWP: in the scope while held, out of it after the release through the second level unseen
 Reset( WEAPON_AWP, 1 );
 assert( CZM_ScopeDown() ); Run( 0.4f ); assert( clientFov == 40 && steps == 1 );
 Run( 1.0f ); assert( clientFov == 40 && steps == 1 ); // held: stays on the first level
 assert( CZM_ScopeUp() );
 bool sawHidden = false;
 for( int i = 0; i < 60; i++ ) {
  int b = Frame( IN_ATTACK );
  if( clientFov != 90 ) { assert( Hidden() && !( b & IN_ATTACK )); sawHidden = true; } // never shown, never shot through
 }
 assert( sawHidden && clientFov == 90 && serverFov == 90 && steps == 3 && !Hidden() );
 assert( shots >= 1 ); // once out, the held fire works again

 // hold, a quick tap: the zoom arrives after the release and is walked out of, unseen
 Reset( WEAPON_SCOUT, 1 ); ping = 0.15f;
 assert( CZM_ScopeDown() ); Frame(); assert( CZM_ScopeUp() );
 for( int i = 0; i < 100; i++ ) { Frame(); if( clientFov != 90 ) assert( Hidden() ); }
 assert( clientFov == 90 && serverFov == 90 && steps == 3 );

 // a slow connection: every step waits for the reported zoom, the open view is never skipped
 Reset( WEAPON_AWP, 1 ); ping = 0.6f;
 assert( CZM_ScopeDown() ); Run( 1.5f ); assert( clientFov == 40 ); assert( CZM_ScopeUp() );
 Run( 4.0f ); assert( clientFov == 90 && serverFov == 90 && steps == 3 );
 ping = 0.05f;

 // one zoom level (AUG): one step in, one step out
 Reset( WEAPON_AUG, 1 );
 assert( CZM_ScopeDown() ); Run( 0.5f ); assert( clientFov == 55 ); assert( CZM_ScopeUp() ); Run( 1.0f );
 assert( clientFov == 90 && steps == 2 );

 // mixed: a short tap zooms in and stays, a tap in the scope is the next step, a long press leaves on release
 Reset( WEAPON_AWP, 2 );
 assert( CZM_ScopeDown() ); Run( 0.1f ); assert( CZM_ScopeUp() ); Run( 1.0f ); assert( clientFov == 40 && steps == 1 );
 assert( CZM_ScopeDown() ); Run( 0.1f ); assert( CZM_ScopeUp() ); Run( 1.0f ); assert( clientFov == 10 && steps == 2 );
 assert( CZM_ScopeDown() ); Run( 0.1f ); assert( CZM_ScopeUp() ); Run( 1.0f ); assert( clientFov == 90 && steps == 3 );
 assert( CZM_ScopeDown() ); Run( 0.6f ); assert( clientFov == 40 ); assert( CZM_ScopeUp() ); Run( 1.5f );
 assert( clientFov == 90 && !Hidden() );

 // other weapons keep the stock +attack2 (silencer, burst, knife)
 Reset( WEAPON_M4A1, 1 );
 assert( !CZM_ScopeDown() && !CZM_ScopeUp() );

 // hold, a shot in the scope: AWP leaves the scope for the bolt and comes back while still held
 Reset( WEAPON_AWP, 1 );
 assert( CZM_ScopeDown() ); Run( 0.5f ); Frame( IN_ATTACK ); assert( shots == 1 );
 Run( 2.0f ); assert( clientFov == 40 );
 // let go during the bolt: the zoom coming back is walked out of unseen
 Frame( IN_ATTACK ); assert( shots == 2 ); Run( 0.2f ); assert( CZM_ScopeUp() ); assert( clientFov == 90 );
 for( int i = 0; i < 150; i++ ) { Frame(); if( clientFov != 90 ) assert( Hidden() ); }
 assert( clientFov == 90 && serverFov == 90 && !Hidden() );

 // pressed again while walking out: out first, then in again
 Reset( WEAPON_AWP, 1 );
 assert( CZM_ScopeDown() ); Run( 0.5f ); assert( CZM_ScopeUp() ); Frame(); assert( Hidden() );
 assert( CZM_ScopeDown() ); Run( 1.5f ); assert( clientFov == 40 && !Hidden() );
 assert( CZM_ScopeUp() ); Run( 1.5f ); assert( clientFov == 90 );

 // switching the weapon ends it all
 Reset( WEAPON_AWP, 1 );
 assert( CZM_ScopeDown() ); Run( 0.5f ); weaponInHands = WEAPON_KNIFE; serverFov = clientFov = 90; Frame();
 assert( CZM_ScopeUp() ); Run( 1.0f ); assert( !Hidden() && steps == 1 );

 // fire on release: the shot goes on letting go, only for AWP and Scout
 Reset( WEAPON_AWP, 0, 1 );
 assert( CZM_FireDown() ); Run( 1.0f ); assert( shots == 0 );
 assert( CZM_FireUp() ); { int b = Frame(); assert( b & IN_ATTACK ); } assert( shots == 1 );
 { int b = Frame(); assert( !( b & IN_ATTACK )); }
 Reset( WEAPON_SCOUT, 0, 1 ); assert( CZM_FireDown() ); assert( CZM_FireUp() ); Frame(); assert( shots == 1 );
 Reset( WEAPON_AK47, 0, 1 ); assert( !CZM_FireDown() && !CZM_FireUp() );
 Reset( WEAPON_AWP, 0, 1 ); assert( CZM_FireDown() ); weaponInHands = WEAPON_DEAGLE; Frame(); assert( !CZM_FireUp() );
 // dead: the stock buttons (the spectator uses them)
 Reset( WEAPON_AWP, 1, 1 ); dead = true; assert( !CZM_FireDown() && !CZM_ScopeDown() ); dead = false;
 puts( "TOUCH_SHOOTING_OK" );
}
'''


class TouchShootingTests(unittest.TestCase):
    def test_scope_modes_and_fire_on_release(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            (p / "hud.h").write_text(HUD)
            (p / "cl_util.h").write_text("#pragma once\n")
            source = (ROOT / "cl_dll/input/czm_shooting.cpp").read_text()
            (p / "main.cpp").write_text(source + SCENARIOS)
            exe = p / "shooting"
            subprocess.run(["g++", "-std=c++11", "-Wall", "-Werror", "-Wno-unused-function", "-I" + folder,
                            "-I" + str(ROOT / "common"), "-I" + str(ROOT / "dlls"), str(p / "main.cpp"), "-o", str(exe)],
                           check=True)
            result = subprocess.run([str(exe)], check=True, capture_output=True, text=True)
            self.assertIn("TOUCH_SHOOTING_OK", result.stdout)

    def test_input_and_view_use_it(self):
        source = (ROOT / "cl_dll/input.cpp").read_text()
        self.assertIn("if( CZM_ScopeDown( ))\n\t\treturn;\n\n\tKeyDown(&in_attack2);", source)
        self.assertIn("if( CZM_FireDown( ))\n\t\treturn;\n\n\tKeyDown( &in_attack );", source)
        self.assertIn("cmd->buttons = CZM_ShootingButtons( cmd->buttons );", source)
        self.assertIn("CZM_ShootingInit();", source)
        self.assertIn("if( CZM_ScopeHidden( ))\n\t{\n\t\tm_iFOV = default_fov->value;", (ROOT / "cl_dll/hud_redraw.cpp").read_text())
        self.assertIn("gHUD.m_iFOV > 40 || CZM_ScopeHidden()", (ROOT / "cl_dll/hud/sniperscope.cpp").read_text())


if __name__ == "__main__":
    unittest.main()
