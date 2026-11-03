/*
	Counter Zombie Mobile, Survival server: what LVL MOD purchases do in the game, as on Kontra.

	Weapon crate (30 minutes, at every spawn as a human):
	  gold    golden AK47 and Deagle          mini   minigun (M249) and a napalm grenade
	  arm50   50 armour                        arm100 100 armour
	  invis   3 charges of auto invisibility: 10 seconds when a zombie comes close
	  blind   a knife hit blinds the zombie for 2.2 seconds
	  gas     the gas mask stops one infection per round
	Critical shot (shop): 3% of the bullets that hit a zombie burn it, freeze it for a second or
	  deal 45 more damage.
	Weapon sounds (shop): the AK47, the minigun, the Deagle and the knife sound like on Kontra.
	Airdrop: every 5-10 minutes a box falls on the map; the first human of CZM to reach it gets tokens.

	czm_lvl.amxx keeps who has what; the API (survival.py) decides every number of tokens.
*/
#include <amxmodx>
#include <cstrike>
#include <engine>
#include <fakemeta>
#include <fun>
#include <hamsandwich>
#include <zombieplague>
#include <czm_survival>
#include <czm_lvl>

#define PLUGIN "CZM LVL FX"
#define VERSION "1.0"
#define AUTHOR "kurostreet"

#define TASK_GIVE 4700
#define TASK_INVIS 4800
#define TASK_BURN 4900
#define TASK_FREEZE 5000
#define TASK_LIGHT 10000
#define AIRDROP_CLASS "czm_airdrop"

#define CRIT_CHANCE 3
#define FIRE_DAMAGE 6.0
#define FIRE_TICKS 4
#define DMG_BONUS 45.0
#define INVIS_SECONDS 10.0
#define INVIS_RADIUS 160.0
#define BLIND_SECONDS 2.2

// Kontra AIR_TOKEN_TABLE: tokens and their weights
new const AIR_TOKENS[] = { 10, 25, 50, 75, 100, 150, 250, 500 };
new const AIR_WEIGHT[] = { 90, 60, 40, 25, 15, 8, 4, 1 };

enum { KIT_AK = 0, KIT_MINI, KIT_DEAGLE, KIT_KNIFE, KIT_COUNT };
new const KIT_ID[KIT_COUNT][] = { "gold_ak_guitar", "minigun_mg", "gold_deagle_laser", "knife_starwars" };
new const KIT_WEAPON[KIT_COUNT] = { CSW_AK47, CSW_M249, CSW_DEAGLE, CSW_KNIFE };
new const KIT_DRAW[KIT_COUNT][] = { "avalon_deluxe_gt_draw.wav", "", "", "" };
new const KIT_SHOT[KIT_COUNT][] = { "avalon_deluxe_gt.wav", "minigun_atack.mp3", "laser_atack.mp3", "star_wars_knife_atack.mp3" };
new const KIT_RELOAD[KIT_COUNT][] = { "", "minigun_reload.mp3", "laser_reload.mp3", "star_wars_knife_reload.mp3" };
new g_hDraw[KIT_COUNT], g_hShot[KIT_COUNT], g_hReload[KIT_COUNT], g_hKnifeHit;
new g_hAirSpawn, g_hAirTake, g_hGold, g_hMini;
new g_beam;

new bool:g_invisible[MAX_PLAYERS + 1], bool:g_gasUsed[MAX_PLAYERS + 1];
// what this life already got from the crate: a dropped gun does not come back until the next spawn
new bool:g_gotGold[MAX_PLAYERS + 1], bool:g_gotMini[MAX_PLAYERS + 1], bool:g_gotArmor[MAX_PLAYERS + 1];
new Float:g_nextShotSound[MAX_PLAYERS + 1], Float:g_nextReloadSound[MAX_PLAYERS + 1];
new g_clipBefore[MAX_PLAYERS + 1];
new g_burnTicks[MAX_PLAYERS + 1];
new Float:g_nextAirdrop;
new g_hud;

public plugin_precache()
{
	for (new k = 0; k < KIT_COUNT; k++)
	{
		g_hDraw[k] = KIT_DRAW[k][0] ? czm_sound_precache(KIT_DRAW[k]) : -1;
		g_hShot[k] = czm_sound_precache(KIT_SHOT[k]);
		g_hReload[k] = KIT_RELOAD[k][0] ? czm_sound_precache(KIT_RELOAD[k]) : -1;
	}
	g_hKnifeHit = czm_sound_precache("s_atack.mp3");
	g_hAirSpawn = czm_sound_precache("airdrop_spawn.mp3");
	g_hAirTake = czm_sound_precache("airdrop_raised.mp3");
	g_hGold = czm_sound_precache("x_goldenAK47.mp3");
	g_hMini = czm_sound_precache("x_minigun.mp3");
	g_beam = precache_model("sprites/laserbeam.spr");
	precache_model("models/w_weaponbox.mdl");
}

public plugin_init()
{
	register_plugin(PLUGIN, VERSION, AUTHOR);
	RegisterHam(Ham_Spawn, "player", "fw_spawn_post", 1);
	RegisterHam(Ham_TakeDamage, "player", "fw_damage_pre", 0);
	RegisterHam(Ham_Killed, "player", "fw_killed_post", 1);
	new name[32];
	for (new k = 0; k < KIT_COUNT; k++)
	{
		get_weaponname(KIT_WEAPON[k], name, charsmax(name));
		RegisterHam(Ham_Weapon_PrimaryAttack, name, "fw_attack_pre", 0);
		RegisterHam(Ham_Weapon_PrimaryAttack, name, "fw_attack_post", 1);
		RegisterHam(Ham_Weapon_Reload, name, "fw_reload_post", 1);
		RegisterHam(Ham_Item_Deploy, name, "fw_deploy_post", 1);
	}
	register_logevent("ev_round_start", 2, "1=Round_Start");
	register_touch(AIRDROP_CLASS, "player", "on_airdrop_touch");
	register_think(AIRDROP_CLASS, "on_airdrop_think");
	g_hud = CreateHudSyncObj();
	g_nextAirdrop = get_gametime() + random_float(300.0, 600.0);
	set_task(0.3, "task_tick", _, _, _, "b");
}

public ev_round_start()
{
	for (new id = 1; id <= MaxClients; id++)
		g_gasUsed[id] = false;
}

public client_disconnected(id)
{
	remove_task(TASK_GIVE + id);
	remove_task(TASK_INVIS + id);
	remove_task(TASK_BURN + id);
	remove_task(TASK_FREEZE + id);
	g_invisible[id] = false;
	g_burnTicks[id] = 0;
}

bool:human(id)
{
	return is_user_alive(id) && !zp_get_user_zombie(id) && !zp_get_user_survivor(id);
}

// ---------------------------------------------------------------- the crate at every spawn

public fw_spawn_post(id)
{
	g_gotGold[id] = false;
	g_gotMini[id] = false;
	g_gotArmor[id] = false;
	if (is_user_alive(id) && czm_lvl_ready(id))
	{
		remove_task(TASK_GIVE + id);
		set_task(0.8, "task_give", TASK_GIVE + id);
	}
}

public zp_user_humanized_post(id, survivor)
{
	if (!survivor && czm_lvl_ready(id))
		set_task(0.3, "task_give", TASK_GIVE + id);
}

public czm_lvl_changed(id)
{
	// a crate bought in the middle of a round comes at once
	if (human(id) && !task_exists(TASK_GIVE + id))
		set_task(0.1, "task_give", TASK_GIVE + id);
}

public task_give(taskid)
{
	new id = taskid - TASK_GIVE;
	if (!human(id))
		return;
	if (czm_lvl_crate(id, "gold") && !g_gotGold[id])
	{
		g_gotGold[id] = true;
		give_primary(id, "weapon_ak47", CSW_AK47, 90);
		give_secondary(id, "weapon_deagle", CSW_DEAGLE, 35);
		czm_play_sound(id, g_hGold);
	}
	if (czm_lvl_crate(id, "mini") && !g_gotMini[id])
	{
		g_gotMini[id] = true;
		give_primary(id, "weapon_m249", CSW_M249, 200);
		if (!user_has_weapon(id, CSW_HEGRENADE))
			give_item(id, "weapon_hegrenade");
		czm_play_sound(id, g_hMini);
	}
	new armor = czm_lvl_crate(id, "arm100") ? 100 : (czm_lvl_crate(id, "arm50") ? 50 : 0);
	if (armor && !g_gotArmor[id])
	{
		g_gotArmor[id] = true;
		if (get_user_armor(id) < armor)
			cs_set_user_armor(id, armor, CS_ARMOR_VESTHELM);
	}
}

drop_slot(id, slot)
{
	new weapons[32], count, name[32];
	get_user_weapons(id, weapons, count);
	for (new i = 0; i < count; i++)
	{
		new w = weapons[i];
		new bool:primary = (1 << w) & ((1 << CSW_SCOUT) | (1 << CSW_XM1014) | (1 << CSW_MAC10) | (1 << CSW_AUG) | (1 << CSW_UMP45) | (1 << CSW_SG550)
			| (1 << CSW_GALIL) | (1 << CSW_FAMAS) | (1 << CSW_AWP) | (1 << CSW_MP5NAVY) | (1 << CSW_M249) | (1 << CSW_M3) | (1 << CSW_M4A1)
			| (1 << CSW_TMP) | (1 << CSW_G3SG1) | (1 << CSW_SG552) | (1 << CSW_AK47) | (1 << CSW_P90)) != 0;
		new bool:secondary = (1 << w) & ((1 << CSW_P228) | (1 << CSW_ELITE) | (1 << CSW_FIVESEVEN) | (1 << CSW_USP) | (1 << CSW_GLOCK18) | (1 << CSW_DEAGLE)) != 0;
		if ((slot == 1 && primary) || (slot == 2 && secondary))
		{
			get_weaponname(w, name, charsmax(name));
			engclient_cmd(id, "drop", name);
		}
	}
}

give_primary(id, const weapon[], csw, ammo)
{
	drop_slot(id, 1);
	give_item(id, weapon);
	cs_set_user_bpammo(id, csw, ammo);
}

give_secondary(id, const weapon[], csw, ammo)
{
	drop_slot(id, 2);
	give_item(id, weapon);
	cs_set_user_bpammo(id, csw, ammo);
}

// ---------------------------------------------------------------- invisibility and the airdrop timer

public task_tick()
{
	new Float:now = get_gametime();
	for (new id = 1; id <= MaxClients; id++)
	{
		if (g_invisible[id] || !human(id) || !czm_lvl_charges(id) || !czm_lvl_crate(id, "invis"))
			continue;
		if (zombie_near(id) && czm_lvl_use_charge(id))
		{
			g_invisible[id] = true;
			set_user_rendering(id, kRenderFxNone, 0, 0, 0, kRenderTransAlpha, 12);
			set_task(INVIS_SECONDS, "task_visible", TASK_INVIS + id);
			hud(id, czm_lang(id) == CZM_EN ? "Invisible for 10 s! Charges left: %d" : "Невидимость 10 с! Осталось зарядов: %d", czm_lvl_charges(id));
		}
	}
	if (now >= g_nextAirdrop)
	{
		g_nextAirdrop = now + random_float(300.0, 600.0);
		if (zp_has_round_started())
			drop_airdrop();
	}
}

bool:zombie_near(id)
{
	new Float:origin[3], Float:other[3];
	entity_get_vector(id, EV_VEC_origin, origin);
	for (new z = 1; z <= MaxClients; z++)
	{
		if (!is_user_alive(z) || !zp_get_user_zombie(z))
			continue;
		entity_get_vector(z, EV_VEC_origin, other);
		if (get_distance_f(origin, other) <= INVIS_RADIUS)
			return true;
	}
	return false;
}

public task_visible(taskid)
{
	new id = taskid - TASK_INVIS;
	g_invisible[id] = false;
	if (is_user_connected(id))
		set_user_rendering(id);
}

public zp_user_infected_post(id, infector, nemesis)
{
	if (g_invisible[id])
	{
		remove_task(TASK_INVIS + id);
		g_invisible[id] = false;
	}
}

// ---------------------------------------------------------------- the gas mask

public zp_user_infect_attempt(id, infector, nemesis)
{
	if (nemesis || g_gasUsed[id] || !czm_lvl_crate(id, "gas"))
		return PLUGIN_CONTINUE;
	g_gasUsed[id] = true;
	hud(id, czm_lang(id) == CZM_EN ? "The gas mask saved you from the infection!" : "Противогаз спас от заражения!");
	return ZP_PLUGIN_HANDLED;
}

// ---------------------------------------------------------------- hits: critical shots, the blinding knife

public fw_damage_pre(victim, inflictor, attacker, Float:damage, damagebits)
{
	if (!(1 <= attacker <= MaxClients) || attacker == victim || !is_user_alive(attacker) || !zp_get_user_zombie(victim)
		|| zp_get_user_zombie(attacker) || !czm_lvl_ready(attacker))
		return HAM_IGNORED;
	if (inflictor != attacker || !(damagebits & DMG_BULLET))
		return HAM_IGNORED;
	new weapon = get_user_weapon(attacker);
	if (weapon == CSW_KNIFE)
	{
		if (czm_lvl_crate(attacker, "blind"))
			blind(victim);
		if (has_kit(attacker, KIT_KNIFE))
			czm_emit_sound(attacker, g_hKnifeHit, CHAN_STATIC);
		return HAM_IGNORED;
	}
	new crit[12];
	czm_lvl_item(attacker, "crit", crit, charsmax(crit));
	if (!crit[0] || random_num(1, 100) > CRIT_CHANCE)
		return HAM_IGNORED;
	if (equal(crit, "dmg2"))
	{
		SetHamParamFloat(4, damage + DMG_BONUS);
		hud(attacker, czm_lang(attacker) == CZM_EN ? "CRITICAL: +%d damage" : "КРИТ: +%d урона", floatround(DMG_BONUS));
	}
	else if (equal(crit, "fire"))
	{
		burn(victim, attacker);
		hud(attacker, czm_lang(attacker) == CZM_EN ? "CRITICAL: the zombie is on fire" : "КРИТ: зомби горит");
	}
	else if (equal(crit, "freeze"))
	{
		freeze(victim);
		hud(attacker, czm_lang(attacker) == CZM_EN ? "CRITICAL: the zombie is frozen" : "КРИТ: зомби заморожен");
	}
	return HAM_IGNORED;
}

blind(victim)
{
	message_begin(MSG_ONE_UNRELIABLE, get_user_msgid("ScreenFade"), _, victim);
	write_short(floatround(0.6 * 4096.0));            // fade back
	write_short(floatround(BLIND_SECONDS * 4096.0));  // held white
	write_short(0x0000);
	write_byte(255);
	write_byte(255);
	write_byte(255);
	write_byte(255);
	message_end();
}

burn(victim, attacker)
{
	if (g_burnTicks[victim])
		return;
	g_burnTicks[victim] = FIRE_TICKS;
	set_user_rendering(victim, kRenderFxGlowShell, 255, 90, 0, kRenderNormal, 20);
	new data[2];
	data[0] = victim; data[1] = attacker;
	set_task(0.5, "task_burn", TASK_BURN + victim, data, sizeof data, "a", FIRE_TICKS);
}

public task_burn(const data[])
{
	new victim = data[0], attacker = data[1];
	if (!is_user_alive(victim) || !zp_get_user_zombie(victim) || --g_burnTicks[victim] <= 0)
	{
		g_burnTicks[victim] = 0;
		remove_task(TASK_BURN + victim);
		if (is_user_connected(victim) && !zp_get_user_nemesis(victim))
			set_user_rendering(victim);
		if (!is_user_alive(victim))
			return;
	}
	if (is_user_connected(attacker))
		ExecuteHamB(Ham_TakeDamage, victim, attacker, attacker, FIRE_DAMAGE, DMG_BURN);
}

freeze(victim)
{
	if (task_exists(TASK_FREEZE + victim))
		return;
	set_user_rendering(victim, kRenderFxGlowShell, 60, 140, 255, kRenderNormal, 25);
	set_user_maxspeed(victim, 1.0);
	entity_set_vector(victim, EV_VEC_velocity, Float:{ 0.0, 0.0, 0.0 });
	set_task(1.0, "task_unfreeze", TASK_FREEZE + victim);
}

public task_unfreeze(taskid)
{
	new victim = taskid - TASK_FREEZE;
	if (!is_user_alive(victim))
		return;
	if (!zp_get_user_nemesis(victim))
		set_user_rendering(victim);
	ExecuteHamB(Ham_CS_Player_ResetMaxSpeed, victim);
}

public fw_killed_post(victim, attacker, shouldgib)
{
	remove_task(TASK_BURN + victim);
	remove_task(TASK_FREEZE + victim);
	g_burnTicks[victim] = 0;
}

// ---------------------------------------------------------------- weapon sounds

kit_of(weapon_csw)
{
	for (new k = 0; k < KIT_COUNT; k++)
		if (KIT_WEAPON[k] == weapon_csw)
			return k;
	return -1;
}

bool:has_kit(id, kit)
{
	new have[24];
	czm_lvl_item(id, "wsound", have, charsmax(have));
	return bool:equal(have, KIT_ID[kit]);
}

owner_of(weapon)
{
	return get_pdata_cbase(weapon, 41, 4); // m_pPlayer
}

public fw_attack_pre(weapon)
{
	new id = owner_of(weapon);
	if (1 <= id <= MaxClients)
		g_clipBefore[id] = cs_get_weapon_ammo(weapon);
}

public fw_attack_post(weapon)
{
	new id = owner_of(weapon);
	if (!(1 <= id <= MaxClients) || !is_user_alive(id))
		return;
	new kit = kit_of(cs_get_weapon_id(weapon));
	if (kit < 0 || !has_kit(id, kit))
		return;
	// a gun sounds only when it really fired; a knife on every swing
	if (kit != KIT_KNIFE && cs_get_weapon_ammo(weapon) >= g_clipBefore[id])
		return;
	new Float:now = get_gametime();
	if (now < g_nextShotSound[id])
		return;
	g_nextShotSound[id] = now + (kit == KIT_KNIFE ? 0.5 : 0.2);
	czm_emit_sound(id, g_hShot[kit], CHAN_STATIC);
}

public fw_reload_post(weapon)
{
	new id = owner_of(weapon);
	new kit = kit_of(cs_get_weapon_id(weapon));
	if (!(1 <= id <= MaxClients) || kit < 0 || g_hReload[kit] < 0 || !has_kit(id, kit) || !get_pdata_int(weapon, 54, 4)) // m_fInReload
		return;
	new Float:now = get_gametime();
	if (now < g_nextReloadSound[id])
		return;
	g_nextReloadSound[id] = now + 1.0;
	czm_emit_sound(id, g_hReload[kit], CHAN_STATIC);
}

public fw_deploy_post(weapon)
{
	new id = owner_of(weapon);
	new kit = kit_of(cs_get_weapon_id(weapon));
	if (1 <= id <= MaxClients && kit >= 0 && g_hDraw[kit] >= 0 && has_kit(id, kit))
		czm_emit_sound(id, g_hDraw[kit], CHAN_STATIC);
}

// ---------------------------------------------------------------- the airdrop

drop_airdrop()
{
	new spot = random_spawn();
	if (!spot)
		return;
	remove_entity_name(AIRDROP_CLASS);
	new Float:origin[3];
	entity_get_vector(spot, EV_VEC_origin, origin);
	origin[2] += 120.0;
	new box = create_entity("info_target");
	if (!is_valid_ent(box))
		return;
	entity_set_string(box, EV_SZ_classname, AIRDROP_CLASS);
	entity_set_model(box, "models/w_weaponbox.mdl");
	entity_set_size(box, Float:{ -12.0, -12.0, 0.0 }, Float:{ 12.0, 12.0, 24.0 });
	entity_set_origin(box, origin);
	entity_set_int(box, EV_INT_solid, SOLID_TRIGGER);
	entity_set_int(box, EV_INT_movetype, MOVETYPE_TOSS);
	set_rendering(box, kRenderFxGlowShell, 255, 200, 40, kRenderNormal, 30);
	entity_set_float(box, EV_FL_nextthink, get_gametime() + 180.0);
	light(origin);
	set_task(5.0, "task_light", TASK_LIGHT + box, _, _, "a", 6);
	czm_play_sound(0, g_hAirSpawn);
	czm_chat(0, "^4[LVL]^1 Аирдроп сброшен! Найди золотой ящик — внутри токены.", "^4[LVL]^1 An airdrop has landed! Find the golden box: it holds tokens.");
}

random_spawn()
{
	new spots[64], count, ent = -1;
	while ((ent = find_ent_by_class(ent, "info_player_deathmatch")) > 0 && count < sizeof spots)
		spots[count++] = ent;
	while ((ent = find_ent_by_class(ent, "info_player_start")) > 0 && count < sizeof spots)
		spots[count++] = ent;
	return count ? spots[random(count)] : 0;
}

light(const Float:origin[3])
{
	message_begin(MSG_BROADCAST, SVC_TEMPENTITY);
	write_byte(TE_BEAMPOINTS);
	engfunc(EngFunc_WriteCoord, origin[0]);
	engfunc(EngFunc_WriteCoord, origin[1]);
	engfunc(EngFunc_WriteCoord, origin[2] - 100.0);
	engfunc(EngFunc_WriteCoord, origin[0]);
	engfunc(EngFunc_WriteCoord, origin[1]);
	engfunc(EngFunc_WriteCoord, origin[2] + 900.0);
	write_short(g_beam);
	write_byte(0);   // start frame
	write_byte(0);   // rate
	write_byte(50);  // life, 0.1 s
	write_byte(30);  // width
	write_byte(8);   // noise
	write_byte(255);
	write_byte(200);
	write_byte(40);
	write_byte(200); // brightness
	write_byte(0);
	message_end();
}

public task_light(taskid)
{
	new box = taskid - TASK_LIGHT;
	if (is_valid_ent(box))
	{
		new Float:origin[3];
		entity_get_vector(box, EV_VEC_origin, origin);
		light(origin);
	}
}

public on_airdrop_think(box)
{
	remove_task(TASK_LIGHT + box);
	if (is_valid_ent(box))
		remove_entity(box);
}

public on_airdrop_touch(box, id)
{
	if (!is_valid_ent(box) || !human(id))
		return;
	if (!czm_lvl_ready(id))
	{
		hud(id, czm_lang(id) == CZM_EN ? "Airdrops are for Counter Zombie Mobile players" : "Аирдроп — для игроков Counter Zombie Mobile");
		return;
	}
	remove_task(TASK_LIGHT + box);
	remove_entity(box);
	new total, roll, i;
	for (i = 0; i < sizeof AIR_WEIGHT; i++)
		total += AIR_WEIGHT[i];
	roll = random(total);
	for (i = 0; i < sizeof AIR_WEIGHT; i++)
	{
		if (roll < AIR_WEIGHT[i])
			break;
		roll -= AIR_WEIGHT[i];
	}
	new amount = AIR_TOKENS[min(i, sizeof AIR_TOKENS - 1)];
	czm_lvl_reward(id, amount);
	czm_play_sound(0, g_hAirTake);
	new name[32];
	get_user_name(id, name, charsmax(name));
	czm_chat(0, "^4[LVL]^3 %s^1 забрал аирдроп: ^4%d^1 токенов", "^4[LVL]^3 %s^1 took the airdrop: ^4%d^1 tokens", name, amount);
}

hud(id, const text[], any:...)
{
	static message[160];
	vformat(message, charsmax(message), text, 3);
	set_hudmessage(255, 210, 60, -1.0, 0.72, 0, 0.0, 2.5, 0.1, 0.4, -1);
	ShowSyncHudMsg(id, g_hud, "%s", message);
}
