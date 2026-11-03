/*
	Counter Zombie Mobile, Survival server: ADS_HUD of the Kontra server.

	Three short lines at the left of the screen remind of the site and the commands. The game
	menus (menu, /lvl) join them when the LVL MOD part arrives.
	/info_off hides them for that player, /info_on brings them back (czm_core keeps the choice).
*/
#include <amxmodx>
#include <czm_survival>

#define PLUGIN "CZM Info"
#define VERSION "1.0"
#define AUTHOR "kurostreet"

new g_hud;

public plugin_init()
{
	register_plugin(PLUGIN, VERSION, AUTHOR);
	g_hud = CreateHudSyncObj();
	set_task(10.0, "task_show", _, _, _, "b");
}

public task_show()
{
	for (new id = 1; id <= MaxClients; id++)
		show(id);
}

show(id)
{
	if (!is_user_connected(id) || is_user_bot(id) || !czm_info_on(id))
		return;
	set_hudmessage(0, 200, 80, 0.01, 0.22, 0, 0.0, 10.5, 0.0, 0.3, -1);
	if (czm_lang(id) == CZM_EN)
		ShowSyncHudMsg(id, g_hud, "Player panel: %s^nNo music: /sound_off^nLanguage: /rus /eng", CZM_SITE);
	else
		ShowSyncHudMsg(id, g_hud, "Панель игрока: %s^nБез музыки: /sound_off^nЯзык: /rus /eng", CZM_SITE);
}

public czm_info_changed(id, bool:on)
{
	if (on)
		show(id);
	else
		ClearSyncHud(id, g_hud);
}

public task_show_one(id)
{
	show(id);
}

public czm_player_ready(id, profile)
{
	set_task(3.0, "task_show_one", id);
}
