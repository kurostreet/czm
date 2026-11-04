// Isolated HLDS smoke test. Never add this plugin to the live server.
// The test copy of czm_menu calls capture_wire() before show_menu().
#include <amxmodx>
#include <fakemeta>
#include <czm_menu>

#pragma dynamic 8192

new g_id, g_wire[4096], g_keys, g_checks, g_failures;
new const RESULT[] = "addons/amxmodx/logs/czm_menu_runtime.txt";

public plugin_init() { register_plugin("CZM Menu Runtime Test", "1.0", "kurostreet"); }

public plugin_cfg()
{
    new marker[256];
    get_localinfo("amxx_configsdir", marker, charsmax(marker));
    add(marker, charsmax(marker), "/czm_menu_isolated.check");
    if (file_exists(marker))
    {
        new ip[64]; get_cvar_string("ip", ip, charsmax(ip));
        if (equal(ip, "127.0.0.1")) set_task(3.0, "run_check");
    }
}

public capture_wire(id, const text[], keys)
{
    if (id == g_id) { copy(g_wire, charsmax(g_wire), text); g_keys = keys; }
}

check(bool:passed, const name[])
{
    new line[256];
    g_checks++;
    if (!passed) g_failures++;
    formatex(line, charsmax(line), "%s %s", passed ? "PASS" : "FAIL", name);
    write_file(RESULT, line);
}

invoke(const plugin[], const function[], argument)
{
    new p = find_plugin_byfile(plugin), f = get_func_id(function, p);
    if (p < 0 || f < 0 || callfunc_begin_i(f, p) != 1) return 0;
    callfunc_push_int(argument);
    return callfunc_end();
}

language(const lang[])
{
    new p = find_plugin_byfile("czm_core.amxx"), f = get_func_id("on_czm_lang", p);
    callfunc_begin_i(f, p); callfunc_push_int(g_id);
    callfunc_push_str("czm_lang"); callfunc_push_str(lang); callfunc_end();
}

capability(const version[])
{
    new p = find_plugin_byfile("czm_menu.amxx"), f = get_func_id("on_menu_ui", p);
    callfunc_begin_i(f, p); callfunc_push_int(g_id);
    callfunc_push_str("czm_menu_ui"); callfunc_push_str(version); callfunc_end();
}

key(number)
{
    new p = find_plugin_byfile("czm_menu.amxx"), f = get_func_id("on_key", p);
    callfunc_begin_i(f, p); callfunc_push_int(g_id); callfunc_push_int(number); callfunc_end();
}

bool:choose(const label[])
{
    new at = contain(g_wire, label);
    if (at < 0) return false;
    new begin = at;
    while (begin > 0 && g_wire[begin - 1] != '^n') begin--;
    for (new k = begin; k < at; k++)
        if ('1' <= g_wire[k] <= '9' && g_wire[k + 1] == '.')
        {
            key(g_wire[k] - '1');
            return true;
        }
    return false;
}

public run_check()
{
    delete_file(RESULT);
    g_id = engfunc(EngFunc_CreateFakeClient, "CZM Menu Check");
    new reject[128];
    dllfunc(DLLFunc_ClientConnect, g_id, "CZM Menu Check", "127.0.0.1", reject);
    dllfunc(DLLFunc_ClientPutInServer, g_id);
    set_pev(g_id, pev_flags, pev(g_id, pev_flags) | FL_FAKECLIENT);
    capability("2"); language("ru"); czm_menu_open(g_id, "main");
    check(contain(g_wire, "#tabs^tmain:Главная:star:") >= 0, "RU sidebar name");
    check(contain(g_wire, "lvl:LVL MOD:crown:") >= 0, "LVL sidebar name");
    check(contain(g_wire, "players:Игроки:users:") >= 0, "players sidebar name");
    check(contain(g_wire, "votes:Голосования:flag:") >= 0, "voting sidebar name");
    check(contain(g_wire, "server:Сообщество:globe:") >= 0, "community sidebar name");
    check(contain(g_wire, "Честная игра • Чистый сервер • Приятное общение^t^tmain^n") >= 0, "full RU footer and root key");
    check(contain(g_wire, "menu_ui") < 0, "no corrupt labels");
    check(contain(g_wire, "admin:") < 0 && contain(g_wire, "a_admin") < 0, "guest cannot see management");
    check(choose("Новости сервера"), "news card dispatch");
    check(contain(g_wire, "#page^ttext^tНовости сервера^t") >= 0 && contain(g_wire, "#body^t") >= 0, "news is an article");
    key(9); check(contain(g_wire, "#czm1^tmenu^tserver^t") == 0, "article back returns to community");
    czm_menu_open(g_id, "main"); check(choose("Приглашения"), "invitations card dispatch");
    check(contain(g_wire, "#page^tfriends^tПригласить друга^t@friends^t") >= 0, "invitation opens friend picker");
    czm_menu_open(g_id, "main"); check(choose("Сообщение админу"), "message card dispatch");
    check(contain(g_wire, "#page^tform^tСообщение админу^tczm_admin_msg^t") >= 0, "message opens private form");
    new stamp = czm_menu_stamp(g_id);
    invoke("czm_menu.amxx", "cmd_close", g_id);
    check(czm_menu_stamp(g_id) > stamp && !g_wire[0] && !g_keys, "close clears page and invalidates async stamp");
    stamp = czm_menu_stamp(g_id); key(0);
    check(!g_wire[0] && czm_menu_stamp(g_id) > stamp, "stale selection after close stays closed");
    czm_menu_open(g_id, "lvl"); check(choose("Подключить профиль"), "guest LVL offers sign in");
    check(contain(g_wire, "#page^taccount^t") >= 0 && contain(g_wire, "@account") >= 0, "LVL sign-in help has account route");
    czm_menu_open(g_id, "admin");
    check(contain(g_wire, "#czm1^tmenu^tmain^t") == 0, "forged management section falls back safely");
    language("en"); czm_menu_open(g_id, "main");
    check(contain(g_wire, "#tabs^tmain:Main:star:") >= 0 && contain(g_wire, "server:Community:globe:") >= 0, "EN sidebar names");
    check(contain(g_wire, "Fair play • Clean server • Friendly chat^t^tmain^n") >= 0, "full EN footer");
    capability("1"); czm_menu_open(g_id, "main"); choose("Message to the staff");
    check(contain(g_wire, "#page") < 0 && contain(g_wire, "Describe the issue") >= 0 && (g_keys & 1), "v1 readable form with input key");
    capability("0"); czm_menu_open(g_id, "main");
    check(contain(g_wire, "#czm1") < 0 && contain(g_wire, "Player panel") >= 0, "classic client still has working text menu");
    new summary[96];
    formatex(summary, charsmax(summary), "MENU_RUNTIME_RESULT checks=%d failures=%d", g_checks, g_failures);
    write_file(RESULT, summary); server_print("%s", summary);
    server_cmd("quit");
}
