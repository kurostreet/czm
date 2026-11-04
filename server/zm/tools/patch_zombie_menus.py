#!/usr/bin/env python3
"""Apply the CZM menu bridge to the installed GPL Zombie Plague 4.4 source.

The original source stays untouched. Deployment compiles this generated copy before
replacing any live plugin; unfamiliar functions fail instead of guessing a patch.
"""
from pathlib import Path
import re
import sys

MARKER = '// CZM weapon and team bridge, revision 1'


def span(source, signature):
    match = re.search(r'(?m)^' + re.escape(signature) + r'\s*\{', source)
    if not match:
        raise ValueError('unsupported Zombie Plague source: ' + signature)
    opening = source.index('{', match.start())
    at, depth = opening + 1, 1
    while depth and at < len(source):
        depth += (source[at] == '{') - (source[at] == '}')
        at += 1
    if depth:
        raise ValueError('unfinished function: ' + signature)
    return match.start(), at


def replace_function(source, signature, replacement):
    a, b = span(source, signature)
    return source[:a] + replacement + source[b:]


PRIMARY = r'''
public show_menu_buy1(taskid)
{
    new id = taskid > g_maxplayers ? ID_SPAWN : taskid;
    if (!is_user_valid_connected(id)) return;
    if (czm_menu_bridge("czm_weapon_bought", id)) g_czmBought[id] = true;
    new bool:automatic = taskid > g_maxplayers;
    if (automatic)
    {
        if (!g_isalive[id] || g_zombie[id] || g_survivor[id]) return;
        if (g_isbot[id] || get_pcvar_num(cvar_randweapons))
        {
            g_czmSecondaryNow[id] = true;
            buy_primary_weapon(id, random_num(0, ArraySize(g_primary_items) - 1));
            menu_buy2(id, random_num(0, ArraySize(g_secondary_items) - 1));
            return;
        }
        new bool:queued = g_czmDue[id] && g_czmDue[id] <= g_czmRound;
        if (queued)
        {
            if (g_czmNextPri[id] >= 0) WPN_AUTO_PRI = g_czmNextPri[id];
            if (g_czmNextSec[id] >= 0) WPN_AUTO_SEC = g_czmNextSec[id];
            g_czmDue[id] = 0;
            g_czmNextPri[id] = g_czmNextSec[id] = -1;
        }
        if (g_czmBought[id] || WPN_AUTO_ON || queued)
        {
            g_czmSecondaryNow[id] = true;
            buy_primary_weapon(id, clamp(WPN_AUTO_PRI, 0, WPN_MAXIDS - 1));
            menu_buy2(id, clamp(WPN_AUTO_SEC, 0, ArraySize(g_secondary_items) - 1));
            return;
        }
    }
    static menu[1024];
    new len, maxloops = min(WPN_STARTID + 7, WPN_MAXIDS);
    if (czm_menu_bridge("czm_capable", id))
        len = formatex(menu, charsmax(menu), "#czmw1^tprimary^t%d^t%d^t%d^t%d^t%d^t%d^n", WPN_STARTID / 7,
            (WPN_MAXIDS + 6) / 7, g_czmBought[id] || !g_isalive[id] || g_zombie[id] || g_survivor[id],
            ArrayGetCell(g_primary_weaponids, clamp(g_czmNextPri[id] >= 0 ? g_czmNextPri[id] : WPN_AUTO_PRI, 0, WPN_MAXIDS - 1)), WPN_AUTO_ON, automatic);
    len += formatex(menu[len], charsmax(menu) - len, "\y%L \r[%d-%d]^n^n", id, "MENU_BUY1_TITLE", WPN_STARTID + 1, maxloops);
    for (new weap = WPN_STARTID; weap < maxloops; weap++)
        len += formatex(menu[len], charsmax(menu) - len, "\r%d.\w %s^n", weap - WPN_STARTID + 1, WEAPONNAMES[ArrayGetCell(g_primary_weaponids, weap)]);
    len += formatex(menu[len], charsmax(menu) - len, "^n\r8.\w %L \y[%L]^n^n\r9.\w %L/%L^n^n\r0.\w %L", id, "MENU_AUTOSELECT", id,
        WPN_AUTO_ON ? "MOTD_ENABLED" : "MOTD_DISABLED", id, "MENU_NEXT", id, "MENU_BACK", id, "MENU_EXIT");
    if (pev_valid(id) == PDATA_SAFE) set_pdata_int(id, OFFSET_CSMENUCODE, 0, OFFSET_LINUX);
    show_menu(id, KEYSMENU, menu, -1, "Buy Menu 1");
}
'''

SECONDARY = r'''
show_menu_buy2(id)
{
    if (!is_user_valid_connected(id)) return;
    static menu[768];
    new len, count = ArraySize(g_secondary_items);
    if (czm_menu_bridge("czm_capable", id))
        len = formatex(menu, charsmax(menu), "#czmw1^tsecondary^t0^t1^t%d^t%d^t%d^t0^n", !g_czmSecondaryNow[id],
            ArrayGetCell(g_secondary_weaponids, clamp(g_czmNextSec[id] >= 0 ? g_czmNextSec[id] : WPN_AUTO_SEC, 0, count - 1)), WPN_AUTO_ON);
    len += formatex(menu[len], charsmax(menu) - len, "\y%L^n", id, "MENU_BUY2_TITLE");
    for (new weap = 0; weap < count; weap++)
        len += formatex(menu[len], charsmax(menu) - len, "^n\r%d.\w %s", weap + 1, WEAPONNAMES[ArrayGetCell(g_secondary_weaponids, weap)]);
    len += formatex(menu[len], charsmax(menu) - len, "^n^n\r8.\w %L \y[%L]^n^n\r0.\w %L", id, "MENU_AUTOSELECT", id,
        WPN_AUTO_ON ? "MOTD_ENABLED" : "MOTD_DISABLED", id, "MENU_EXIT");
    if (pev_valid(id) == PDATA_SAFE) set_pdata_int(id, OFFSET_CSMENUCODE, 0, OFFSET_LINUX);
    show_menu(id, KEYSMENU, menu, -1, "Buy Menu 2");
}
'''

PICK_PRIMARY = r'''
public menu_buy1(id, key)
{
    if (!is_user_valid_connected(id) || key < 0 || key > 9) return PLUGIN_HANDLED;
    if (key >= MENU_KEY_AUTOSELECT || WPN_SELECTION >= WPN_MAXIDS)
    {
        switch (key)
        {
            case MENU_KEY_AUTOSELECT: WPN_AUTO_ON = 1 - WPN_AUTO_ON;
            case MENU_KEY_NEXT: WPN_STARTID = WPN_STARTID + 7 < WPN_MAXIDS ? WPN_STARTID + 7 : 0;
            case MENU_KEY_EXIT: return PLUGIN_HANDLED;
        }
        show_menu_buy1(id);
        return PLUGIN_HANDLED;
    }
    g_czmSecondaryNow[id] = !g_czmBought[id] && !czm_menu_bridge("czm_weapon_bought", id) && g_isalive[id] && !g_zombie[id] && !g_survivor[id];
    if (g_czmSecondaryNow[id])
    {
        WPN_AUTO_PRI = WPN_SELECTION;
        g_czmBought[id] = true;
        czm_menu_bridge("czm_weapon_mark", id);
        buy_primary_weapon(id, WPN_AUTO_PRI);
    }
    else
    {
        g_czmNextPri[id] = WPN_SELECTION;
        g_czmDue[id] = g_czmRound + 1;
    }
    show_menu_buy2(id);
    return PLUGIN_HANDLED;
}
'''

PICK_SECONDARY = r'''
public menu_buy2(id, key)
{
    if (!is_user_valid_connected(id) || key < 0 || key > 9) return PLUGIN_HANDLED;
    if (key >= ArraySize(g_secondary_items))
    {
        if (key == MENU_KEY_AUTOSELECT) WPN_AUTO_ON = 1 - WPN_AUTO_ON;
        if (key != MENU_KEY_EXIT) show_menu_buy2(id);
        return PLUGIN_HANDLED;
    }
    new bool:apply = g_czmSecondaryNow[id] && g_isalive[id] && !g_zombie[id] && !g_survivor[id];
    g_czmSecondaryNow[id] = false;
    if (!apply)
    {
        g_czmNextSec[id] = key;
        g_czmDue[id] = g_czmRound + 1;
        czm_menu_bridge("czm_loadout_queued", id);
        return PLUGIN_HANDLED;
    }
    WPN_AUTO_SEC = key;
    zp_drop_weapons(id, 2);
    new weaponid = ArrayGetCell(g_secondary_weaponids, key), wname[32];
    ArrayGetString(g_secondary_items, key, wname, charsmax(wname));
    zp_give_item(id, wname);
    ExecuteHamB(Ham_GiveAmmo, id, MAXBPAMMO[weaponid], AMMOTYPE[weaponid], MAXBPAMMO[weaponid]);
    g_canbuy[id] = false;
    g_czmBought[id] = true;
    return PLUGIN_HANDLED;
}
'''

BRIDGE = r'''
// Calls only the enabled CZM integration; the stock mod remains usable without it.
czm_menu_bridge(const callback[], id, value = 0)
{
    new p = find_plugin_byfile("czm_play.amxx"), result;
    if (p < 0) return 0;
    new f = get_func_id(callback, p);
    if (f < 0 || callfunc_begin_i(f, p) != 1) return 0;
    callfunc_push_int(id);
    callfunc_push_int(value);
    result = callfunc_end();
    return result;
}

// The client uses this command for separate Previous/Next buttons, with server-side bounds.
public czm_weapon_catalog(id)
{
    show_menu_buy1(id);
    return PLUGIN_HANDLED;
}

public czm_weapon_page(id)
{
    new text[12];
    read_argv(1, text, charsmax(text));
    WPN_STARTID = clamp(str_to_num(text), 0, max(0, (WPN_MAXIDS + 6) / 7 - 1)) * 7;
    show_menu_buy1(id);
    return PLUGIN_HANDLED;
}
'''


def patch(source):
    if MARKER in source:
        return source
    for token in ('Zombie Plague Mod 4.4', 'g_canbuy[id] = false', 'WPN_AUTO_PRI', 'show_menu_game(id)'):
        if token not in source:
            raise ValueError('unsupported Zombie Plague source: ' + token)
    source = MARKER + '\nnew bool:g_czmBought[33], bool:g_czmSecondaryNow[33];\nnew g_czmNextPri[33], g_czmNextSec[33], g_czmDue[33], g_czmRound;\n' + source
    for signature, body in [('public show_menu_buy1(taskid)', PRIMARY), ('show_menu_buy2(id)', SECONDARY),
                            ('public menu_buy1(id, key)', PICK_PRIMARY), ('public menu_buy2(id, key)', PICK_SECONDARY)]:
        source = replace_function(source, signature, body.strip())
    for signature, code in [
        ('public clcmd_changeteam(id)', '\n\tif (czm_menu_bridge("czm_team_open", id)) return PLUGIN_HANDLED;\n'),
        ('public menu_game(id, key)', '\n\tif (key == 0 && czm_menu_bridge("czm_weapon_open", id)) { show_menu_buy1(id); return PLUGIN_HANDLED; }\n'),
        ('public event_round_start()', '\n\tg_czmRound++;\n'),
        ('public client_putinserver(id)', '\n\tg_czmBought[id] = g_czmSecondaryNow[id] = false;\n\tg_czmNextPri[id] = g_czmNextSec[id] = -1;\n\tg_czmDue[id] = 0;\n')]:
        a, _ = span(source, signature)
        at = source.index('{', a) + 1
        source = source[:at] + code + source[at:]
    a, _ = span(source, 'public plugin_init()')
    at = source.index('{', a) + 1
    source = source[:at] + '\n\tregister_clcmd("czm_weapon_page", "czm_weapon_page");\n\tregister_clcmd("czm_weapon_catalog", "czm_weapon_catalog");\n' + source[at:]
    return source + '\n' + BRIDGE


if __name__ == '__main__':
    incoming, output = map(Path, sys.argv[1:])
    text = incoming.read_text(encoding='utf-8', errors='surrogateescape')
    output.write_text(patch(text), encoding='utf-8', errors='surrogateescape')
    print('CZM Zombie Plague bridge ready:', output.name)
