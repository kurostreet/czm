/*
	Counter Zombie Mobile, Survival server: the server menu.

	Plugins register sections (the tabs) and items (the cards) through czm_menu.inc. The CZM game
	gets the menu with everything it needs to draw the window (tabs, icons, colours, subtitles,
	badges) in the menu text itself; other games get a plain text menu built from the same items.

	The text for the game ("czm_menu_ui" 1 in the game):
		#czm1<TAB>menu<TAB>section<TAB>head<TAB>sub<TAB>chip<TAB>foot
		#tabs<TAB>key:name:icon:badge<TAB>...
		(empty line)
		\r1.\w name<TAB>sub<TAB>icon<TAB>RRGGBB<TAB>badge
		...
		\r0.\w Exit
	An old-style menu: newmenus cut every line at 255 bytes.
*/
#include <amxmodx>
#include <czm_survival>
#define CZM_MENU_PLUGIN
#include <czm_menu>

// open() owns a 4096-cell wire buffer and calls rich_head() plus plugin forwards.
// AMXX's default 4096-cell stack cannot even hold that one buffer: the collision
// overwrites the registry/string data and makes later cvar callbacks invalid.
#pragma dynamic 16384

#define PLUGIN  "CZM Menu"
#define VERSION "1.0"
#define AUTHOR  "Counter Zombie Mobile"

#define MAX_SECTIONS 32
#define MAX_ITEMS    192
#define MENU_ID      "CZM Menu"

// czm_admin.amxx tells who is staff; without it nobody is
native czm_staff(id);
native czm_privilege(id);

enum _:Section
{
	SecKey[16],
	SecRu[40],
	SecEn[40],
	SecIcon[16],
	SecParent[16],
	SecPlugin,
	SecOrder,
	SecAccess
}

enum _:Item
{
	ItSection[16],
	ItKey[24],
	ItRu[40],
	ItEn[40],
	ItSubRu[48],
	ItSubEn[48],
	ItIcon[16],
	ItColor[8],
	ItOpen[16],   // "#section" handlers
	ItPlugin,
	ItFunc,
	ItOrder,
	ItAccess
}

new g_sections[MAX_SECTIONS][Section], g_numSections;
new g_items[MAX_ITEMS][Item], g_numItems;

// what the player has on the screen
new bool:g_rich[MAX_PLAYERS + 1];
new g_shown[MAX_PLAYERS + 1];          // section, -1 none
new g_page[MAX_PLAYERS + 1];
new g_slot[MAX_PLAYERS + 1][10];       // item at the slot, or SLOT_*
#define SLOT_NONE -1
#define SLOT_NEXT -2
#define SLOT_BACK -3
#define SLOT_MAIN -4

// this display: what plugins changed in czm_menu_build
new g_building;
new g_stName[MAX_ITEMS][40], g_stSub[MAX_ITEMS][48], g_stBadge[MAX_ITEMS][16], bool:g_stHide[MAX_ITEMS], bool:g_stOff[MAX_ITEMS];
new g_tabBadge[MAX_SECTIONS][8];

new g_fwBuild, g_menuId;
new g_cvarMotto;

public plugin_natives()
{
	register_library("czm_menu");
	register_native("czm_menu_section", "native_section");
	register_native("czm_menu_item", "native_item");
	register_native("czm_menu_open", "native_open");
	register_native("czm_menu_state", "native_state");
	register_native("czm_menu_rich", "native_rich");
	set_native_filter("native_filter");
}

// czm_staff and czm_privilege are optional: the menu works while czm_admin is off
public native_filter(const name[], index, trap)
{
	if (!trap && (equal(name, "czm_staff") || equal(name, "czm_privilege")))
		return PLUGIN_HANDLED;
	return PLUGIN_CONTINUE;
}

public plugin_init()
{
	register_plugin(PLUGIN, VERSION, AUTHOR);
	g_fwBuild = CreateMultiForward("czm_menu_build", ET_IGNORE, FP_CELL, FP_STRING);
	g_menuId = register_menuid(MENU_ID);
	register_menucmd(g_menuId, 1023, "on_key");
	register_clcmd("czm_menu_tab", "cmd_tab");
	// the words under the cards, "ru | en"
	g_cvarMotto = create_cvar("czm_menu_motto", "Честная игра • Чистый сервер • Приятное общение | Fair play • Clean server • Friendly chat");
}

public client_connect(id)
{
	g_rich[id] = false;
	g_shown[id] = -1;
}

public client_putinserver(id)
{
	if (!is_user_bot(id) && !is_user_hltv(id))
		query_client_cvar(id, "czm_menu_ui", "on_menu_ui");
}

public on_menu_ui(id, const cvar[], const value[])
{
	if (is_user_connected(id))
		g_rich[id] = str_to_num(value) >= 1;
}

// ---------------------------------------------------------------- registry

find_section(const key[])
{
	for (new i = 0; i < g_numSections; i++)
		if (equali(g_sections[i][SecKey], key))
			return i;
	return -1;
}

find_item(const key[])
{
	for (new i = 0; i < g_numItems; i++)
		if (equali(g_items[i][ItKey], key))
			return i;
	return -1;
}

// tabs, newlines and the separators of the tab line never get into a field
clean(text[])
{
	for (new i = 0; text[i]; i++)
		if (text[i] == '^t' || text[i] == '^n' || text[i] == '|')
			text[i] = ' ';
}

public native_section(plugin, params)
{
	new key[32], parent[32];
	get_string(1, key, charsmax(key));
	if (params >= 7)
		get_string(7, parent, charsmax(parent));
	if (!valid_key(key) || (parent[0] && (!valid_key(parent) || equali(key, parent))))
		return 0;
	new s = find_section(key);
	if (s >= 0 && g_sections[s][SecPlugin] != plugin)
		return 0;
	if (s < 0)
	{
		if (g_numSections >= MAX_SECTIONS)
			return 0;
		s = g_numSections++;
	}
	copy(g_sections[s][SecKey], charsmax(g_sections[][SecKey]), key);
	copy(g_sections[s][SecParent], charsmax(g_sections[][SecParent]), parent);
	g_sections[s][SecPlugin] = plugin;
	get_string(2, g_sections[s][SecRu], charsmax(g_sections[][SecRu]));
	get_string(3, g_sections[s][SecEn], charsmax(g_sections[][SecEn]));
	get_string(4, g_sections[s][SecIcon], charsmax(g_sections[][SecIcon]));
	g_sections[s][SecOrder] = get_param(5);
	g_sections[s][SecAccess] = get_param(6);
	clean(g_sections[s][SecRu]);
	clean(g_sections[s][SecEn]);
	// ":" separates the fields of a tab
	replace_all(g_sections[s][SecRu], charsmax(g_sections[][SecRu]), ":", " ");
	replace_all(g_sections[s][SecEn], charsmax(g_sections[][SecEn]), ":", " ");
	return 1;
}

public native_item(plugin, params)
{
	new key[24];
	get_string(2, key, charsmax(key));
	new i = find_item(key);
	if (i >= 0 && g_items[i][ItPlugin] != plugin)
		return 0;
	if (i < 0)
	{
		if (g_numItems >= MAX_ITEMS)
			return 0;
		i = g_numItems++;
	}
	get_string(1, g_items[i][ItSection], charsmax(g_items[][ItSection]));
	copy(g_items[i][ItKey], charsmax(g_items[][ItKey]), key);
	get_string(3, g_items[i][ItRu], charsmax(g_items[][ItRu]));
	get_string(4, g_items[i][ItEn], charsmax(g_items[][ItEn]));
	get_string(5, g_items[i][ItSubRu], charsmax(g_items[][ItSubRu]));
	get_string(6, g_items[i][ItSubEn], charsmax(g_items[][ItSubEn]));
	get_string(7, g_items[i][ItIcon], charsmax(g_items[][ItIcon]));
	get_string(8, g_items[i][ItColor], charsmax(g_items[][ItColor]));
	new handler[32];
	get_string(9, handler, charsmax(handler));
	g_items[i][ItOpen][0] = EOS;
	g_items[i][ItFunc] = -1;
	g_items[i][ItPlugin] = plugin;
	if (handler[0] == '#')
		copy(g_items[i][ItOpen], charsmax(g_items[][ItOpen]), handler[1]);
	else if (handler[0])
		g_items[i][ItFunc] = get_func_id(handler, plugin);
	g_items[i][ItOrder] = get_param(10);
	g_items[i][ItAccess] = get_param(11);
	clean(g_items[i][ItRu]);
	clean(g_items[i][ItEn]);
	clean(g_items[i][ItSubRu]);
	clean(g_items[i][ItSubEn]);
	return 1;
}

public native_open(plugin, params)
{
	new id = get_param(1), key[16];
	get_string(2, key, charsmax(key));
	if (1 <= id <= MaxClients && is_user_connected(id))
		open(id, key[0] ? key : "main", 0);
	return 1;
}

public native_state(plugin, params)
{
	new id = get_param(1), key[24];
	if (id != g_building)
		return 0;
	get_string(2, key, charsmax(key));
	if (key[0] == '#')
	{
		new s = find_section(key[1]);
		if (s >= 0)
			get_string(5, g_tabBadge[s], charsmax(g_tabBadge[]));
		return s >= 0;
	}
	new i = find_item(key);
	if (i < 0)
		return 0;
	get_string(3, g_stName[i], charsmax(g_stName[]));
	get_string(4, g_stSub[i], charsmax(g_stSub[]));
	get_string(5, g_stBadge[i], charsmax(g_stBadge[]));
	g_stHide[i] = bool:get_param(6);
	g_stOff[i] = bool:get_param(7);
	clean(g_stName[i]);
	clean(g_stSub[i]);
	clean(g_stBadge[i]);
	return 1;
}

public native_rich(plugin, params)
{
	new id = get_param(1);
	return 1 <= id <= MaxClients && g_rich[id];
}

// ---------------------------------------------------------------- who sees what

bool:valid_key(const key[])
{
	new len = strlen(key);
	if (!len || len > 15)
		return false;
	for (new k = 0; k < len; k++)
		if (!(('a' <= key[k] <= 'z') || ('A' <= key[k] <= 'Z') || ('0' <= key[k] <= '9') || key[k] == '_'))
			return false;
	return true;
}

staff_of(id)
{
	return LibraryExists("czm_admin", LibType_Library) ? czm_staff(id) : 0;
}

bool:allowed(id, access)
{
	if (access == CZM_MENU_ALL)
		return true;
	if (access & ~(CZM_MENU_STAFF | CZM_MENU_HEAD | CZM_MENU_PRIV | CZM_MENU_VIP | CZM_MENU_PREMIUM | CZM_MENU_DELUXE | CZM_MENU_TESTER))
		return false;
	new staff = staff_of(id), privilege = LibraryExists("czm_admin", LibType_Library) ? czm_privilege(id) : 0;
	return ((access & CZM_MENU_HEAD) && staff >= 2)
		|| ((access & CZM_MENU_STAFF) && staff >= 1)
		|| ((access & CZM_MENU_PRIV) && (staff >= 1 || privilege > 0))
		|| ((access & CZM_MENU_VIP) && privilege == 1)
		|| ((access & CZM_MENU_PREMIUM) && privilege == 2)
		|| ((access & CZM_MENU_DELUXE) && privilege == 3)
		|| ((access & CZM_MENU_TESTER) && privilege == 4);
}

// Access to a child never bypasses its parent; invalid parents and cycles fail closed.
bool:section_allowed(id, s)
{
	for (new depth = 0; depth < MAX_SECTIONS; depth++)
	{
		if (s < 0 || s >= g_numSections || !allowed(id, g_sections[s][SecAccess]))
			return false;
		if (!g_sections[s][SecParent][0])
			return true;
		s = find_section(g_sections[s][SecParent]);
	}
	return false;
}

section_root(s)
{
	for (new depth = 0; depth < MAX_SECTIONS && s >= 0 && s < g_numSections; depth++)
	{
		if (!g_sections[s][SecParent][0])
			return s;
		s = find_section(g_sections[s][SecParent]);
	}
	return -1;
}

bool:item_allowed(id, i)
{
	if (i < 0 || i >= g_numItems || !allowed(id, g_items[i][ItAccess]))
		return false;
	return !g_items[i][ItOpen][0] || section_allowed(id, find_section(g_items[i][ItOpen]));
}

bool:can_dispatch(id, s, i)
{
	return section_allowed(id, s) && item_allowed(id, i);
}

bool:section_visible(id, s)
{
	if (!section_allowed(id, s))
		return false;
	for (new i = 0; i < g_numItems; i++)
		if (equali(g_items[i][ItSection], g_sections[s][SecKey]) && item_allowed(id, i))
			return true;
	return false;
}

// the sections in their order, the items of one section in theirs
sorted_sections(out[MAX_SECTIONS])
{
	new n;
	for (new s = 0; s < g_numSections; s++)
	{
		new at = n++;
		while (at > 0 && g_sections[out[at - 1]][SecOrder] > g_sections[s][SecOrder])
		{
			out[at] = out[at - 1];
			at--;
		}
		out[at] = s;
	}
	return n;
}

section_items(id, s, out[MAX_ITEMS])
{
	new n;
	for (new i = 0; i < g_numItems; i++)
	{
		if (!equali(g_items[i][ItSection], g_sections[s][SecKey]) || !item_allowed(id, i) || g_stHide[i])
			continue;
		new at = n++;
		while (at > 0 && g_items[out[at - 1]][ItOrder] > g_items[i][ItOrder])
		{
			out[at] = out[at - 1];
			at--;
		}
		out[at] = i;
	}
	return n;
}

// ---------------------------------------------------------------- the menu

open(id, const key[], page)
{
	new s = find_section(key);
	if (s < 0 || !section_visible(id, s))
		s = find_section("main");
	if (s < 0)
		return;

	// what the plugins say about this player now
	for (new i = 0; i < g_numItems; i++)
	{
		g_stName[i][0] = g_stSub[i][0] = g_stBadge[i][0] = EOS;
		g_stHide[i] = g_stOff[i] = false;
	}
	for (new t = 0; t < g_numSections; t++)
		g_tabBadge[t][0] = EOS;
	new ret;
	g_building = id;
	ExecuteForward(g_fwBuild, ret, id, g_sections[s][SecKey]);
	g_building = 0;

	new list[MAX_ITEMS], count = section_items(id, s, list);
	new bool:en = czm_lang(id) == CZM_EN, bool:main = equali(g_sections[s][SecKey], "main") != 0;
	new text[4096], len, keys = (1 << 9);
	if (g_rich[id])
		len = rich_head(id, s, en, text, charsmax(text));
	else
		len = plain_head(s, en, text, charsmax(text));
	// A growing sidebar must not cut the final cards or the exit off the wire message.
	new capacity = g_rich[id] ? clamp((charsmax(text) - len - 128) / 160, 2, 9) : 9;
	new perPage = count > capacity ? capacity - 1 : capacity, pages = max(1, (count + perPage - 1) / perPage);
	page = clamp(page, 0, pages - 1);
	g_shown[id] = s;
	g_page[id] = page;
	for (new k = 0; k < 10; k++)
		g_slot[id][k] = SLOT_NONE;

	new first = page * perPage, slot;
	for (new n = first; n < count && n < first + perPage; n++)
	{
		new i = list[n];
		new bool:off = g_stOff[i] || (g_items[i][ItFunc] < 0 && !g_items[i][ItOpen][0]);
		if (!off)
		{
			g_slot[id][slot] = i;
			keys |= (1 << slot);
		}
		new name[40], sub[48];
		if (g_stName[i][0])
			copy(name, charsmax(name), g_stName[i]);
		else if (en)
			copy(name, charsmax(name), g_items[i][ItEn]);
		else
			copy(name, charsmax(name), g_items[i][ItRu]);
		if (g_stSub[i][0])
			copy(sub, charsmax(sub), g_stSub[i]);
		else if (en)
			copy(sub, charsmax(sub), g_items[i][ItSubEn]);
		else
			copy(sub, charsmax(sub), g_items[i][ItSubRu]);
		if (g_rich[id])
			len += formatex(text[len], charsmax(text) - len, "%s%d.%s %s^t%s^t%s^t%s^t%s^n", off ? "\d" : "\r", slot + 1, off ? "" : "\w",
				name, sub, g_items[i][ItIcon], g_items[i][ItColor], g_stBadge[i]);
		else
		{
			// "!" marks a red badge for the window; the text menu shows the mark in yellow
			new badge[16];
			copy(badge, charsmax(badge), g_stBadge[i][g_stBadge[i][0] == '!' ? 1 : 0]);
			len += formatex(text[len], charsmax(text) - len, "%s%d.%s %s%s%s^n", off ? "\d" : "\r", slot + 1, off ? "" : "\w",
				name, badge[0] ? " \y" : "", badge);
		}
		slot++;
	}

	// the ninth slot: the next page, back to the first, or (text menus) back to the main section
	new extra = SLOT_NONE, label[16];
	if (pages > 1)
	{
		extra = page + 1 < pages ? SLOT_NEXT : SLOT_BACK;
		copy(label, charsmax(label), extra == SLOT_NEXT ? (en ? "More" : "Далее") : (en ? "Back" : "Назад"));
	}
	else if (!main && !g_rich[id])
	{
		extra = SLOT_MAIN;
		copy(label, charsmax(label), en ? "Back" : "Назад");
	}
	if (extra != SLOT_NONE)
	{
		g_slot[id][8] = extra;
		keys |= (1 << 8);
		if (g_rich[id])
			len += formatex(text[len], charsmax(text) - len, "\r9.\w %s^t^tmore^t9BA6B8^t^n", label);
		else
			len += formatex(text[len], charsmax(text) - len, "^n\r9.\w %s^n", label);
	}
	formatex(text[len], charsmax(text) - len, "^n\r0.\w %s", en ? "Exit" : "Выход");
	show_menu(id, keys, text, -1, MENU_ID);
}

rich_head(id, s, bool:en, text[], max)
{
	new mode[24], sub[96], chip[96], motto[160], ru[80], eng[80];
	new root = section_root(s), parent = find_section(g_sections[s][SecParent]);
	get_cvar_string("czm_server_name", mode, charsmax(mode));
	strtoupper(mode);
	formatex(sub, charsmax(sub), "COUNTER ZOMBIE · %s", mode[0] ? mode : "SURVIVAL");
	if (parent >= 0)
		formatex(sub, charsmax(sub), "%s / %s", en ? g_sections[parent][SecEn] : g_sections[parent][SecRu], en ? g_sections[s][SecEn] : g_sections[s][SecRu]);
	chip_text(chip, charsmax(chip));
	get_pcvar_string(g_cvarMotto, motto, charsmax(motto));
	strtok(motto, ru, charsmax(ru), eng, charsmax(eng), '|');
	trim(ru);
	trim(eng);
	new len = formatex(text, max, "#czm1^tmenu^t%s^t%s^t%s^t%s^t%s^t%s^t%s^n#tabs", g_sections[s][SecKey],
		en ? "SERVER MENU" : "МЕНЮ СЕРВЕРА", sub, chip, en && eng[0] ? eng : ru,
		g_sections[s][SecParent], root >= 0 ? g_sections[root][SecKey] : g_sections[s][SecKey]);
	new order[MAX_SECTIONS], n = sorted_sections(order);
	for (new k = 0; k < n; k++)
	{
		new t = order[k];
		if (!g_sections[t][SecParent][0] && section_visible(id, t))
			len += formatex(text[len], max - len, "^t%s:%s:%s:%s", g_sections[t][SecKey],
				en ? g_sections[t][SecEn] : g_sections[t][SecRu], g_sections[t][SecIcon], g_tabBadge[t]);
	}
	len += formatex(text[len], max - len, "^n^n");
	return len;
}

plain_head(s, bool:en, text[], max)
{
	new chip[96];
	chip_text(chip, charsmax(chip));
	if (equali(g_sections[s][SecKey], "main"))
		return formatex(text, max, "\y%s^n\d%s^n^n", en ? "SERVER MENU" : "МЕНЮ СЕРВЕРА", chip);
	return formatex(text, max, "\y%s^n\d%s^n^n", en ? g_sections[s][SecEn] : g_sections[s][SecRu], chip);
}

chip_text(out[], len)
{
	new map[32], left = max(get_timeleft(), 0);
	get_mapname(map, charsmax(map));
	formatex(out, len, "%d/%d · %s · %d:%02d", get_playersnum(), MaxClients, map, left / 60, left % 60);
}

public on_key(id, key)
{
	new s = g_shown[id];
	g_shown[id] = -1;
	if (key < 0 || key >= 9 || s < 0)
		return PLUGIN_HANDLED;
	new i = g_slot[id][key];
	switch (i)
	{
		case SLOT_NEXT: open(id, g_sections[s][SecKey], g_page[id] + 1);
		case SLOT_BACK: open(id, g_sections[s][SecKey], 0);
		case SLOT_MAIN:
		{
			if (g_sections[s][SecParent][0])
				open(id, g_sections[s][SecParent], 0);
			else
				open(id, "main", 0);
		}
		case SLOT_NONE: {}
		default:
		{
			if (!can_dispatch(id, s, i))
				return PLUGIN_HANDLED;
			if (g_items[i][ItOpen][0])
				open(id, g_items[i][ItOpen], 0);
			else if (g_items[i][ItFunc] >= 0 && callfunc_begin_i(g_items[i][ItFunc], g_items[i][ItPlugin]) == 1)
			{
				callfunc_push_int(id);
				callfunc_push_str(g_items[i][ItKey], false);
				callfunc_end();
			}
		}
	}
	return PLUGIN_HANDLED;
}

// the tabs of the window
public cmd_tab(id)
{
	new key[16];
	read_argv(1, key, charsmax(key));
	open(id, key, 0);
	return PLUGIN_HANDLED;
}
