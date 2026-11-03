/*
	Counter Zombie Mobile, Survival server: AmmoManager of the Kontra server.

	Humans (alive, while a round is on) get their reserve ammo filled to the value of their gun:
	at round start (after 2.5 and 5 seconds), and then every 60 seconds. A reload with the
	reserve run dry is a gamble, as on Kontra: half the time the reserve comes back, half the
	time it misfires: a click, and no ammo for the next 5 seconds.

	Magazine sizes stay those of the game: the game predicts reloads on the phone with its own
	magazine sizes, and a server-side size would make the counter jump.
*/
#include <amxmodx>
#include <cstrike>
#include <fakemeta>
#include <hamsandwich>
#include <zombieplague>
#include <czm_survival>

#define PLUGIN "CZM Ammo"
#define VERSION "1.0"
#define AUTHOR "kurostreet"

#define TASK_START 4500

// Kontra's reserve per gun (AmmoManager_v8, WEAPON_AMMO "reserve")
new const RESERVE[CSW_P90 + 1] = {
	0,
	40,  // CSW_P228
	0,
	35,  // CSW_SCOUT
	0,   // CSW_HEGRENADE
	25,  // CSW_XM1014
	0,   // CSW_C4
	40,  // CSW_MAC10
	100, // CSW_AUG
	0,   // CSW_SMOKEGRENADE
	35,  // CSW_ELITE
	40,  // CSW_FIVESEVEN
	40,  // CSW_UMP45
	40,  // CSW_SG550
	60,  // CSW_GALIL
	60,  // CSW_FAMAS
	40,  // CSW_USP
	40,  // CSW_GLOCK18
	30,  // CSW_AWP
	45,  // CSW_MP5NAVY
	150, // CSW_M249
	25,  // CSW_M3
	70,  // CSW_M4A1
	40,  // CSW_TMP
	40,  // CSW_G3SG1
	0,   // CSW_FLASHBANG
	25,  // CSW_DEAGLE
	35,  // CSW_SG552
	70,  // CSW_AK47
	0,   // CSW_KNIFE
	50   // CSW_P90
};

new const MISFIRE[] = "misfire_while_reloading.mp3";

new g_hMisfire;
new bool:g_roundOn;
new Float:g_blockedUntil[MAX_PLAYERS + 1];
new g_cvarRefill, g_cvarMisfire, g_cvarBlock;

public plugin_precache()
{
	g_hMisfire = czm_sound_precache(MISFIRE);
}

public plugin_init()
{
	register_plugin(PLUGIN, VERSION, AUTHOR);
	g_cvarRefill = create_cvar("czm_ammo_refill", "60", _, "Seconds between reserve refills", true, 5.0);
	g_cvarMisfire = create_cvar("czm_ammo_misfire", "50", _, "Chance in % that a dry reload misfires");
	g_cvarBlock = create_cvar("czm_ammo_block", "5", _, "Seconds without ammo after a misfire");

	register_logevent("ev_round_start", 2, "1=Round_Start");
	register_logevent("ev_round_end", 2, "1=Round_End");

	new name[32];
	for (new w = CSW_P228; w <= CSW_P90; w++)
	{
		if (!RESERVE[w] || !get_weaponname(w, name, charsmax(name)))
			continue;
		RegisterHam(Ham_Weapon_Reload, name, "fw_reload_pre", 0);
	}
	set_task(1.0, "task_refill_check", _, _, _, "b");
}

public ev_round_start()
{
	g_roundOn = true;
	remove_task(TASK_START);
	set_task(2.5, "task_fill_all", TASK_START);
	set_task(5.0, "task_fill_all", TASK_START);
}

public ev_round_end()
{
	g_roundOn = false;
	remove_task(TASK_START);
}

public task_fill_all()
{
	for (new id = 1; id <= MaxClients; id++)
		fill(id);
}

new Float:g_nextRefill;

public task_refill_check()
{
	new Float:now = get_gametime();
	if (!g_roundOn)
	{
		g_nextRefill = now + get_pcvar_float(g_cvarRefill);
		return;
	}
	if (now < g_nextRefill)
		return;
	g_nextRefill = now + get_pcvar_float(g_cvarRefill);
	task_fill_all();
}

bool:human(id)
{
	return is_user_alive(id) && !zp_get_user_zombie(id) && !zp_get_user_survivor(id);
}

fill(id)
{
	if (!g_roundOn || !human(id) || get_gametime() < g_blockedUntil[id])
		return;
	new weapons[32], count;
	get_user_weapons(id, weapons, count);
	for (new i = 0; i < count; i++)
	{
		new w = weapons[i];
		if (w > 0 && w <= CSW_P90 && RESERVE[w] && cs_get_user_bpammo(id, w) < RESERVE[w])
			cs_set_user_bpammo(id, w, RESERVE[w]);
	}
}

public fw_reload_pre(weapon)
{
	new id = get_pdata_cbase(weapon, 41, 4); // m_pPlayer
	if (!(1 <= id <= MaxClients) || !g_roundOn || !human(id))
		return HAM_IGNORED;
	new w = cs_get_weapon_id(weapon);
	if (!(0 < w <= CSW_P90) || !RESERVE[w] || cs_get_user_bpammo(id, w) > 0)
		return HAM_IGNORED;
	new Float:now = get_gametime();
	if (now < g_blockedUntil[id])
		return HAM_IGNORED;
	if (random_num(1, 100) <= get_pcvar_num(g_cvarMisfire))
	{
		g_blockedUntil[id] = now + get_pcvar_float(g_cvarBlock);
		czm_play_sound(id, g_hMisfire);
		return HAM_IGNORED;
	}
	cs_set_user_bpammo(id, w, RESERVE[w]);
	return HAM_IGNORED;
}

public client_disconnected(id)
{
	g_blockedUntil[id] = 0.0;
}
