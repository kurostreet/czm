/*
	Counter Zombie Mobile, Survival server: the sounds of the Kontra server.

	SoundWelcome      the welcome track and a greeting in chat, only to the player who joined
	RoundRandomSongs  a random song every 60..220 s while a round is on
	EndGameMusic      a random track when a round ends
	Music_AutoPlay    s_autoplay every 5 minutes
	SoundChangeMap    a sound when the map vote begins
	Sound_weather     weather sounds every 6..8 minutes, never the same twice in a row
	SoundZombieAtack  infection and death sounds (zombies: the Zombie Plague sound list in
	                  zombieplague.ini points at Kontra's files; humans: here)
	                  and the announcement when the infection begins, in the player's language
	ZOMBIE_BULLET_PAIN a zombie voices its pain with a 30% chance, one line at a time
	heartbeat_T_CT    a heartbeat and a soft red pulse at low health

	/sound_off (czm_core) silences all of it for that player. A track that is still playing is
	never cut by the next one, except the end-of-round music, which always starts.
*/
#include <amxmodx>
#include <fakemeta>
#include <hamsandwich>
#include <zombieplague>
#include <czm_survival>

#define PLUGIN "CZM Sounds"
#define VERSION "1.0"
#define AUTHOR "kurostreet"

#define TASK_WELCOME 4100
#define TASK_SONG 4200
#define TASK_BEAT2 4300

new const WELCOME[] = "welcome_s.mp3";
new const AUTOPLAY[] = "s_autoplay.mp3";
new const MAP_VOTE[] = "s_change_map.mp3";
new const SONGS[][] = { "z_song1.mp3", "z_song2.mp3", "z_song3.mp3", "z_song4.mp3", "z_song5.mp3" };
new const END_MUSIC[][] = {
	"end_sound1.mp3", "end_sound2.mp3", "end_sound3.mp3", "end_sound4.mp3", "end_sound5.mp3", "end_sound6.mp3",
	"end_sound7.mp3", "end_sound8.mp3", "end_sound9.mp3", "end_sound10.mp3", "end_sound11.mp3", "end_sound12.mp3"
};
new const WEATHER[][] = { "weather1.wav", "weather2.wav", "weather3.wav", "weather4.wav", "weather5.wav", "weather6.wav" };
new const INFECTION_RU[] = "inf_rus.mp3";
new const INFECTION_EN[] = "inf_eng.mp3";
new const HUMAN_DIE[] = "csct_death.wav";
new const PAIN[][] = { "z_1.mp3", "z_2.mp3", "z_3.mp3", "z_4.mp3", "z_5.mp3", "z_6.mp3", "z_7.mp3" };
new const PULSE1[] = "pulse1.mp3";
new const PULSE2[] = "pulse2.mp3";

new g_hWelcome, g_hAutoplay, g_hMapVote, g_hPulse1, g_hPulse2, g_hHumanDie;
new g_hSongs[sizeof SONGS], g_hEnd[sizeof END_MUSIC], g_hWeather[sizeof WEATHER];
new g_hPain[sizeof PAIN], g_hInfectionRu, g_hInfectionEn;

new bool:g_roundOn;
new g_lastWeather = -1;
new Float:g_nextWeather;
new bool:g_mapVotePlayed;

new Float:g_painUntil[MAX_PLAYERS + 1];
new g_beatState[MAX_PLAYERS + 1];
new Float:g_nextBeat[MAX_PLAYERS + 1];
new g_msgScreenFade;

new g_cvarSongMin, g_cvarSongMax, g_cvarPainChance, g_cvarBeat1, g_cvarBeat2;

public plugin_precache()
{
	g_hWelcome = czm_sound_precache(WELCOME);
	g_hAutoplay = czm_sound_precache(AUTOPLAY);
	g_hMapVote = czm_sound_precache(MAP_VOTE);
	g_hPulse1 = czm_sound_precache(PULSE1);
	g_hPulse2 = czm_sound_precache(PULSE2);
	g_hHumanDie = czm_sound_precache(HUMAN_DIE);
	for (new i = 0; i < sizeof SONGS; i++) g_hSongs[i] = czm_sound_precache(SONGS[i]);
	for (new i = 0; i < sizeof END_MUSIC; i++) g_hEnd[i] = czm_sound_precache(END_MUSIC[i]);
	for (new i = 0; i < sizeof WEATHER; i++) g_hWeather[i] = czm_sound_precache(WEATHER[i]);
	g_hInfectionRu = czm_sound_precache(INFECTION_RU);
	g_hInfectionEn = czm_sound_precache(INFECTION_EN);
	for (new i = 0; i < sizeof PAIN; i++) g_hPain[i] = czm_sound_precache(PAIN[i]);
}

public plugin_init()
{
	register_plugin(PLUGIN, VERSION, AUTHOR);

	g_cvarSongMin = create_cvar("czm_song_min", "60");
	g_cvarSongMax = create_cvar("czm_song_max", "220");
	g_cvarPainChance = create_cvar("czm_pain_chance", "30");
	g_cvarBeat1 = create_cvar("czm_heartbeat_hp1", "50", _, "Heartbeat starts at this share of health, %");
	g_cvarBeat2 = create_cvar("czm_heartbeat_hp2", "30", _, "Stronger heartbeat at this share of health, %");

	register_logevent("ev_round_start", 2, "1=Round_Start");
	register_logevent("ev_round_end", 2, "1=Round_End");
	RegisterHam(Ham_Killed, "player", "fw_killed_post", 1);
	RegisterHam(Ham_TakeDamage, "player", "fw_damage_post", 1);

	g_msgScreenFade = get_user_msgid("ScreenFade");

	set_task(300.0, "task_autoplay", _, _, _, "b");
	set_task(0.2, "task_tick", _, _, _, "b");
	g_nextWeather = get_gametime() + random_float(360.0, 480.0);
}

// ---------------------------------------------------------------- welcome

public czm_player_ready(id, profile)
{
	remove_task(TASK_WELCOME + id);
	set_task(1.8, "task_welcome", TASK_WELCOME + id);
}

public task_welcome(taskid)
{
	new id = taskid - TASK_WELCOME;
	if (!is_user_connected(id))
		return;
	czm_play_music(id, g_hWelcome, true);
	new name[32];
	get_user_name(id, name, charsmax(name));
	czm_chat(id, "^4———————————————", "^4———————————————");
	czm_chat(id, "^4• ^1Добро пожаловать, ^4%s^1!", "^4• ^1Welcome, ^4%s^1!", name);
	czm_chat(id, "^4• ^1Панель игрока: ^4%s ^1— вход по почте или нику CZM", "^4• ^1Player panel: ^4%s ^1— sign in with your CZM email or nick", CZM_SITE);
	czm_chat(id, "^4• ^1Без музыки: ^4/sound_off^1, язык: ^4/rus /eng", "^4• ^1No music: ^4/sound_off^1, language: ^4/rus /eng");
}

public client_disconnected(id)
{
	remove_task(TASK_WELCOME + id);
	remove_task(TASK_BEAT2 + id);
	g_painUntil[id] = 0.0;
	g_beatState[id] = 0;
}

// ---------------------------------------------------------------- music

public ev_round_start()
{
	g_roundOn = true;
	schedule_song();
}

public ev_round_end()
{
	g_roundOn = false;
	remove_task(TASK_SONG);
	czm_play_music(0, g_hEnd[random(sizeof g_hEnd)], true);
	for (new id = 1; id <= MaxClients; id++)
		stop_beat(id);
}

schedule_song()
{
	remove_task(TASK_SONG);
	new lo = get_pcvar_num(g_cvarSongMin), hi = get_pcvar_num(g_cvarSongMax);
	set_task(float(random_num(lo, max(lo, hi))), "task_song", TASK_SONG);
}

public task_song()
{
	if (!g_roundOn)
		return;
	czm_play_music(0, g_hSongs[random(sizeof g_hSongs)]);
	schedule_song();
}

public task_autoplay()
{
	czm_play_music(0, g_hAutoplay);
}

// ---------------------------------------------------------------- weather, map vote, heartbeat

public task_tick()
{
	new Float:now = get_gametime();

	if (g_roundOn && now >= g_nextWeather)
	{
		new pick = random(sizeof g_hWeather);
		if (pick == g_lastWeather)
			pick = (pick + 1) % sizeof g_hWeather;
		g_lastWeather = pick;
		czm_play_sound(0, g_hWeather[pick]);
		g_nextWeather = now + random_float(360.0, 480.0);
	}

	if (!g_mapVotePlayed && get_cvar_float("mp_timelimit") > 0.0)
	{
		// the stock map chooser starts its vote with a little over two minutes left
		new left = get_timeleft();
		if (0 < left <= 130)
		{
			g_mapVotePlayed = true;
			czm_play_music(0, g_hMapVote, true);
		}
	}

	new p1 = get_pcvar_num(g_cvarBeat1), p2 = get_pcvar_num(g_cvarBeat2);
	for (new id = 1; id <= MaxClients; id++)
	{
		if (!g_roundOn || !is_user_alive(id) || is_user_bot(id))
		{
			stop_beat(id);
			continue;
		}
		new Float:health = float(get_user_health(id));
		new Float:full = zp_get_user_zombie(id) ? float(zp_get_zombie_maxhealth(id)) : 100.0;
		new Float:share = full > 0.0 ? health * 100.0 / full : 100.0;
		new level = share <= float(p2) ? 2 : (share <= float(p1) ? 1 : 0);
		if (level != g_beatState[id])
		{
			g_beatState[id] = level;
			g_nextBeat[id] = now;
		}
		if (!level || now < g_nextBeat[id])
			continue;
		beat(id, level);
		g_nextBeat[id] = now + (level == 2 ? 1.55 : 0.80) + 0.05;
	}
}

beat(id, level)
{
	czm_play_sound(id, level == 2 ? g_hPulse2 : g_hPulse1);
	fade(id, level == 2 ? 54 : 32, level == 2 ? 0.28 : 0.22);
	// the second, weaker stroke of a heartbeat
	new data[2];
	data[0] = level;
	remove_task(TASK_BEAT2 + id);
	set_task(0.18, "task_beat2", TASK_BEAT2 + id, data, sizeof data);
}

public task_beat2(const data[], taskid)
{
	new id = taskid - TASK_BEAT2;
	if (is_user_alive(id) && g_beatState[id])
		fade(id, floatround((data[0] == 2 ? 54 : 32) * 0.55), data[0] == 2 ? 0.28 : 0.22);
}

stop_beat(id)
{
	g_beatState[id] = 0;
	remove_task(TASK_BEAT2 + id);
}

fade(id, alpha, Float:seconds)
{
	if (!is_user_connected(id))
		return;
	message_begin(MSG_ONE_UNRELIABLE, g_msgScreenFade, _, id);
	write_short(floatround(seconds * 4096.0)); // duration
	write_short(0);                            // hold
	write_short(0x0000);                       // FFADE_IN: from the colour back to clear
	write_byte(200);
	write_byte(0);
	write_byte(0);
	write_byte(alpha);
	message_end();
}

// ---------------------------------------------------------------- zombies

public zp_round_started(gamemode, id)
{
	for (new i = 1; i <= MaxClients; i++)
		if (is_user_connected(i))
			czm_play_sound(i, czm_lang(i) == CZM_EN ? g_hInfectionEn : g_hInfectionRu);
}

public fw_killed_post(victim, attacker, shouldgib)
{
	stop_beat(victim);
	g_painUntil[victim] = 0.0;
	if (!zp_get_user_zombie(victim))
		czm_emit_sound(victim, g_hHumanDie, CHAN_VOICE);
}

public fw_damage_post(victim, inflictor, attacker, Float:damage, damagebits)
{
	if (damage <= 0.0 || !is_user_alive(victim) || !zp_get_user_zombie(victim))
		return;
	if (!czm_sound_on(victim) || random_num(1, 100) > get_pcvar_num(g_cvarPainChance))
		return;
	new Float:now = get_gametime();
	if (now < g_painUntil[victim])
		return;
	new handle = g_hPain[random(sizeof g_hPain)];
	// the static channel is not cut by the short hit sounds the game plays on every bullet
	if (czm_emit_sound(victim, handle, CHAN_STATIC))
		g_painUntil[victim] = now + czm_sound_length(handle);
}
