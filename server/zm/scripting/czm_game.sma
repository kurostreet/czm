/*
	Counter Zombie Mobile, Survival server: the game menu of the Kontra server (GAME_MENU_v31,
	TeleportRequest_v2_5, save_money_v3 and the map vote of the Kontra rooms).

	menu, меню, /menu open the server menu (czm_menu). This plugin adds the tabs
	  Главное      → the panel on the site, settings, voting, teleport, invitations, news, a message
	                 to the staff (LVL MOD and the admin menu come from czm_lvl and czm_admin)
	  Игроки       → teleport (call a human to you or go to one, they answer yes or no),
	                 invitations (the site, the player panel and Telegram in chat), the violators
	  Голосования  → change the map [x/4], ban [x/5] or mute [x/4] a player, the violators
	  Сервер       → news (bot /zmnews or the admin menu), the player panel, the next map, a message
	                 to the staff (the owner's bot gets it, online staff see it at once)
	  Настройки    → language, music and sounds, the hints on the left

	A vote holds one voice per player (the CZM profile, else the address) and resets with the
	map. A ban by vote lasts 30 minutes, a mute an hour; staff are immune. Two minutes before the
	end of the map everyone chooses the next map (or ten more minutes, once).
	Ammo packs are kept for 30 days by the player's key, as money was on Kontra.
*/
#include <amxmodx>
#include <amxmisc>
#include <fakemeta>
#include <hamsandwich>
#include <nvault>
#include <zombieplague>
#include <czm_survival>
#include <czm_api>
#include <czm_admin>
#include <czm_menu>

#define PLUGIN "CZM Game"
#define VERSION "1.0"
#define AUTHOR "kurostreet"

#define VOTES_MAP 4
#define VOTES_BAN 5
#define VOTES_MUTE 4
#define VOTE_COOLDOWN 180.0
#define VOTE_BAN_SECONDS 1800
#define VOTE_MUTE_SECONDS 3600

#define MAPVOTE_AT 120          // seconds left on the map when the vote starts
#define MAPVOTE_SECONDS 20
#define MAPVOTE_CHOICES 5
#define EXTEND_MINUTES 10.0

#define TP_COOLDOWN 180.0
#define TP_ANSWER 15

#define MAX_NEWS 6
#define TASK_TP 6100
#define TASK_PACKS 6200
#define TASK_MAPVOTE 6300
#define TASK_CHANGE 6400

new g_vault;
new g_hInvite, g_hYes, g_hNo, g_hTeleport, g_hVoteStart, g_hVoteStop, g_hMessage, g_hMapMusic;

// ---------------------------------------------------------------- votes
new Trie:g_mapVoters;                     // player key → 1
new Trie:g_banVoters, Trie:g_muteVoters;  // "<target key>|<voter key>" → 1
new Trie:g_banCount, Trie:g_muteCount;    // target key → voices
new Trie:g_cooldown;                      // "ban|<key>" / "mute|<key>" → gametime it opens again
new Float:g_mapCooldown;
new g_pickKind[MAX_PLAYERS + 1];          // 1 ban, 2 mute, 3 teleport here, 4 teleport there

// ---------------------------------------------------------------- the map vote
new g_maps[64][32], g_mapCount;
new g_choice[MAPVOTE_CHOICES + 1][32], g_choiceVotes[MAPVOTE_CHOICES + 1], g_choiceCount;
new bool:g_mapVoteRunning, bool:g_mapVoteDone, bool:g_extended, bool:g_changeNow;
new g_nextMap[32], g_mapVoteLeft, Float:g_chatTime;

// ---------------------------------------------------------------- teleport
new Float:g_tpReady[MAX_PLAYERS + 1];
new g_tpFrom[MAX_PLAYERS + 1], g_tpMode[MAX_PLAYERS + 1];   // on the target: who asks, 1 = come to me, 2 = may I come
new g_tpLeft[MAX_PLAYERS + 1];

// ---------------------------------------------------------------- news
new g_newsId[MAX_NEWS], g_newsRu[MAX_NEWS][164], g_newsEn[MAX_NEWS][164], g_newsWhen[MAX_NEWS], g_newsCount;
new g_newsSeen[MAX_PLAYERS + 1];

new g_hud;

public plugin_precache()
{
	g_hInvite = czm_sound_precache("sound_duel.mp3");
	g_hYes = czm_sound_precache("yes_duel.mp3");
	g_hNo = czm_sound_precache("no_duel.mp3");
	g_hTeleport = czm_sound_precache("soud_teleport_buff.mp3");
	g_hVoteStart = czm_sound_precache("vote_start.mp3");
	g_hVoteStop = czm_sound_precache("vote_stop.mp3");
	g_hMessage = czm_sound_precache("admin_message.mp3");
	g_hMapMusic = czm_sound_precache("s_change_map.mp3");
}

public plugin_init()
{
	register_plugin(PLUGIN, VERSION, AUTHOR);
	register_clcmd("say", "cmd_say");
	register_clcmd("say_team", "cmd_say");
	register_clcmd("menu", "game_menu");
	register_clcmd("czm_admin_msg", "cmd_admin_msg");
	menu_register();
	register_message(SVC_INTERMISSION, "msg_intermission");
	create_cvar("amx_nextmap", "", FCVAR_SERVER | FCVAR_SPONLY, "The next map, chosen by the players' vote");
	g_mapVoters = TrieCreate();
	g_banVoters = TrieCreate();
	g_muteVoters = TrieCreate();
	g_banCount = TrieCreate();
	g_muteCount = TrieCreate();
	g_cooldown = TrieCreate();
	g_hud = CreateHudSyncObj();
	set_task(1.0, "task_second", _, _, _, "b");
}

public plugin_cfg()
{
	czm_api_init();
	g_vault = nvault_open("czm_game");
	if (g_vault != INVALID_HANDLE)
		nvault_prune(g_vault, 0, get_systime() - 30 * 86400);
	load_maps();
	set_task(2.0, "task_news");
	set_task(300.0, "task_news", _, _, _, "b");
}

public plugin_end()
{
	for (new id = 1; id <= MaxClients; id++)
		if (is_user_connected(id))
			save_packs(id);
	if (g_vault != INVALID_HANDLE)
		nvault_close(g_vault);
	if (g_chatTime > 0.0)
		set_cvar_float("mp_chattime", g_chatTime);
	TrieDestroy(g_mapVoters);
	TrieDestroy(g_banVoters);
	TrieDestroy(g_muteVoters);
	TrieDestroy(g_banCount);
	TrieDestroy(g_muteCount);
	TrieDestroy(g_cooldown);
}

// ---------------------------------------------------------------- helpers

bool:en(id)
{
	return czm_lang(id) == CZM_EN;
}

item(menu, id, const ru[], const en_[], const info[])
{
	menu_additem(menu, czm_lang(id) == CZM_EN ? en_ : ru, info);
}

texts(menu, id)
{
	menu_setprop(menu, MPROP_BACKNAME, en(id) ? "Back" : "Назад");
	menu_setprop(menu, MPROP_NEXTNAME, en(id) ? "More" : "Далее");
	menu_setprop(menu, MPROP_EXITNAME, en(id) ? "Exit" : "Выход");
}

menu_info(menu, item_, info[], len)
{
	new access, callback;
	menu_item_getinfo(menu, item_, access, info, len, _, _, callback);
}

humans_online(skip = 0)
{
	new count;
	for (new i = 1; i <= MaxClients; i++)
		if (i != skip && is_user_connected(i) && !is_user_bot(i) && !is_user_hltv(i))
			count++;
	return count;
}

// How many voices a vote needs: the Kontra number, or less when few people play (60% of them).
need(fixed, skip, least)
{
	return clamp((humans_online(skip) * 6 + 9) / 10, least, fixed);
}

key_of(id, out[], len)
{
	czm_player_key(id, out, len);
	if (!out[0])
		get_user_ip(id, out, len, 1);
}

// ---------------------------------------------------------------- chat commands

public cmd_say(id)
{
	new text[64];
	read_args(text, charsmax(text));
	remove_quotes(text);
	trim(text);
	if (text[0] != '/' && text[0] != '!')
	{
		// plain chat: only the bare words, so "menu please" stays a chat line
		if (equali(text, "menu") || equali(text, "меню"))
			return game_menu(id);
		if (equali(text, "rtv"))
		{
			vote_map(id);
			return PLUGIN_HANDLED;
		}
		return PLUGIN_CONTINUE;
	}
	new cmd[16];
	parse(text[1], cmd, charsmax(cmd));
	if (equali(cmd, "menu") || equali(cmd, "меню"))
		return game_menu(id);
	if (equali(cmd, "rtv") || equali(cmd, "rockthevote"))
	{
		vote_map(id);
		return PLUGIN_HANDLED;
	}
	if (equali(cmd, "tp"))
	{
		tp_menu(id);
		return PLUGIN_HANDLED;
	}
	if (equali(cmd, "news"))
	{
		show_news(id);
		return PLUGIN_HANDLED;
	}
	if (equali(cmd, "board"))
	{
		show_board(id);
		return PLUGIN_HANDLED;
	}
	if (equali(cmd, "nextmap"))
	{
		czm_chat(id, "^4[CZM]^1 Следующая карта: ^4%s", "^4[CZM]^1 Next map: ^4%s", g_nextMap[0] ? g_nextMap : (en(id) ? "after the vote" : "после голосования"));
		return PLUGIN_HANDLED;
	}
	return PLUGIN_CONTINUE;
}

// ---------------------------------------------------------------- the game menu

// the tabs and cards of this plugin in the server menu (czm_menu)
menu_register()
{
	czm_menu_section("main", "Главное", "Main", "star", 0);
	czm_menu_section("players", "Игроки", "Players", "users", 30);
	czm_menu_section("votes", "Голосования", "Voting", "flag", 40);
	czm_menu_section("server", "Сервер", "Server", "globe", 50);
	czm_menu_section("settings", "Настройки", "Settings", "gear", 60);

	czm_menu_item("main", "panel", "Панель на сайте", "Player panel", "Скины, магазин, топ", "Skins, shop, top", "globe", "6BDAA7", "on_czm_menu", 20);
	czm_menu_item("main", "go_settings", "Настройки", "Settings", "Язык, звуки, подсказки", "Language, sounds, hints", "gear", "F59E0B", "#settings", 30);
	czm_menu_item("main", "go_votes", "Голосования", "Voting", "Карта, бан, мут", "Map, ban, mute", "flag", "A855F7", "#votes", 40);
	czm_menu_item("main", "tp", "Телепорт", "Teleport", "К другу по запросу", "To a friend, on request", "target", "22D3EE", "on_czm_menu", 50);
	czm_menu_item("main", "invite", "Приглашения", "Invitations", "Позвать друга на сервер", "Call a friend here", "person_add", "E53F4D", "on_czm_menu", 60);
	czm_menu_item("main", "news", "Новости сервера", "Server news", "Что нового на сервере", "What is new here", "bell", "63A1EF", "on_czm_menu", 70);
	czm_menu_item("main", "msg", "Сообщение админу", "Message to the staff", "Прочитает владелец", "The owner reads it", "chat", "F97316", "on_czm_menu", 80);

	czm_menu_item("players", "pl_tp", "Телепорт", "Teleport", "Позвать к себе или пойти к другу", "Call a human or go to one", "target", "22D3EE", "on_czm_menu", 10);
	czm_menu_item("players", "pl_invite", "Приглашения", "Invitations", "Сайт, панель и Telegram в чат", "The site, panel and Telegram", "person_add", "E53F4D", "on_czm_menu", 20);
	czm_menu_item("players", "pl_board", "Нарушители", "Violators", "Баны и муты сейчас", "Bans and mutes now", "block", "9BA6B8", "on_czm_menu", 30);

	czm_menu_item("votes", "v_map", "За смену карты", "Change the map", "Голоса всех игроков", "Everyone's votes", "flag", "A855F7", "on_czm_menu", 10);
	czm_menu_item("votes", "v_ban", "За бан игрока", "Ban a player", "На 30 минут", "For 30 minutes", "block", "E53F4D", "on_czm_menu", 20);
	czm_menu_item("votes", "v_mute", "За мут игрока", "Mute a player", "На час, чат и голос", "For an hour, chat and voice", "sound", "F59E0B", "on_czm_menu", 30);
	czm_menu_item("votes", "v_board", "Нарушители", "Violators", "Баны и муты сейчас", "Bans and mutes now", "block", "9BA6B8", "on_czm_menu", 40);

	czm_menu_item("server", "sv_news", "Новости сервера", "Server news", "Что нового на сервере", "What is new here", "bell", "63A1EF", "on_czm_menu", 10);
	czm_menu_item("server", "sv_panel", "Панель на сайте", "Player panel", "Вход одной кнопкой", "Signed in with one tap", "globe", "6BDAA7", "on_czm_menu", 20);
	czm_menu_item("server", "sv_next", "Следующая карта", "Next map", "После голосования", "After the vote", "play", "22D3EE", "on_czm_menu", 30);
	czm_menu_item("server", "sv_msg", "Сообщение админу", "Message to the staff", "Прочитает владелец", "The owner reads it", "chat", "F97316", "on_czm_menu", 40);

	czm_menu_item("settings", "set_lang", "Язык", "Language", "Русский или English", "Русский or English", "globe", "63A1EF", "on_czm_menu", 10);
	czm_menu_item("settings", "set_sound", "Музыка и звуки", "Music and sounds", "Звуки и музыка сервера", "The server's sounds and music", "sound", "A855F7", "on_czm_menu", 20);
	czm_menu_item("settings", "set_info", "Подсказки слева", "Hints on the left", "Строки слева вверху", "The lines at the top left", "info", "F59E0B", "on_czm_menu", 30);
}

public game_menu(id)
{
	czm_menu_open(id, "main");
	return PLUGIN_HANDLED;
}

// what changes from player to player: cooldowns, new news, votes, the settings
public czm_menu_build(id, const section[])
{
	new line[48], Float:wait = g_tpReady[id] - get_gametime();
	if (wait > 0.0)
	{
		new left = floatround(wait, floatround_ceil);
		formatex(line, charsmax(line), "%d:%02d", left / 60, left % 60);
		czm_menu_state(id, "tp", _, _, line);
		czm_menu_state(id, "pl_tp", _, _, line);
	}
	if (news_unseen(id))
	{
		czm_menu_state(id, "news", _, _, "!NEW");
		czm_menu_state(id, "sv_news", _, _, "!NEW");
		czm_menu_state(id, "#server", _, _, "1");
	}
	formatex(line, charsmax(line), "%d/%d", TrieGetSize(g_mapVoters), need(VOTES_MAP, 0, 1));
	czm_menu_state(id, "v_map", _, _, line);
	if (g_nextMap[0])
		czm_menu_state(id, "sv_next", _, g_nextMap);
	czm_menu_state(id, "set_lang", _, _, en(id) ? "EN" : "RU");
	czm_menu_state(id, "set_sound", _, _, czm_sound_on(id) ? (en(id) ? "on" : "вкл") : (en(id) ? "off" : "выкл"));
	czm_menu_state(id, "set_info", _, _, czm_info_on(id) ? (en(id) ? "on" : "вкл") : (en(id) ? "off" : "выкл"));
}

public on_czm_menu(id, const key[])
{
	if (equal(key, "panel") || equal(key, "sv_panel"))
		open_panel(id);
	else if (equal(key, "tp") || equal(key, "pl_tp"))
		tp_menu(id);
	else if (equal(key, "invite") || equal(key, "pl_invite"))
		invite(id);
	else if (equal(key, "news") || equal(key, "sv_news"))
		show_news(id);
	else if (equal(key, "pl_board") || equal(key, "v_board"))
		show_board(id);
	else if (equal(key, "msg") || equal(key, "sv_msg"))
	{
		czm_chat(id, "^4[CZM]^1 Напиши сообщение администрации и отправь — его прочитает владелец сервера.",
			"^4[CZM]^1 Type your message to the staff and send it: the server owner reads it.");
		client_cmd(id, "messagemode czm_admin_msg");
	}
	else if (equal(key, "v_map"))
	{
		vote_map(id);
		czm_menu_open(id, "votes");
	}
	else if (equal(key, "v_ban") || equal(key, "v_mute"))
	{
		g_pickKind[id] = equal(key, "v_ban") ? 1 : 2;
		pick_player(id);
	}
	else if (equal(key, "sv_next"))
	{
		czm_chat(id, "^4[CZM]^1 Следующая карта: ^4%s", "^4[CZM]^1 Next map: ^4%s", g_nextMap[0] ? g_nextMap : (en(id) ? "after the vote" : "после голосования"));
		czm_menu_open(id, "server");
	}
	else if (equal(key, "set_lang"))
	{
		czm_set_lang(id, en(id) ? CZM_RU : CZM_EN);
		czm_menu_open(id, "settings");
	}
	else if (equal(key, "set_sound"))
	{
		amxclient_cmd(id, czm_sound_on(id) ? "sound_off" : "sound_on");
		czm_menu_open(id, "settings");
	}
	else if (equal(key, "set_info"))
	{
		amxclient_cmd(id, "say", czm_info_on(id) ? "/info_off" : "/info_on");
		czm_menu_open(id, "settings");
	}
}

// The CZM game opens the panel in the phone's browser already signed in (czm_panel asks the API for a
// one-time link); other games get the address in chat.
open_panel(id)
{
	client_cmd(id, "czm_panel");
	czm_chat(id, "^4[CZM]^1 Панель игрока открывается в браузере. Если нет: ^4%s/panel", "^4[CZM]^1 The player panel opens in your browser. If not: ^4%s/panel", CZM_SITE);
}

invite(id)
{
	czm_chat(id, "^4[CZM]^1 Сайт игры: ^4%s", "^4[CZM]^1 The game's site: ^4%s", CZM_SITE);
	czm_chat(id, "^4[CZM]^1 Панель игрока: ^4%s/panel", "^4[CZM]^1 Player panel: ^4%s/panel", CZM_SITE);
	czm_chat(id, "^4[CZM]^1 Telegram: ^4t.me/counter_zombie_mobile", "^4[CZM]^1 Telegram: ^4t.me/counter_zombie_mobile");
	set_hudmessage(0, 255, 255, -1.0, 0.32, 0, 0.0, 3.0, 0.2, 0.4, -1);
	ShowSyncHudMsg(id, g_hud, en(id) ? "LINKS ARE IN THE CHAT!" : "ССЫЛКИ В ЧАТЕ!");
}

// ---------------------------------------------------------------- votes

vote_map(id)
{
	if (g_mapVoteRunning || g_mapVoteDone)
	{
		czm_chat(id, "^4[CZM]^1 Карта уже выбирается или выбрана.", "^4[CZM]^1 The next map is being chosen or already chosen.");
		return;
	}
	if (get_gametime() < g_mapCooldown)
	{
		czm_chat(id, "^4[CZM]^1 Недавно уже голосовали — подожди.", "^4[CZM]^1 There was a vote recently: wait a little.");
		return;
	}
	new key[40];
	key_of(id, key, charsmax(key));
	if (TrieKeyExists(g_mapVoters, key))
	{
		czm_chat(id, "^4[CZM]^1 Ты уже голосовал.", "^4[CZM]^1 You have voted already.");
		return;
	}
	TrieSetCell(g_mapVoters, key, 1);
	new have = TrieGetSize(g_mapVoters), needed = need(VOTES_MAP, 0, 1), name[32];
	get_user_name(id, name, charsmax(name));
	czm_chat(0, "^4[CZM]^3 %s^1 за смену карты: ^4%d/%d^1 (menu → Голосования или rtv).", "^4[CZM]^3 %s^1 wants another map: ^4%d/%d^1 (menu → Voting or rtv).", name, have, needed);
	if (have >= needed)
	{
		TrieClear(g_mapVoters);
		g_mapCooldown = get_gametime() + VOTE_COOLDOWN;
		czm_chat(0, "^4[CZM]^1 Игроки решили сменить карту! Выбираем следующую.", "^4[CZM]^1 The players want another map! Choose the next one.");
		g_changeNow = true;
		start_map_vote();
	}
}

pick_player(id)
{
	new title[96], line[64], info[8], players[MAX_PLAYERS], count, kind = g_pickKind[id];
	if (kind <= 2)
		formatex(title, charsmax(title), "\y%s^n\d%s", kind == 1 ? (en(id) ? "BAN A PLAYER" : "ЗА БАН ИГРОКА") : (en(id) ? "MUTE A PLAYER" : "ЗА МУТ ИГРОКА"),
			en(id) ? "a voice per player, staff are immune" : "один голос на игрока, админов нельзя");
	else
		formatex(title, charsmax(title), "\y%s", kind == 3 ? (en(id) ? "Call to me" : "Позвать к себе") : (en(id) ? "Go to" : "Телепорт к игроку"));
	new menu = menu_create(title, "on_pick_player");
	get_players(players, count, "ch");
	for (new k = 0; k < count; k++)
	{
		new p = players[k];
		if (p == id)
			continue;
		get_user_name(p, line, charsmax(line));
		if (kind <= 2)
		{
			new key[40], voices;
			key_of(p, key, charsmax(key));
			TrieGetCell(kind == 1 ? g_banCount : g_muteCount, key, voices);
			if (czm_staff(p) != CZM_STAFF_NONE)
				add(line, charsmax(line), en(id) ? " \r[staff]" : " \r[админ]");
			else if (czm_privilege(p))
			{
				new priv[12];
				czm_privilege_name(p, priv, charsmax(priv));
				format(line, charsmax(line), "%s \y[%s]", line, priv);
			}
			else
				format(line, charsmax(line), "%s \d[%d/%d]", line, voices, need(kind == 1 ? VOTES_BAN : VOTES_MUTE, p, 2));
		}
		else if (!is_user_alive(p) || zp_get_user_zombie(p))
			continue;
		num_to_str(get_user_userid(p), info, charsmax(info));
		menu_additem(menu, line, info);
	}
	if (!menu_items(menu))
	{
		menu_destroy(menu);
		czm_chat(id, "^4[CZM]^1 Подходящих игроков нет.", "^4[CZM]^1 There is nobody to choose.");
		return;
	}
	texts(menu, id);
	menu_display(id, menu);
}

public on_pick_player(id, menu, item_)
{
	if (item_ < 0)
	{
		menu_destroy(menu);
		return PLUGIN_HANDLED;
	}
	new info[8];
	menu_info(menu, item_, info, charsmax(info));
	menu_destroy(menu);
	new target = find_player_ex(FindPlayer_MatchUserId, str_to_num(info));
	if (!target)
	{
		czm_chat(id, "^4[CZM]^1 Игрок уже вышел.", "^4[CZM]^1 The player has left.");
		return PLUGIN_HANDLED;
	}
	switch (g_pickKind[id])
	{
		case 1, 2: vote_against(id, target, g_pickKind[id] == 1);
		case 3, 4: tp_request(id, target, g_pickKind[id] == 3 ? 1 : 2);
	}
	return PLUGIN_HANDLED;
}

vote_against(id, target, bool:ban)
{
	if (czm_staff(target) != CZM_STAFF_NONE || czm_privilege(target))
	{
		czm_chat(id, "^4[CZM]^1 Против администрации и игроков с привилегией голосовать нельзя.", "^4[CZM]^1 Staff and privileged players are immune.");
		return;
	}
	new targetKey[40], voterKey[40], pair[84], gate[48], Float:until;
	key_of(target, targetKey, charsmax(targetKey));
	key_of(id, voterKey, charsmax(voterKey));
	formatex(gate, charsmax(gate), "%s|%s", ban ? "ban" : "mute", targetKey);
	if (TrieGetCell(g_cooldown, gate, until) && get_gametime() < until)
	{
		czm_chat(id, "^4[CZM]^1 Это голосование на перерыве.", "^4[CZM]^1 This vote is on a break.");
		return;
	}
	if (!ban && czm_muted(target))
	{
		czm_chat(id, "^4[CZM]^1 У игрока уже мут.", "^4[CZM]^1 The player is muted already.");
		return;
	}
	formatex(pair, charsmax(pair), "%s|%s", targetKey, voterKey);
	new Trie:voters = ban ? g_banVoters : g_muteVoters, Trie:counts = ban ? g_banCount : g_muteCount;
	if (TrieKeyExists(voters, pair))
	{
		czm_chat(id, "^4[CZM]^1 Ты уже голосовал.", "^4[CZM]^1 You have voted already.");
		return;
	}
	TrieSetCell(voters, pair, 1);
	new voices;
	TrieGetCell(counts, targetKey, voices);
	TrieSetCell(counts, targetKey, ++voices);
	new needed = need(ban ? VOTES_BAN : VOTES_MUTE, target, 2), name[32], who[32];
	get_user_name(target, name, charsmax(name));
	get_user_name(id, who, charsmax(who));
	if (ban)
		czm_chat(0, "^4[CZM]^3 %s^1 голосует за бан ^3%s^1: ^4%d/%d", "^4[CZM]^3 %s^1 votes to ban ^3%s^1: ^4%d/%d", who, name, voices, needed);
	else
		czm_chat(0, "^4[CZM]^3 %s^1 голосует за мут ^3%s^1: ^4%d/%d", "^4[CZM]^3 %s^1 votes to mute ^3%s^1: ^4%d/%d", who, name, voices, needed);
	czm_play_sound(id, g_hVoteStart);
	if (voices < needed)
		return;
	TrieDeleteKey(counts, targetKey);
	clear_votes_for(voters, targetKey);
	TrieSetCell(g_cooldown, gate, get_gametime() + VOTE_COOLDOWN);
	czm_play_sound(0, g_hVoteStop);
	// no reason: by 0 already tells everyone it was the players' vote
	czm_sanction(target, ban ? "ban" : "mute", ban ? VOTE_BAN_SECONDS : VOTE_MUTE_SECONDS, "", 0);
}

// Forgets the voices about one player once the vote passed, so a later vote starts from zero.
clear_votes_for(Trie:voters, const targetKey[])
{
	new TrieIter:it = TrieIterCreate(voters), pair[84], prefix[44], len;
	len = formatex(prefix, charsmax(prefix), "%s|", targetKey);
	new Array:drop = ArrayCreate(sizeof pair);
	while (!TrieIterEnded(it))
	{
		TrieIterGetKey(it, pair, charsmax(pair));
		if (equal(pair, prefix, len))
			ArrayPushString(drop, pair);
		TrieIterNext(it);
	}
	TrieIterDestroy(it);
	for (new k = 0; k < ArraySize(drop); k++)
	{
		ArrayGetString(drop, k, pair, charsmax(pair));
		TrieDeleteKey(voters, pair);
	}
	ArrayDestroy(drop);
}

show_board(id)
{
	new data[2];
	data[0] = id; data[1] = get_user_userid(id);
	czm_api("GET", "/survival/board?limit=10", CZM_JSON_NONE, "on_board", data, sizeof data);
}

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
	new EzJSON:board = ezjson_object_get_value(root, "board"), count = ezjson_array_get_count(board);
	if (!count)
		czm_chat(id, "^4[CZM]^1 Доска нарушителей пуста.", "^4[CZM]^1 The violators board is empty.");
	else
		czm_chat(id, "^4[CZM]^1 Доска нарушителей:", "^4[CZM]^1 Violators board:");
	for (new k = 0; k < count; k++)
	{
		new EzJSON:it = ezjson_array_get_value(board, k), kind[8], name[32], reason[64], left[24];
		ezjson_object_get_string(it, "kind", kind, charsmax(kind));
		ezjson_object_get_string(it, "name", name, charsmax(name));
		ezjson_object_get_string(it, "reason", reason, charsmax(reason));
		if (!reason[0] && ezjson_object_get_bool(it, "vote"))
			copy(reason, charsmax(reason), en(id) ? "players' vote" : "голосование игроков");
		czm_api_left(ezjson_object_get_number(it, "left"), left, charsmax(left), czm_lang(id));
		if (equal(kind, "ban"))
			czm_chat(id, "^3%s^1 — ^4бан^1 %s%s%s", "^3%s^1 — ^4ban^1 %s%s%s", name, left, reason[0] ? ", " : "", reason);
		else
			czm_chat(id, "^3%s^1 — ^4мут^1 %s%s%s", "^3%s^1 — ^4mute^1 %s%s%s", name, left, reason[0] ? ", " : "", reason);
		ezjson_free(it);
	}
	ezjson_free(board);
	ezjson_free(root);
}

// ---------------------------------------------------------------- the map vote

load_maps()
{
	new path[64], line[48], current[32];
	get_cvar_string("mapcyclefile", path, charsmax(path));
	get_mapname(current, charsmax(current));
	new fh = fopen(path, "rt");
	while (fh && !feof(fh) && g_mapCount < sizeof g_maps)
	{
		fgets(fh, line, charsmax(line));
		trim(line);
		if (!line[0] || line[0] == ';' || line[0] == '/' || equali(line, current) || !is_map_valid(line))
			continue;
		copy(g_maps[g_mapCount++], charsmax(g_maps[]), line);
	}
	if (fh)
		fclose(fh);
}

public task_second()
{
	// the vote two minutes before the end of the map
	if (!g_mapVoteRunning && !g_mapVoteDone && get_cvar_float("mp_timelimit") > 0.0)
	{
		new left = get_timeleft();
		if (0 < left <= MAPVOTE_AT)
		{
			g_changeNow = false;
			start_map_vote();
		}
	}
	for (new id = 1; id <= MaxClients; id++)
		if (g_tpFrom[id] && --g_tpLeft[id] <= 0)
			tp_answer(id, false, true);
}

start_map_vote()
{
	if (g_mapVoteRunning || g_mapCount == 0)
		return;
	g_mapVoteRunning = true;
	// random maps of the cycle, without repeats
	new order[sizeof g_maps], n = g_mapCount;
	for (new k = 0; k < n; k++)
		order[k] = k;
	for (new k = n - 1; k > 0; k--)
	{
		new j = random(k + 1), t = order[k];
		order[k] = order[j];
		order[j] = t;
	}
	g_choiceCount = min(n, MAPVOTE_CHOICES);
	for (new k = 0; k < g_choiceCount; k++)
	{
		copy(g_choice[k], charsmax(g_choice[]), g_maps[order[k]]);
		g_choiceVotes[k] = 0;
	}
	// ten more minutes of this map, once, unless the players asked for another map
	new bool:extend = !g_extended && !g_changeNow;
	if (extend)
	{
		get_mapname(g_choice[g_choiceCount], charsmax(g_choice[]));
		g_choiceVotes[g_choiceCount] = 0;
	}
	new title[96], line[64], info[4];
	for (new p = 1; p <= MaxClients; p++)
	{
		if (!is_user_connected(p) || is_user_bot(p))
			continue;
		formatex(title, charsmax(title), "\y%s^n\d%s", en(p) ? "NEXT MAP" : "СЛЕДУЮЩАЯ КАРТА",
			en(p) ? "the vote lasts 20 seconds" : "голосование 20 секунд");
		new menu = menu_create(title, "on_map_vote");
		for (new k = 0; k < g_choiceCount; k++)
		{
			num_to_str(k, info, charsmax(info));
			menu_additem(menu, g_choice[k], info);
		}
		if (extend)
		{
			formatex(line, charsmax(line), en(p) ? "\yStay here 10 more minutes" : "\yОстаться ещё на 10 минут");
			num_to_str(g_choiceCount, info, charsmax(info));
			menu_additem(menu, line, info);
		}
		menu_setprop(menu, MPROP_EXIT, MEXIT_NEVER);
		menu_setprop(menu, MPROP_PERPAGE, 0);
		menu_display(p, menu, 0, MAPVOTE_SECONDS);
	}
	if (g_changeNow)
		czm_play_music(0, g_hMapMusic, true);
	czm_play_sound(0, g_hVoteStart);
	g_mapVoteLeft = MAPVOTE_SECONDS;
	set_task(1.0, "task_map_vote", TASK_MAPVOTE, _, _, "a", MAPVOTE_SECONDS);
}

public on_map_vote(id, menu, item_)
{
	if (item_ >= 0 && g_mapVoteRunning)
	{
		new info[4], name[32];
		menu_info(menu, item_, info, charsmax(info));
		new k = str_to_num(info);
		if (0 <= k <= g_choiceCount)
		{
			g_choiceVotes[k]++;
			get_user_name(id, name, charsmax(name));
			if (k == g_choiceCount)
				czm_chat(0, "^4[CZM]^3 %s^1: остаться ещё на 10 минут", "^4[CZM]^3 %s^1: 10 more minutes here", name);
			else
				czm_chat(0, "^4[CZM]^3 %s^1 выбрал ^4%s", "^4[CZM]^3 %s^1 chose ^4%s", name, g_choice[k]);
		}
	}
	menu_destroy(menu);
	return PLUGIN_HANDLED;
}

public task_map_vote()
{
	if (--g_mapVoteLeft > 0)
		return;
	g_mapVoteRunning = false;
	g_mapVoteDone = true;
	czm_play_sound(0, g_hVoteStop);
	new bool:extend = !g_extended && !g_changeNow, best = 0, top = -1;
	new last = extend ? g_choiceCount : g_choiceCount - 1;
	for (new k = 0; k <= last; k++)
		if (g_choiceVotes[k] > top || (g_choiceVotes[k] == top && random(2)))
		{
			top = g_choiceVotes[k];
			best = k;
		}
	if (extend && best == g_choiceCount && top > 0)
	{
		g_extended = true;
		g_mapVoteDone = false;     // another vote comes two minutes before the new end
		set_cvar_float("mp_timelimit", get_cvar_float("mp_timelimit") + EXTEND_MINUTES);
		czm_chat(0, "^4[CZM]^1 Остаёмся на этой карте ещё ^4%d^1 минут.", "^4[CZM]^1 We stay on this map ^4%d^1 more minutes.", floatround(EXTEND_MINUTES));
		return;
	}
	if (best == g_choiceCount)
		best = random(g_choiceCount);   // nobody voted for staying: a random map of the choice
	copy(g_nextMap, charsmax(g_nextMap), g_choice[best]);
	set_cvar_string("amx_nextmap", g_nextMap);
	czm_chat(0, "^4[CZM]^1 Следующая карта: ^4%s^1 (голосов: %d).", "^4[CZM]^1 Next map: ^4%s^1 (%d votes).", g_nextMap, max(top, 0));
	set_hudmessage(255, 210, 0, -1.0, 0.25, 0, 0.0, 5.0, 0.2, 0.5, -1);
	for (new p = 1; p <= MaxClients; p++)
		if (is_user_connected(p) && !is_user_bot(p))
			ShowSyncHudMsg(p, g_hud, "%s^n%s", en(p) ? "NEXT MAP" : "СЛЕДУЮЩАЯ КАРТА", g_nextMap);
	if (g_changeNow)
	{
		czm_chat(0, "^4[CZM]^1 Смена карты через 5 секунд.", "^4[CZM]^1 The map changes in 5 seconds.");
		set_task(5.0, "task_change", TASK_CHANGE);
	}
}

public task_change()
{
	if (g_chatTime > 0.0)
		set_cvar_float("mp_chattime", g_chatTime);
	server_cmd("changelevel %s", g_nextMap);
}

// The game goes to the next map of the cycle after the scoreboard; we go to the chosen one first.
public msg_intermission()
{
	if (!g_nextMap[0] || task_exists(TASK_CHANGE))
		return;
	g_chatTime = get_cvar_float("mp_chattime");
	set_cvar_float("mp_chattime", g_chatTime + 3.0);
	set_task(floatmax(g_chatTime, 2.0), "task_change", TASK_CHANGE);
}

// ---------------------------------------------------------------- teleport

public tp_menu(id)
{
	if (!is_user_alive(id) || zp_get_user_zombie(id))
	{
		czm_chat(id, "^4[CZM]^1 Телепорт — для живых людей.", "^4[CZM]^1 Teleport is for living humans.");
		return PLUGIN_HANDLED;
	}
	new Float:wait = g_tpReady[id] - get_gametime();
	if (wait > 0.0)
	{
		czm_chat(id, "^4[CZM]^1 Телепорт будет доступен через ^4%d^1 с.", "^4[CZM]^1 Teleport is ready in ^4%d^1 s.", floatround(wait, floatround_ceil));
		return PLUGIN_HANDLED;
	}
	new title[64];
	formatex(title, charsmax(title), "\y%s", en(id) ? "TELEPORT" : "ТЕЛЕПОРТ");
	new menu = menu_create(title, "on_tp_menu");
	item(menu, id, "Позвать игрока к себе", "Call a player to me", "3");
	item(menu, id, "Телепортироваться к игроку", "Go to a player", "4");
	texts(menu, id);
	menu_display(id, menu);
	return PLUGIN_HANDLED;
}

public on_tp_menu(id, menu, item_)
{
	if (item_ < 0)
	{
		menu_destroy(menu);
		return PLUGIN_HANDLED;
	}
	new info[4];
	menu_info(menu, item_, info, charsmax(info));
	menu_destroy(menu);
	g_pickKind[id] = str_to_num(info);
	pick_player(id);
	return PLUGIN_HANDLED;
}

tp_request(id, target, mode)
{
	if (!is_user_alive(id) || zp_get_user_zombie(id) || !is_user_alive(target) || zp_get_user_zombie(target))
	{
		czm_chat(id, "^4[CZM]^1 Телепорт — между живыми людьми.", "^4[CZM]^1 Teleport works between living humans.");
		return;
	}
	if (g_tpFrom[target])
	{
		czm_chat(id, "^4[CZM]^1 Этому игроку уже пришёл запрос, попробуй позже.", "^4[CZM]^1 That player already has a request: try later.");
		return;
	}
	g_tpReady[id] = get_gametime() + TP_COOLDOWN;
	g_tpFrom[target] = id;
	g_tpMode[target] = mode;
	g_tpLeft[target] = TP_ANSWER;
	new name[32], title[160];
	get_user_name(id, name, charsmax(name));
	if (mode == 1)
		formatex(title, charsmax(title), en(target) ? "\y%s\w calls you to them^n\d15 seconds to answer" : "\y%s\w зовёт тебя к себе^n\d15 секунд на ответ", name);
	else
		formatex(title, charsmax(title), en(target) ? "\y%s\w wants to come to you^n\d15 seconds to answer" : "\y%s\w хочет телепортироваться к тебе^n\d15 секунд на ответ", name);
	new menu = menu_create(title, "on_tp_answer");
	item(menu, target, "Да", "Yes", "1");
	item(menu, target, "Нет", "No", "0");
	menu_setprop(menu, MPROP_EXIT, MEXIT_NEVER);
	menu_display(target, menu, 0, TP_ANSWER);
	czm_play_sound(target, g_hInvite);
	get_user_name(target, name, charsmax(name));
	czm_chat(id, "^4[CZM]^1 Запрос отправлен игроку ^3%s^1.", "^4[CZM]^1 The request went to ^3%s^1.", name);
}

public on_tp_answer(id, menu, item_)
{
	if (item_ >= 0 && g_tpFrom[id])
	{
		new info[4];
		menu_info(menu, item_, info, charsmax(info));
		tp_answer(id, info[0] == '1', false);
	}
	menu_destroy(menu);
	return PLUGIN_HANDLED;
}

tp_answer(target, bool:yes, bool:timeout)
{
	new from = g_tpFrom[target], mode = g_tpMode[target];
	g_tpFrom[target] = 0;
	if (!from || !is_user_connected(from))
		return;
	new name[32];
	get_user_name(target, name, charsmax(name));
	if (!yes)
	{
		czm_play_sound(from, g_hNo);
		if (timeout)
			czm_chat(from, "^4[CZM]^3 %s^1 не ответил.", "^4[CZM]^3 %s^1 did not answer.", name);
		else
			czm_chat(from, "^4[CZM]^3 %s^1 отказался.", "^4[CZM]^3 %s^1 said no.", name);
		return;
	}
	czm_play_sound(from, g_hYes);
	if (!is_user_alive(from) || zp_get_user_zombie(from) || !is_user_alive(target) || zp_get_user_zombie(target))
	{
		czm_chat(from, "^4[CZM]^1 Телепорт отменён: кто-то уже не человек.", "^4[CZM]^1 Teleport cancelled: someone is no longer human.");
		return;
	}
	new bool:ok = mode == 1 ? teleport_near(target, from) : teleport_near(from, target);
	if (!ok)
	{
		czm_chat(from, "^4[CZM]^1 Рядом нет места для телепорта.", "^4[CZM]^1 No free spot there.");
		return;
	}
	czm_play_sound(from, g_hTeleport);
	czm_play_sound(target, g_hTeleport);
}

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

// ---------------------------------------------------------------- messages to the staff

public cmd_admin_msg(id)
{
	new text[200], name[32], ip[40];
	read_args(text, charsmax(text));
	remove_quotes(text);
	trim(text);
	if (strlen(text) < 3)
		return PLUGIN_HANDLED;
	get_user_name(id, name, charsmax(name));
	get_user_ip(id, ip, charsmax(ip), 1);
	new EzJSON:body = ezjson_init_object(), data[2], server[32];
	get_cvar_string("czm_server_name", server, charsmax(server));
	ezjson_object_set_number(body, "player", czm_profile(id));
	ezjson_object_set_string(body, "ip", ip);
	ezjson_object_set_string(body, "name", name);
	ezjson_object_set_string(body, "text", text);
	ezjson_object_set_string(body, "server", server[0] ? server : "survival");
	data[0] = id; data[1] = get_user_userid(id);
	czm_api("POST", "/survival/server/message", body, "on_admin_msg", data, sizeof data);
	ezjson_free(body);
	// staff who play now read it at once
	replace_all(text, charsmax(text), "%", "");
	for (new p = 1; p <= MaxClients; p++)
		if (p != id && is_user_connected(p) && czm_staff(p) != CZM_STAFF_NONE)
		{
			client_print_color(p, print_team_default, "^4[%s]^3 %s^1: %s", en(p) ? "To the staff" : "Админу", name, text);
			czm_play_sound(p, g_hMessage);
		}
	return PLUGIN_HANDLED;
}

public on_admin_msg(EzHttpRequest:request)
{
	new data[2];
	ezhttp_get_user_data(request, data);
	new id = data[0], code, EzJSON:root = czm_api_answer(request, code);
	if (is_user_connected(id) && get_user_userid(id) == data[1])
	{
		new error[24];
		if (CZM_JSON_OK(root) && code != 200)
			ezjson_object_get_string(root, "error", error, charsmax(error));
		if (code == 200)
			czm_chat(id, "^4[CZM]^1 Сообщение отправлено администрации. Спасибо!", "^4[CZM]^1 Your message went to the staff. Thank you!");
		else if (equal(error, "message_limit"))
			czm_chat(id, "^4[CZM]^1 Не чаще трёх сообщений за 10 минут.", "^4[CZM]^1 At most three messages in 10 minutes.");
		else
			czm_chat(id, "^4[CZM]^1 Сообщение не ушло, попробуй позже.", "^4[CZM]^1 The message did not go: try later.");
	}
	if (CZM_JSON_OK(root))
		ezjson_free(root);
}

// ---------------------------------------------------------------- news

public task_news()
{
	if (czm_api_ready())
		czm_api("GET", "/survival/news?limit=6", CZM_JSON_NONE, "on_news");
}

public on_news(EzHttpRequest:request)
{
	new code, EzJSON:root = czm_api_answer(request, code);
	if (code == 200 && CZM_JSON_OK(root))
	{
		new EzJSON:list = ezjson_object_get_value(root, "news");
		g_newsCount = min(ezjson_array_get_count(list), MAX_NEWS);
		for (new k = 0; k < g_newsCount; k++)
		{
			new EzJSON:it = ezjson_array_get_value(list, k);
			g_newsId[k] = ezjson_object_get_number(it, "id");
			g_newsWhen[k] = ezjson_object_get_number(it, "created");
			ezjson_object_get_string(it, "ru", g_newsRu[k], charsmax(g_newsRu[]));
			ezjson_object_get_string(it, "en", g_newsEn[k], charsmax(g_newsEn[]));
			ezjson_free(it);
		}
		ezjson_free(list);
	}
	if (CZM_JSON_OK(root))
		ezjson_free(root);
}

bool:news_unseen(id)
{
	return g_newsCount > 0 && g_newsId[0] > g_newsSeen[id];
}

show_news(id)
{
	if (!g_newsCount)
	{
		czm_chat(id, "^4[CZM]^1 Новостей пока нет.", "^4[CZM]^1 No news yet.");
		return;
	}
	new date[16];
	// oldest first: the newest is at the bottom, next to the input line
	for (new k = g_newsCount - 1; k >= 0; k--)
	{
		format_time(date, charsmax(date), "%d.%m", g_newsWhen[k]);
		client_print_color(id, print_team_default, "^4[%s]^1 %s%s", date, (g_newsId[k] > g_newsSeen[id]) ? "^3" : "", en(id) ? g_newsEn[k] : g_newsRu[k]);
	}
	g_newsSeen[id] = g_newsId[0];
	new key[48], value[12];
	czm_player_key(id, key, charsmax(key));
	if (key[0] && g_vault != INVALID_HANDLE)
	{
		format(key, charsmax(key), "news:%s", key);
		num_to_str(g_newsSeen[id], value, charsmax(value));
		nvault_set(g_vault, key, value);
	}
}

// ---------------------------------------------------------------- players come and go

public czm_player_ready(id, profile)
{
	g_newsSeen[id] = 0;
	g_tpReady[id] = 0.0;
	g_tpFrom[id] = 0;
	if (is_user_bot(id) || g_vault == INVALID_HANDLE)
		return;
	new key[48], value[16], stamp;
	czm_player_key(id, key, charsmax(key));
	if (!key[0])
		return;
	format(key, charsmax(key), "news:%s", key);
	if (nvault_lookup(g_vault, key, value, charsmax(value), stamp))
		g_newsSeen[id] = str_to_num(value);
	// Zombie Plague hands out the starting packs as the player comes in; ours come a moment later
	remove_task(TASK_PACKS + id);
	set_task(1.5, "task_packs", TASK_PACKS + id);
	if (news_unseen(id))
		set_task(8.0, "task_news_hint", TASK_PACKS + MAX_PLAYERS + id);
}

public task_news_hint(taskid)
{
	new id = taskid - TASK_PACKS - MAX_PLAYERS;
	if (is_user_connected(id) && news_unseen(id))
		czm_chat(id, "^4[CZM]^1 Есть новости сервера: ^4menu^1 → Новости.", "^4[CZM]^1 There is server news: ^4menu^1 → News.");
}

public task_packs(taskid)
{
	new id = taskid - TASK_PACKS, key[48], value[16], stamp;
	if (!is_user_connected(id))
		return;
	czm_player_key(id, key, charsmax(key));
	format(key, charsmax(key), "packs:%s", key);
	if (nvault_lookup(g_vault, key, value, charsmax(value), stamp))
	{
		new saved = str_to_num(value);
		if (saved > zp_get_user_ammo_packs(id))
			zp_set_user_ammo_packs(id, saved);
	}
}

save_packs(id)
{
	if (is_user_bot(id) || g_vault == INVALID_HANDLE || task_exists(TASK_PACKS + id))
		return;
	new key[48], value[16];
	czm_player_key(id, key, charsmax(key));
	if (!key[0])
		return;
	format(key, charsmax(key), "packs:%s", key);
	num_to_str(zp_get_user_ammo_packs(id), value, charsmax(value));
	nvault_set(g_vault, key, value);
}

public client_disconnected(id)
{
	save_packs(id);
	remove_task(TASK_PACKS + id);
	remove_task(TASK_PACKS + MAX_PLAYERS + id);
	// a request to or from the player who left ends here
	if (g_tpFrom[id])
		g_tpFrom[id] = 0;
	for (new p = 1; p <= MaxClients; p++)
		if (g_tpFrom[p] == id)
			g_tpFrom[p] = 0;
}
