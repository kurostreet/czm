/*
	Counter Zombie Mobile, Survival server: ZombieAutoRevive of the Kontra server.

	Once the infection has begun, a player who dies comes back as a zombie after 20 seconds,
	and a player who joins mid-round waits the same 20 seconds. At death the screen goes dark
	for a second, as on Kontra; a countdown shows how long is left. Rounds of Zombie Plague that
	forbid respawning (zp_nem_allow_respawn and the like) keep their rule. Zombie Plague's own
	deathmatch stays off (zp_deathmatch 0), so nobody is brought back twice.
*/
#include <amxmodx>
#include <hamsandwich>
#include <zombieplague>
#include <czm_survival>

#define PLUGIN "CZM Revive"
#define VERSION "1.0"
#define AUTHOR "kurostreet"

new g_left[MAX_PLAYERS + 1];
new g_msgScreenFade, g_hud;
new g_cvarDelay;
new bool:g_roundEnded;

public plugin_init()
{
	register_plugin(PLUGIN, VERSION, AUTHOR);
	g_cvarDelay = create_cvar("czm_revive_delay", "20", _, "Seconds before a dead player comes back as a zombie", true, 1.0);
	RegisterHam(Ham_Killed, "player", "fw_killed_post", 1);
	RegisterHam(Ham_Spawn, "player", "fw_spawn_post", 1);
	g_msgScreenFade = get_user_msgid("ScreenFade");
	g_hud = CreateHudSyncObj();
	set_task(1.0, "task_second", _, _, _, "b");
	register_logevent("ev_round_end", 2, "1=Round_End");
}

public ev_round_end()
{
	g_roundEnded = true;
}

public zp_round_started(gamemode, id)
{
	g_roundEnded = false;
}

bool:respawn_allowed()
{
	if (g_roundEnded || !zp_has_round_started())
		return false;
	if (zp_is_nemesis_round() && !get_cvar_num("zp_nem_allow_respawn"))
		return false;
	if (zp_is_survivor_round() && !get_cvar_num("zp_surv_allow_respawn"))
		return false;
	if (zp_is_swarm_round() && !get_cvar_num("zp_swarm_allow_respawn"))
		return false;
	if (zp_is_plague_round() && !get_cvar_num("zp_plague_allow_respawn"))
		return false;
	return true;
}

public fw_killed_post(victim, attacker, shouldgib)
{
	if (!is_user_connected(victim) || is_user_bot(victim))
		return;
	message_begin(MSG_ONE_UNRELIABLE, g_msgScreenFade, _, victim);
	write_short(4096);   // a second to darken
	write_short(4096);   // and a second held
	write_short(0x0001); // FFADE_OUT
	write_byte(0);
	write_byte(0);
	write_byte(0);
	write_byte(255);
	message_end();
	g_left[victim] = get_pcvar_num(g_cvarDelay);
}

public task_second()
{
	new bool:allowed = respawn_allowed();
	for (new id = 1; id <= MaxClients; id++)
	{
		if (!is_user_connected(id) || is_user_alive(id) || !(1 <= get_user_team(id) <= 2))
		{
			g_left[id] = 0;
			continue;
		}
		if (!allowed)
			continue;
		if (!g_left[id])
			g_left[id] = get_pcvar_num(g_cvarDelay); // joined mid-round or died before the infection
		if (--g_left[id] <= 0)
		{
			g_left[id] = 0;
			zp_respawn_user(id, ZP_TEAM_ZOMBIE);
			continue;
		}
		if (!is_user_bot(id))
		{
			set_hudmessage(255, 60, 60, -1.0, 0.30, 0, 0.0, 1.1, 0.0, 0.0, -1);
			ShowSyncHudMsg(id, g_hud, czm_lang(id) == CZM_EN ? "Back as a zombie in %d s" : "Возрождение зомби через %d с", g_left[id]);
		}
	}
}

public fw_spawn_post(id)
{
	if (is_user_alive(id))
		g_left[id] = 0;
}

public client_disconnected(id)
{
	g_left[id] = 0;
}
