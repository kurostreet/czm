// Copy to scripting/<your_plugin>.sma, rename the keys, compile and add the plugin
// after czm_menu.amxx in plugins-czm.ini. This template is not loaded automatically.
#include <amxmodx>
#include <czm_survival>
#include <czm_menu>

// ALL, VIP, PREMIUM, DELUXE, MODERATOR or ADMIN. OR flags accept any listed role.
// A child also requires access to every parent, regardless of its own flag.
#define EXAMPLE_ACCESS CZM_MENU_ALL

public plugin_init()
{
    register_plugin("CZM Menu example", "1.0", "kurostreet");
    // Root: a sidebar tab. Keep section keys <= 15 ASCII letters/digits/_ .
    czm_menu_section("extra", "Мой плагин", "My plugin", "star", 55, EXAMPLE_ACCESS);
    czm_menu_item("main", "extra_home", "Мой плагин", "My plugin",
        "Команды сервера", "Server commands", "star", "E53F4D", "#extra", 55, EXAMPLE_ACCESS);

    // Child: not a separate sidebar tab. The window supplies the Back button.
    czm_menu_section("extra_details", "Подраздел", "Subsection", "users", 10, EXAMPLE_ACCESS, "extra");
    czm_menu_item("extra", "extra_details_link", "Подраздел", "Subsection",
        "Открыть команды", "Open commands", "users", "63A1EF", "#extra_details", 10);
    czm_menu_item("extra_details", "extra_action", "Проверить команду", "Test command",
        "Пример обработчика", "Example handler", "chat", "6BDAA7", "on_extra_action", 10);
}

public on_extra_action(id, const key[])
{
    // Replace with the plugin's real action. The menu checks access again at dispatch.
    // Also check authorization in any separate chat/console entry point you expose.
    if (!equal(key, "extra_action"))
        return;
    czm_chat(id, "^4[CZM]^1 Команда плагина выполнена.", "^4[CZM]^1 Plugin command executed.");
    czm_menu_open(id, "extra_details");
}

public czm_menu_build(id, const section[])
{
    // Per-player text and badges are temporary for this display only.
    if (equal(section, "extra_details"))
        czm_menu_state(id, "extra_action", _, _, "NEW");
}
