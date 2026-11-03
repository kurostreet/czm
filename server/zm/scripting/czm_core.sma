/*
	Counter Zombie Mobile, Survival server: the base every other czm_* plugin stands on.

	* the player's language (RU/EN): the game tells it (ui_language), /rus and /eng change it,
	  players of other clients get it from their first chat lines, as on the Kontra server;
	* /sound_on and /sound_off, /info_on and /info_off;
	* the CZM profile: the game sends a signed ticket in setinfo _czm, only to our servers.
	  The ticket is "<profile>.<expires>.<signature>", the signature is the first 32 hex digits of
	  sha256(key "|v1|" profile "|" expires "|" address "|" key). The address is this server's public
	  IP:port, so a ticket that leaked to another server does not open ours;
	* the sound list (configs/survival_sounds.json, built by tools/prepare_content.py): plugins ask
	  for a sound by its Kontra name and play it through one place that respects /sound_off and
	  does not cut a track that is still playing.
*/
#include <amxmodx>
#include <amxmisc>
#include <fakemeta>
#include <json>
#include <nvault>

#define PLUGIN "CZM Core"
#define VERSION "1.0"
#define AUTHOR "kurostreet"

#define MAX_SOUNDS 320
#define TICKET_SKEW 60

enum _:SoundData
{
	SndFile[64],
	SndKind,
	Float:SndLength,
	bool:SndCached
}

new g_sounds[MAX_SOUNDS][SoundData];
new g_soundCount;
new Trie:g_soundByName;

// Where the language came from; a stronger source is never overruled by a weaker one.
enum
{
	LANG_NONE = 0,
	LANG_CHAT,   // guessed from what the player writes (clients that do not tell it)
	LANG_GAME,   // the game's own language (ui_language)
	LANG_CHOSEN  // /rus or /eng
}

new g_lang[MAX_PLAYERS + 1];
new g_langSource[MAX_PLAYERS + 1];
new bool:g_soundOn[MAX_PLAYERS + 1];
new bool:g_infoOn[MAX_PLAYERS + 1];
new g_profile[MAX_PLAYERS + 1];
new bool:g_ready[MAX_PLAYERS + 1];
new Float:g_musicUntil[MAX_PLAYERS + 1];

new g_vault = INVALID_HANDLE;
new g_ticketKey[96];
new g_fwLang, g_fwReady, g_fwInfo;
new g_cvarAddress, g_cvarDefaultLang;

public plugin_natives()
{
	register_library("czm_core");
	register_native("czm_lang", "native_lang");
	register_native("czm_set_lang", "native_set_lang");
	register_native("czm_sound_on", "native_sound_on");
	register_native("czm_info_on", "native_info_on");
	register_native("czm_profile", "native_profile");
	register_native("czm_player_key", "native_player_key");
	register_native("czm_sound_precache", "native_sound_precache");
	register_native("czm_sound_kind", "native_sound_kind");
	register_native("czm_sound_length", "native_sound_length");
	register_native("czm_sound_path", "native_sound_path");
	register_native("czm_play_sound", "native_play_sound");
	register_native("czm_play_music", "native_play_music");
	register_native("czm_stop_music", "native_stop_music");
	register_native("czm_emit_sound", "native_emit_sound");
}

public plugin_precache()
{
	g_soundByName = TrieCreate();
	load_sounds();
}

public plugin_init()
{
	register_plugin(PLUGIN, VERSION, AUTHOR);

	// The public address the tickets are signed for, e.g. "194.226.112.249:27016".
	g_cvarAddress = create_cvar("czm_public_address", "", FCVAR_PROTECTED);
	g_cvarDefaultLang = create_cvar("czm_default_lang", "ru");

	g_fwLang = CreateMultiForward("czm_lang_changed", ET_IGNORE, FP_CELL, FP_CELL);
	g_fwReady = CreateMultiForward("czm_player_ready", ET_IGNORE, FP_CELL, FP_CELL);
	g_fwInfo = CreateMultiForward("czm_info_changed", ET_IGNORE, FP_CELL, FP_CELL);

	register_clcmd("say", "cmd_say");
	register_clcmd("say_team", "cmd_say");
	register_clcmd("czm_rus", "cmd_rus");
	register_clcmd("czm_eng", "cmd_eng");
	register_clcmd("sound_on", "cmd_sound_on");
	register_clcmd("sound_off", "cmd_sound_off");
	register_clcmd("info_on", "cmd_info_on");
	register_clcmd("info_off", "cmd_info_off");

	g_vault = nvault_open("czm_prefs");
	load_ticket_key();
}

public plugin_end()
{
	if (g_vault != INVALID_HANDLE)
		nvault_close(g_vault);
	if (g_soundByName)
		TrieDestroy(g_soundByName);
}

// ---------------------------------------------------------------- sounds

load_sounds()
{
	new path[128];
	get_configsdir(path, charsmax(path));
	add(path, charsmax(path), "/survival_sounds.json");
	new JSON:root = json_parse(path, true);
	if (root == Invalid_JSON)
	{
		log_amx("survival_sounds.json is missing or broken: no Kontra sounds on this map");
		return;
	}
	new count = json_object_get_count(root);
	new name[64], file[64], kind[8];
	for (new i = 0; i < count && g_soundCount < MAX_SOUNDS; i++)
	{
		json_object_get_name(root, i, name, charsmax(name));
		new JSON:item = json_object_get_value_at(root, i);
		json_object_get_string(item, "file", file, charsmax(file));
		json_object_get_string(item, "kind", kind, charsmax(kind));
		formatex(g_sounds[g_soundCount][SndFile], charsmax(g_sounds[][SndFile]), "survival/%s", file);
		g_sounds[g_soundCount][SndKind] = equal(kind, "music") ? CZM_SND_MUSIC : CZM_SND_EFFECT;
		g_sounds[g_soundCount][SndLength] = json_object_get_real(item, "len");
		json_free(item);
		strtolower(name);
		TrieSetCell(g_soundByName, name, g_soundCount);
		g_soundCount++;
	}
	json_free(root);
}

bool:valid_sound(handle)
{
	return 0 <= handle < g_soundCount;
}

public native_sound_precache(plugin, params)
{
	new name[64], handle;
	get_string(1, name, charsmax(name));
	strtolower(name);
	if (!TrieGetCell(g_soundByName, name, handle))
	{
		log_amx("sound %s is not in survival_sounds.json", name);
		return -1;
	}
	if (!g_sounds[handle][SndCached])
	{
		if (g_sounds[handle][SndKind] == CZM_SND_MUSIC)
		{
			new path[80];
			formatex(path, charsmax(path), "sound/%s", g_sounds[handle][SndFile]);
			precache_generic(path);
		}
		else
			precache_sound(g_sounds[handle][SndFile]);
		g_sounds[handle][SndCached] = true;
	}
	return handle;
}

public native_sound_kind(plugin, params)
{
	new handle = get_param(1);
	return valid_sound(handle) ? g_sounds[handle][SndKind] : CZM_SND_MISSING;
}

public Float:native_sound_length(plugin, params)
{
	new handle = get_param(1);
	return valid_sound(handle) ? g_sounds[handle][SndLength] : 0.0;
}

public native_sound_path(plugin, params)
{
	new handle = get_param(1);
	if (!valid_sound(handle))
		return 0;
	set_string(2, g_sounds[handle][SndFile], get_param(3));
	return 1;
}

bool:can_hear(id)
{
	return is_user_connected(id) && !is_user_bot(id) && g_soundOn[id];
}

public native_play_sound(plugin, params)
{
	new id = get_param(1), handle = get_param(2);
	if (!valid_sound(handle))
		return 0;
	new sent;
	for (new i = id ? id : 1, last = id ? id : MaxClients; i <= last; i++)
	{
		if (!can_hear(i))
			continue;
		client_cmd(i, "play ^"%s^"", g_sounds[handle][SndFile]);
		sent++;
	}
	return sent;
}

public native_play_music(plugin, params)
{
	new id = get_param(1), handle = get_param(2), bool:force = bool:get_param(3);
	if (!valid_sound(handle))
		return 0;
	new Float:now = get_gametime(), sent;
	for (new i = id ? id : 1, last = id ? id : MaxClients; i <= last; i++)
	{
		if (!can_hear(i) || (!force && g_musicUntil[i] > now))
			continue;
		client_cmd(i, "mp3 play ^"sound/%s^"", g_sounds[handle][SndFile]);
		g_musicUntil[i] = now + g_sounds[handle][SndLength];
		sent++;
	}
	return sent;
}

public native_stop_music(plugin, params)
{
	new id = get_param(1);
	for (new i = id ? id : 1, last = id ? id : MaxClients; i <= last; i++)
	{
		if (!is_user_connected(i) || is_user_bot(i))
			continue;
		client_cmd(i, "mp3 stop");
		g_musicUntil[i] = 0.0;
	}
}

public native_emit_sound(plugin, params)
{
	new entity = get_param(1), handle = get_param(2);
	if (!valid_sound(handle) || !pev_valid(entity))
		return 0;
	emit_sound(entity, get_param(3), g_sounds[handle][SndFile], get_param_f(4), ATTN_NORM, 0, PITCH_NORM);
	return 1;
}

// ---------------------------------------------------------------- players

public client_connect(id)
{
	g_lang[id] = default_lang();
	g_langSource[id] = LANG_NONE;
	g_soundOn[id] = true;
	g_infoOn[id] = true;
	g_profile[id] = 0;
	g_ready[id] = false;
	g_musicUntil[id] = 0.0;
}

public client_putinserver(id)
{
	if (is_user_bot(id) || is_user_hltv(id))
		return;
	g_profile[id] = check_ticket(id);
	load_prefs(id);
	g_ready[id] = true;
	new ret;
	ExecuteForward(g_fwReady, ret, id, g_profile[id]);
	query_client_cvar(id, "ui_language", "on_ui_language");
}

public client_disconnected(id)
{
	if (g_ready[id])
		save_prefs(id);
	g_ready[id] = false;
}

public on_ui_language(id, const cvar[], const value[])
{
	if (!is_user_connected(id))
		return;
	if (equali(value, "russian"))
		set_lang(id, CZM_RU, LANG_GAME);
	else if (equali(value, "english"))
		set_lang(id, CZM_EN, LANG_GAME);
}

default_lang()
{
	new value[8];
	get_pcvar_string(g_cvarDefaultLang, value, charsmax(value));
	return equali(value, "en") ? CZM_EN : CZM_RU;
}

set_lang(id, lang, source)
{
	if (source < g_langSource[id] && source != LANG_CHOSEN)
		return;
	new changed = g_lang[id] != lang || g_langSource[id] == LANG_NONE;
	g_lang[id] = lang;
	g_langSource[id] = source;
	if (changed)
	{
		new ret;
		ExecuteForward(g_fwLang, ret, id, lang);
	}
}

player_key(id, out[], len)
{
	if (g_profile[id])
		return formatex(out, len, "p%d", g_profile[id]);
	new authid[44];
	get_user_authid(id, authid, charsmax(authid));
	return formatex(out, len, "a%s", authid);
}

load_prefs(id)
{
	if (g_vault == INVALID_HANDLE)
		return;
	new key[48], value[16], stamp;
	player_key(id, key, charsmax(key));
	if (!nvault_lookup(g_vault, key, value, charsmax(value), stamp))
		return;
	// "<lang><source><sound><info>", e.g. "r310": Russian chosen by /rus, sounds on, info off.
	if ((value[0] == 'r' || value[0] == 'e') && '1' <= value[1] <= '3')
	{
		g_lang[id] = value[0] == 'e' ? CZM_EN : CZM_RU;
		g_langSource[id] = value[1] - '0';
	}
	g_soundOn[id] = value[2] != '0';
	g_infoOn[id] = value[3] != '0';
}

save_prefs(id)
{
	if (g_vault == INVALID_HANDLE)
		return;
	new key[48], value[8];
	player_key(id, key, charsmax(key));
	formatex(value, charsmax(value), "%c%d%d%d", g_lang[id] == CZM_EN ? 'e' : 'r', g_langSource[id],
		g_soundOn[id] ? 1 : 0, g_infoOn[id] ? 1 : 0);
	nvault_set(g_vault, key, value);
}

// ---------------------------------------------------------------- ticket

load_ticket_key()
{
	new path[128];
	get_configsdir(path, charsmax(path));
	add(path, charsmax(path), "/czm_ticket.key");
	new fh = fopen(path, "rt");
	if (!fh)
	{
		log_amx("czm_ticket.key is missing: every player is a guest");
		return;
	}
	fgets(fh, g_ticketKey, charsmax(g_ticketKey));
	fclose(fh);
	trim(g_ticketKey);
	if (strlen(g_ticketKey) < 32)
	{
		g_ticketKey[0] = 0;
		log_amx("czm_ticket.key is too short: every player is a guest");
	}
}

check_ticket(id)
{
	if (!g_ticketKey[0])
		return 0;
	new ticket[96], address[64];
	get_user_info(id, "_czm", ticket, charsmax(ticket));
	get_pcvar_string(g_cvarAddress, address, charsmax(address));
	if (!ticket[0] || !address[0])
		return 0;

	new part[3][48], count, start, len = strlen(ticket);
	for (new i = 0; i <= len && count < 3; i++)
	{
		if (ticket[i] == '.' || ticket[i] == 0)
		{
			copy(part[count], min(i - start, charsmax(part[])), ticket[start]);
			count++;
			start = i + 1;
		}
	}
	if (count != 3 || start <= len || !is_str_num(part[0]) || !is_str_num(part[1]) || strlen(part[2]) != 32)
		return 0;

	new profile = str_to_num(part[0]), expires = str_to_num(part[1]), now = get_systime();
	if (profile <= 0 || expires < now - TICKET_SKEW || expires > now + 3600)
		return 0;

	new message[256], digest[65];
	formatex(message, charsmax(message), "%s|v1|%d|%d|%s|%s", g_ticketKey, profile, expires, address, g_ticketKey);
	hash_string(message, Hash_Sha256, digest, charsmax(digest));
	digest[32] = 0;
	strtolower(part[2]);
	return equal(digest, part[2]) ? profile : 0;
}

// ---------------------------------------------------------------- commands

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
		copy(cmd, charsmax(cmd), text[1]);
		if (equali(cmd, "rus") || equali(cmd, "ru"))
			return cmd_rus(id);
		if (equali(cmd, "eng") || equali(cmd, "en"))
			return cmd_eng(id);
		if (equali(cmd, "sound_on"))
			return cmd_sound_on(id);
		if (equali(cmd, "sound_off"))
			return cmd_sound_off(id);
		if (equali(cmd, "info_on"))
			return cmd_info_on(id);
		if (equali(cmd, "info_off"))
			return cmd_info_off(id);
		return PLUGIN_CONTINUE;
	}

	// Kontra picked the language from what a player writes; the game tells it more reliably,
	// so the guess only matters for players whose client does not.
	if (g_langSource[id] <= LANG_CHAT)
	{
		new cyr, lat;
		count_letters(text, cyr, lat);
		if (cyr)
			set_lang(id, CZM_RU, LANG_CHAT);
		else if (lat >= 3)
			set_lang(id, CZM_EN, LANG_CHAT);
	}
	return PLUGIN_CONTINUE;
}

count_letters(const text[], &cyr, &lat)
{
	cyr = 0;
	lat = 0;
	for (new i = 0; text[i]; i++)
	{
		new c = text[i] & 0xFF;
		if ((c == 0xD0 || c == 0xD1) && text[i + 1])
		{
			// UTF-8 Cyrillic: А-я and Ё/ё start with 0xD0 or 0xD1.
			cyr++;
			i++;
		}
		else if (('a' <= c <= 'z') || ('A' <= c <= 'Z'))
			lat++;
	}
}

public cmd_rus(id)
{
	set_lang(id, CZM_RU, LANG_CHOSEN);
	save_prefs(id);
	return PLUGIN_HANDLED;
}

public cmd_eng(id)
{
	set_lang(id, CZM_EN, LANG_CHOSEN);
	save_prefs(id);
	return PLUGIN_HANDLED;
}

public cmd_sound_on(id)
{
	g_soundOn[id] = true;
	save_prefs(id);
	client_print_color(id, print_team_default, g_lang[id] == CZM_EN ? "^4[CZM]^1 Server sounds and music are ^4on^1." : "^4[CZM]^1 Звуки и музыка сервера ^4включены^1.");
	return PLUGIN_HANDLED;
}

public cmd_sound_off(id)
{
	g_soundOn[id] = false;
	save_prefs(id);
	client_cmd(id, "mp3 stop");
	g_musicUntil[id] = 0.0;
	client_print_color(id, print_team_default, g_lang[id] == CZM_EN ? "^4[CZM]^1 Server sounds and music are ^3off^1. Turn on: ^4/sound_on" : "^4[CZM]^1 Звуки и музыка сервера ^3выключены^1. Включить: ^4/sound_on");
	return PLUGIN_HANDLED;
}

public cmd_info_on(id)
{
	set_info(id, true);
	return PLUGIN_HANDLED;
}

public cmd_info_off(id)
{
	set_info(id, false);
	return PLUGIN_HANDLED;
}

set_info(id, bool:on)
{
	g_infoOn[id] = on;
	save_prefs(id);
	new ret;
	ExecuteForward(g_fwInfo, ret, id, on);
}

// ---------------------------------------------------------------- natives

public native_lang(plugin, params)
{
	new id = get_param(1);
	return 1 <= id <= MaxClients ? g_lang[id] : default_lang();
}

public native_set_lang(plugin, params)
{
	new id = get_param(1);
	if (1 <= id <= MaxClients)
	{
		set_lang(id, get_param(2) == CZM_EN ? CZM_EN : CZM_RU, LANG_CHOSEN);
		save_prefs(id);
	}
}

public bool:native_sound_on(plugin, params)
{
	new id = get_param(1);
	return 1 <= id <= MaxClients && g_soundOn[id];
}

public bool:native_info_on(plugin, params)
{
	new id = get_param(1);
	return 1 <= id <= MaxClients && g_infoOn[id];
}

public native_profile(plugin, params)
{
	new id = get_param(1);
	return 1 <= id <= MaxClients ? g_profile[id] : 0;
}

public native_player_key(plugin, params)
{
	new id = get_param(1), key[48];
	if (!(1 <= id <= MaxClients))
		return 0;
	player_key(id, key, charsmax(key));
	return set_string(2, key, get_param(3));
}
