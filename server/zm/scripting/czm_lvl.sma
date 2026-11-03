/*
	Counter Zombie Mobile, Survival server: LVL MOD of the Kontra server (LVL_MOD_v82), in the game.

	The API (server/czm/czm/survival.py) keeps every number. This plugin
	* tells the API what happened: play time, kills, deaths, rounds, wins (every 10 seconds; a batch
	  is resent with the same id until the API answers, so nothing counts twice);
	* shows what the API answers: "+N tokens", level ups, the map top at the end of the map;
	* puts on what the player wears: the human skin, the glow colour, the prefix in chat;
	* opens the LVL menu (lvl, /lvl); the server menu (menu, меню) is czm_game's.
	Only players who came with a CZM ticket have a profile; the others are guests.
*/
#include <amxmodx>
#include <amxmisc>
#include <cstrike>
#include <fakemeta>
#include <fun>
#include <hamsandwich>
#include <zombieplague>
#include <easy_http>
#include <czm_survival>
#include <czm_admin>
#include <czm_menu>

#define PLUGIN "CZM LVL"
#define VERSION "1.0"
#define AUTHOR "kurostreet"

#define MAX_CATS 8
#define MAX_ITEMS 16
#define TASK_LOOK 4600
#define REPORT_EVERY 10.0
#define J_NONE EzInvalid_JSON
#define J_OK(%1) (%1 != EzInvalid_JSON)

// ---------------------------------------------------------------- catalog (from the API)
new g_catKey[MAX_CATS][12], g_catName[MAX_CATS][2][40], g_catCount;
new g_itemId[MAX_CATS][MAX_ITEMS][24], g_itemName[MAX_CATS][MAX_ITEMS][2][40];
new g_itemPrice[MAX_CATS][MAX_ITEMS], bool:g_itemShop[MAX_CATS][MAX_ITEMS], bool:g_itemAdmin[MAX_CATS][MAX_ITEMS];
new g_itemModel[MAX_CATS][MAX_ITEMS][24], g_itemBase[MAX_CATS][MAX_ITEMS][16], g_itemGlow[MAX_CATS][MAX_ITEMS][8];
new g_itemCount[MAX_CATS];
new g_upId[3][12], g_upName[3][2][40], g_upPrice[3], g_upCount;
new g_bpPrice, g_bpDays, g_bpDaily, g_payMinLvl, g_payDaily;
new bool:g_catalogReady;

// ---------------------------------------------------------------- players
new g_profile[MAX_PLAYERS + 1], g_session[MAX_PLAYERS + 1], bool:g_loaded[MAX_PLAYERS + 1];
new g_lvl[MAX_PLAYERS + 1], g_tokens[MAX_PLAYERS + 1], Float:g_tokBoostUntil[MAX_PLAYERS + 1];
// the tag everyone sees with the CZM game (the player list, the player in the crosshair, the chat):
// the level, the wins in %, the prefix in its colour, the privilege; toasts for "+tokens" and levels
new g_wr[MAX_PLAYERS + 1], g_nextKills[MAX_PLAYERS + 1];
new g_msgTag, g_msgToast, g_msgProgress;
new g_nextTime[MAX_PLAYERS + 1], g_killsStep[MAX_PLAYERS + 1], g_timeStep[MAX_PLAYERS + 1];
new bool:g_progressUi[MAX_PLAYERS + 1], g_progressSent[MAX_PLAYERS + 1][96];
new g_tagSent[MAX_PLAYERS + 1][64];
new bool:g_tagSynced[MAX_PLAYERS + 1];
new g_equip[MAX_PLAYERS + 1][MAX_CATS];              // item index or -1
new bool:g_owned[MAX_PLAYERS + 1][MAX_CATS][MAX_ITEMS];
new bool:g_bpActive[MAX_PLAYERS + 1], bool:g_bpDailyReady[MAX_PLAYERS + 1], g_bpLeftDays[MAX_PLAYERS + 1];
new g_bpProgress[MAX_PLAYERS + 1][6], g_bpClaimed[MAX_PLAYERS + 1];
new g_payToday[MAX_PLAYERS + 1];

// the weapon crate (catalog "crate"): what it holds and until when each player has it
#define MAX_CRATE 8
new g_crateId[MAX_CRATE][12], g_crateName[MAX_CRATE][2][40], g_cratePrice[MAX_CRATE], g_crateCount;
new Float:g_crateUntil[MAX_PLAYERS + 1][MAX_CRATE], g_charges[MAX_PLAYERS + 1];
new g_fwChanged;

enum { D_TIME = 0, D_KILLS, D_ZKILLS, D_DEATHS, D_ROUNDS, D_WINS, D_SURVIVED, D_CTWINS, D_COUNT };
new const D_NAMES[D_COUNT][] = { "time", "kills", "zkills", "deaths", "rounds", "wins", "survived", "ctwins" };
new g_delta[MAX_PLAYERS + 1][D_COUNT];
new bool:g_inRound[MAX_PLAYERS + 1];

new Trie:g_mapKills;              // profile -> kills on this map
new EzJSON:g_pending = J_NONE;  // the batch the API has not confirmed yet
new g_pendingId[48];
new bool:g_sending;
new g_batchSeq, g_mapStamp;
new bool:g_mapEndSent;

new g_serverToken[65];
new g_cvarApi, g_cvarServer;
new g_hudTokens, g_hudLevel;
new g_hRank;
new g_payTarget[MAX_PLAYERS + 1];

new const PULL_SOUND[] = "s_change_rang.mp3";

// Human knives of the shop: models/czm_survival/v_<id>.mdl (and p_<id>.mdl when the model has one)
new const KNIFE_IDS[][] = { "katana", "axe", "glass", "sickle" };
new bool:g_knifeV[sizeof KNIFE_IDS], bool:g_knifeP[sizeof KNIFE_IDS];

// Our own player models of the shop skins: models/player/<name>/<name>.mdl. A skin whose model
// is not on the server falls back to the stock model named in the catalog ("base").
new const SKIN_MODELS[][] = { "czm_gsg9_admin", "czm_sas_custom", "czm_leet_pirate", "czm_professional", "czm_survivor" };
new bool:g_skinReady[sizeof SKIN_MODELS];

public plugin_natives()
{
	register_library("czm_lvl");
	register_native("czm_lvl_ready", "native_ready");
	register_native("czm_lvl_item", "native_item");
	register_native("czm_lvl_crate", "native_crate");
	register_native("czm_lvl_charges", "native_charges");
	register_native("czm_lvl_use_charge", "native_use_charge");
	register_native("czm_lvl_reward", "native_reward");
}

public plugin_precache()
{
	g_hRank = czm_sound_precache(PULL_SOUND);
	new path[64];
	for (new k = 0; k < sizeof KNIFE_IDS; k++)
	{
		formatex(path, charsmax(path), "models/czm_survival/v_%s.mdl", KNIFE_IDS[k]);
		if ((g_knifeV[k] = bool:file_exists(path)))
			precache_model(path);
		formatex(path, charsmax(path), "models/czm_survival/p_%s.mdl", KNIFE_IDS[k]);
		if ((g_knifeP[k] = bool:file_exists(path)))
			precache_model(path);
	}
	for (new k = 0; k < sizeof SKIN_MODELS; k++)
	{
		formatex(path, charsmax(path), "models/player/%s/%s.mdl", SKIN_MODELS[k], SKIN_MODELS[k]);
		if (!(g_skinReady[k] = bool:file_exists(path)))
			continue;
		precache_model(path);
		formatex(path, charsmax(path), "models/player/%s/%sT.mdl", SKIN_MODELS[k], SKIN_MODELS[k]);
		if (file_exists(path))
			precache_model(path);
	}
}

// The player model to put on for a skin: ours when the server has it, else the stock one
skin_model(c, i, out[], len)
{
	for (new k = 0; k < sizeof SKIN_MODELS; k++)
		if (equal(g_itemModel[c][i], SKIN_MODELS[k]))
			return copy(out, len, g_skinReady[k] ? g_itemModel[c][i] : g_itemBase[c][i]);
	return copy(out, len, g_itemModel[c][i]);
}

public plugin_init()
{
	register_plugin(PLUGIN, VERSION, AUTHOR);
	// Register after the game DLL's standard messages. Custom engine registrations do not
	// enter Metamod's user-message lookup; send them through Fakemeta as well, not message_begin.
	g_msgTag = engfunc(EngFunc_RegUserMsg, "CzmTag", -1);
	g_msgToast = engfunc(EngFunc_RegUserMsg, "CzmToast", -1);
	g_msgProgress = engfunc(EngFunc_RegUserMsg, "CzmProgress", 24);
	log_amx("Client messages: CzmTag=%d CzmToast=%d CzmProgress=%d", g_msgTag, g_msgToast, g_msgProgress);
	g_cvarApi = create_cvar("czm_api_url", "http://127.0.0.1:8200", FCVAR_PROTECTED, "Where the CZM API answers");
	g_cvarServer = create_cvar("czm_server_name", "survival");

	register_clcmd("say", "cmd_say");
	register_clcmd("say_team", "cmd_say_team");
	register_clcmd("lvl", "menu_lvl");
	menu_register();

	RegisterHam(Ham_Killed, "player", "fw_killed_post", 1);
	RegisterHam(Ham_Spawn, "player", "fw_spawn_post", 1);
	RegisterHam(Ham_Item_Deploy, "weapon_knife", "fw_knife_deploy_post", 1);
	register_logevent("ev_round_start", 2, "1=Round_Start");
	register_logevent("ev_round_end", 2, "1=Round_End");

	g_fwChanged = CreateMultiForward("czm_lvl_changed", ET_IGNORE, FP_CELL);
	g_hudTokens = CreateHudSyncObj();
	g_hudLevel = CreateHudSyncObj();
	g_mapKills = TrieCreate();
	g_mapStamp = get_systime();
	for (new i = 0; i <= MaxClients; i++)
		reset_player(i);
	set_task(REPORT_EVERY, "task_report", _, _, _, "b");
	set_task(2.0, "task_tags", _, _, _, "b");
	set_task(1.0, "task_map_end", _, _, _, "b");
}

public plugin_cfg()
{
	load_server_token();
	set_task(1.0, "task_catalog");
}

public plugin_end()
{
	TrieDestroy(g_mapKills);
	if (J_OK(g_pending))
		ezjson_free(g_pending);
}

load_server_token()
{
	new path[128], key[96];
	get_configsdir(path, charsmax(path));
	add(path, charsmax(path), "/czm_ticket.key");
	new fh = fopen(path, "rt");
	if (!fh)
	{
		log_amx("czm_ticket.key is missing: LVL MOD cannot reach the API");
		return;
	}
	fgets(fh, key, charsmax(key));
	fclose(fh);
	trim(key);
	new message[128];
	formatex(message, charsmax(message), "%s|server", key);
	hash_string(message, Hash_Sha256, g_serverToken, charsmax(g_serverToken));
}

// ---------------------------------------------------------------- HTTP

api(const method[], const path[], EzJSON:body, const callback[], const data[] = "", len = 0)
{
	new url[160];
	get_pcvar_string(g_cvarApi, url, charsmax(url));
	add(url, charsmax(url), "/api/v1");
	add(url, charsmax(url), path);
	// every server mode (survival, escape) keeps its own economy in the API
	new mode[24];
	get_pcvar_string(g_cvarServer, mode, charsmax(mode));
	if (mode[0])
	{
		add(url, charsmax(url), contain(path, "?") != -1 ? "&mode=" : "?mode=");
		add(url, charsmax(url), mode);
	}
	new EzHttpOptions:opt = ezhttp_create_options();
	ezhttp_option_set_header(opt, "Content-Type", "application/json");
	ezhttp_option_set_header(opt, "X-CZM-Server", g_serverToken);
	ezhttp_option_set_timeout(opt, 8000);
	ezhttp_option_set_connect_timeout(opt, 3000);
	if (len)
		ezhttp_option_set_user_data(opt, data, len);
	if (J_OK(body))
		ezhttp_option_set_body_from_json(opt, body);
	if (equal(method, "GET"))
		ezhttp_get(url, callback, opt);
	else
		ezhttp_post(url, callback, opt);
}

EzJSON:answer(EzHttpRequest:request, &code)
{
	code = 0;
	if (ezhttp_get_error_code(request) != EZH_OK)
		return J_NONE;
	code = ezhttp_get_http_code(request);
	return ezhttp_parse_json_response(request);
}

// ---------------------------------------------------------------- catalog

public task_catalog()
{
	api("GET", "/survival/catalog", J_NONE, "on_catalog");
}

public on_catalog(EzHttpRequest:request)
{
	new code, EzJSON:root = answer(request, code);
	if (code != 200 || !J_OK(root))
	{
		if (J_OK(root)) ezjson_free(root);
		set_task(30.0, "task_catalog");
		return;
	}
	new EzJSON:cats = ezjson_object_get_value(root, "categories");
	g_catCount = min(ezjson_array_get_count(cats), MAX_CATS);
	for (new c = 0; c < g_catCount; c++)
	{
		new EzJSON:cat = ezjson_array_get_value(cats, c);
		ezjson_object_get_string(cat, "key", g_catKey[c], charsmax(g_catKey[]));
		ezjson_object_get_string(cat, "ru", g_catName[c][CZM_RU], charsmax(g_catName[][]));
		ezjson_object_get_string(cat, "en", g_catName[c][CZM_EN], charsmax(g_catName[][]));
		new EzJSON:items = ezjson_object_get_value(cat, "items");
		g_itemCount[c] = min(ezjson_array_get_count(items), MAX_ITEMS);
		for (new i = 0; i < g_itemCount[c]; i++)
		{
			new EzJSON:it = ezjson_array_get_value(items, i);
			ezjson_object_get_string(it, "id", g_itemId[c][i], charsmax(g_itemId[][]));
			ezjson_object_get_string(it, "ru", g_itemName[c][i][CZM_RU], charsmax(g_itemName[][][]));
			ezjson_object_get_string(it, "en", g_itemName[c][i][CZM_EN], charsmax(g_itemName[][][]));
			g_itemPrice[c][i] = ezjson_object_get_number(it, "price");
			g_itemShop[c][i] = ezjson_object_get_bool(it, "shop");
			g_itemAdmin[c][i] = ezjson_object_has_value(it, "admin") && ezjson_object_get_bool(it, "admin");
			g_itemModel[c][i][0] = g_itemBase[c][i][0] = g_itemGlow[c][i][0] = 0;
			if (ezjson_object_has_value(it, "model"))
				ezjson_object_get_string(it, "model", g_itemModel[c][i], charsmax(g_itemModel[][][]));
			if (ezjson_object_has_value(it, "base"))
				ezjson_object_get_string(it, "base", g_itemBase[c][i], charsmax(g_itemBase[][][]));
			if (ezjson_object_has_value(it, "glow"))
				ezjson_object_get_string(it, "glow", g_itemGlow[c][i], charsmax(g_itemGlow[][][]));
			ezjson_free(it);
		}
		ezjson_free(items);
		ezjson_free(cat);
	}
	ezjson_free(cats);

	new EzJSON:ups = ezjson_object_get_value(root, "upgrades");
	g_upCount = min(ezjson_array_get_count(ups), sizeof g_upId);
	for (new u = 0; u < g_upCount; u++)
	{
		new EzJSON:it = ezjson_array_get_value(ups, u);
		ezjson_object_get_string(it, "id", g_upId[u], charsmax(g_upId[]));
		ezjson_object_get_string(it, "ru", g_upName[u][CZM_RU], charsmax(g_upName[][]));
		ezjson_object_get_string(it, "en", g_upName[u][CZM_EN], charsmax(g_upName[][]));
		g_upPrice[u] = ezjson_object_get_number(it, "price");
		ezjson_free(it);
	}
	ezjson_free(ups);
	new EzJSON:crate = ezjson_object_get_value(root, "crate.items", true);
	g_crateCount = J_OK(crate) ? min(ezjson_array_get_count(crate), MAX_CRATE) : 0;
	for (new k = 0; k < g_crateCount; k++)
	{
		new EzJSON:it = ezjson_array_get_value(crate, k);
		ezjson_object_get_string(it, "id", g_crateId[k], charsmax(g_crateId[]));
		ezjson_object_get_string(it, "ru", g_crateName[k][CZM_RU], charsmax(g_crateName[][]));
		ezjson_object_get_string(it, "en", g_crateName[k][CZM_EN], charsmax(g_crateName[][]));
		g_cratePrice[k] = ezjson_object_get_number(it, "price");
		ezjson_free(it);
	}
	if (J_OK(crate)) ezjson_free(crate);
	g_bpPrice = ezjson_object_get_number(root, "battlepass.price", true);
	g_bpDays = ezjson_object_get_number(root, "battlepass.days", true);
	g_bpDaily = ezjson_object_get_number(root, "battlepass.daily", true);
	g_payMinLvl = ezjson_object_get_number(root, "pay.min_lvl", true);
	g_payDaily = ezjson_object_get_number(root, "pay.daily", true);
	ezjson_free(root);
	g_catalogReady = true;
}

cat_index(const key[])
{
	for (new c = 0; c < g_catCount; c++)
		if (equal(g_catKey[c], key))
			return c;
	return -1;
}

item_index(c, const id[])
{
	for (new i = 0; i < g_itemCount[c]; i++)
		if (equali(g_itemId[c][i], id))
			return i;
	return -1;
}

// ---------------------------------------------------------------- players and their state

reset_player(id)
{
	g_profile[id] = 0;
	g_loaded[id] = false;
	g_lvl[id] = 0;
	g_wr[id] = 0;
	g_nextKills[id] = 0;
	g_nextTime[id] = g_killsStep[id] = g_timeStep[id] = 0;
	g_progressSent[id][0] = EOS;
	g_tagSent[id][0] = EOS;
	g_tagSynced[id] = false;
	g_tokens[id] = 0;
	g_tokBoostUntil[id] = 0.0;
	g_inRound[id] = false;
	g_charges[id] = 0;
	for (new k = 0; k < MAX_CRATE; k++)
		g_crateUntil[id][k] = 0.0;
	for (new c = 0; c < MAX_CATS; c++)
	{
		g_equip[id][c] = -1;
		for (new i = 0; i < MAX_ITEMS; i++)
			g_owned[id][c][i] = false;
	}
	for (new d = 0; d < D_COUNT; d++)
		g_delta[id][d] = 0;
	send_progress(id);
}

public client_putinserver(id)
{
	g_progressUi[id] = false;
	if (!is_user_bot(id) && !is_user_hltv(id))
		query_client_cvar(id, "czm_progress_ui", "on_progress_ui");
}

public on_progress_ui(id, const cvar[], const value[])
{
	if (is_user_connected(id))
	{
		g_progressUi[id] = str_to_num(value) >= 1;
		g_progressSent[id][0] = EOS;
		send_progress(id);
	}
}

public czm_player_ready(id, profile)
{
	reset_player(id);
	g_session[id]++;
	if (!profile || is_user_bot(id))
		return;
	g_profile[id] = profile;
	new EzJSON:body = ezjson_init_object(), EzJSON:args = ezjson_init_object(), name[32];
	get_user_name(id, name, charsmax(name));
	ezjson_object_set_number(body, "player", profile);
	ezjson_object_set_string(body, "op", "join-00000000");
	ezjson_object_set_string(body, "action", "join");
	ezjson_object_set_string(args, "nick", name);
	ezjson_object_set_value(body, "args", args);
	ezjson_free(args);
	new data[3];
	data[0] = id; data[1] = g_session[id]; data[2] = profile;
	api("POST", "/survival/server/join", body, "on_join", data, sizeof data);
	ezjson_free(body);
}

public on_join(EzHttpRequest:request)
{
	new data[3];
	ezhttp_get_user_data(request, data);
	new id = data[0], code, EzJSON:root = answer(request, code);
	if (is_user_connected(id) && g_session[id] == data[1] && code == 200 && J_OK(root))
	{
		new EzJSON:st = ezjson_object_get_value(root, "state");
		apply_state(id, st);
		ezjson_free(st);
		g_loaded[id] = true;
		send_progress(id);
		czm_chat(id, "^4[LVL]^1 Ваш уровень: ^4%d^1, токенов: ^4%d^1. Меню: ^4lvl", "^4[LVL]^1 Your level: ^4%d^1, tokens: ^4%d^1. Menu: ^4lvl", g_lvl[id], g_tokens[id]);
		look(id);
	}
	if (J_OK(root))
		ezjson_free(root);
}

public client_disconnected(id)
{
	// what the player did before leaving still goes with the next batch
	if (g_loaded[id])
		keep_leaver(id);
	g_session[id]++;
	g_progressUi[id] = false;
	reset_player(id);
	remove_task(TASK_LOOK + id);
}

// Deltas of players who left are kept by profile until the next batch.
new Trie:g_leavers;

keep_leaver(id)
{
	if (!g_leavers)
		g_leavers = TrieCreate();
	new key[16], row[D_COUNT + 1];
	num_to_str(g_profile[id], key, charsmax(key));
	TrieGetArray(g_leavers, key, row, sizeof row);
	for (new d = 0; d < D_COUNT; d++)
		row[d] += g_delta[id][d];
	TrieSetArray(g_leavers, key, row, sizeof row);
}

apply_state(id, EzJSON:st)
{
	if (!J_OK(st))
		return;
	g_lvl[id] = ezjson_object_get_number(st, "lvl");
	g_tokens[id] = ezjson_object_get_number(st, "tokens");
	g_wr[id] = ezjson_object_get_number(st, "wr", true);
	g_nextKills[id] = ezjson_object_get_number(st, "next_lvl_kills", true);
	g_nextTime[id] = ezjson_object_get_number(st, "next_lvl_time", true);
	// Old API releases omit the step fields; these are their documented rules.
	g_killsStep[id] = ezjson_object_get_number(st, "lvl_kills_step", true);
	g_timeStep[id] = ezjson_object_get_number(st, "lvl_time_step", true);
	if (g_killsStep[id] <= 0) g_killsStep[id] = 10;
	if (g_timeStep[id] <= 0) g_timeStep[id] = 600;
	new left = ezjson_object_get_number(st, "boosts.tokens", true);
	g_tokBoostUntil[id] = left > 0 ? get_gametime() + float(left) : 0.0;
	g_bpActive[id] = ezjson_object_get_bool(st, "battlepass.active", true);
	g_bpDailyReady[id] = ezjson_object_get_bool(st, "battlepass.daily", true);
	g_bpLeftDays[id] = (ezjson_object_get_number(st, "battlepass.left", true) + 86399) / 86400;
	new const kinds[6][] = { "kills", "time", "ctwin", "spent", "sent", "days" };
	for (new k = 0; k < 6; k++)
	{
		new path[40];
		formatex(path, charsmax(path), "battlepass.progress.%s", kinds[k]);
		g_bpProgress[id][k] = ezjson_object_get_number(st, path, true);
	}
	new EzJSON:claimed = ezjson_object_get_value(st, "battlepass.claimed", true);
	g_bpClaimed[id] = J_OK(claimed) ? ezjson_array_get_count(claimed) : 0;
	if (J_OK(claimed)) ezjson_free(claimed);
	g_payToday[id] = ezjson_object_get_number(st, "pay.today", true);
	new EzJSON:crate = ezjson_object_get_value(st, "crate");
	for (new k = 0; k < g_crateCount; k++)
	{
		new left = J_OK(crate) && ezjson_object_has_value(crate, g_crateId[k]) ? ezjson_object_get_number(crate, g_crateId[k]) : 0;
		g_crateUntil[id][k] = left > 0 ? get_gametime() + float(left) : 0.0;
	}
	g_charges[id] = J_OK(crate) ? ezjson_object_get_number(crate, "charges") : 0;
	if (J_OK(crate)) ezjson_free(crate);

	new EzJSON:owned = ezjson_object_get_value(st, "owned");
	new EzJSON:equipped = ezjson_object_get_value(st, "equipped");
	for (new c = 0; c < g_catCount; c++)
	{
		for (new i = 0; i < MAX_ITEMS; i++)
			g_owned[id][c][i] = false;
		new EzJSON:list = J_OK(owned) ? ezjson_object_get_value(owned, g_catKey[c]) : J_NONE;
		for (new n = 0, count = J_OK(list) ? ezjson_array_get_count(list) : 0; n < count; n++)
		{
			new item[24];
			ezjson_array_get_string(list, n, item, charsmax(item));
			new i = item_index(c, item);
			if (i >= 0)
				g_owned[id][c][i] = true;
		}
		if (J_OK(list)) ezjson_free(list);
		new item[24];
		item[0] = 0;
		if (J_OK(equipped) && ezjson_object_has_value(equipped, g_catKey[c]))
			ezjson_object_get_string(equipped, g_catKey[c], item, charsmax(item));
		g_equip[id][c] = item[0] ? item_index(c, item) : -1;
	}
	if (J_OK(owned)) ezjson_free(owned);
	if (J_OK(equipped)) ezjson_free(equipped);
	send_progress(id);
	new ret;
	ExecuteForward(g_fwChanged, ret, id);
}

bool:boosted(id)
{
	return g_tokBoostUntil[id] > get_gametime();
}

// ---------------------------------------------------------------- what happens in the game

public fw_killed_post(victim, attacker, shouldgib)
{
	if (g_loaded[victim])
		g_delta[victim][D_DEATHS]++;
	if (!(1 <= attacker <= MaxClients) || attacker == victim || !g_loaded[attacker])
		return;
	g_delta[attacker][D_KILLS]++;
	count_map_kill(attacker);
	if (!zp_get_user_zombie(attacker) && zp_get_user_zombie(victim))
	{
		g_delta[attacker][D_ZKILLS]++;
		new name[32];
		get_user_name(victim, name, charsmax(name));
		tokens_hud(attacker, boosted(attacker) ? 2 : 1, czm_lang(attacker) == CZM_EN ? "for the kill" : "за убийство", name);
	}
}

public zp_user_infected_post(id, infector, nemesis)
{
	if (g_loaded[id])
		g_delta[id][D_DEATHS]++;
	if (1 <= infector <= MaxClients && infector != id && g_loaded[infector])
	{
		g_delta[infector][D_KILLS]++;
		count_map_kill(infector);
	}
	if (!nemesis)
		set_user_rendering(id);
}

count_map_kill(id)
{
	new key[16], kills;
	num_to_str(g_profile[id], key, charsmax(key));
	TrieGetCell(g_mapKills, key, kills);
	TrieSetCell(g_mapKills, key, kills + 1);
}

public ev_round_start()
{
	for (new id = 1; id <= MaxClients; id++)
		g_inRound[id] = g_loaded[id] && 1 <= get_user_team(id) <= 2;
}

public ev_round_end()
{
	new humans;
	for (new id = 1; id <= MaxClients; id++)
		if (is_user_alive(id) && !zp_get_user_zombie(id))
			humans++;
	for (new id = 1; id <= MaxClients; id++)
	{
		if (!g_inRound[id] || !g_loaded[id])
			continue;
		g_inRound[id] = false;
		new bool:human = !zp_get_user_zombie(id);
		new bool:won = humans > 0 ? human : !human;
		g_delta[id][D_ROUNDS]++;
		if (won)
			g_delta[id][D_WINS]++;
		if (won && human)
			g_delta[id][D_CTWINS]++;
		if (human && is_user_alive(id))
		{
			g_delta[id][D_SURVIVED]++;
			tokens_hud(id, boosted(id) ? 6 : 3, czm_lang(id) == CZM_EN ? "survived the round" : "выжил раунд", "");
		}
	}
}

// ---------------------------------------------------------------- reports

public task_report()
{
	if (g_sending || !g_serverToken[0])
		return;
	for (new id = 1; id <= MaxClients; id++)
		if (g_loaded[id] && 1 <= get_user_team(id) <= 2)
			g_delta[id][D_TIME] += floatround(REPORT_EVERY);
	if (!J_OK(g_pending))
		build_batch();
	if (!J_OK(g_pending))
		return;
	g_sending = true;
	api("POST", "/survival/server/report", g_pending, "on_report");
}

build_batch()
{
	new EzJSON:entries = ezjson_init_array(), count;
	for (new id = 1; id <= MaxClients; id++)
	{
		if (!g_loaded[id])
			continue;
		new EzJSON:e = ezjson_init_object(), name[32], any_ = 0;
		get_user_name(id, name, charsmax(name));
		ezjson_object_set_number(e, "player", g_profile[id]);
		ezjson_object_set_string(e, "nick", name);
		for (new d = 0; d < D_COUNT; d++)
		{
			ezjson_object_set_number(e, D_NAMES[d], g_delta[id][d]);
			any_ += g_delta[id][d];
			g_delta[id][d] = 0;
		}
		if (any_)
		{
			ezjson_array_append_value(entries, e);
			count++;
		}
		ezjson_free(e);
	}
	if (g_leavers)
	{
		new TrieIter:it = TrieIterCreate(g_leavers), key[16], row[D_COUNT + 1];
		while (!TrieIterEnded(it))
		{
			TrieIterGetKey(it, key, charsmax(key));
			TrieIterGetArray(it, row, sizeof row);
			new EzJSON:e = ezjson_init_object();
			ezjson_object_set_number(e, "player", str_to_num(key));
			for (new d = 0; d < D_COUNT; d++)
				ezjson_object_set_number(e, D_NAMES[d], row[d]);
			ezjson_array_append_value(entries, e);
			ezjson_free(e);
			count++;
			TrieIterNext(it);
		}
		TrieIterDestroy(it);
		TrieClear(g_leavers);
	}

	new EzJSON:live = live_snapshot();
	if (!count && !J_OK(live))
	{
		ezjson_free(entries);
		return;
	}
	g_batchSeq++;
	formatex(g_pendingId, charsmax(g_pendingId), "%d-%d-%d", get_cvar_num("hostport"), g_mapStamp, g_batchSeq);
	new server[32];
	get_pcvar_string(g_cvarServer, server, charsmax(server));
	g_pending = ezjson_init_object();
	ezjson_object_set_string(g_pending, "batch", g_pendingId);
	ezjson_object_set_string(g_pending, "server", server);
	ezjson_object_set_value(g_pending, "entries", entries);
	ezjson_free(entries);
	if (J_OK(live))
	{
		ezjson_object_set_value(g_pending, "live", live);
		ezjson_free(live);
	}
}

EzJSON:live_snapshot()
{
	new EzJSON:live = ezjson_init_object(), EzJSON:players = ezjson_init_array(), map[32], name[32];
	get_mapname(map, charsmax(map));
	ezjson_object_set_string(live, "map", map);
	ezjson_object_set_number(live, "timeleft", get_timeleft());
	ezjson_object_set_number(live, "max", MaxClients);
	for (new id = 1; id <= MaxClients; id++)
	{
		if (!is_user_connected(id) || is_user_hltv(id))
			continue;
		new EzJSON:p = ezjson_init_object();
		get_user_name(id, name, charsmax(name));
		ezjson_object_set_string(p, "nick", name);
		ezjson_object_set_number(p, "frags", get_user_frags(id));
		ezjson_object_set_number(p, "deaths", get_user_deaths(id));
		ezjson_object_set_number(p, "lvl", g_loaded[id] ? g_lvl[id] : 0);
		ezjson_object_set_bool(p, "zombie", bool:zp_get_user_zombie(id));
		ezjson_object_set_bool(p, "alive", bool:is_user_alive(id));
		ezjson_object_set_bool(p, "bot", bool:is_user_bot(id));
		ezjson_object_set_number(p, "profile", g_profile[id]);
		ezjson_array_append_value(players, p);
		ezjson_free(p);
	}
	ezjson_object_set_value(live, "players", players);
	ezjson_free(players);
	return live;
}

public on_report(EzHttpRequest:request)
{
	g_sending = false;
	new code, EzJSON:root = answer(request, code);
	if (code != 200 || !J_OK(root))
	{
		// the same batch goes again next time: the API counts it once
		if (J_OK(root)) ezjson_free(root);
		return;
	}
	ezjson_free(g_pending);
	g_pending = J_NONE;

	new EzJSON:states = ezjson_object_get_value(root, "states");
	new EzJSON:events = ezjson_object_get_value(root, "events");
	for (new id = 1; id <= MaxClients; id++)
	{
		if (!g_loaded[id])
			continue;
		new key[16];
		num_to_str(g_profile[id], key, charsmax(key));
		if (J_OK(states) && ezjson_object_has_value(states, key))
		{
			new EzJSON:st = ezjson_object_get_value(states, key);
			new before = g_equip_signature(id);
			apply_state(id, st);
			ezjson_free(st);
			if (before != g_equip_signature(id))
				look(id);
		}
		if (J_OK(events) && ezjson_object_has_value(events, key))
		{
			new EzJSON:list = ezjson_object_get_value(events, key);
			for (new n = 0, count = ezjson_array_get_count(list); n < count; n++)
			{
				new EzJSON:ev = ezjson_array_get_value(list, n), type[12], reason[16];
				ezjson_object_get_string(ev, "type", type, charsmax(type));
				if (equal(type, "level"))
					level_up(id, ezjson_object_get_number(ev, "lvl"));
				else
				{
					ezjson_object_get_string(ev, "reason", reason, charsmax(reason));
					// kills and survived rounds were shown at once by this plugin
					if (equal(reason, "time"))
						tokens_hud(id, ezjson_object_get_number(ev, "amount"), czm_lang(id) == CZM_EN ? "for 10 minutes in the game" : "за 10 минут в игре", "");
					else if (equal(reason, "battlepass"))
						tokens_hud(id, ezjson_object_get_number(ev, "amount"), czm_lang(id) == CZM_EN ? "battle pass task" : "задание пропуска", "");
				}
				ezjson_free(ev);
			}
			ezjson_free(list);
		}
	}
	if (J_OK(states)) ezjson_free(states);
	if (J_OK(events)) ezjson_free(events);
	ezjson_free(root);
}

g_equip_signature(id)
{
	new sum;
	for (new c = 0; c < g_catCount; c++)
		sum = sum * 31 + g_equip[id][c] + 1;
	return sum;
}

// ---------------------------------------------------------------- the map top

public task_map_end()
{
	if (g_mapEndSent || get_cvar_float("mp_timelimit") <= 0.0)
		return;
	new left = get_timeleft();
	if (left <= 0 || left > 12)
		return;
	g_mapEndSent = true;
	new EzJSON:body = ezjson_init_object(), EzJSON:kills = ezjson_init_object(), batch[48];
	formatex(batch, charsmax(batch), "%d-%d", get_cvar_num("hostport"), g_mapStamp);
	ezjson_object_set_string(body, "batch", batch);
	new TrieIter:it = TrieIterCreate(g_mapKills), key[16], value;
	while (!TrieIterEnded(it))
	{
		TrieIterGetKey(it, key, charsmax(key));
		TrieIterGetCell(it, value);
		ezjson_object_set_number(kills, key, value);
		TrieIterNext(it);
	}
	TrieIterDestroy(it);
	ezjson_object_set_value(body, "kills", kills);
	ezjson_free(kills);
	api("POST", "/survival/server/map_end", body, "on_map_end");
	ezjson_free(body);
}

public on_map_end(EzHttpRequest:request)
{
	new code, EzJSON:root = answer(request, code);
	if (code == 200 && J_OK(root))
	{
		new EzJSON:top = ezjson_object_get_value(root, "top");
		new count = J_OK(top) ? min(ezjson_array_get_count(top), 3) : 0;
		if (count)
		{
			czm_chat(0, "^4[LVL]^1 Лучшие на карте:", "^4[LVL]^1 Best on this map:");
			czm_play_music(0, g_hRank, true);
		}
		for (new n = 0; n < count; n++)
		{
			new EzJSON:row = ezjson_array_get_value(top, n), nick[32];
			ezjson_object_get_string(row, "nick", nick, charsmax(nick));
			czm_chat(0, "^4%d. ^3%s^1 — %d убийств, ^4+%d^1 токенов", "^4%d. ^3%s^1 — %d kills, ^4+%d^1 tokens",
				n + 1, nick, ezjson_object_get_number(row, "kills"), ezjson_object_get_number(row, "reward"));
			ezjson_free(row);
		}
		if (J_OK(top)) ezjson_free(top);
	}
	if (J_OK(root)) ezjson_free(root);
}

// ---------------------------------------------------------------- HUD

tokens_hud(id, amount, const reason[], const victim[])
{
	if (!is_user_connected(id) || amount <= 0)
		return;
	if (czm_menu_rich(id))
	{
		new text[96];
		formatex(text, charsmax(text), "%s%s%s", reason, victim[0] ? " " : "", victim);
		toast(id, 1, amount, text);
		return;
	}
	set_hudmessage(255, 200, 40, 0.02, 0.17, 0, 0.0, 3.0, 0.1, 0.4, -1);
	if (victim[0])
		ShowSyncHudMsg(id, g_hudTokens, "+%d Tokens %s %s", amount, reason, victim);
	else
		ShowSyncHudMsg(id, g_hudTokens, "+%d Tokens %s", amount, reason);
}

level_up(id, level)
{
	new name[32];
	get_user_name(id, name, charsmax(name));
	g_lvl[id] = max(g_lvl[id], level);
	if (czm_menu_rich(id))
	{
		toast(id, 2, level, name);
		czm_play_sound(id, g_hRank);
		return;
	}
	set_hudmessage(80, 220, 255, 0.02, 0.21, 0, 0.0, 4.0, 0.1, 0.5, -1);
	ShowSyncHudMsg(id, g_hudLevel, czm_lang(id) == CZM_EN ? "%s reached LVL %d" : "%s повысил уровень: LVL %d", name, level);
	czm_play_sound(id, g_hRank);
}

// ---------------------------------------------------------------- what the player wears

public fw_spawn_post(id)
{
	if (is_user_alive(id) && g_loaded[id])
	{
		remove_task(TASK_LOOK + id);
		set_task(0.5, "task_look", TASK_LOOK + id);
	}
}

public zp_user_humanized_post(id, survivor)
{
	if (g_loaded[id] && !survivor)
		look(id);
}

public task_look(taskid)
{
	look(taskid - TASK_LOOK);
}

look(id)
{
	if (!is_user_alive(id) || zp_get_user_zombie(id) || zp_get_user_survivor(id))
		return;
	knife_look(id);
	new skin = cat_index("skin"), glow = cat_index("skincolor"), model[24];
	new worn = (skin >= 0) ? g_equip[id][skin] : -1;
	if (worn >= 0 && skin_model(skin, worn, model, charsmax(model)))
		zp_override_user_model(id, model);
	new r, g, b;
	if (glow >= 0 && g_equip[id][glow] >= 0)
	{
		hex_color(g_itemId[glow][g_equip[id][glow]], r, g, b);
		set_user_rendering(id, kRenderFxGlowShell, r, g, b, kRenderNormal, 16);
	}
	else if (worn >= 0 && g_itemGlow[skin][worn][0])
	{
		// a skin with a glow of its own (the survivor) shines when no other glow is chosen
		hex_color(g_itemGlow[skin][worn], r, g, b);
		set_user_rendering(id, kRenderFxGlowShell, r, g, b, kRenderNormal, 10);
	}
	else
		set_user_rendering(id);
}

public fw_knife_deploy_post(weapon)
{
	new id = get_pdata_cbase(weapon, 41, 4); // m_pPlayer
	if (1 <= id <= MaxClients)
		knife_look(id);
}

knife_look(id)
{
	if (!is_user_alive(id) || !g_loaded[id] || zp_get_user_zombie(id) || get_user_weapon(id) != CSW_KNIFE)
		return;
	new c = cat_index("knife");
	if (c < 0 || g_equip[id][c] < 0)
		return;
	for (new k = 0; k < sizeof KNIFE_IDS; k++)
	{
		if (!equal(g_itemId[c][g_equip[id][c]], KNIFE_IDS[k]) || !g_knifeV[k])
			continue;
		new path[64];
		formatex(path, charsmax(path), "models/czm_survival/v_%s.mdl", KNIFE_IDS[k]);
		set_pev(id, pev_viewmodel2, path);
		if (g_knifeP[k])
		{
			formatex(path, charsmax(path), "models/czm_survival/p_%s.mdl", KNIFE_IDS[k]);
			set_pev(id, pev_weaponmodel2, path);
		}
		return;
	}
}

// a toast of the CZM game: kind 1 "+N tokens" (text: why), 2 a new level (text: the nick)
toast(id, kind, value, const text[])
{
	engfunc(EngFunc_MessageBegin, MSG_ONE, g_msgToast, Float:{0.0, 0.0, 0.0}, id);
	write_byte(kind);
	write_short(value);
	write_string(text);
	message_end();
}

hex6(value, out[8])
{
	static const digits[] = "0123456789ABCDEF";
	for (new i = 5; i >= 0; i--)
	{
		out[i] = digits[value & 0xF];
		value >>= 4;
	}
	out[6] = EOS;
}

// the level colours of Kontra
level_color(level)
{
	if (level <= 10) return 0xFFFFFF;
	if (level <= 20) return 0x00FFAA;
	if (level <= 40) return 0x00FFFF;
	if (level <= 80) return 0x0088FF;
	if (level <= 160) return 0xAA00FF;
	if (level <= 320) return 0xFF8800;
	if (level <= 640) return 0xFFD700;
	if (level <= 1280) return 0xFF4500;
	return 0xFF0000;
}

// what the tag of a player says: the prefix in the owner's language and its colour
tag_parts(id, prefix[], len, &color)
{
	new cat = cat_index("prefix"), col = cat_index("prefcolor");
	new p = g_loaded[id] && cat >= 0 ? g_equip[id][cat] : -1;
	prefix[0] = EOS;
	color = 0xFFFFFF;
	if (p < 0)
		return;
	copy(prefix, len, g_itemName[cat][p][czm_lang(id)]);
	if (col >= 0 && g_equip[id][col] >= 0)
	{
		new r, g, b;
		hex_color(g_itemId[col][g_equip[id][col]], r, g, b);
		color = (r << 16) | (g << 8) | b;
	}
}

// Private state goes only to its owner and only to a client that supports this message.
send_progress(id)
{
	if (!g_progressUi[id] || !is_user_connected(id))
		return;
	new sig[96], level = g_loaded[id] ? g_lvl[id] : -1;
	formatex(sig, charsmax(sig), "%d|%d|%d|%d|%d|%d", level, g_tokens[id], g_nextKills[id], g_killsStep[id], g_nextTime[id], g_timeStep[id]);
	if (equal(sig, g_progressSent[id]))
		return;
	copy(g_progressSent[id], charsmax(g_progressSent[]), sig);
	engfunc(EngFunc_MessageBegin, MSG_ONE, g_msgProgress, Float:{0.0, 0.0, 0.0}, id);
	write_long(level);
	write_long(g_tokens[id]);
	write_long(g_nextKills[id]);
	write_long(g_killsStep[id]);
	write_long(g_nextTime[id]);
	write_long(g_timeStep[id]);
	message_end();
}

send_tag(id, to)
{
	new prefix[32], priv[12], color;
	tag_parts(id, prefix, charsmax(prefix), color);
	czm_privilege_name(id, priv, charsmax(priv));
	engfunc(EngFunc_MessageBegin, MSG_ONE, g_msgTag, Float:{0.0, 0.0, 0.0}, to);
	write_byte(id);
	write_short(g_loaded[id] ? g_lvl[id] : 0);
	write_byte(g_loaded[id] ? clamp(g_wr[id], 0, 100) : 0);
	write_string(prefix);
	write_long(color);
	write_string(priv);
	message_end();
}

// every two seconds: a changed tag goes to every CZM game, a new CZM game gets them all
public task_tags()
{
	new players[MAX_PLAYERS], count, viewers[MAX_PLAYERS], seen;
	get_players(players, count, "ch");
	for (new k = 0; k < count; k++)
		send_progress(players[k]);
	for (new k = 0; k < count; k++)
		if (czm_menu_rich(players[k]))
			viewers[seen++] = players[k];

	for (new k = 0; k < count; k++)
	{
		new id = players[k], prefix[32], priv[12], color, sig[64];
		tag_parts(id, prefix, charsmax(prefix), color);
		czm_privilege_name(id, priv, charsmax(priv));
		formatex(sig, charsmax(sig), "%d|%d|%s|%x|%s", g_loaded[id] ? g_lvl[id] : 0, g_wr[id], prefix, color, priv);
		if (equal(sig, g_tagSent[id]))
			continue;
		copy(g_tagSent[id], charsmax(g_tagSent[]), sig);
		for (new v = 0; v < seen; v++)
			if (g_tagSynced[viewers[v]])
				send_tag(id, viewers[v]);
	}
	for (new v = 0; v < seen; v++)
	{
		new to = viewers[v];
		if (g_tagSynced[to])
			continue;
		g_tagSynced[to] = true;
		for (new k = 0; k < count; k++)
			send_tag(players[k], to);
	}
}

hex_color(const hex[], &r, &g, &b)
{
	new value = 0;
	for (new i = hex[0] == '#' ? 1 : 0, n = 0; hex[i] && n < 6; i++, n++)
	{
		new c = hex[i], digit = ('0' <= c <= '9') ? c - '0' : (('a' <= c <= 'f') ? c - 'a' + 10 : (('A' <= c <= 'F') ? c - 'A' + 10 : 0));
		value = value * 16 + digit;
	}
	r = (value >> 16) & 0xFF;
	g = (value >> 8) & 0xFF;
	b = value & 0xFF;
}

// ---------------------------------------------------------------- chat

public cmd_say(id)
{
	return chat(id, false);
}

public cmd_say_team(id)
{
	return chat(id, true);
}

chat(id, bool:team)
{
	new text[192];
	read_args(text, charsmax(text));
	remove_quotes(text);
	trim(text);
	if (!text[0] || text[0] == '@')
		return PLUGIN_CONTINUE;
	if (text[0] == '/' || text[0] == '!')
	{
		new cmd[24], arg[48];
		parse(text[1], cmd, charsmax(cmd), arg, charsmax(arg));
		if (equali(cmd, "lvl") || equali(cmd, "лвл"))
			return menu_lvl(id);
		if (equali(cmd, "top"))
			return show_top(id);
		if (equali(cmd, "promo"))
			return use_promo(id, arg);
		return PLUGIN_CONTINUE;
	}
	if (equali(text, "lvl") || equali(text, "лвл"))
		return menu_lvl(id);

	// the message goes out with the level and the prefix, as on Kontra
	new name[32], priv[12], bool:zombie = bool:zp_get_user_zombie(id), bool:dead = !is_user_alive(id);
	get_user_name(id, name, charsmax(name));
	czm_privilege_name(id, priv, charsmax(priv));
	new prefix = cat_index("prefix"), color = cat_index("prefcolor");
	new p = g_loaded[id] && prefix >= 0 ? g_equip[id][prefix] : -1;
	new code = 3;
	if (p >= 0 && color >= 0 && g_equip[id][color] >= 0)
		code = chat_color(g_itemId[color][g_equip[id][color]]);
	for (new to = 1; to <= MaxClients; to++)
	{
		if (!is_user_connected(to) || is_user_bot(to))
			continue;
		if (team && (bool:zp_get_user_zombie(to) != zombie || get_user_team(to) != get_user_team(id)))
			continue;
		new lang = czm_lang(to), line[256], len;
		if (dead)
			len += formatex(line[len], charsmax(line) - len, "^1*%s* ", lang == CZM_EN ? "DEAD" : "МЁРТВ");
		if (team)
			len += formatex(line[len], charsmax(line) - len, "^1(%s) ", zombie ? (lang == CZM_EN ? "Zombies" : "Зомби") : (lang == CZM_EN ? "Humans" : "Люди"));
		if (priv[0])
			len += formatex(line[len], charsmax(line) - len, "^3[%s] ", priv);
		if (czm_menu_rich(to))
		{
			// ^7RRGGBB: a colour of the CZM game's chat
			if (g_loaded[id])
			{
				new hex[8];
				hex6(level_color(g_lvl[id]), hex);
				len += formatex(line[len], charsmax(line) - len, "^7%s[LVL %d] ", hex, g_lvl[id]);
			}
			if (p >= 0)
			{
				new tagColor = 0xFFFFFF, r, g, b;
				if (color >= 0 && g_equip[id][color] >= 0)
				{
					hex_color(g_itemId[color][g_equip[id][color]], r, g, b);
					tagColor = (r << 16) | (g << 8) | b;
				}
				new hex[8];
				hex6(tagColor, hex);
				len += formatex(line[len], charsmax(line) - len, "^7%s[%s] ", hex, g_itemName[prefix][p][lang]);
			}
		}
		else
		{
			if (g_loaded[id])
				len += formatex(line[len], charsmax(line) - len, "^4[LVL %d] ", g_lvl[id]);
			if (p >= 0)
				len += formatex(line[len], charsmax(line) - len, "%c[%s] ", code, g_itemName[prefix][p][lang]);
		}
		formatex(line[len], charsmax(line) - len, "^3%s^1: %s", name, text);
		client_print_color(to, id, "%s", line);
	}
	// the server log and the panel console still see the chat
	log_message("^"%s<%d><%s><>^" %s ^"%s^"", name, get_user_userid(id), "", team ? "say_team" : "say", text);
	return PLUGIN_HANDLED;
}

// The game's chat has three colours: the team colour, green and the normal yellow.
chat_color(const hex[])
{
	new r, g, b;
	hex_color(hex, r, g, b);
	if (g > 160 && r < 120 && b < 170)
		return 4; // green
	if (r > 200 && g > 120 && b < 120)
		return 1; // the normal yellow
	return 3;     // the team colour
}

// ---------------------------------------------------------------- actions

act(id, const name[], EzJSON:args, const callback[] = "on_action")
{
	if (!g_loaded[id])
	{
		czm_chat(id, "^4[LVL]^1 LVL MOD работает для игроков CZM.", "^4[LVL]^1 LVL MOD works for CZM players.");
		if (J_OK(args)) ezjson_free(args);
		return;
	}
	new EzJSON:body = ezjson_init_object(), op[48];
	formatex(op, charsmax(op), "%d-%d-%d-%d", g_profile[id], get_systime(), random_num(100000, 999999), g_session[id]);
	ezjson_object_set_number(body, "player", g_profile[id]);
	ezjson_object_set_string(body, "op", op);
	ezjson_object_set_string(body, "action", name);
	if (J_OK(args))
	{
		ezjson_object_set_value(body, "args", args);
		ezjson_free(args);
	}
	new data[2];
	data[0] = id; data[1] = g_session[id];
	api("POST", "/survival/server/action", body, callback, data, sizeof data);
	ezjson_free(body);
}

// answers nobody needs to read about (a used charge): only the state is taken
public on_quiet(EzHttpRequest:request)
{
	new data[2];
	ezhttp_get_user_data(request, data);
	new id = data[0], code, EzJSON:root = answer(request, code);
	if (is_user_connected(id) && g_session[id] == data[1] && code == 200 && J_OK(root))
	{
		new EzJSON:st = ezjson_object_get_value(root, "state");
		apply_state(id, st);
		ezjson_free(st);
	}
	if (J_OK(root)) ezjson_free(root);
}

EzJSON:args1(const k1[], const v1[])
{
	new EzJSON:a = ezjson_init_object();
	ezjson_object_set_string(a, k1, v1);
	return a;
}

EzJSON:args2(const k1[], const v1[], const k2[], const v2[])
{
	new EzJSON:a = args1(k1, v1);
	ezjson_object_set_string(a, k2, v2);
	return a;
}

public on_action(EzHttpRequest:request)
{
	new data[2];
	ezhttp_get_user_data(request, data);
	new id = data[0], code, EzJSON:root = answer(request, code);
	if (!is_user_connected(id) || g_session[id] != data[1])
	{
		if (J_OK(root)) ezjson_free(root);
		return;
	}
	if (code == 200 && J_OK(root))
	{
		new action[16];
		ezjson_object_get_string(root, "action", action, charsmax(action));
		new EzJSON:st = ezjson_object_get_value(root, "state");
		apply_state(id, st);
		ezjson_free(st);
		look(id);
		done_message(id, action, root);
	}
	else
	{
		new error[24];
		if (J_OK(root))
			ezjson_object_get_string(root, "error", error, charsmax(error));
		error_message(id, error);
	}
	if (J_OK(root)) ezjson_free(root);
}

done_message(id, const action[], EzJSON:root)
{
	if (equal(action, "buy"))
	{
		if (ezjson_object_get_bool(root, "bought"))
			czm_chat(id, "^4[LVL]^1 Куплено и надето. Осталось токенов: ^4%d", "^4[LVL]^1 Bought and put on. Tokens left: ^4%d", g_tokens[id]);
		else
			czm_chat(id, "^4[LVL]^1 Надето.", "^4[LVL]^1 Put on.");
	}
	else if (equal(action, "equip"))
		czm_chat(id, "^4[LVL]^1 Готово.", "^4[LVL]^1 Done.");
	else if (equal(action, "upgrade"))
		czm_chat(id, "^4[LVL]^1 Прокачка куплена. LVL ^4%d^1, токенов ^4%d", "^4[LVL]^1 Upgrade bought. LVL ^4%d^1, tokens ^4%d", g_lvl[id], g_tokens[id]);
	else if (equal(action, "pay"))
	{
		new nick[32];
		ezjson_object_get_string(root, "nick", nick, charsmax(nick));
		czm_chat(id, "^4[LVL]^1 Передано ^4%d^1 токенов игроку ^3%s", "^4[LVL]^1 Sent ^4%d^1 tokens to ^3%s", ezjson_object_get_number(root, "amount"), nick);
		new target = ezjson_object_get_number(root, "target");
		for (new to = 1; to <= MaxClients; to++)
		{
			if (g_loaded[to] && g_profile[to] == target)
			{
				new name[32];
				get_user_name(id, name, charsmax(name));
				czm_chat(to, "^4[LVL]^1 ^4+%d^1 токенов от ^3%s", "^4[LVL]^1 ^4+%d^1 tokens from ^3%s", ezjson_object_get_number(root, "amount"), name);
				g_tokens[to] += ezjson_object_get_number(root, "amount");
			}
		}
	}
	else if (equal(action, "reward"))
		czm_chat(id, "^4[LVL]^1 Аирдроп: ^4+%d^1 токенов!", "^4[LVL]^1 Airdrop: ^4+%d^1 tokens!", ezjson_object_get_number(root, "amount"));
	else if (equal(action, "crate"))
		czm_chat(id, "^4[LVL]^1 Ящик открыт на 30 минут: всё выдаётся при каждом спавне человеком.", "^4[LVL]^1 The crate is yours for 30 minutes: it is given at every spawn as a human.");
	else if (equal(action, "bp_buy"))
		czm_chat(id, "^4[LVL]^1 Боевой пропуск активирован на ^4%d^1 дней!", "^4[LVL]^1 Battle pass active for ^4%d^1 days!", g_bpDays);
	else if (equal(action, "bp_daily"))
		czm_chat(id, "^4[LVL]^1 ^4+%d^1 токенов за вход.", "^4[LVL]^1 ^4+%d^1 tokens for coming in.", ezjson_object_get_number(root, "amount"));
	else if (equal(action, "bp_final"))
		czm_chat(id, "^4[LVL]^1 Награда пропуска получена!", "^4[LVL]^1 Battle pass reward received!");
	else if (equal(action, "promo"))
	{
		new kind[8];
		ezjson_object_get_string(root, "kind", kind, charsmax(kind));
		czm_chat(id, "^4[LVL]^1 Промокод: ^4+%d %s", "^4[LVL]^1 Promo code: ^4+%d %s", ezjson_object_get_number(root, "amount"),
			equal(kind, "lvl") ? "LVL" : (czm_lang(id) == CZM_EN ? "tokens" : "токенов"));
	}
}

error_message(id, const error[])
{
	new const codes[][] = { "tokens", "not_owned", "admin_only", "not_for_sale", "pay_lvl", "pay_limit", "bp_active",
		"bp_inactive", "bp_daily_done", "bp_tasks", "bp_final_done", "promo", "promo_used", "player", "self" };
	new const ru[][] = { "Не хватает токенов.", "Этого у тебя нет.", "Только для администраторов.", "Это не продаётся.",
		"Перевод доступен с 10 LVL.", "Дневной лимит переводов исчерпан.", "Пропуск уже активен.", "Сначала купи боевой пропуск.",
		"Сегодня награда уже получена.", "Сначала выполни все задания.", "Эта награда уже получена.", "Нет такого промокода.",
		"Этот промокод ты уже использовал.", "Игрок не найден.", "Себе нельзя." };
	new const en[][] = { "Not enough tokens.", "You do not own it.", "Administrators only.", "Not for sale.",
		"Transfers open at LVL 10.", "Today's transfer limit is used up.", "The pass is already active.", "Buy the battle pass first.",
		"Today's reward is already taken.", "Finish every task first.", "This reward is already taken.", "No such promo code.",
		"You have used this promo code.", "Player not found.", "Not to yourself." };
	for (new i = 0; i < sizeof codes; i++)
	{
		if (equal(error, codes[i]))
		{
			czm_chat(id, "^4[LVL]^3 %s", "^4[LVL]^3 %s", ru[i], en[i]);
			return;
		}
	}
	czm_chat(id, "^4[LVL]^3 Не получилось, попробуй ещё раз.", "^4[LVL]^3 That did not work, try again.");
}

use_promo(id, const code[])
{
	if (!code[0])
	{
		czm_chat(id, "^4[LVL]^1 Напиши: ^4/promo КОД", "^4[LVL]^1 Type: ^4/promo CODE");
		return PLUGIN_HANDLED;
	}
	act(id, "promo", args1("code", code));
	return PLUGIN_HANDLED;
}

// ---------------------------------------------------------------- menus

// the LVL MOD tab of the server menu (czm_menu)
menu_register()
{
	czm_menu_section("lvl", "LVL MOD", "LVL MOD", "crown", 10);
	czm_menu_item("main", "go_lvl", "LVL MOD", "LVL MOD", "Уровень, токены, магазин", "Level, tokens, shop", "crown", "E7BB60", "#lvl", 10);
	czm_menu_item("lvl", "lvl_profile", "Профиль", "Profile", "Уровень, время, победы", "Level, time, wins", "user", "63A1EF", "on_czm_menu_lvl", 10);
	czm_menu_item("lvl", "lvl_shop", "Магазин", "Shop", "Скины, ножи, префиксы", "Skins, knives, prefixes", "cart", "E7BB60", "on_czm_menu_lvl", 20);
	czm_menu_item("lvl", "lvl_upgrades", "Прокачка", "Upgrades", "LVL и токены ×2", "LVL and tokens ×2", "bolt", "F59E0B", "on_czm_menu_lvl", 30);
	czm_menu_item("lvl", "lvl_crate", "Ящик с оружием", "Weapon crate", "Помощь на 30 минут", "Help for 30 minutes", "box", "E53F4D", "on_czm_menu_lvl", 40);
	czm_menu_item("lvl", "lvl_bp", "Боевой пропуск", "Battle pass", "Задания и награды", "Tasks and rewards", "ticket", "A855F7", "on_czm_menu_lvl", 50);
	czm_menu_item("lvl", "lvl_pay", "Перевод токенов", "Send tokens", "Другу на сервере", "To a friend here", "coins", "6BDAA7", "on_czm_menu_lvl", 60);
	czm_menu_item("lvl", "lvl_top", "Топ игроков", "Top players", "Лучшие на сервере", "The best here", "trophy", "E7BB60", "on_czm_menu_lvl", 70);
	czm_menu_item("lvl", "lvl_promo", "Промокод", "Promo code", "Ввести код", "Enter a code", "gift", "22D3EE", "on_czm_menu_lvl", 80);
}

public czm_menu_build(id, const section[])
{
	new ru = czm_lang(id) == CZM_RU, line[48];
	if (!g_loaded[id])
	{
		// guests: LVL MOD needs the CZM profile
		czm_menu_state(id, "go_lvl", _, ru ? "Для игроков CZM" : "For CZM players", _, false, true);
		static const keys[][] = {"lvl_profile", "lvl_shop", "lvl_upgrades", "lvl_crate", "lvl_bp", "lvl_pay", "lvl_top", "lvl_promo"};
		for (new k = 0; k < sizeof keys; k++)
			czm_menu_state(id, keys[k], _, _, _, false, true);
		return;
	}
	formatex(line, charsmax(line), ru ? "LVL %d · токенов %d" : "LVL %d · %d tokens", g_lvl[id], g_tokens[id]);
	czm_menu_state(id, "go_lvl", _, line);
	czm_menu_state(id, "lvl_profile", _, line);
	if (g_bpDailyReady[id])
	{
		czm_menu_state(id, "lvl_bp", _, _, ru ? "!НАГРАДА" : "!REWARD");
		czm_menu_state(id, "#lvl", _, _, "1");
	}
}

public on_czm_menu_lvl(id, const key[])
{
	if (!g_loaded[id])
		return menu_lvl(id);
	if (equal(key, "lvl_profile"))
		show_profile(id);
	else if (equal(key, "lvl_shop"))
		menu_shop(id);
	else if (equal(key, "lvl_upgrades"))
		menu_upgrades(id);
	else if (equal(key, "lvl_crate"))
		menu_crate(id);
	else if (equal(key, "lvl_bp"))
		menu_bp(id);
	else if (equal(key, "lvl_pay"))
		menu_pay(id);
	else if (equal(key, "lvl_top"))
		show_top(id);
	else if (equal(key, "lvl_promo"))
		use_promo(id, "");
	return PLUGIN_HANDLED;
}

public menu_lvl(id)
{
	if (!g_loaded[id])
	{
		czm_chat(id, "^4[LVL]^1 LVL MOD работает для игроков CZM: зайди из игры Counter Zombie Mobile.", "^4[LVL]^1 LVL MOD works for Counter Zombie Mobile players.");
		return PLUGIN_HANDLED;
	}
	czm_menu_open(id, "lvl");
	return PLUGIN_HANDLED;
}

show_profile(id)
{
	api_me(id);
}

api_me(id)
{
	// the profile in chat: one request for fresh numbers
	new EzJSON:body = ezjson_init_object(), EzJSON:args = ezjson_init_object(), name[32];
	get_user_name(id, name, charsmax(name));
	ezjson_object_set_number(body, "player", g_profile[id]);
	ezjson_object_set_string(body, "op", "profile-0000");
	ezjson_object_set_string(body, "action", "join");
	ezjson_object_set_string(args, "nick", name);
	ezjson_object_set_value(body, "args", args);
	ezjson_free(args);
	new data[2];
	data[0] = id; data[1] = g_session[id];
	api("POST", "/survival/server/join", body, "on_profile", data, sizeof data);
	ezjson_free(body);
}

public on_profile(EzHttpRequest:request)
{
	new data[2];
	ezhttp_get_user_data(request, data);
	new id = data[0], code, EzJSON:root = answer(request, code);
	if (is_user_connected(id) && g_session[id] == data[1] && code == 200 && J_OK(root))
	{
		new EzJSON:st = ezjson_object_get_value(root, "state");
		apply_state(id, st);
		new kills = ezjson_object_get_number(st, "kills"), deaths = ezjson_object_get_number(st, "deaths");
		new seconds = ezjson_object_get_number(st, "time"), matches = ezjson_object_get_number(st, "matches");
		new wins = ezjson_object_get_number(st, "wins"), wr = ezjson_object_get_number(st, "wr");
		new nk = ezjson_object_get_number(st, "next_lvl_kills"), nt = ezjson_object_get_number(st, "next_lvl_time");
		ezjson_free(st);
		czm_chat(id, "^4[LVL]^1 LVL ^4%d^1 · токены ^4%d^1 · убийств ^4%d^1 · смертей ^4%d", "^4[LVL]^1 LVL ^4%d^1 · tokens ^4%d^1 · kills ^4%d^1 · deaths ^4%d", g_lvl[id], g_tokens[id], kills, deaths);
		czm_chat(id, "^4[LVL]^1 В игре ^4%d ч %d мин^1 · раундов ^4%d^1 · побед ^4%d^1 (%d%%)", "^4[LVL]^1 Played ^4%d h %d min^1 · rounds ^4%d^1 · wins ^4%d^1 (%d%%)", seconds / 3600, seconds / 60 % 60, matches, wins, wr);
		czm_chat(id, "^4[LVL]^1 До следующего LVL: ^4%d^1 убийств или ^4%d^1 мин", "^4[LVL]^1 Next LVL: ^4%d^1 kills or ^4%d^1 min", nk, (nt + 59) / 60);
	}
	if (J_OK(root)) ezjson_free(root);
}

menu_shop(id)
{
	if (!g_catalogReady)
		return;
	new ru = czm_lang(id) == CZM_RU, title[96], item[80], info[4];
	formatex(title, charsmax(title), ru ? "\yМАГАЗИН^n\wТокены \r%d" : "\ySHOP^n\wTokens \r%d", g_tokens[id]);
	new menu = menu_create(title, "on_menu_shop");
	for (new c = 0; c < g_catCount; c++)
	{
		new have, total;
		for (new i = 0; i < g_itemCount[c]; i++)
		{
			if (g_itemShop[c][i] || g_owned[id][c][i]) total++;
			if (g_owned[id][c][i]) have++;
		}
		formatex(item, charsmax(item), "%s \d%d/%d", g_catName[c][ru ? CZM_RU : CZM_EN], have, total);
		num_to_str(c, info, charsmax(info));
		menu_additem(menu, item, info);
	}
	menu_display(id, menu);
}

public on_menu_shop(id, menu, key)
{
	if (key == MENU_EXIT)
	{
		menu_destroy(menu);
		return PLUGIN_HANDLED;
	}
	new info[4], dummy;
	menu_item_getinfo(menu, key, dummy, info, charsmax(info), _, _, dummy);
	menu_destroy(menu);
	menu_cat_items(id, str_to_num(info));
	return PLUGIN_HANDLED;
}

menu_cat_items(id, c)
{
	new ru = czm_lang(id) == CZM_RU, title[96], item[96], info[8];
	formatex(title, charsmax(title), "\y%s^n\wТокены \r%d", g_catName[c][ru ? CZM_RU : CZM_EN], g_tokens[id]);
	if (!ru)
		formatex(title, charsmax(title), "\y%s^n\wTokens \r%d", g_catName[c][CZM_EN], g_tokens[id]);
	new menu = menu_create(title, "on_menu_items");
	for (new i = 0; i < g_itemCount[c]; i++)
	{
		if (!g_itemShop[c][i] && !g_owned[id][c][i] && !g_itemAdmin[c][i])
			continue;
		new state_[32];
		if (g_equip[id][c] == i)
			copy(state_, charsmax(state_), ru ? "\y[надето]" : "\y[on]");
		else if (g_owned[id][c][i])
			copy(state_, charsmax(state_), ru ? "\g[есть]" : "\g[owned]");
		else
			formatex(state_, charsmax(state_), "\r%d", g_itemPrice[c][i]);
		formatex(item, charsmax(item), "%s %s", g_itemName[c][i][ru ? CZM_RU : CZM_EN], state_);
		formatex(info, charsmax(info), "%d %d", c, i);
		menu_additem(menu, item, info);
	}
	menu_display(id, menu);
}

public on_menu_items(id, menu, key)
{
	if (key == MENU_EXIT)
	{
		menu_destroy(menu);
		menu_shop(id);
		return PLUGIN_HANDLED;
	}
	new info[8], dummy, cs[4], is[4];
	menu_item_getinfo(menu, key, dummy, info, charsmax(info), _, _, dummy);
	menu_destroy(menu);
	parse(info, cs, charsmax(cs), is, charsmax(is));
	new c = str_to_num(cs), i = str_to_num(is);
	if (g_equip[id][c] == i)
		act(id, "equip", args2("cat", g_catKey[c], "item", ""));       // take off
	else
		act(id, "buy", args2("cat", g_catKey[c], "item", g_itemId[c][i])); // buys once, then only puts on
	return PLUGIN_HANDLED;
}

menu_upgrades(id)
{
	new ru = czm_lang(id) == CZM_RU, title[96], item[80];
	formatex(title, charsmax(title), ru ? "\yПРОКАЧКА^n\wТокены \r%d" : "\yUPGRADES^n\wTokens \r%d", g_tokens[id]);
	new menu = menu_create(title, "on_menu_upgrades");
	for (new u = 0; u < g_upCount; u++)
	{
		formatex(item, charsmax(item), "%s \r%d", g_upName[u][ru ? CZM_RU : CZM_EN], g_upPrice[u]);
		menu_additem(menu, item);
	}
	menu_display(id, menu);
}

public on_menu_upgrades(id, menu, key)
{
	menu_destroy(menu);
	if (0 <= key < g_upCount)
		act(id, "upgrade", args1("item", g_upId[key]));
	return PLUGIN_HANDLED;
}

menu_crate(id)
{
	new ru = czm_lang(id) == CZM_RU, title[128], item[96];
	formatex(title, charsmax(title), ru ? "\yЯЩИК С ОРУЖИЕМ^n\wна 30 минут, выдаётся каждый спавн^nТокены \r%d" : "\yWEAPON CRATE^n\wfor 30 minutes, given every spawn^nTokens \r%d", g_tokens[id]);
	new menu = menu_create(title, "on_menu_crate");
	new Float:now = get_gametime();
	for (new k = 0; k < g_crateCount; k++)
	{
		if (g_crateUntil[id][k] > now)
			formatex(item, charsmax(item), ru ? "%s \y[ещё %d мин]" : "%s \y[%d min left]", g_crateName[k][ru ? CZM_RU : CZM_EN], floatround((g_crateUntil[id][k] - now) / 60.0, floatround_ceil));
		else
			formatex(item, charsmax(item), "%s \r%d", g_crateName[k][ru ? CZM_RU : CZM_EN], g_cratePrice[k]);
		menu_additem(menu, item);
	}
	menu_display(id, menu);
}

public on_menu_crate(id, menu, key)
{
	menu_destroy(menu);
	if (0 <= key < g_crateCount)
		act(id, "crate", args1("item", g_crateId[key]));
	return PLUGIN_HANDLED;
}

menu_bp(id)
{
	new ru = czm_lang(id) == CZM_RU, title[160], item[80];
	if (!g_bpActive[id])
	{
		formatex(title, charsmax(title), ru ? "\yБОЕВОЙ ПРОПУСК^n\w%d дней: %d токенов каждый день и награды за задания^nТокены \r%d"
			: "\yBATTLE PASS^n\w%d days: %d tokens every day and task rewards^nTokens \r%d", g_bpDays, g_bpDaily, g_tokens[id]);
		new menu = menu_create(title, "on_menu_bp_buy");
		formatex(item, charsmax(item), ru ? "Купить за \r%d" : "Buy for \r%d", g_bpPrice);
		menu_additem(menu, item);
		menu_display(id, menu);
		return;
	}
	formatex(title, charsmax(title), ru ? "\yБОЕВОЙ ПРОПУСК^n\wОсталось \r%d\w дн., заданий выполнено \r%d\w из 24"
		: "\yBATTLE PASS^n\w\r%d\w days left, \r%d\w of 24 tasks done", g_bpLeftDays[id], g_bpClaimed[id]);
	new menu = menu_create(title, "on_menu_bp");
	formatex(item, charsmax(item), ru ? "Награда за вход \r+%d%s" : "Daily reward \r+%d%s", g_bpDaily, g_bpDailyReady[id] ? "" : (ru ? " \d(получено)" : " \d(taken)"));
	menu_additem(menu, item);
	formatex(item, charsmax(item), ru ? "Задания: убито %d, сыграно %d ч, побед %d" : "Tasks: %d kills, %d h played, %d wins",
		g_bpProgress[id][0], g_bpProgress[id][1] / 3600, g_bpProgress[id][2]);
	menu_additem(menu, item);
	menu_additem(menu, ru ? "Финал: +200 LVL" : "Final: +200 LVL");
	menu_additem(menu, ru ? "Финал: +50000 токенов" : "Final: +50000 tokens");
	menu_additem(menu, ru ? "Финал: префикс BATTLE PASS" : "Final: the BATTLE PASS prefix");
	menu_display(id, menu);
}

public on_menu_bp_buy(id, menu, key)
{
	menu_destroy(menu);
	if (key == 0)
		act(id, "bp_buy", J_NONE);
	return PLUGIN_HANDLED;
}

public on_menu_bp(id, menu, key)
{
	menu_destroy(menu);
	switch (key)
	{
		case 0: act(id, "bp_daily", J_NONE);
		case 1: czm_chat(id, "^4[LVL]^1 Все задания и прогресс — в панели на ^4%s", "^4[LVL]^1 Every task and its progress is in the panel at ^4%s", CZM_SITE);
		case 2: act(id, "bp_final", args1("item", "lvl"));
		case 3: act(id, "bp_final", args1("item", "tokens"));
		case 4: act(id, "bp_final", args1("item", "prefix"));
	}
	return PLUGIN_HANDLED;
}

menu_pay(id)
{
	new ru = czm_lang(id) == CZM_RU, title[128], name[32], info[4];
	formatex(title, charsmax(title), ru ? "\yПЕРЕВОД ТОКЕНОВ^n\wс %d LVL, до %d в день, сегодня \r%d" : "\ySEND TOKENS^n\wfrom LVL %d, up to %d a day, today \r%d",
		g_payMinLvl, g_payDaily, g_payToday[id]);
	new menu = menu_create(title, "on_menu_pay");
	for (new to = 1; to <= MaxClients; to++)
	{
		if (to == id || !g_loaded[to])
			continue;
		get_user_name(to, name, charsmax(name));
		num_to_str(to, info, charsmax(info));
		menu_additem(menu, name, info);
	}
	if (!menu_items(menu))
	{
		menu_destroy(menu);
		czm_chat(id, "^4[LVL]^1 Сейчас некому переводить. Друзьям вне игры — через панель на ^4%s", "^4[LVL]^1 Nobody to send to right now. Use the panel at ^4%s^1 for friends outside the game", CZM_SITE);
		return;
	}
	menu_display(id, menu);
}

public on_menu_pay(id, menu, key)
{
	if (key == MENU_EXIT)
	{
		menu_destroy(menu);
		return PLUGIN_HANDLED;
	}
	new info[4], dummy;
	menu_item_getinfo(menu, key, dummy, info, charsmax(info), _, _, dummy);
	menu_destroy(menu);
	g_payTarget[id] = str_to_num(info);
	new ru = czm_lang(id) == CZM_RU, title[64];
	formatex(title, charsmax(title), ru ? "\yСколько передать?" : "\yHow many?");
	new amounts = menu_create(title, "on_menu_pay_amount");
	menu_additem(amounts, "10");
	menu_additem(amounts, "50");
	menu_additem(amounts, "100");
	menu_display(id, amounts);
	return PLUGIN_HANDLED;
}

public on_menu_pay_amount(id, menu, key)
{
	menu_destroy(menu);
	new to = g_payTarget[id];
	if (!(0 <= key <= 2) || !(1 <= to <= MaxClients) || !g_loaded[to])
		return PLUGIN_HANDLED;
	new const amounts[] = { 10, 50, 100 };
	new EzJSON:a = ezjson_init_object();
	ezjson_object_set_number(a, "target", g_profile[to]);
	ezjson_object_set_number(a, "amount", amounts[key]);
	act(id, "pay", a);
	return PLUGIN_HANDLED;
}

show_top(id)
{
	new data[2];
	data[0] = id; data[1] = g_session[id];
	api("GET", "/survival/top?kind=lvl&limit=10", J_NONE, "on_top", data, sizeof data);
	return PLUGIN_HANDLED;
}

public on_top(EzHttpRequest:request)
{
	new data[2];
	ezhttp_get_user_data(request, data);
	new id = data[0], code, EzJSON:root = answer(request, code);
	if (is_user_connected(id) && g_session[id] == data[1] && code == 200 && J_OK(root))
	{
		new EzJSON:top = ezjson_object_get_value(root, "top");
		czm_chat(id, "^4[LVL]^1 Топ игроков по уровню:", "^4[LVL]^1 Top players by level:");
		for (new n = 0, count = J_OK(top) ? min(ezjson_array_get_count(top), 10) : 0; n < count; n++)
		{
			new EzJSON:row = ezjson_array_get_value(top, n), nick[32];
			ezjson_object_get_string(row, "nick", nick, charsmax(nick));
			czm_chat(id, "^4%d. ^3%s^1 — LVL ^4%d^1, убийств %d", "^4%d. ^3%s^1 — LVL ^4%d^1, %d kills", n + 1, nick,
				ezjson_object_get_number(row, "lvl"), ezjson_object_get_number(row, "kills"));
			ezjson_free(row);
		}
		if (J_OK(top)) ezjson_free(top);
	}
	if (J_OK(root)) ezjson_free(root);
}


// ---------------------------------------------------------------- natives for czm_lvl_fx and the airdrop

crate_index(const name[])
{
	for (new k = 0; k < g_crateCount; k++)
		if (equal(g_crateId[k], name))
			return k;
	return -1;
}

public bool:native_ready(plugin, params)
{
	new id = get_param(1);
	return 1 <= id <= MaxClients && g_loaded[id];
}

public native_item(plugin, params)
{
	new id = get_param(1), cat[16];
	get_string(2, cat, charsmax(cat));
	new c = cat_index(cat);
	if (!(1 <= id <= MaxClients) || !g_loaded[id] || c < 0 || g_equip[id][c] < 0)
		return set_string(3, "", get_param(4));
	return set_string(3, g_itemId[c][g_equip[id][c]], get_param(4));
}

public native_crate(plugin, params)
{
	new id = get_param(1), name[16];
	get_string(2, name, charsmax(name));
	new k = crate_index(name);
	if (!(1 <= id <= MaxClients) || !g_loaded[id] || k < 0)
		return 0;
	new Float:left = g_crateUntil[id][k] - get_gametime();
	return left > 0.0 ? floatround(left) : 0;
}

public native_charges(plugin, params)
{
	new id = get_param(1);
	return 1 <= id <= MaxClients && g_loaded[id] ? g_charges[id] : 0;
}

public native_use_charge(plugin, params)
{
	new id = get_param(1);
	if (!(1 <= id <= MaxClients) || !g_loaded[id] || g_charges[id] <= 0)
		return 0;
	g_charges[id]--;
	act(id, "crate_use", J_NONE, "on_quiet");
	return 1;
}

public native_reward(plugin, params)
{
	new id = get_param(1), amount = get_param(2);
	if (!(1 <= id <= MaxClients) || !g_loaded[id])
		return 0;
	new EzJSON:a = ezjson_init_object();
	ezjson_object_set_string(a, "kind", "airdrop");
	ezjson_object_set_number(a, "amount", amount);
	act(id, "reward", a);
	return 1;
}
