// Counter Zombie Mobile, Survival server: what czm_core.amxx gives the other plugins.
#if defined _czm_survival_included
	#endinput
#endif
#define _czm_survival_included

#define CZM_SITE "counter-zombie.ru"

enum
{
	CZM_RU = 0,
	CZM_EN
}

enum
{
	CZM_SND_MISSING = 0,
	CZM_SND_EFFECT,
	CZM_SND_MUSIC
}

// czm_core itself takes only the constants above.
#if defined CZM_CORE_PLUGIN
	#endinput
#endif

#pragma reqlib czm_core

// The player's language: CZM_RU or CZM_EN.
native czm_lang(id);
native czm_set_lang(id, lang);

// Whether the player keeps our sounds and music on (/sound_on, /sound_off).
native bool:czm_sound_on(id);

// Whether the player keeps the info lines on the screen (/info_on, /info_off).
native bool:czm_info_on(id);

// The CZM profile of the player, proven by the ticket the game sends; 0 when there is none.
native czm_profile(id);

// A stable key for the player's saved data: "p<profile>" for a CZM player, "a<authid>" otherwise.
native czm_player_key(id, out[], len);

// Sounds by their Kontra name ("end_sound1.mp3"). Call czm_sound_precache() in plugin_precache;
// it returns a handle (or -1 when the file is not on the server) that the play natives take.
native czm_sound_precache(const name[]);
native czm_sound_kind(handle);
native Float:czm_sound_length(handle);
native czm_sound_path(handle, out[], len);

// Plays an effect only to this player (or to everyone with id 0), if their sounds are on.
native czm_play_sound(id, handle);

// Plays a track on the music channel. Without force a track that is still playing is left alone.
// Returns how many players got it.
native czm_play_music(id, handle, bool:force = false);
native czm_stop_music(id);

// Plays an effect from an entity, heard by players around it.
native czm_emit_sound(entity, handle, channel = 2, Float:volume = 1.0);

// Called when a player changes language (manually, from the game or by chat).
forward czm_lang_changed(id, lang);

// Called when a player turns the info lines on or off.
forward czm_info_changed(id, bool:on);

// Called once the player's profile is known (after the ticket check), profile is 0 for guests.
forward czm_player_ready(id, profile);

// Chat in the player's language. id 0 sends each player their own language.
// Colors as in client_print_color: ^1 normal, ^3 team, ^4 green.
stock czm_chat(id, const ru[], const en[], any:...)
{
	static text[192];
	if (id)
	{
		vformat(text, charsmax(text), czm_lang(id) == CZM_EN ? en : ru, 4);
		client_print_color(id, print_team_default, "%s", text);
		return;
	}
	for (new i = 1; i <= MaxClients; i++)
	{
		if (!is_user_connected(i) || is_user_bot(i))
			continue;
		vformat(text, charsmax(text), czm_lang(i) == CZM_EN ? en : ru, 4);
		client_print_color(i, print_team_default, "%s", text);
	}
}

stock czm_text(id, out[], len, const ru[], const en[])
{
	return copy(out, len, czm_lang(id) == CZM_EN ? en : ru);
}
