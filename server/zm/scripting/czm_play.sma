// CZM: team entry, a separate Zombie Plague menu and authoritative aim health.
#include <amxmodx>
#include <cstrike>
#include <fun>
#include <fakemeta>
#include <hamsandwich>
#include <zombieplague>
#include <czm_survival>
#include <czm_menu>

new g_msgAim, g_zp = -1;
new Trie:g_purchased;
new g_maxHp[MAX_PLAYERS + 1], g_teamChoice[MAX_PLAYERS + 1];
new g_joinUserid[MAX_PLAYERS + 1], g_joinTeam[MAX_PLAYERS + 1];
new g_aimSent[MAX_PLAYERS + 1][3];
new Float:g_aimHeartbeat[MAX_PLAYERS + 1], Float:g_nextJoin[MAX_PLAYERS + 1];
new bool:g_aimUi[MAX_PLAYERS + 1];

public plugin_natives()
{
    register_library("czm_play");
}

public plugin_init()
{
    register_plugin("CZM Play", "1.0", "kurostreet");
    g_purchased = TrieCreate();
    register_clcmd("czm_join", "cmd_join");
    register_clcmd("czm_weapons", "cmd_weapons");
    register_clcmd("buy", "cmd_weapons");
    register_clcmd("buyequip", "cmd_weapons");
    register_clcmd("autobuy", "cmd_weapons");
    register_clcmd("rebuy", "cmd_weapons");
    register_clcmd("czm_zombie_menu", "cmd_zombie_menu");
    g_msgAim = engfunc(EngFunc_RegUserMsg, "CzmAim", 9);
    RegisterHam(Ham_Spawn, "player", "spawn_post", 1);
    register_event("HLTV", "new_round", "a", "1=0", "2=0");
    set_task(0.15, "task_aim", _, _, _, "b");
}

public client_putinserver(id)
{
    g_maxHp[id] = 0;
    g_teamChoice[id] = g_joinUserid[id] = g_joinTeam[id] = 0;
    g_nextJoin[id] = g_aimHeartbeat[id] = 0.0;
    g_aimUi[id] = false;
    for (new k = 0; k < 3; k++) g_aimSent[id][k] = -1;
    if (!is_user_bot(id) && !is_user_hltv(id))
        query_client_cvar(id, "czm_aim_ui", "aim_capability");
}

public client_disconnected(id)
{
    g_aimUi[id] = false;
    g_joinUserid[id] = 0;
    remove_task(id + 7200);
    remove_task(id + 7300);
}

public aim_capability(id, const name[], const value[])
{
    if (is_user_connected(id)) g_aimUi[id] = str_to_num(value) >= 1;
}

public czm_capable(id, unused)
{
    return is_user_connected(id) && czm_menu_rich(id);
}

public czm_weapon_open(id, unused)
{
    return is_user_connected(id); // the patched mod opens its own real weapon catalog
}

public czm_team_open(id, unused)
{
    if (!czm_capable(id, 0)) return 0;
    client_cmd(id, "showvguimenu 2");
    return 1;
}

// The purchase limit survives reconnects during this map, keyed by the CZM profile.
public czm_weapon_bought(id, unused)
{
    if (!is_user_connected(id) || is_user_bot(id)) return 0;
    new key[64], value;
    czm_player_key(id, key, charsmax(key));
    return TrieGetCell(g_purchased, key, value) && value;
}

public czm_weapon_mark(id, unused)
{
    if (!is_user_connected(id) || is_user_bot(id)) return 0;
    new key[64];
    czm_player_key(id, key, charsmax(key));
    TrieSetCell(g_purchased, key, 1);
    return 1;
}

public plugin_end() { TrieDestroy(g_purchased); }

public czm_loadout_queued(id, unused)
{
    czm_chat(id, "^4[CZM]^1 Выбор сохранён. Оружие будет выдано в следующем раунде.",
        "^4[CZM]^1 Selection saved. Your loadout will be applied next round.");
    return 1;
}

zp_call(const name[], id, value = -1)
{
    if (g_zp < 0) g_zp = find_plugin_byfile("zombie_plague40.amxx");
    if (g_zp < 0) return 0;
    new f = get_func_id(name, g_zp);
    if (f < 0 || callfunc_begin_i(f, g_zp) != 1) return 0;
    callfunc_push_int(id);
    if (value >= 0) callfunc_push_int(value);
    callfunc_end();
    return 1;
}

public cmd_weapons(id)
{
    if (is_user_connected(id)) client_cmd(id, "czm_weapon_catalog");
    return PLUGIN_HANDLED;
}

public cmd_zombie_menu(id)
{
    if (is_user_connected(id)) client_cmd(id, "say /zpmenu");
    return PLUGIN_HANDLED;
}

bool:special_round()
{
    return zp_is_nemesis_round() || zp_is_survivor_round() || zp_is_swarm_round() || zp_is_plague_round();
}

public cmd_join(id)
{
    if (!is_user_connected(id) || get_gametime() < g_nextJoin[id]) return PLUGIN_HANDLED;
    g_nextJoin[id] = get_gametime() + 0.8;
    new choice[16];
    read_argv(1, choice, charsmax(choice));
    if (equal(choice, "spectator"))
    {
        // The mod protects the last human/zombie and special rounds itself.
        zp_call("menu_game", id, 5);
        return PLUGIN_HANDLED;
    }
    new wanted = equal(choice, "human") ? ZP_TEAM_HUMAN : (equal(choice, "zombie") ? ZP_TEAM_ZOMBIE : 0);
    if (!wanted && !equal(choice, "auto")) return PLUGIN_HANDLED;
    g_teamChoice[id] = wanted;
    if (cs_get_user_team(id) == CS_TEAM_SPECTATOR || cs_get_user_team(id) == CS_TEAM_UNASSIGNED)
    {
        // engclient_cmd reaches the game DLL instead of ZP's jointeam blocker.
        // Finishing class selection is required even when the class card is hidden.
        engclient_cmd(id, "jointeam", "5");
        engclient_cmd(id, "joinclass", "5");
        g_joinUserid[id] = get_user_userid(id);
        g_joinTeam[id] = wanted;
        remove_task(id + 7200);
        set_task(0.25, "finish_join", id + 7200);
        return PLUGIN_HANDLED;
    }
    if (is_user_alive(id))
    {
        if (wanted == ZP_TEAM_ZOMBIE && !zp_get_user_zombie(id) && !special_round() && zp_has_round_started() && !zp_get_user_last_human(id))
        {
            zp_infect_user(id);
            return PLUGIN_HANDLED;
        }
        if (!wanted || (wanted == ZP_TEAM_HUMAN && !zp_get_user_zombie(id)) || (wanted == ZP_TEAM_ZOMBIE && zp_get_user_zombie(id)))
            czm_chat(id, "^4[CZM]^1 Ты уже в игре.", "^4[CZM]^1 You are already playing.");
        else
            czm_chat(id, "^4[CZM]^1 Выбор команды сохранён на следующий раунд.", "^4[CZM]^1 Team choice saved for the next round.");
        return PLUGIN_HANDLED;
    }
    // Dead members of a playing team keep the server's existing revive countdown.
    czm_chat(id, "^4[CZM]^1 Ожидай возрождения по правилам раунда.", "^4[CZM]^1 Wait for the round's respawn timer.");
    return PLUGIN_HANDLED;
}

public finish_join(task)
{
    new id = task - 7200;
    if (!is_user_connected(id) || get_user_userid(id) != g_joinUserid[id]) return;
    g_joinUserid[id] = 0;
    if (cs_get_user_team(id) != CS_TEAM_T && cs_get_user_team(id) != CS_TEAM_CT)
    {
        czm_chat(id, "^4[CZM]^1 Сейчас войти не удалось. Выбери команду ещё раз.", "^4[CZM]^1 Could not join. Please choose a team again.");
        client_cmd(id, "showvguimenu 2");
        return;
    }
    if (!is_user_alive(id) && !zp_has_round_started())
        zp_respawn_user(id, ZP_TEAM_HUMAN);
    if (is_user_alive(id) && g_joinTeam[id] == ZP_TEAM_ZOMBIE && !special_round() && zp_has_round_started() && !zp_get_user_last_human(id))
        zp_infect_user(id);
    else if (!is_user_alive(id))
        czm_chat(id, "^4[CZM]^1 Ты в игре. Ожидай возрождения.", "^4[CZM]^1 You have joined. Waiting to respawn.");
}

public new_round()
{
    for (new id = 1; id <= MaxClients; id++) g_maxHp[id] = 0;
}

public zp_round_started(mode, first)
{
    if (special_round()) return;
    for (new id = 1; id <= MaxClients; id++)
        if (is_user_alive(id) && g_teamChoice[id] == ZP_TEAM_ZOMBIE && !zp_get_user_zombie(id) && !zp_get_user_last_human(id))
            zp_infect_user(id);
}

public spawn_post(id)
{
    if (!is_user_alive(id)) return;
    g_maxHp[id] = max(1, get_user_health(id));
    remove_task(id + 7300);
    set_task(0.15, "capture_maxhp", id + 7300);
}

public zp_user_infected_post(id, infector, nemesis) { spawn_post(id); }
public zp_user_humanized_post(id, survivor) { spawn_post(id); }

public capture_maxhp(task)
{
    new id = task - 7300;
    if (is_user_alive(id)) g_maxHp[id] = max(g_maxHp[id], get_user_health(id));
}

public task_aim()
{
    new Float:now = get_gametime();
    for (new viewer = 1; viewer <= MaxClients; viewer++)
    {
        if (!g_aimUi[viewer] || !is_user_connected(viewer)) continue;
        new target, hit, hp, limit;
        if (is_user_alive(viewer)) get_user_aiming(viewer, target, hit, 4096);
        if (1 <= target <= MaxClients && is_user_alive(target) && target != viewer)
        {
            hp = get_user_health(target);
            if (hp > g_maxHp[target]) g_maxHp[target] = hp;
            limit = max(1, g_maxHp[target]);
        }
        else target = 0;
        if (g_aimSent[viewer][0] == target && g_aimSent[viewer][1] == hp && g_aimSent[viewer][2] == limit && now < g_aimHeartbeat[viewer]) continue;
        g_aimSent[viewer][0] = target; g_aimSent[viewer][1] = hp; g_aimSent[viewer][2] = limit;
        g_aimHeartbeat[viewer] = now + 0.6;
        engfunc(EngFunc_MessageBegin, MSG_ONE_UNRELIABLE, g_msgAim, Float:{0.0, 0.0, 0.0}, viewer);
        write_byte(target); write_long(hp); write_long(limit); message_end();
    }
}
