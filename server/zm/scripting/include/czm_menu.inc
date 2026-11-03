// Counter Zombie Mobile, Survival server: one server menu for every plugin (czm_menu.amxx).
//
// A plugin adds its tab (section) and its cards (items) in plugin_init; the CZM game draws them as a
// window with tabs on the left and cards with icons, other games get a text menu. A plugin that is
// off adds nothing, so its tab is not there.
#if defined _czm_menu_included
	#endinput
#endif
#define _czm_menu_included

// who sees a section or an item
#define CZM_MENU_ALL     0
#define CZM_MENU_STAFF   1   // moderators and head administrators
#define CZM_MENU_HEAD    2   // head administrators only
#define CZM_MENU_PRIV    4   // players with a privilege (VIP+, PREMIUM, DELUXE, TESTER) and the staff

#if defined CZM_MENU_PLUGIN
	#endinput
#endif
#pragma reqlib czm_menu

// A tab on the left of the window. icon: one of the game's icons (star, crown, users, flag, globe,
// gear, shield, bell, chat, target, ...); order: smaller first.
native czm_menu_section(const key[], const ru[], const en[], const icon[], order = 50, access = CZM_MENU_ALL);

// A card of a section. color: "RRGGBB". handler: a public function of the calling plugin,
// handler(id, const key[]); "#section" instead opens that section.
native czm_menu_item(const section[], const key[], const ru[], const en[], const sub_ru[] = "", const sub_en[] = "",
	const icon[] = "", const color[] = "", const handler[] = "", order = 50, access = CZM_MENU_ALL);

// Opens the menu on a section.
native czm_menu_open(id, const section[] = "main");

// Only inside czm_menu_build: this player sees an item differently this time. Empty texts keep the
// registered ones; badge: a short mark on the card ("NEW", "2:41"; "!" first makes it red); hide
// leaves the card out, off greys it out. key "#section" sets the badge of that tab.
native czm_menu_state(id, const key[], const name[] = "", const sub[] = "", const badge[] = "", bool:hide = false, bool:off = false);

// Runs before a section is shown to a player.
forward czm_menu_build(id, const section[]);

// Whether the player's game draws the window (the CZM game); the others get the text menu.
native bool:czm_menu_rich(id);
