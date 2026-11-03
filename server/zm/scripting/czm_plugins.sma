// Counter Zombie Mobile, Survival server: our plugins on and off one by one, for testing.
//
// Server console (the console in the owner panel):
//   czm_plugins                  the list: on or off, running or not, what each one needs
//   czm_plugin_off <name|all>    off from the next map
//   czm_plugin_on <name|all>     on from the next map
// The choice is kept in configs/plugins-czm.ini as ";off <name>.amxx"; a deploy keeps it.
// This plugin needs none of the others, so it works while they are all off.
#include <amxmodx>
#include <amxmisc>

#define MAX_LINES 64
#define LINE_LEN 128

// in the order of plugins-czm.ini
new const NAMES[][] = {"czm_core", "czm_sounds", "czm_revive", "czm_ammo", "czm_info", "czm_admin", "czm_game",
	"czm_lvl", "czm_lvl_fx"};
// what each one needs on: without them it does not load
new const NEEDS[][] = {"", "czm_core", "czm_core", "czm_core", "czm_core", "czm_core", "czm_core czm_admin",
	"czm_core czm_admin", "czm_core czm_lvl"};
new const ABOUT[][] = {
	"профиль CZM, язык, /sound /info",
	"музыка и звуки Kontra",
	"автовозрождение зомби",
	"патроны",
	"подсказки на экране",
	"админ-меню, баны, муты, привилегии",
	"меню сервера, голосования, телепорт, сообщения админам",
	"LVL MOD: уровни, токены, магазин, пропуск",
	"ящик с оружием, крит-пули, звуки оружия, аирдроп"
};

new g_ini[160];
new g_lines[MAX_LINES][LINE_LEN];
new g_count;

public plugin_init()
{
	register_plugin("CZM plugins", "1.0", "Counter Zombie Mobile");
	register_srvcmd("czm_plugins", "cmd_list");
	register_srvcmd("czm_plugin_on", "cmd_on");
	register_srvcmd("czm_plugin_off", "cmd_off");
	get_configsdir(g_ini, charsmax(g_ini));
	add(g_ini, charsmax(g_ini), "/plugins-czm.ini");
}

bool:load_ini()
{
	g_count = 0;
	new fp = fopen(g_ini, "rt");
	if (!fp)
	{
		server_print("[CZM] нет файла %s", g_ini);
		return false;
	}
	while (g_count < MAX_LINES && !feof(fp))
	{
		if (!fgets(fp, g_lines[g_count], LINE_LEN - 1))
			break;
		trim(g_lines[g_count]);
		g_count++;
	}
	fclose(fp);
	return true;
}

bool:save_ini()
{
	new fp = fopen(g_ini, "wt");
	if (!fp)
	{
		server_print("[CZM] не удалось записать %s", g_ini);
		return false;
	}
	for (new i = 0; i < g_count; i++)
	{
		fputs(fp, g_lines[i]);
		fputs(fp, "^n");
	}
	fclose(fp);
	return true;
}

// the line of the plugin in the file: "name.amxx [debug]" is on, ";off name.amxx" is off
find_line(const name[], &bool:on)
{
	new file[48];
	formatex(file, charsmax(file), "%s.amxx", name);
	new len = strlen(file);
	for (new i = 0; i < g_count; i++)
	{
		new at = equal(g_lines[i], ";off ", 5) ? 5 : 0;
		if (equali(g_lines[i][at], file, len) && (g_lines[i][at + len] == EOS || g_lines[i][at + len] == ' '))
		{
			on = at == 0;
			return i;
		}
	}
	return -1;
}

bool:is_on(const name[])
{
	new bool:on;
	return find_line(name, on) >= 0 && on;
}

name_index(const arg[])
{
	new name[48];
	copy(name, charsmax(name), arg);
	new dot = contain(name, ".amxx");
	if (dot >= 0)
		name[dot] = EOS;
	for (new i = 0; i < sizeof NAMES; i++)
		if (equali(name, NAMES[i]))
			return i;
	return -1;
}

running(const name[], status[], len)
{
	new file[48];
	formatex(file, charsmax(file), "%s.amxx", name);
	new id = find_plugin_byfile(file);
	if (id == INVALID_PLUGIN_ID)
	{
		copy(status, len, "не загружен");
		return;
	}
	new f[2], n[2], v[2], a[2], st[32];
	get_plugin(id, f, 1, n, 1, v, 1, a, 1, st, charsmax(st));
	copy(status, len, (equal(st, "running") || equal(st, "debug")) ? "работает" : st);
}

public cmd_list()
{
	if (!load_ini())
		return PLUGIN_HANDLED;
	server_print("[CZM] Наши плагины (изменения работают со следующей карты):");
	for (new i = 0; i < sizeof NAMES; i++)
	{
		new status[32];
		running(NAMES[i], status, charsmax(status));
		server_print("  %-11s %-5s сейчас: %-11s %s%s%s", NAMES[i], is_on(NAMES[i]) ? "ВКЛ" : "выкл", status, ABOUT[i],
			NEEDS[i][0] ? ". Нужен: " : "", NEEDS[i]);
	}
	server_print("[CZM] czm_plugin_off <имя|all>, czm_plugin_on <имя|all>; сразу применить: changelevel <карта>");
	return PLUGIN_HANDLED;
}

set_plugin(index, bool:on)
{
	new bool:now, line = find_line(NAMES[index], now);
	if (line < 0)
	{
		if (!on || g_count >= MAX_LINES)
			return;
		formatex(g_lines[g_count++], LINE_LEN - 1, "%s.amxx", NAMES[index]);
		return;
	}
	if (now == on)
		return;
	new text[LINE_LEN];
	if (on)
		copy(text, charsmax(text), g_lines[line][5]);
	else
		formatex(text, charsmax(text), ";off %s", g_lines[line]);
	copy(g_lines[line], LINE_LEN - 1, text);
}

change(bool:on)
{
	new arg[48];
	read_argv(1, arg, charsmax(arg));
	trim(arg);
	if (!arg[0])
	{
		server_print("[CZM] укажи плагин или all, список: czm_plugins");
		return;
	}
	if (!load_ini())
		return;
	if (equali(arg, "all"))
	{
		for (new i = 0; i < sizeof NAMES; i++)
			set_plugin(i, on);
	}
	else
	{
		new index = name_index(arg);
		if (index < 0)
		{
			server_print("[CZM] нет такого плагина: %s (список: czm_plugins)", arg);
			return;
		}
		set_plugin(index, on);
	}
	if (!save_ini())
		return;
	server_print("[CZM] %s %s со следующей карты", arg, on ? "включится" : "выключится");
	// what would not load
	for (new i = 0; i < sizeof NAMES; i++)
	{
		if (!is_on(NAMES[i]) || !NEEDS[i][0])
			continue;
		new need[2][24];
		parse(NEEDS[i], need[0], charsmax(need[]), need[1], charsmax(need[]));
		for (new k = 0; k < 2; k++)
			if (need[k][0] && !is_on(need[k]))
				server_print("[CZM] внимание: %s не загрузится без %s (czm_plugin_on %s)", NAMES[i], need[k], need[k]);
	}
}

public cmd_on()
{
	change(true);
	return PLUGIN_HANDLED;
}

public cmd_off()
{
	change(false);
	return PLUGIN_HANDLED;
}
