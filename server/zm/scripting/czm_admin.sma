/*
	Counter Zombie Mobile, Survival server: the staff and the order of the Kontra server
	(A_ADMIN_MENU, A_BAN_MANAGER, AdminMessage).

	* Who is staff comes from the API: the head administrators of CZM (admin) and the CZM
	  moderators. A player proves the profile with the CZM ticket; a guest is never staff.
	* Bans and mutes live in the API (survival_mod.py): they hold on every map and after a restart,
	  and the owner sees them in the bot (/zmbans). This plugin kicks the banned and silences the
	  muted, in chat and in voice.
	* The admin menu (/admin, админ, or menu → Админ-меню): punish, give, round modes, a message to
	  everyone, a yes/no poll, the map, the airdrop, the violators board, players' messages, news.
	  Moderators punish (a week at most), speak to everyone, run polls, change the map and lift what
	  moderators and votes gave; everything else is for the head administrators.
*/
#include <amxmodx>
#include <amxmisc>
#include <cstrike>
#include <engine>
#include <fakemeta>
#include <fun>
#include <hamsandwich>
#include <zombieplague>
#include <czm_survival>
#include <czm_api>
#define CZM_ADMIN_PLUGIN
#include <czm_admin>

#define PLUGIN "CZM Admin"
#define VERSION "1.0"
#define AUTHOR "kurostreet"

#define TASK_UNMUTE 5100
#define TASK_KICK 5200
#define TASK_MAP 5300
#define TASK_POLL 5400
#define POLL_SECONDS 20

enum
{
	SCOPE_PLAYER = 0,
	SCOPE_SELF,
	SCOPE_HUMANS,
	SCOPE_ZOMBIES,
	SCOPE_ALL
}

new g_staff[MAX_PLAYERS + 1], g_session[MAX_PLAYERS + 1], g_priv[MAX_PLAYERS + 1];

// Kontra's privileges: index 0 is none (the same order as czm_admin.inc and the API)
new const PRIV_KEYS[][] = { "", "vip", "premium", "deluxe", "tester" };
new const PRIV_NAMES[][] = { "", "VIP+", "PREMIUM", "DELUXE", "TESTER" };
new bool:g_muted[MAX_PLAYERS + 1], bool:g_frozen[MAX_PLAYERS + 1];
new g_kickText[MAX_PLAYERS + 1][96];

// what a staff member is doing in the menu
new g_doing[MAX_PLAYERS + 1][12];    // the action picked before the player list
new g_target[MAX_PLAYERS + 1];       // userid of the chosen player
new g_scope[MAX_PLAYERS + 1];        // give: SCOPE_*
new g_seconds[MAX_PLAYERS + 1];      // ban or mute: how long

new g_mapNext[32], g_mapLeft;

// the LVL MOD shop, for giving items (from the API catalog)
#define MAX_CATS 8
#define MAX_ITEMS 16
new g_catKey[MAX_CATS][12], g_catName[MAX_CATS][2][40], g_catCount;
new g_itemId[MAX_CATS][MAX_ITEMS][24], g_itemName[MAX_CATS][MAX_ITEMS][2][40], g_itemCount[MAX_CATS];
new g_grantCat[MAX_PLAYERS + 1];
new g_pollText[128], g_pollYes, g_pollNo, g_pollLeft, bool:g_pollRunning;
new g_hud;

new const REASONS[][2][] =
{
	{ "Читы", "Cheating" },
	{ "Оскорбления", "Insults" },
	{ "Спам и флуд", "Spam" },
	{ "Мешает игре", "Ruining the game" },
	{ "Реклама", "Advertising" }
};

// give: weapon_* names and how much spare ammo comes with them
new const GIVE_WEAPONS[][] = { "weapon_ak47", "weapon_m4a1", "weapon_awp", "weapon_m249", "weapon_deagle", "weapon_hegrenade" };
new const GIVE_NAMES[][] = { "AK-47", "M4A1", "AWP", "M249", "Desert Eagle", "HE" };
new const GIVE_CSW[] = { CSW_AK47, CSW_M4A1, CSW_AWP, CSW_M249, CSW_DEAGLE, CSW_HEGRENADE };
new const GIVE_AMMO[] = { 90, 90, 30, 200, 35, 1 };

public plugin_natives()
{
	register_library("czm_admin");
	register_native("czm_staff", "native_staff");
	register_native("czm_muted", "native_muted");
	register_native("czm_sanction", "native_sanction");
	register_native("czm_admin_menu", "native_admin_menu");
	register_native("czm_privilege", "native_privilege");
	register_native("czm_privilege_name", "native_privilege_name");
}

public plugin_init()
{
	register_plugin(PLUGIN, VERSION, AUTHOR);
	register_clcmd("say", "cmd_say");
	register_clcmd("say_team", "cmd_say");
	register_clcmd("admin", "admin_menu");
	register_clcmd("czm_say_all", "cmd_say_all");
	register_clcmd("czm_poll", "cmd_poll");
	register_clcmd("czm_news", "cmd_news");
	RegisterHam(Ham_Spawn, "player", "fw_spawn_post", 1);
	g_hud = CreateHudSyncObj();
}

public plugin_cfg()
{
	if (!czm_api_init())
		log_amx("czm_ticket.key is missing: no staff, bans and mutes are not checked");
	set_task(3.0, "task_catalog");
}

public task_catalog()
{
	czm_api("GET", "/survival/catalog", CZM_JSON_NONE, "on_catalog");
}

public on_catalog(EzHttpRequest:request)
{
	new code, EzJSON:root = czm_api_answer(request, code);
	if (code != 200 || !CZM_JSON_OK(root))
	{
		if (CZM_JSON_OK(root)) ezjson_free(root);
		set_task(60.0, "task_catalog");
		return;
	}
	new EzJSON:cats = ezjson_object_get_value(root, "categories");
	g_catCount = 0;
	for (new c = 0; c < ezjson_array_get_count(cats) && g_catCount < MAX_CATS; c++)
	{
		new EzJSON:cat = ezjson_array_get_value(cats, c), EzJSON:items = ezjson_object_get_value(cat, "items"), k = g_catCount++;
		ezjson_object_get_string(cat, "key", g_catKey[k], charsmax(g_catKey[]));
		ezjson_object_get_string(cat, "ru", g_catName[k][0], charsmax(g_catName[][]));
		ezjson_object_get_string(cat, "en", g_catName[k][1], charsmax(g_catName[][]));
		g_itemCount[k] = 0;
		for (new i = 0; i < ezjson_array_get_count(items) && g_itemCount[k] < MAX_ITEMS; i++)
		{
			new EzJSON:it = ezjson_array_get_value(items, i);
			// the head administrators' own items are never given
			if (!ezjson_object_has_value(it, "admin"))
			{
				new n = g_itemCount[k]++;
				ezjson_object_get_string(it, "id", g_itemId[k][n], charsmax(g_itemId[][]));
				ezjson_object_get_string(it, "ru", g_itemName[k][n][0], charsmax(g_itemName[][][]));
				ezjson_object_get_string(it, "en", g_itemName[k][n][1], charsmax(g_itemName[][][]));
			}
			ezjson_free(it);
		}
		ezjson_free(items);
		ezjson_free(cat);
	}
	ezjson_free(cats);
	ezjson_free(root);
}

// ---------------------------------------------------------------- natives

public native_staff(plugin, params)
{
	new id = get_param(1);
	return (1 <= id <= MaxClients) ? g_staff[id] : CZM_STAFF_NONE;
}

public bool:native_muted(plugin, params)
{
	new id = get_param(1);
	return (1 <= id <= MaxClients) && g_muted[id];
}

public native_sanction(plugin, params)
{
	new kind[8], reason[64];
	get_string(2, kind, charsmax(kind));
	get_string(4, reason, charsmax(reason));
	return sanction(get_param(1), kind, get_param(3), reason, get_param(5));
}

public native_admin_menu(plugin, params)
{
	return admin_menu(get_param(1));
}

public native_privilege(plugin, params)
{
	new id = get_param(1);
	return (1 <= id <= MaxClients) ? g_priv[id] : 0;
}

public native_privilege_name(plugin, params)
{
	new id = get_param(1);
	return set_string(2, (1 <= id <= MaxClients) ? PRIV_NAMES[g_priv[id]] : "", get_param(3));
}

// What the staff did goes to the owner (bot /zmlog), as LogsServer of Kontra kept it
staff_log(id, const action[], target = 0, const detail[] = "")
{
	if (!czm_api_ready())
		return;
	new EzJSON:body = ezjson_init_object(), name[32];
	get_user_name(id, name, charsmax(name));
	ezjson_object_set_number(body, "by_player", czm_profile(id));
	ezjson_object_set_string(body, "by_name", name);
	ezjson_object_set_string(body, "action", action);
	if (target && is_user_connected(target))
	{
		get_user_name(target, name, charsmax(name));
		ezjson_object_set_number(body, "target_player", czm_profile(target));
		ezjson_object_set_string(body, "target_name", name);
	}
	ezjson_object_set_string(body, "detail", detail);
	czm_api("POST", "/survival/server/staff_log", body, "on_staff_log");
	ezjson_free(body);
}

public on_staff_log(EzHttpRequest:request)
{
	new code, EzJSON:root = czm_api_answer(request, code);
	if (CZM_JSON_OK(root))
		ezjson_free(root);
}

// ---------------------------------------------------------------- who comes in

priv_index(const kind[])
{
	for (new k = 1; k < sizeof PRIV_KEYS; k++)
		if (equal(kind, PRIV_KEYS[k]))
			return k;
	return 0;
}

public czm_player_ready(id, profile)
{
	g_session[id]++;
	g_staff[id] = CZM_STAFF_NONE;
	g_priv[id] = 0;
	set_mute(id, false);
	if (is_user_bot(id) || is_user_hltv(id) || !czm_api_ready())
		return;
	new EzJSON:body = ezjson_init_object(), ip[40], name[32];
	get_user_ip(id, ip, charsmax(ip), 1);
	get_user_name(id, name, charsmax(name));
	ezjson_object_set_number(body, "player", profile);
	ezjson_object_set_string(body, "ip", ip);
	ezjson_object_set_string(body, "name", name);
	new data[2];
	data[0] = id; data[1] = g_session[id];
	czm_api("POST", "/survival/server/check", body, "on_check", data, sizeof data);
	ezjson_free(body);
}

public on_check(EzHttpRequest:request)
{
	new data[2];
	ezhttp_get_user_data(request, data);
	new id = data[0], code, EzJSON:root = czm_api_answer(request, code);
	if (!is_user_connected(id) || g_session[id] != data[1] || code != 200 || !CZM_JSON_OK(root))
	{
		if (CZM_JSON_OK(root)) ezjson_free(root);
		return;
	}
	new role[16];
	ezjson_object_get_string(root, "role", role, charsmax(role));
	g_staff[id] = equal(role, "admin") ? CZM_STAFF_ADMIN : (equal(role, "moderator") ? CZM_STAFF_MODERATOR : CZM_STAFF_NONE);
	g_priv[id] = 0;
	if (ezjson_object_has_value(root, "privilege", EzJSONObject))
	{
		new kind[16];
		ezjson_object_get_string(root, "privilege.kind", kind, charsmax(kind), true);
		g_priv[id] = priv_index(kind);
	}
	if (ezjson_object_has_value(root, "ban", EzJSONObject))
	{
		new reason[64];
		ezjson_object_get_string(root, "ban.reason", reason, charsmax(reason), true);
		kick_banned(id, ezjson_object_get_number(root, "ban.left", true), reason);
	}
	else if (ezjson_object_has_value(root, "mute", EzJSONObject))
	{
		new left = ezjson_object_get_number(root, "mute.left", true), text[24];
		set_mute(id, true, left);
		czm_api_left(left, text, charsmax(text), czm_lang(id));
		czm_chat(id, "^4[CZM]^1 У тебя мут чата и голоса ещё ^4%s^1.", "^4[CZM]^1 You are muted (chat and voice) for ^4%s^1.", text);
	}
	if (g_staff[id] != CZM_STAFF_NONE)
		czm_chat(id, "^4[CZM]^1 Админ-меню: ^4/admin^1 или menu.", "^4[CZM]^1 Admin menu: ^4/admin^1 or menu.");
	ezjson_free(root);
}

public client_disconnected(id)
{
	g_session[id]++;
	g_staff[id] = CZM_STAFF_NONE;
	g_priv[id] = 0;
	g_muted[id] = false;
	g_frozen[id] = false;
	remove_task(TASK_UNMUTE + id);
	remove_task(TASK_KICK + id);
}

kick_banned(id, left, const reason[])
{
	new text[24], lang = czm_lang(id);
	czm_api_left(left, text, charsmax(text), lang);
	if (lang == CZM_EN)
		formatex(g_kickText[id], charsmax(g_kickText[]), "Banned (%s)%s%s. Appeal: %s", text, reason[0] ? ": " : "", reason, CZM_SITE);
	else
		formatex(g_kickText[id], charsmax(g_kickText[]), "Бан (%s)%s%s. Обжаловать: %s", text, reason[0] ? ": " : "", reason, CZM_SITE);
	// a moment later, so the player sees why in the console
	client_print(id, print_console, "%s", g_kickText[id]);
	set_task(0.5, "task_kick", TASK_KICK + id);
}

public task_kick(taskid)
{
	new id = taskid - TASK_KICK;
	if (is_user_connected(id))
		server_cmd("kick #%d ^"%s^"", get_user_userid(id), g_kickText[id]);
}

set_mute(id, bool:on, left = 0)
{
	g_muted[id] = on;
	remove_task(TASK_UNMUTE + id);
	if (!is_user_connected(id))
		return;
	set_speak(id, on ? SPEAK_MUTED : SPEAK_NORMAL);
	if (on && left > 0)
		set_task(float(left) + 1.0, "task_unmute", TASK_UNMUTE + id);
}

public task_unmute(taskid)
{
	new id = taskid - TASK_UNMUTE;
	set_mute(id, false);
	if (is_user_connected(id))
		czm_chat(id, "^4[CZM]^1 Мут закончился, можно писать и говорить.", "^4[CZM]^1 Your mute is over: you can chat and talk again.");
}

// ---------------------------------------------------------------- the muted are silent

public cmd_say(id)
{
	new text[192];
	read_args(text, charsmax(text));
	remove_quotes(text);
	trim(text);
	if (!text[0])
		return PLUGIN_CONTINUE;
	if (text[0] == '/' || text[0] == '!')
	{
		new cmd[16];
		parse(text[1], cmd, charsmax(cmd));
		if (equali(cmd, "admin") || equali(cmd, "админ"))
			return admin_menu(id);
		return PLUGIN_CONTINUE;
	}
	if (equali(text, "admin") || equali(text, "админ"))
		return admin_menu(id);
	if (!g_muted[id] || equali(text, "menu") || equali(text, "меню") || equali(text, "lvl") || equali(text, "лвл"))
		return PLUGIN_CONTINUE;
	czm_chat(id, "^4[CZM]^1 У тебя мут: чат закрыт. Доска нарушителей: menu → Голосования.",
		"^4[CZM]^1 You are muted: chat is closed. The board: menu → Voting.");
	return PLUGIN_HANDLED;
}

// ---------------------------------------------------------------- bans and mutes

sanction(target, const kind[], seconds, const reason[], by)
{
	if (!is_user_connected(target) || is_user_bot(target) || !czm_api_ready())
		return 0;
	new EzJSON:body = ezjson_init_object(), name[32], ip[40];
	get_user_name(target, name, charsmax(name));
	get_user_ip(target, ip, charsmax(ip), 1);
	ezjson_object_set_string(body, "action", "add");
	ezjson_object_set_string(body, "kind", kind);
	ezjson_object_set_number(body, "player", czm_profile(target));
	ezjson_object_set_string(body, "ip", ip);
	ezjson_object_set_string(body, "name", name);
	ezjson_object_set_number(body, "seconds", seconds);
	ezjson_object_set_string(body, "reason", reason);
	if (by)
	{
		new byName[32];
		get_user_name(by, byName, charsmax(byName));
		ezjson_object_set_number(body, "by_player", czm_profile(by));
		ezjson_object_set_string(body, "by_name", byName);
	}
	new data[6];
	data[0] = target; data[1] = get_user_userid(target);
	data[2] = by; data[3] = by ? get_user_userid(by) : 0;
	data[4] = equal(kind, "ban");
	data[5] = seconds;
	copy(g_kickText[target], charsmax(g_kickText[]), reason);
	czm_api("POST", "/survival/server/sanction", body, "on_sanction", data, sizeof data);
	ezjson_free(body);
	return 1;
}

public on_sanction(EzHttpRequest:request)
{
	new data[6];
	ezhttp_get_user_data(request, data);
	new target = data[0], by = data[2], bool:ban = bool:data[4], code, EzJSON:root = czm_api_answer(request, code);
	new bool:here = is_user_connected(target) && get_user_userid(target) == data[1];
	new bool:byHere = by && is_user_connected(by) && get_user_userid(by) == data[3];
	if (code == 200 && CZM_JSON_OK(root))
	{
		new left = ezjson_object_get_number(root, "left"), name[32], text[24], reason[64];
		if (here)
		{
			get_user_name(target, name, charsmax(name));
			copy(reason, charsmax(reason), g_kickText[target]);
			for (new i = 1; i <= MaxClients; i++)
			{
				if (!is_user_connected(i) || is_user_bot(i))
					continue;
				czm_api_left(left, text, charsmax(text), czm_lang(i));
				if (!by)
					copy(reason, charsmax(reason), czm_lang(i) == CZM_EN ? "players' vote" : "голосование игроков");
				if (ban)
					czm_chat(i, "^4[CZM]^3 %s^1 забанен на ^4%s^1%s%s", "^4[CZM]^3 %s^1 is banned for ^4%s^1%s%s", name, text, reason[0] ? ": " : ".", reason);
				else
					czm_chat(i, "^4[CZM]^3 %s^1 получил мут на ^4%s^1%s%s", "^4[CZM]^3 %s^1 is muted for ^4%s^1%s%s", name, text, reason[0] ? ": " : ".", reason);
			}
			if (!by)
				copy(reason, charsmax(reason), czm_lang(target) == CZM_EN ? "players' vote" : "голосование игроков");
			if (ban)
				kick_banned(target, left, reason);
			else
				set_mute(target, true, left);
		}
	}
	else if (ban && here && code == 0)
	{
		// the API is away: the player still leaves, but the ban is not kept
		server_cmd("kick #%d", data[1]);
		if (byHere)
			czm_chat(by, "^4[CZM]^1 API не отвечает: игрок кикнут, но бан не записан.", "^4[CZM]^1 The API is away: kicked, but the ban was not kept.");
	}
	else if (byHere)
	{
		new error[24];
		if (CZM_JSON_OK(root))
			ezjson_object_get_string(root, "error", error, charsmax(error));
		if (equal(error, "immune"))
			czm_chat(by, "^4[CZM]^1 Этого игрока может наказать только главный админ.", "^4[CZM]^1 Only a head administrator may punish this player.");
		else if (equal(error, "too_long"))
			czm_chat(by, "^4[CZM]^1 Модератор даёт бан или мут до 7 дней.", "^4[CZM]^1 A moderator gives up to 7 days.");
		else
			czm_chat(by, "^4[CZM]^1 Не получилось (%s).", "^4[CZM]^1 It did not work (%s).", error[0] ? error : "API");
	}
	if (CZM_JSON_OK(root))
		ezjson_free(root);
}

lift(id, sanctionId)
{
	new EzJSON:body = ezjson_init_object();
	ezjson_object_set_string(body, "action", "lift");
	ezjson_object_set_number(body, "id", sanctionId);
	ezjson_object_set_number(body, "by_player", czm_profile(id));
	new data[2];
	data[0] = id; data[1] = get_user_userid(id);
	czm_api("POST", "/survival/server/sanction", body, "on_lift", data, sizeof data);
	new detail[16];
	formatex(detail, charsmax(detail), "#%d", sanctionId);
	staff_log(id, "lift", 0, detail);
	ezjson_free(body);
}

public on_lift(EzHttpRequest:request)
{
	new data[2];
	ezhttp_get_user_data(request, data);
	new id = data[0], code, EzJSON:root = czm_api_answer(request, code);
	new bool:here = is_user_connected(id) && get_user_userid(id) == data[1];
	if (code == 200 && CZM_JSON_OK(root))
	{
		new player = ezjson_object_get_number(root, "player"), kind[8], name[32];
		ezjson_object_get_string(root, "kind", kind, charsmax(kind));
		ezjson_object_get_string(root, "name", name, charsmax(name));
		// a muted player who is here speaks again at once
		for (new i = 1; i <= MaxClients; i++)
			if (is_user_connected(i) && g_muted[i] && equal(kind, "mute") && ((player && czm_profile(i) == player) || (!player && is_named(i, name))))
				task_unmute(TASK_UNMUTE + i);
		if (here)
			czm_chat(id, "^4[CZM]^1 Снято: ^4%s^1.", "^4[CZM]^1 Lifted: ^4%s^1.", name);
	}
	else if (here)
		czm_chat(id, "^4[CZM]^1 Снять не получилось: это дал главный админ.", "^4[CZM]^1 Could not lift it: a head administrator gave it.");
	if (CZM_JSON_OK(root))
		ezjson_free(root);
}

bool:is_named(id, const name[])
{
	new have[32];
	get_user_name(id, have, charsmax(have));
	return bool:equal(have, name);
}

// ---------------------------------------------------------------- the admin menu

bool:staff(id, need = CZM_STAFF_MODERATOR)
{
	if (g_staff[id] >= need)
		return true;
	if (g_staff[id] == CZM_STAFF_NONE)
		czm_chat(id, "^4[CZM]^1 Это меню — для администрации сервера.", "^4[CZM]^1 This menu is for the server staff.");
	else
		czm_chat(id, "^4[CZM]^1 Это может только главный админ.", "^4[CZM]^1 Only a head administrator can do this.");
	return false;
}

item_add(menu, id, const ru[], const en[], const info[])
{
	menu_additem(menu, czm_lang(id) == CZM_EN ? en : ru, info);
}

texts(menu, id)
{
	new bool:en = czm_lang(id) == CZM_EN;
	menu_setprop(menu, MPROP_BACKNAME, en ? "Back" : "Назад");
	menu_setprop(menu, MPROP_NEXTNAME, en ? "More" : "Далее");
	menu_setprop(menu, MPROP_EXITNAME, en ? "Exit" : "Выход");
}

public admin_menu(id)
{
	if (!staff(id))
		return PLUGIN_HANDLED;
	new title[96], bool:en = czm_lang(id) == CZM_EN, bool:head = g_staff[id] == CZM_STAFF_ADMIN;
	formatex(title, charsmax(title), "\y%s^n\d%s", en ? "ADMIN MENU" : "АДМИН МЕНЮ",
		head ? (en ? "head administrator" : "главный администратор") : (en ? "moderator" : "модератор"));
	new menu = menu_create(title, "on_admin_menu");
	item_add(menu, id, "Наказать игрока", "Punish a player", "punish");
	if (head)
		item_add(menu, id, "Выдать игроку", "Give a player", "give");
	if (head)
		item_add(menu, id, "Режим раунда", "Round mode", "mode");
	item_add(menu, id, "Сообщение всем", "Message to everyone", "say");
	item_add(menu, id, "Опрос ДА / НЕТ", "Yes / no poll", "poll");
	item_add(menu, id, "Сменить карту", "Change the map", "map");
	if (head)
		item_add(menu, id, "Сбросить аирдроп", "Drop an airdrop", "airdrop");
	item_add(menu, id, "Нарушители: снять бан или мут", "Violators: lift a ban or mute", "board");
	item_add(menu, id, "Сообщения игроков", "Players' messages", "inbox");
	if (head)
		item_add(menu, id, "Новость сервера", "Server news", "news");
	if (head)
		item_add(menu, id, "Привилегия игроку (VIP+, PREMIUM...)", "Privilege (VIP+, PREMIUM...)", "priv");
	texts(menu, id);
	menu_display(id, menu);
	return PLUGIN_HANDLED;
}

public on_admin_menu(id, menu, item)
{
	if (item < 0)
	{
		menu_destroy(menu);
		return PLUGIN_HANDLED;
	}
	new info[12], access, callback;
	menu_item_getinfo(menu, item, access, info, charsmax(info), _, _, callback);
	menu_destroy(menu);
	if (!staff(id))
		return PLUGIN_HANDLED;
	if (equal(info, "punish"))
	{
		copy(g_doing[id], charsmax(g_doing[]), "punish");
		pick_player(id, false);
	}
	else if (equal(info, "give") && staff(id, CZM_STAFF_ADMIN))
		give_scope_menu(id);
	else if (equal(info, "mode") && staff(id, CZM_STAFF_ADMIN))
		mode_menu(id);
	else if (equal(info, "say"))
	{
		czm_chat(id, "^4[CZM]^1 Напиши сообщение для всех и отправь.", "^4[CZM]^1 Type the message for everyone and send it.");
		client_cmd(id, "messagemode czm_say_all");
	}
	else if (equal(info, "poll"))
	{
		if (g_pollRunning)
			czm_chat(id, "^4[CZM]^1 Опрос уже идёт.", "^4[CZM]^1 A poll is already on.");
		else
		{
			czm_chat(id, "^4[CZM]^1 Напиши вопрос опроса (ответ ДА или НЕТ) и отправь.", "^4[CZM]^1 Type the poll question (yes or no) and send it.");
			client_cmd(id, "messagemode czm_poll");
		}
	}
	else if (equal(info, "map"))
		map_menu(id);
	else if (equal(info, "airdrop") && staff(id, CZM_STAFF_ADMIN))
	{
		server_cmd("czm_airdrop");
		staff_log(id, "airdrop");
		czm_chat(id, "^4[CZM]^1 Аирдроп сброшен.", "^4[CZM]^1 The airdrop is down.");
	}
	else if (equal(info, "board"))
	{
		new data[2];
		data[0] = id; data[1] = get_user_userid(id);
		czm_api("GET", "/survival/board?limit=40", CZM_JSON_NONE, "on_board", data, sizeof data);
	}
	else if (equal(info, "inbox"))
	{
		new data[2];
		data[0] = id; data[1] = get_user_userid(id);
		czm_api("GET", "/survival/server/messages?limit=8", CZM_JSON_NONE, "on_inbox", data, sizeof data);
	}
	else if (equal(info, "priv") && staff(id, CZM_STAFF_ADMIN))
	{
		copy(g_doing[id], charsmax(g_doing[]), "priv");
		pick_player(id, true);
	}
	else if (equal(info, "news") && staff(id, CZM_STAFF_ADMIN))
	{
		czm_chat(id, "^4[CZM]^1 Напиши новость (русский | english) и отправь.", "^4[CZM]^1 Type the news (русский | english) and send it.");
		client_cmd(id, "messagemode czm_news");
	}
	return PLUGIN_HANDLED;
}

// ---------------------------------------------------------------- choosing a player

pick_player(id, bool:withSelf)
{
	new title[64], bool:en = czm_lang(id) == CZM_EN;
	formatex(title, charsmax(title), "\y%s", en ? "Choose a player" : "Выбери игрока");
	new menu = menu_create(title, "on_pick_player"), players[MAX_PLAYERS], count, name[48], info[8];
	get_players(players, count, "ch");
	for (new k = 0; k < count; k++)
	{
		new p = players[k];
		if (p == id && !withSelf)
			continue;
		get_user_name(p, name, charsmax(name));
		if (g_staff[p] == CZM_STAFF_ADMIN)
			add(name, charsmax(name), en ? " \r[admin]" : " \r[админ]");
		else if (g_staff[p] == CZM_STAFF_MODERATOR)
			add(name, charsmax(name), en ? " \r[mod]" : " \r[модер]");
		else if (g_muted[p])
			add(name, charsmax(name), en ? " \d[muted]" : " \d[мут]");
		num_to_str(get_user_userid(p), info, charsmax(info));
		menu_additem(menu, name, info);
	}
	if (!menu_items(menu))
	{
		menu_destroy(menu);
		czm_chat(id, "^4[CZM]^1 На сервере нет других игроков.", "^4[CZM]^1 Nobody else is on the server.");
		return;
	}
	texts(menu, id);
	menu_display(id, menu);
}

public on_pick_player(id, menu, item)
{
	if (item < 0)
	{
		menu_destroy(menu);
		return PLUGIN_HANDLED;
	}
	new info[8], access, callback;
	menu_item_getinfo(menu, item, access, info, charsmax(info), _, _, callback);
	menu_destroy(menu);
	g_target[id] = str_to_num(info);
	new target = find_player_ex(FindPlayer_MatchUserId, g_target[id]);
	if (!target)
	{
		czm_chat(id, "^4[CZM]^1 Игрок уже вышел.", "^4[CZM]^1 The player has left.");
		return PLUGIN_HANDLED;
	}
	if (equal(g_doing[id], "punish"))
		punish_menu(id, target);
	else if (equal(g_doing[id], "give"))
		give_menu(id);
	else if (equal(g_doing[id], "priv"))
		priv_menu(id, target);
	else if (equal(g_doing[id], "nemesis") || equal(g_doing[id], "survivor"))
		start_mode(id, g_doing[id], target);
	return PLUGIN_HANDLED;
}

// ---------------------------------------------------------------- punishments

punish_menu(id, target)
{
	new title[96], name[32], bool:en = czm_lang(id) == CZM_EN, bool:head = g_staff[id] == CZM_STAFF_ADMIN;
	get_user_name(target, name, charsmax(name));
	formatex(title, charsmax(title), "\y%s^n\w%s", en ? "Punish" : "Наказать", name);
	new menu = menu_create(title, "on_punish_menu");
	item_add(menu, id, "Кикнуть", "Kick", "kick");
	item_add(menu, id, "Бан на 30 минут", "Ban for 30 minutes", "b1800");
	item_add(menu, id, "Бан на 1 день", "Ban for 1 day", "b86400");
	item_add(menu, id, "Бан на 7 дней", "Ban for 7 days", "b604800");
	if (head)
		item_add(menu, id, "Бан навсегда", "Ban forever", "b0");
	item_add(menu, id, "Мут на 1 час", "Mute for 1 hour", "m3600");
	item_add(menu, id, "Мут на 1 день", "Mute for 1 day", "m86400");
	item_add(menu, id, "Мут на 7 дней", "Mute for 7 days", "m604800");
	item_add(menu, id, "Убить", "Kill", "slay");
	item_add(menu, id, g_frozen[target] ? "Разморозить" : "Заморозить", g_frozen[target] ? "Unfreeze" : "Freeze", "freeze");
	item_add(menu, id, "Шлёпнуть", "Slap", "slap");
	texts(menu, id);
	menu_display(id, menu);
}

public on_punish_menu(id, menu, item)
{
	if (item < 0)
	{
		menu_destroy(menu);
		return PLUGIN_HANDLED;
	}
	new info[12], access, callback;
	menu_item_getinfo(menu, item, access, info, charsmax(info), _, _, callback);
	menu_destroy(menu);
	new target = find_player_ex(FindPlayer_MatchUserId, g_target[id]);
	if (!staff(id) || !target)
		return PLUGIN_HANDLED;
	if ((g_staff[target] != CZM_STAFF_NONE && g_staff[id] != CZM_STAFF_ADMIN) || g_staff[target] == CZM_STAFF_ADMIN)
	{
		czm_chat(id, "^4[CZM]^1 Этого игрока может наказать только главный админ.", "^4[CZM]^1 Only a head administrator may punish this player.");
		return PLUGIN_HANDLED;
	}
	new name[32], admin[32];
	get_user_name(target, name, charsmax(name));
	get_user_name(id, admin, charsmax(admin));
	if (info[0] == 'b' || info[0] == 'm')
	{
		copy(g_doing[id], charsmax(g_doing[]), info[0] == 'b' ? "ban" : "mute");
		g_seconds[id] = str_to_num(info[1]);
		reason_menu(id);
	}
	else if (equal(info, "kick"))
	{
		staff_log(id, "kick", target);
		server_cmd("kick #%d ^"%s^"", g_target[id], czm_lang(target) == CZM_EN ? "Kicked by the staff" : "Кик от администрации");
		czm_chat(0, "^4[CZM]^3 %s^1 кикнут (%s).", "^4[CZM]^3 %s^1 was kicked (%s).", name, admin);
	}
	else if (equal(info, "slay"))
	{
		if (is_user_alive(target))
			user_kill(target, 1);
		staff_log(id, "slay", target);
		czm_chat(0, "^4[CZM]^1 Админ ^4%s^1 убил ^3%s^1.", "^4[CZM]^1 Admin ^4%s^1 killed ^3%s^1.", admin, name);
	}
	else if (equal(info, "freeze"))
	{
		g_frozen[target] = !g_frozen[target];
		freeze(target, g_frozen[target]);
		staff_log(id, g_frozen[target] ? "freeze" : "unfreeze", target);
		if (g_frozen[target])
			czm_chat(0, "^4[CZM]^1 Админ ^4%s^1 заморозил ^3%s^1.", "^4[CZM]^1 Admin ^4%s^1 froze ^3%s^1.", admin, name);
		else
			czm_chat(0, "^4[CZM]^1 Админ ^4%s^1 разморозил ^3%s^1.", "^4[CZM]^1 Admin ^4%s^1 unfroze ^3%s^1.", admin, name);
	}
	else if (equal(info, "slap"))
	{
		if (is_user_alive(target))
			user_slap(target, 0);
		punish_menu(id, target);
	}
	return PLUGIN_HANDLED;
}

freeze(id, bool:on)
{
	if (!is_user_alive(id))
		return;
	new flags = pev(id, pev_flags);
	set_pev(id, pev_flags, on ? (flags | FL_FROZEN) : (flags & ~FL_FROZEN));
	if (on)
		set_user_rendering(id, kRenderFxGlowShell, 0, 120, 255, kRenderNormal, 20);
	else
		set_user_rendering(id);
}

public fw_spawn_post(id)
{
	// a new life starts unfrozen
	if (is_user_alive(id) && g_frozen[id])
	{
		g_frozen[id] = false;
		freeze(id, false);
	}
}

reason_menu(id)
{
	new title[64], bool:en = czm_lang(id) == CZM_EN;
	formatex(title, charsmax(title), "\y%s", en ? "Reason" : "Причина");
	new menu = menu_create(title, "on_reason_menu"), info[4];
	for (new r = 0; r < sizeof REASONS; r++)
	{
		num_to_str(r, info, charsmax(info));
		menu_additem(menu, REASONS[r][en ? 1 : 0], info);
	}
	item_add(menu, id, "Без причины", "No reason", "-1");
	texts(menu, id);
	menu_display(id, menu);
}

public on_reason_menu(id, menu, item)
{
	if (item < 0)
	{
		menu_destroy(menu);
		return PLUGIN_HANDLED;
	}
	new info[4], access, callback;
	menu_item_getinfo(menu, item, access, info, charsmax(info), _, _, callback);
	menu_destroy(menu);
	new target = find_player_ex(FindPlayer_MatchUserId, g_target[id]), r = str_to_num(info);
	if (!staff(id) || !target)
		return PLUGIN_HANDLED;
	// the reason is kept in Russian: the board, the bot and most players read Russian
	sanction(target, g_doing[id], g_seconds[id], r >= 0 ? REASONS[r][0] : "", id);
	new detail[80];
	formatex(detail, charsmax(detail), "%d s %s", g_seconds[id], r >= 0 ? REASONS[r][0] : "");
	staff_log(id, g_doing[id], target, detail);
	return PLUGIN_HANDLED;
}

// ---------------------------------------------------------------- giving

give_scope_menu(id)
{
	new title[64], bool:en = czm_lang(id) == CZM_EN;
	formatex(title, charsmax(title), "\y%s", en ? "Give to whom" : "Кому выдать");
	new menu = menu_create(title, "on_give_scope");
	item_add(menu, id, "Игроку", "A player", "0");
	item_add(menu, id, "Себе", "Myself", "1");
	item_add(menu, id, "Всем людям", "All humans", "2");
	item_add(menu, id, "Всем зомби", "All zombies", "3");
	item_add(menu, id, "Всем", "Everyone", "4");
	texts(menu, id);
	menu_display(id, menu);
}

public on_give_scope(id, menu, item)
{
	if (item < 0)
	{
		menu_destroy(menu);
		return PLUGIN_HANDLED;
	}
	new info[4], access, callback;
	menu_item_getinfo(menu, item, access, info, charsmax(info), _, _, callback);
	menu_destroy(menu);
	g_scope[id] = str_to_num(info);
	if (g_scope[id] == SCOPE_PLAYER)
	{
		copy(g_doing[id], charsmax(g_doing[]), "give");
		pick_player(id, true);
	}
	else
		give_menu(id);
	return PLUGIN_HANDLED;
}

give_menu(id)
{
	new title[64], bool:en = czm_lang(id) == CZM_EN, info[8];
	formatex(title, charsmax(title), "\y%s", en ? "Give" : "Выдать");
	new menu = menu_create(title, "on_give_menu");
	item_add(menu, id, "+100 здоровья", "+100 health", "hp");
	item_add(menu, id, "Броня 100", "Armor 100", "armor");
	item_add(menu, id, "Возродить", "Revive", "revive");
	for (new w = 0; w < sizeof GIVE_WEAPONS; w++)
	{
		formatex(info, charsmax(info), "w%d", w);
		menu_additem(menu, GIVE_NAMES[w], info);
	}
	item_add(menu, id, "+50 аммо-паков", "+50 ammo packs", "packs");
	if (g_scope[id] <= SCOPE_SELF && g_catCount)
		item_add(menu, id, "\yПредмет LVL MOD (скин, префикс, нож)", "\yLVL MOD item (skin, prefix, knife)", "lvl");
	item_add(menu, id, "Телепорт ко мне", "Teleport to me", "tp");
	item_add(menu, id, "Сделать зомби", "Make a zombie", "zombie");
	item_add(menu, id, "Сделать человеком", "Make a human", "human");
	texts(menu, id);
	menu_display(id, menu);
}

public on_give_menu(id, menu, item)
{
	if (item < 0)
	{
		menu_destroy(menu);
		return PLUGIN_HANDLED;
	}
	new info[8], access, callback;
	menu_item_getinfo(menu, item, access, info, charsmax(info), _, _, callback);
	menu_destroy(menu);
	if (!staff(id, CZM_STAFF_ADMIN))
		return PLUGIN_HANDLED;
	if (equal(info, "lvl"))
	{
		grant_cat_menu(id);
		return PLUGIN_HANDLED;
	}
	new targets[MAX_PLAYERS], count = scope_players(id, targets), done = 0;
	for (new k = 0; k < count; k++)
		done += give(id, targets[k], info);
	new const SCOPES[][] = { "", "self", "all humans", "all zombies", "everyone" };
	new detail[48];
	formatex(detail, charsmax(detail), "%s %s x%d", info, SCOPES[g_scope[id]], done);
	staff_log(id, "give", g_scope[id] == SCOPE_PLAYER ? find_player_ex(FindPlayer_MatchUserId, g_target[id]) : 0, detail);
	czm_chat(id, "^4[CZM]^1 Выдано: ^4%d^1.", "^4[CZM]^1 Given: ^4%d^1.", done);
	give_menu(id);
	return PLUGIN_HANDLED;
}

scope_players(id, targets[MAX_PLAYERS])
{
	new count = 0;
	switch (g_scope[id])
	{
		case SCOPE_PLAYER:
		{
			new target = find_player_ex(FindPlayer_MatchUserId, g_target[id]);
			if (target)
				targets[count++] = target;
		}
		case SCOPE_SELF: targets[count++] = id;
		default:
		{
			for (new p = 1; p <= MaxClients; p++)
			{
				if (!is_user_connected(p) || is_user_hltv(p))
					continue;
				new bool:zombie = bool:zp_get_user_zombie(p);
				if (g_scope[id] == SCOPE_ALL || (g_scope[id] == SCOPE_ZOMBIES) == zombie)
					targets[count++] = p;
			}
		}
	}
	return count;
}

give(id, target, const what[])
{
	new bool:alive = bool:is_user_alive(target), bool:zombie = alive && zp_get_user_zombie(target);
	if (equal(what, "revive"))
	{
		if (alive)
			return 0;
		return zp_respawn_user(target, ZP_TEAM_HUMAN) ? 1 : 0;
	}
	if (equal(what, "packs"))
	{
		zp_set_user_ammo_packs(target, zp_get_user_ammo_packs(target) + 50);
		return 1;
	}
	if (!alive)
		return 0;
	if (equal(what, "hp"))
		set_user_health(target, get_user_health(target) + 100);
	else if (equal(what, "armor"))
		set_user_armor(target, 100);
	else if (what[0] == 'w')
	{
		if (zombie)
			return 0;
		new w = str_to_num(what[1]);
		give_item(target, GIVE_WEAPONS[w]);
		if (GIVE_CSW[w] != CSW_HEGRENADE)
			cs_set_user_bpammo(target, GIVE_CSW[w], GIVE_AMMO[w]);
	}
	else if (equal(what, "tp"))
	{
		if (target == id || !is_user_alive(id))
			return 0;
		return teleport_near(target, id) ? 1 : 0;
	}
	else if (equal(what, "zombie"))
		return (!zombie && zp_infect_user(target, 0, 0, 0)) ? 1 : 0;
	else if (equal(what, "human"))
		return (zombie && zp_disinfect_user(target, 0)) ? 1 : 0;
	return 1;
}

// ---------------------------------------------------------------- giving LVL MOD items

grant_target(id)
{
	return g_scope[id] == SCOPE_SELF ? id : find_player_ex(FindPlayer_MatchUserId, g_target[id]);
}

grant_cat_menu(id)
{
	new target = grant_target(id), title[96], name[32], info[4], bool:en = czm_lang(id) == CZM_EN;
	if (!target || !czm_profile(target))
	{
		czm_chat(id, "^4[CZM]^1 Предметы LVL MOD — только игрокам с профилем CZM.", "^4[CZM]^1 LVL MOD items go to players with a CZM profile only.");
		return;
	}
	get_user_name(target, name, charsmax(name));
	formatex(title, charsmax(title), "\y%s^n\w%s", en ? "Give an item" : "Подарить предмет", name);
	new menu = menu_create(title, "on_grant_cat");
	for (new c = 0; c < g_catCount; c++)
		if (g_itemCount[c])
		{
			num_to_str(c, info, charsmax(info));
			menu_additem(menu, g_catName[c][en ? 1 : 0], info);
		}
	texts(menu, id);
	menu_display(id, menu);
}

public on_grant_cat(id, menu, item)
{
	if (item < 0)
	{
		menu_destroy(menu);
		return PLUGIN_HANDLED;
	}
	new info[4], access, callback, title[64], bool:en = czm_lang(id) == CZM_EN;
	menu_item_getinfo(menu, item, access, info, charsmax(info), _, _, callback);
	menu_destroy(menu);
	new c = g_grantCat[id] = str_to_num(info);
	formatex(title, charsmax(title), "\y%s", g_catName[c][en ? 1 : 0]);
	new items = menu_create(title, "on_grant_item");
	for (new i = 0; i < g_itemCount[c]; i++)
	{
		num_to_str(i, info, charsmax(info));
		menu_additem(items, g_itemName[c][i][en ? 1 : 0], info);
	}
	texts(items, id);
	menu_display(id, items);
	return PLUGIN_HANDLED;
}

public on_grant_item(id, menu, item)
{
	if (item < 0)
	{
		menu_destroy(menu);
		return PLUGIN_HANDLED;
	}
	new info[4], access, callback;
	menu_item_getinfo(menu, item, access, info, charsmax(info), _, _, callback);
	menu_destroy(menu);
	new target = grant_target(id), c = g_grantCat[id], i = str_to_num(info);
	if (!staff(id, CZM_STAFF_ADMIN) || !target || !czm_profile(target) || i >= g_itemCount[c])
		return PLUGIN_HANDLED;
	new EzJSON:body = ezjson_init_object(), EzJSON:args = ezjson_init_object(), op[40], data[4];
	formatex(op, charsmax(op), "grant-%d-%d-%d", get_systime(), czm_profile(target), random(1000000));
	ezjson_object_set_number(body, "player", czm_profile(target));
	ezjson_object_set_string(body, "op", op);
	ezjson_object_set_string(body, "action", "grant");
	ezjson_object_set_number(args, "by", czm_profile(id));
	ezjson_object_set_string(args, "cat", g_catKey[c]);
	ezjson_object_set_string(args, "item", g_itemId[c][i]);
	ezjson_object_set_value(body, "args", args);
	ezjson_free(args);
	data[0] = id; data[1] = get_user_userid(id); data[2] = c; data[3] = i;
	czm_api("POST", "/survival/server/action", body, "on_grant", data, sizeof data);
	new detail[40];
	formatex(detail, charsmax(detail), "%s:%s", g_catKey[c], g_itemId[c][i]);
	staff_log(id, "grant", target, detail);
	ezjson_free(body);
	return PLUGIN_HANDLED;
}

public on_grant(EzHttpRequest:request)
{
	new data[4];
	ezhttp_get_user_data(request, data);
	new id = data[0], c = data[2], i = data[3], code, EzJSON:root = czm_api_answer(request, code);
	if (is_user_connected(id) && get_user_userid(id) == data[1])
	{
		new error[24];
		if (CZM_JSON_OK(root) && code != 200)
			ezjson_object_get_string(root, "error", error, charsmax(error));
		if (code == 200)
			czm_chat(id, "^4[CZM]^1 Подарено: ^4%s^1. Наденется в начале следующей жизни.", "^4[CZM]^1 Given: ^4%s^1. It goes on with the next life.", g_itemName[c][i][czm_lang(id) == CZM_EN ? 1 : 0]);
		else if (equal(error, "owned"))
			czm_chat(id, "^4[CZM]^1 Это у игрока уже есть.", "^4[CZM]^1 The player has it already.");
		else
			czm_chat(id, "^4[CZM]^1 Не получилось (%s).", "^4[CZM]^1 It did not work (%s).", error[0] ? error : "API");
	}
	if (CZM_JSON_OK(root))
		ezjson_free(root);
}

// ---------------------------------------------------------------- privileges (Kontra AdminManager)

priv_menu(id, target)
{
	new title[96], name[32], info[4], bool:en = czm_lang(id) == CZM_EN;
	if (!czm_profile(target))
	{
		czm_chat(id, "^4[CZM]^1 Привилегии — только игрокам с профилем CZM.", "^4[CZM]^1 Privileges go to players with a CZM profile only.");
		return;
	}
	get_user_name(target, name, charsmax(name));
	formatex(title, charsmax(title), "\y%s^n\w%s%s%s", en ? "Privilege" : "Привилегия", name, g_priv[target] ? " \d- " : "", PRIV_NAMES[g_priv[target]]);
	new menu = menu_create(title, "on_priv_menu");
	for (new k = 1; k < sizeof PRIV_KEYS; k++)
	{
		num_to_str(k, info, charsmax(info));
		menu_additem(menu, PRIV_NAMES[k], info);
	}
	if (g_priv[target])
		item_add(menu, id, "\rСнять привилегию", "\rTake it away", "0");
	texts(menu, id);
	menu_display(id, menu);
}

public on_priv_menu(id, menu, item)
{
	if (item < 0)
	{
		menu_destroy(menu);
		return PLUGIN_HANDLED;
	}
	new info[4], access, callback, bool:en = czm_lang(id) == CZM_EN;
	menu_item_getinfo(menu, item, access, info, charsmax(info), _, _, callback);
	menu_destroy(menu);
	new kind = str_to_num(info);
	if (!kind)
	{
		set_privilege(id, 0, 0);
		return PLUGIN_HANDLED;
	}
	g_seconds[id] = kind;    // the kind waits here while the term is chosen
	new title[64];
	formatex(title, charsmax(title), "\y%s: \w%s", en ? "For how long" : "На сколько", PRIV_NAMES[kind]);
	new terms = menu_create(title, "on_priv_term");
	item_add(terms, id, "7 дней", "7 days", "604800");
	item_add(terms, id, "30 дней", "30 days", "2592000");
	item_add(terms, id, "90 дней", "90 days", "7776000");
	item_add(terms, id, "Навсегда", "Forever", "0");
	texts(terms, id);
	menu_display(id, terms);
	return PLUGIN_HANDLED;
}

public on_priv_term(id, menu, item)
{
	if (item < 0)
	{
		menu_destroy(menu);
		return PLUGIN_HANDLED;
	}
	new info[12], access, callback;
	menu_item_getinfo(menu, item, access, info, charsmax(info), _, _, callback);
	menu_destroy(menu);
	set_privilege(id, g_seconds[id], str_to_num(info));
	return PLUGIN_HANDLED;
}

set_privilege(id, kind, seconds)
{
	new target = find_player_ex(FindPlayer_MatchUserId, g_target[id]);
	if (!staff(id, CZM_STAFF_ADMIN) || !target || !czm_profile(target))
		return;
	new EzJSON:body = ezjson_init_object(), name[32], data[5];
	get_user_name(id, name, charsmax(name));
	ezjson_object_set_number(body, "player", czm_profile(target));
	ezjson_object_set_string(body, "kind", PRIV_KEYS[kind]);
	ezjson_object_set_number(body, "seconds", seconds);
	ezjson_object_set_number(body, "by_player", czm_profile(id));
	ezjson_object_set_string(body, "by_name", name);
	data[0] = id; data[1] = get_user_userid(id); data[2] = target; data[3] = get_user_userid(target); data[4] = kind;
	czm_api("POST", "/survival/server/privilege", body, "on_privilege", data, sizeof data);
	ezjson_free(body);
	staff_log(id, kind ? "privilege" : "privilege_off", target, PRIV_NAMES[kind]);
}

public on_privilege(EzHttpRequest:request)
{
	new data[5];
	ezhttp_get_user_data(request, data);
	new id = data[0], target = data[2], kind = data[4], code, EzJSON:root = czm_api_answer(request, code);
	new bool:here = is_user_connected(target) && get_user_userid(target) == data[3];
	if (code == 200)
	{
		if (here)
		{
			new name[32];
			g_priv[target] = kind;
			get_user_name(target, name, charsmax(name));
			if (kind)
				czm_chat(0, "^4[CZM]^3 %s^1 получил привилегию ^4%s^1!", "^4[CZM]^3 %s^1 got the ^4%s^1 privilege!", name, PRIV_NAMES[kind]);
			else
				czm_chat(0, "^4[CZM]^1 У ^3%s^1 больше нет привилегии.", "^4[CZM]^3 %s^1 no longer has a privilege.", name);
		}
	}
	else if (is_user_connected(id) && get_user_userid(id) == data[1])
		czm_chat(id, "^4[CZM]^1 Привилегия не сохранилась.", "^4[CZM]^1 The privilege was not saved.");
	if (CZM_JSON_OK(root))
		ezjson_free(root);
}

// Puts a player next to another one, on a spot where nobody is stuck.
bool:teleport_near(who, to)
{
	new Float:base[3], Float:spot[3];
	pev(to, pev_origin, base);
	new const Float:OFFSETS[][3] = { {48.0, 0.0, 0.0}, {-48.0, 0.0, 0.0}, {0.0, 48.0, 0.0}, {0.0, -48.0, 0.0}, {0.0, 0.0, 74.0} };
	new hull = (pev(who, pev_flags) & FL_DUCKING) ? HULL_HEAD : HULL_HUMAN;
	for (new k = 0; k < sizeof OFFSETS; k++)
	{
		spot[0] = base[0] + OFFSETS[k][0];
		spot[1] = base[1] + OFFSETS[k][1];
		spot[2] = base[2] + OFFSETS[k][2];
		engfunc(EngFunc_TraceHull, spot, spot, 0, hull, who, 0);
		if (!get_tr2(0, TR_StartSolid) && !get_tr2(0, TR_AllSolid) && get_tr2(0, TR_InOpen))
		{
			engfunc(EngFunc_SetOrigin, who, spot);
			set_pev(who, pev_velocity, Float:{0.0, 0.0, 0.0});
			return true;
		}
	}
	return false;
}

// ---------------------------------------------------------------- round modes

mode_menu(id)
{
	new title[96], bool:en = czm_lang(id) == CZM_EN;
	formatex(title, charsmax(title), "\y%s^n\d%s", en ? "Round mode" : "Режим раунда",
		en ? "starts before the infection only" : "запускается только до заражения");
	new menu = menu_create(title, "on_mode_menu");
	item_add(menu, id, "Немезида (выбрать игрока)", "Nemesis (choose a player)", "nemesis");
	item_add(menu, id, "Выживший (выбрать игрока)", "Survivor (choose a player)", "survivor");
	item_add(menu, id, "Рой", "Swarm", "swarm");
	item_add(menu, id, "Множественное заражение", "Multiple infection", "multi");
	item_add(menu, id, "Чума", "Plague", "plague");
	texts(menu, id);
	menu_display(id, menu);
}

public on_mode_menu(id, menu, item)
{
	if (item < 0)
	{
		menu_destroy(menu);
		return PLUGIN_HANDLED;
	}
	new info[12], access, callback;
	menu_item_getinfo(menu, item, access, info, charsmax(info), _, _, callback);
	menu_destroy(menu);
	if (!staff(id, CZM_STAFF_ADMIN))
		return PLUGIN_HANDLED;
	if (zp_has_round_started())
	{
		czm_chat(id, "^4[CZM]^1 Раунд уже начался: режим включается до заражения.", "^4[CZM]^1 The round has started: modes start before the infection.");
		return PLUGIN_HANDLED;
	}
	if (equal(info, "nemesis") || equal(info, "survivor"))
	{
		copy(g_doing[id], charsmax(g_doing[]), info);
		pick_player(id, true);
	}
	else
		start_mode(id, info, 0);
	return PLUGIN_HANDLED;
}

start_mode(id, const mode[], target)
{
	new bool:ok;
	if (equal(mode, "nemesis"))
		ok = target && is_user_alive(target) && zp_make_user_nemesis(target);
	else if (equal(mode, "survivor"))
		ok = target && is_user_alive(target) && zp_make_user_survivor(target);
	else
	{
		// the Zombie Plague console commands; the server console has every access
		server_cmd("zp_%s", mode);
		ok = true;
	}
	if (ok)
		staff_log(id, "mode", target, mode);
	if (!ok)
		czm_chat(id, "^4[CZM]^1 Этот режим сейчас не запустить.", "^4[CZM]^1 This mode cannot start now.");
}

// ---------------------------------------------------------------- speaking to everyone

public cmd_say_all(id)
{
	if (!staff(id))
		return PLUGIN_HANDLED;
	new text[160], name[32];
	read_args(text, charsmax(text));
	remove_quotes(text);
	trim(text);
	replace_all(text, charsmax(text), "%", "");
	if (!text[0])
		return PLUGIN_HANDLED;
	get_user_name(id, name, charsmax(name));
	set_hudmessage(255, 210, 0, -1.0, 0.25, 0, 0.0, 8.0, 0.3, 0.6, -1);
	ShowSyncHudMsg(0, g_hud, "%s:^n%s", name, text);
	czm_chat(0, "^4[Админ]^3 %s^1: %s", "^4[Admin]^3 %s^1: %s", name, text);
	staff_log(id, "say", 0, text);
	return PLUGIN_HANDLED;
}

public cmd_news(id)
{
	if (!staff(id, CZM_STAFF_ADMIN))
		return PLUGIN_HANDLED;
	new text[300], ru[200], en[200];
	read_args(text, charsmax(text));
	remove_quotes(text);
	trim(text);
	strtok2(text, ru, charsmax(ru), en, charsmax(en), '|', TRIM_FULL);
	if (strlen(ru) < 3)
		return PLUGIN_HANDLED;
	new EzJSON:body = ezjson_init_object(), data[2];
	ezjson_object_set_number(body, "by_player", czm_profile(id));
	ezjson_object_set_string(body, "ru", ru);
	ezjson_object_set_string(body, "en", en);
	data[0] = id; data[1] = get_user_userid(id);
	czm_api("POST", "/survival/server/news", body, "on_news", data, sizeof data);
	staff_log(id, "news", 0, ru);
	ezjson_free(body);
	return PLUGIN_HANDLED;
}

public on_news(EzHttpRequest:request)
{
	new data[2];
	ezhttp_get_user_data(request, data);
	new id = data[0], code, EzJSON:root = czm_api_answer(request, code);
	if (is_user_connected(id) && get_user_userid(id) == data[1])
	{
		if (code == 200)
			czm_chat(id, "^4[CZM]^1 Новость опубликована: menu → Новости.", "^4[CZM]^1 The news is out: menu → News.");
		else
			czm_chat(id, "^4[CZM]^1 Новость не сохранилась.", "^4[CZM]^1 The news was not saved.");
	}
	if (CZM_JSON_OK(root))
		ezjson_free(root);
}

// ---------------------------------------------------------------- the yes/no poll

public cmd_poll(id)
{
	if (!staff(id) || g_pollRunning)
		return PLUGIN_HANDLED;
	read_args(g_pollText, charsmax(g_pollText));
	remove_quotes(g_pollText);
	trim(g_pollText);
	replace_all(g_pollText, charsmax(g_pollText), "%", "");
	if (!g_pollText[0])
		return PLUGIN_HANDLED;
	g_pollRunning = true;
	g_pollYes = g_pollNo = 0;
	g_pollLeft = POLL_SECONDS;
	new title[192];
	for (new p = 1; p <= MaxClients; p++)
	{
		if (!is_user_connected(p) || is_user_bot(p))
			continue;
		new bool:en = czm_lang(p) == CZM_EN;
		formatex(title, charsmax(title), "\y%s^n\w%s", en ? "POLL" : "ОПРОС", g_pollText);
		new menu = menu_create(title, "on_poll_vote");
		menu_additem(menu, en ? "Yes" : "Да", "1");
		menu_additem(menu, en ? "No" : "Нет", "2");
		menu_setprop(menu, MPROP_EXIT, MEXIT_NEVER);
		menu_display(p, menu, 0, POLL_SECONDS);
	}
	czm_play_all_beep();
	set_task(1.0, "task_poll", TASK_POLL, _, _, "a", POLL_SECONDS);
	staff_log(id, "poll", 0, g_pollText);
	return PLUGIN_HANDLED;
}

czm_play_all_beep()
{
	client_cmd(0, "spk buttons/blip1");
}

public on_poll_vote(id, menu, item)
{
	if (item >= 0 && g_pollRunning)
	{
		new info[4], access, callback;
		menu_item_getinfo(menu, item, access, info, charsmax(info), _, _, callback);
		if (info[0] == '1')
			g_pollYes++;
		else
			g_pollNo++;
	}
	menu_destroy(menu);
	return PLUGIN_HANDLED;
}

public task_poll()
{
	if (--g_pollLeft > 0)
		return;
	g_pollRunning = false;
	new bool:yes = g_pollYes > g_pollNo, bool:tie = g_pollYes == g_pollNo;
	set_hudmessage(yes ? 0 : 255, yes ? 230 : 80, tie ? 255 : 0, -1.0, 0.3, 0, 0.0, 6.0, 0.3, 0.6, -1);
	for (new p = 1; p <= MaxClients; p++)
	{
		if (!is_user_connected(p) || is_user_bot(p))
			continue;
		new bool:en = czm_lang(p) == CZM_EN;
		ShowSyncHudMsg(p, g_hud, "%s^n%s: %d  |  %s: %d", tie ? (en ? "A TIE" : "НИЧЬЯ") : (yes ? (en ? "PLAYERS VOTED YES!" : "ИГРОКИ ЗА ДА!") : (en ? "PLAYERS VOTED NO!" : "ИГРОКИ ЗА НЕТ!")),
			en ? "Yes" : "Да", g_pollYes, en ? "No" : "Нет", g_pollNo);
	}
	czm_chat(0, "^4[Опрос]^1 %s — ^4да %d^1, ^3нет %d", "^4[Poll]^1 %s — ^4yes %d^1, ^3no %d", g_pollText, g_pollYes, g_pollNo);
}

// ---------------------------------------------------------------- the map

map_menu(id)
{
	new title[64], bool:en = czm_lang(id) == CZM_EN, path[64], line[48], current[32];
	formatex(title, charsmax(title), "\y%s", en ? "Change the map to" : "Сменить карту на");
	new menu = menu_create(title, "on_map_menu");
	get_cvar_string("mapcyclefile", path, charsmax(path));
	get_mapname(current, charsmax(current));
	new fh = fopen(path, "rt");
	while (fh && !feof(fh))
	{
		fgets(fh, line, charsmax(line));
		trim(line);
		if (!line[0] || line[0] == ';' || line[0] == '/' || equali(line, current) || !is_map_valid(line))
			continue;
		menu_additem(menu, line, line);
	}
	if (fh)
		fclose(fh);
	texts(menu, id);
	menu_display(id, menu);
}

public on_map_menu(id, menu, item)
{
	if (item < 0)
	{
		menu_destroy(menu);
		return PLUGIN_HANDLED;
	}
	new info[32], access, callback, name[32];
	menu_item_getinfo(menu, item, access, info, charsmax(info), _, _, callback);
	menu_destroy(menu);
	if (!staff(id) || task_exists(TASK_MAP))
		return PLUGIN_HANDLED;
	copy(g_mapNext, charsmax(g_mapNext), info);
	g_mapLeft = 5;
	get_user_name(id, name, charsmax(name));
	czm_chat(0, "^4[CZM]^1 Админ ^4%s^1 меняет карту на ^4%s^1 через 5 секунд.", "^4[CZM]^1 Admin ^4%s^1 changes the map to ^4%s^1 in 5 seconds.", name, g_mapNext);
	set_task(1.0, "task_map", TASK_MAP, _, _, "a", g_mapLeft);
	staff_log(id, "map", 0, g_mapNext);
	return PLUGIN_HANDLED;
}

public task_map()
{
	if (--g_mapLeft > 0)
	{
		set_hudmessage(255, 210, 0, -1.0, 0.3, 0, 0.0, 1.0, 0.0, 0.0, -1);
		ShowSyncHudMsg(0, g_hud, "%s: %d", g_mapNext, g_mapLeft);
		return;
	}
	server_cmd("changelevel %s", g_mapNext);
}

// ---------------------------------------------------------------- the violators board and the inbox

public on_board(EzHttpRequest:request)
{
	new data[2];
	ezhttp_get_user_data(request, data);
	new id = data[0], code, EzJSON:root = czm_api_answer(request, code);
	if (!is_user_connected(id) || get_user_userid(id) != data[1] || code != 200 || !CZM_JSON_OK(root))
	{
		if (CZM_JSON_OK(root)) ezjson_free(root);
		return;
	}
	new bool:en = czm_lang(id) == CZM_EN, title[64];
	formatex(title, charsmax(title), "\y%s", en ? "Violators: choose to lift" : "Нарушители: выбери, чтобы снять");
	new menu = menu_create(title, "on_board_menu"), EzJSON:board = ezjson_object_get_value(root, "board");
	new count = ezjson_array_get_count(board), line[96], name[32], left[24], info[12];
	for (new k = 0; k < count; k++)
	{
		new EzJSON:it = ezjson_array_get_value(board, k), kind[8];
		ezjson_object_get_string(it, "kind", kind, charsmax(kind));
		ezjson_object_get_string(it, "name", name, charsmax(name));
		czm_api_left(ezjson_object_get_number(it, "left"), left, charsmax(left), _:en);
		formatex(line, charsmax(line), "%s %s \d%s%s", equal(kind, "ban") ? (en ? "\r[ban]\w" : "\r[бан]\w") : (en ? "\y[mute]\w" : "\y[мут]\w"),
			name, left, ezjson_object_get_bool(it, "vote") ? (en ? ", vote" : ", голосование") : "");
		num_to_str(ezjson_object_get_number(it, "id"), info, charsmax(info));
		menu_additem(menu, line, info);
		ezjson_free(it);
	}
	ezjson_free(board);
	ezjson_free(root);
	if (!count)
	{
		menu_destroy(menu);
		czm_chat(id, "^4[CZM]^1 Нарушителей нет.", "^4[CZM]^1 Nobody is banned or muted.");
		return;
	}
	texts(menu, id);
	menu_display(id, menu);
}

public on_board_menu(id, menu, item)
{
	if (item < 0)
	{
		menu_destroy(menu);
		return PLUGIN_HANDLED;
	}
	new info[12], access, callback;
	menu_item_getinfo(menu, item, access, info, charsmax(info), _, _, callback);
	menu_destroy(menu);
	if (staff(id))
		lift(id, str_to_num(info));
	return PLUGIN_HANDLED;
}

public on_inbox(EzHttpRequest:request)
{
	new data[2];
	ezhttp_get_user_data(request, data);
	new id = data[0], code, EzJSON:root = czm_api_answer(request, code);
	if (!is_user_connected(id) || get_user_userid(id) != data[1] || code != 200 || !CZM_JSON_OK(root))
	{
		if (CZM_JSON_OK(root)) ezjson_free(root);
		return;
	}
	new EzJSON:list = ezjson_object_get_value(root, "messages"), count = ezjson_array_get_count(list);
	if (!count)
		czm_chat(id, "^4[CZM]^1 Сообщений от игроков нет.", "^4[CZM]^1 No messages from players.");
	// oldest first, so the newest ends up at the bottom of the chat
	for (new k = count - 1; k >= 0; k--)
	{
		new EzJSON:it = ezjson_array_get_value(list, k), name[32], text[192];
		ezjson_object_get_string(it, "name", name, charsmax(name));
		ezjson_object_get_string(it, "text", text, charsmax(text));
		client_print_color(id, print_team_default, "^4>>^3 %s^1: %s", name, text);
		ezjson_free(it);
	}
	ezjson_free(list);
	ezjson_free(root);
}
