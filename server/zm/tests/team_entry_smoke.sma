// Isolated HLDS integration check. Requires configs/czm_entry_isolated.check.
// Use a private clone bound to loopback; this check quits that instance when done.
#include <amxmodx>
#include <cstrike>
#include <fakemeta>
#include <czm_menu>

new g_id, g_step, g_failures;
new const g_commands[][] = {"jointeam", "jointeam", "jointeam", "jointeam", "jointeam", "jointeam", "czm_join", "czm_join", "czm_join", "czm_join", "czm_join", "czm_join"};
new const g_choices[][] = {"5", "6", "1", "6", "2", "6", "auto", "spectator", "human", "spectator", "zombie", "spectator"};

public plugin_init() { register_plugin("CZM Isolated Entry Check", "1.0", "kurostreet"); }
public plugin_cfg()
{
    new marker[256]; get_localinfo("amxx_configsdir", marker, charsmax(marker));
    add(marker, charsmax(marker), "/czm_entry_isolated.check");
    if (!file_exists(marker)) { server_print("ENTRY_SMOKE_REFUSED no isolated marker"); return; }
    set_cvar_float("zp_delay", 120.0);
    set_task(3.0, "start_check");
}
set_ui(const plugin[], const callback[], const cvar[], const value[])
{
    new p = find_plugin_byfile(plugin);
    if (p < 0) return 0;
    new f = get_func_id(callback, p);
    if (f < 0 || callfunc_begin_i(f, p) != 1) return 0;
    callfunc_push_int(g_id); callfunc_push_str(cvar); callfunc_push_str(value); callfunc_end();
    return 1;
}
public start_check()
{
    g_id = engfunc(EngFunc_CreateFakeClient, "CZM Entry Check");
    if (!g_id) { server_print("ENTRY_SMOKE_FAIL create"); server_cmd("quit"); return; }
    new reject[128];
    dllfunc(DLLFunc_ClientConnect, g_id, "CZM Entry Check", "127.0.0.1", reject);
    dllfunc(DLLFunc_ClientPutInServer, g_id);
    set_pev(g_id, pev_flags, pev(g_id, pev_flags) | FL_FAKECLIENT);
    if (!is_user_connected(g_id) || !set_ui("czm_menu.amxx", "on_menu_ui", "czm_menu_ui", "1") || !set_ui("czm_play.amxx", "aim_capability", "czm_aim_ui", "1"))
    { server_print("ENTRY_SMOKE_FAIL prepare"); server_cmd("quit"); return; }
    set_user_flags(g_id, read_flags("abcdefghijklmnopqrstu"));
    set_ui("czm_play.amxx", "play_capability", "czm_play_ui", "1");
    server_print("ENTRY_SMOKE_START id=%d team=%d", g_id, _:cs_get_user_team(g_id));
    run_action();
}
public run_action()
{
    if (g_step == sizeof g_commands)
    {
        server_print("ENTRY_SMOKE_DONE steps=%d failures=%d", g_step, g_failures);
        server_cmd("quit"); return;
    }
    amxclient_cmd(g_id, g_commands[g_step], g_choices[g_step]);
    set_task(0.6, "check_action");
}
public check_action()
{
    new CsTeams:team = cs_get_user_team(g_id);
    new bool:ok = g_step % 2 ? team == CS_TEAM_SPECTATOR && !is_user_alive(g_id) : team == CS_TEAM_T || team == CS_TEAM_CT;
    if (!ok) g_failures++;
    server_print("ENTRY_SMOKE_STEP n=%d command=%s %s team=%d alive=%d ok=%d", g_step, g_commands[g_step], g_choices[g_step], _:team, is_user_alive(g_id), ok);
    g_step++;
    set_task(0.5, "run_action");
}
