/* Counter Zombie Mobile: how the scope and fire buttons act on a touch screen. GPL-2.0-or-later.

Scope (czm_scope_mode) for the weapons with a scope: AWP, Scout, G3SG1, SG 550, AUG, SG 552.
  0 tap   - every press is the next zoom step, as on a PC (the stock +attack2);
  1 hold  - in the scope while the button is held, out of it when the button is let go;
  2 mixed - from the open view a short tap zooms in and stays, a long press works like "hold";
            a tap in the scope is the next step, as with "tap".
The weapon takes one zoom step per +attack2 and at most one every 0.3 s, so leaving the scope
from the first level goes through the second one. While the client walks out of the scope it
shows the open view and holds the fire back: the steps on the way are never seen and never shot
through. Each step waits until the server reports the new zoom, a slow connection cannot skip
past the open view. AWP and Scout zoom back in by themselves after the bolt; when the scope was
let go meanwhile, the client walks out again.

Fire on release (czm_sniper_release) for AWP and Scout: the shot goes when "Fire" is let go.
The fire button lies on the look zone, so the finger aims by sliding over it.

The left fire button (czm_fire_left) is shown by the engine (patch czm-left-fire).
*/
#include "hud.h"
#include "cl_util.h"
#include "in_buttons.h"
#include "weapontype.h"

float HUD_GetFOV( void );
bool CL_IsDead( void );

enum { SCOPE_TAP, SCOPE_HOLD, SCOPE_MIXED };

#define CZM_ZOOM_STEP 0.33f   // the scoped weapons take a zoom step every 0.3 s
#define CZM_STEP_WAIT 1.0f    // no word from the server about a step: try the next one anyway
#define CZM_TAP 0.25f         // mixed: a shorter press is a tap
#define CZM_RESUME 1.8f       // AWP 1.45 s and Scout 1.25 s after a shot zoom back in
#define CZM_GIVE_UP 3.0f

static cvar_t *s_scopeMode, *s_release, *s_defaultFov;

static struct
{
	bool held;      // the scope button is down and handled here
	bool hold;      // letting it go leaves the scope
	int weapon;     // the weapon the scope button was pressed with
	float pressed;
	bool leave;     // walking out of the scope
	float leaveUntil;
	bool reenter;   // pressed again while walking out: zoom in once out
	bool step;      // one zoom step in the next command
	float nextStep; // the weapon takes the next step from this time
	float stepFov;  // the zoom when the last step was sent
	float stepAt;
	bool fireHeld;
	int fireWeapon;
	bool fire;      // the shot of a let-go fire button, in the next command
	float shot;     // the last command with a bolt-action shot
} s;

void CZM_ShootingInit( void )
{
	s_scopeMode = gEngfuncs.pfnRegisterVariable( "czm_scope_mode", "0", FCVAR_ARCHIVE );
	s_release = gEngfuncs.pfnRegisterVariable( "czm_sniper_release", "0", FCVAR_ARCHIVE );
	gEngfuncs.pfnRegisterVariable( "czm_fire_left", "0", FCVAR_ARCHIVE );
}

static int Weapon( void )
{
	return CL_IsDead() ? 0 : gHUD.m_Ammo.CurrentWeaponId();
}

static bool HasScope( int weapon )
{
	switch( weapon )
	{
	case WEAPON_AWP:
	case WEAPON_SCOUT:
	case WEAPON_G3SG1:
	case WEAPON_SG550:
	case WEAPON_AUG:
	case WEAPON_SG552:
		return true;
	}
	return false;
}

static bool BoltAction( int weapon )
{
	return weapon == WEAPON_AWP || weapon == WEAPON_SCOUT;
}

// the zoom the server reports; 0 and the default field of view are the open view
static bool Zoomed( void )
{
	const float fov = HUD_GetFOV();
	float open;

	if( !s_defaultFov )
		s_defaultFov = gEngfuncs.pfnGetCvarPointer( "default_fov" ); // the HUD makes it after the input
	open = s_defaultFov ? s_defaultFov->value : 90.0f;

	if( open <= 0.0f )
		open = 90.0f;
	return fov > 0.0f && fov < open - 0.5f;
}

static int ScopeMode( void )
{
	return s_scopeMode ? (int)s_scopeMode->value : SCOPE_TAP;
}

// the client walks out of the scope: show the open view and do not shoot
bool CZM_ScopeHidden( void )
{
	return s.leave && Zoomed();
}

// +attack2: true when handled here, the stock button stays up
bool CZM_ScopeDown( void )
{
	const int mode = ScopeMode(), weapon = Weapon();

	// a press always starts afresh: a release lost to a menu that opened meanwhile must not stick,
	// and the release of a press left to the stock button must reach it
	s.held = s.reenter = false;
	if( mode != SCOPE_HOLD && mode != SCOPE_MIXED )
		return false;
	if( !HasScope( weapon ))
		return false;

	s.held = true;
	s.weapon = weapon;
	s.pressed = gEngfuncs.GetClientTime();
	if( CZM_ScopeHidden( ))
	{
		// still on the way out: finish it, then zoom in from the open view
		s.hold = true;
		s.reenter = true;
		return true;
	}
	s.leave = false;
	if( !Zoomed( ))
	{
		s.hold = true;
		s.step = true; // zoom in
	}
	else if( mode == SCOPE_MIXED )
	{
		s.hold = false;
		s.step = true; // a tap in the scope: the next step
	}
	else
		s.hold = true; // already in the scope (zoomed back after a shot): letting go leaves it
	return true;
}

bool CZM_ScopeUp( void )
{
	const float now = gEngfuncs.GetClientTime();

	if( !s.held )
		return false;

	s.held = false;
	if( s.reenter )
	{
		s.reenter = false; // let go before the scope was left: just leave it
		return true;
	}
	if( s.hold && ( ScopeMode() == SCOPE_HOLD || now - s.pressed >= CZM_TAP ) && Weapon() == s.weapon )
	{
		s.step = false; // a zoom step not sent yet is not needed any more
		s.leave = true;
		s.leaveUntil = now + CZM_GIVE_UP;
	}
	return true;
}

// +attack: true when handled here
bool CZM_FireDown( void )
{
	const int weapon = Weapon();

	if( s.fireHeld )
		return true;
	if( !s_release || s_release->value == 0.0f || !BoltAction( weapon ))
		return false;

	s.fireHeld = true;
	s.fireWeapon = weapon;
	return true;
}

bool CZM_FireUp( void )
{
	if( !s.fireHeld )
		return false;

	s.fireHeld = false;
	if( Weapon() == s.fireWeapon )
		s.fire = true;
	return true;
}

// every command: zoom steps, the shot of a let-go fire button, no shots while leaving the scope
int CZM_ShootingButtons( int buttons )
{
	const float now = gEngfuncs.GetClientTime();
	const int weapon = Weapon();
	const bool zoomed = Zoomed();
	bool inFlight;

	// a new map starts the client clock again
	if( s.nextStep > now + CZM_GIVE_UP || s.stepAt > now || s.shot > now )
		s.nextStep = s.stepAt = s.shot = 0.0f;
	if( s.leaveUntil > now + CZM_GIVE_UP )
		s.leave = false;

	// another weapon in the hands or death: nothing to finish
	if( weapon != s.weapon )
	{
		s.step = s.leave = s.hold = s.reenter = false;
		s.weapon = weapon;
	}
	if( s.fireHeld && weapon != s.fireWeapon )
		s.fireHeld = false;

	// the last step is sent and the server has not reported a new zoom yet
	inFlight = s.stepAt > 0.0f && now - s.stepAt < CZM_STEP_WAIT && HUD_GetFOV() == s.stepFov;

	if( s.leave )
	{
		if( now > s.leaveUntil )
			s.leave = s.reenter = false;
		else if( zoomed )
		{
			if( !inFlight )
				s.step = true;
		}
		else if( !inFlight && ( s.reenter || now - s.shot > CZM_RESUME ))
		{
			// out of the scope, and a shot cannot bring it back any more
			s.leave = false;
			if( s.reenter )
			{
				s.reenter = false;
				s.step = s.held; // pressed again on the way out and still held: zoom in
			}
		}
	}

	if( s.step && now >= s.nextStep )
	{
		buttons |= IN_ATTACK2;
		s.step = false;
		s.nextStep = now + CZM_ZOOM_STEP;
		s.stepFov = HUD_GetFOV();
		s.stepAt = now;
	}

	if( s.fire )
	{
		buttons |= IN_ATTACK;
		s.fire = false;
	}

	if( CZM_ScopeHidden( ))
		buttons &= ~IN_ATTACK;

	if(( buttons & IN_ATTACK ) && BoltAction( weapon ))
		s.shot = now;

	return buttons;
}
