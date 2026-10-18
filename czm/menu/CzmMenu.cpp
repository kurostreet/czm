/*
CzmMenu.cpp - Counter Zombie Mobile menu: shared drawing, language, servers, loading screen
Copyright (C) 2026 Counter Zombie Mobile authors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.
*/

#include <ctype.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "extdll_menu.h"
#include "BaseMenu.h"
#include "Utils.h"
#include "BaseWindow.h"
#include "FontManager.h"
#include "Scissor.h"
#include "CzmMenu.h"
#include "../../common/czm_hud_layout.h"
#include "CzmJson.h"
#include "../../common/czm_settings_names.h"

// The engine publishes loading progress through these cvars (engine/client/czm_loading.c).
// Stage numbers must match the engine.
enum
{
	CZM_STAGE_NONE = 0,
	CZM_STAGE_CONNECT,
	CZM_STAGE_HANDSHAKE,
	CZM_STAGE_DOWNLOAD,
	CZM_STAGE_PRECACHE,
	CZM_STAGE_ENTER,
	CZM_STAGE_LOCAL,
};

// cancel button, in screen fractions; the engine uses the same numbers for touch input
#define CZM_CANCEL_X0 0.815f
#define CZM_CANCEL_X1 0.955f
#define CZM_CANCEL_Y0 0.818f
#define CZM_CANCEL_Y1 0.898f
#define CZM_BACKGROUND_Y0 0.700f
#define CZM_BACKGROUND_Y1 0.780f

#define CZM_LOADING_IMAGES 5
#define CZM_TIPS 10

/*
=================
language
=================
*/
static const struct { const char *key, *ru, *en; } s_strings[] =
{
	// loading screen
	{ "tip1", "Совет: зомби быстрее людей — держись ближе к своим и прикрывай спину.", "Tip: zombies are faster than humans — stay close to your team." },
	{ "tip2", "Совет: в узком проходе толпу зомби сдерживать намного проще.", "Tip: a narrow corridor makes a zombie horde much easier to hold." },
	{ "tip3", "Совет: перезаряжайся заранее, пока зомби далеко.", "Tip: reload early, while the zombies are still far away." },
	{ "tip4", "Совет: не стой на открытом месте — ищи укрытие и высоту.", "Tip: don't stand in the open — find cover and high ground." },
	{ "tip5", "Совет: дробовик и пулемёт хорошо останавливают зомби вблизи.", "Tip: shotguns and machine guns stop zombies up close." },
	{ "tip6", "Совет: граната помогает отбросить толпу и выиграть пару секунд.", "Tip: a grenade pushes the horde back and buys you a few seconds." },
	{ "tip7", "Совет: целься в голову — так зомби падают быстрее.", "Tip: aim for the head — zombies go down faster." },
	{ "tip8", "Совет: стал зомби — нападай вместе с другими, по одному не ходи.", "Tip: turned into a zombie? Attack together, never alone." },
	{ "tip9", "Совет: с друзьями выживать проще — зови их в игру.", "Tip: surviving is easier with friends — invite them to play." },
	{ "tip10", "Совет: настрой кнопки под себя в «Настройках», вкладка «Управление».", "Tip: tune your buttons in Settings, on the Controls tab." },
	{ "st_local", "Запуск игры…", "Starting the game…" },
	{ "st_connect", "Подключение к серверу…", "Connecting to the server…" },
	{ "st_handshake", "Получение данных сервера…", "Receiving server data…" },
	{ "st_download", "Скачивание файлов сервера", "Downloading server files" },
	{ "st_precache", "Загрузка карты и моделей…", "Loading the map and models…" },
	{ "st_enter", "Вход в игру…", "Entering the game…" },
	{ "of", "из", "of" },
	{ "mb", "МБ", "MB" },
	{ "mbps", "МБ/с", "MB/s" },
	{ "kbps", "КБ/с", "KB/s" },
	{ "lbl_map", "Карта", "Map" },
	{ "lbl_players", "Игроки", "Players" },
	{ "lbl_ping", "Пинг", "Ping" },
	{ "ms", "мс", "ms" },
	{ "cancel", "Отмена", "Cancel" },
	// connection errors
	{ "err_connect", "Соединение прервалось до входа в игру.\nПричина отключения не передана.", "The connection closed before entering the game.\nNo disconnect reason was provided." },
	{ "err_timeout", "Сервер не ответил за отведённое время.\nСоединение закрыто по таймауту.", "The server did not respond in time.\nThe connection timed out." },
	{ "err_full", "Сервер заполнен.\nПопробуй позже или выбери другой режим.", "The server is full.\nTry again later or pick another mode." },
	{ "err_password", "Неверный пароль сервера.", "Wrong server password." },
	{ "err_banned", "Доступ на этот сервер закрыт.", "You are not allowed on this server." },
	{ "err_kicked", "Сервер отключил тебя.", "The server disconnected you." },
	{ "err_generic", "Не удалось подключиться к серверу.", "Could not connect to the server." },
	// main screen
	{ "nick_hint", "Нажми, чтобы открыть профиль", "Tap to open your profile" },
	{ "in_game", "в игре", "playing" },
	{ "querying", "Опрашиваем сервер…", "Checking the server…" },
	{ "offline", "Сервер не отвечает", "Server is not responding" },
	{ "full", "Сервер полон", "Server is full" },
	{ "nav_friends", "Друзья", "Friends" },
	{ "nav_friends_hint", "Друзья и сообщения", "Friends and messages" },
	{ "nav_chat", "Чат", "Chat" },
	{ "nav_servers", "Серверы", "Servers" },
	{ "nav_settings", "Настройки", "Settings" },
	{ "nav_about", "Об игре", "About" },
	{ "nav_chat_hint", "Игроки онлайн", "Players online" },
	{ "nav_chat_online", "%d онлайн", "%d online" },
	{ "nav_servers_hint", "Найти игру", "Find a game" },
	{ "nav_settings_hint", "Управление и HUD", "Controls and HUD" },
	{ "nav_about_hint", "Проект и контакты", "Project and contacts" },
	{ "bell_title", "Уведомления", "Notifications" },
	{ "bell_empty", "Пока нет уведомлений", "No notifications yet" },
	{ "about_title", "Об игре", "About" },
	{ "about_tg", "Связь с разработчиком", "Contact the developer" },
	{ "about_group", "Группа игры", "Game community" },
	{ "about_site", "Сайт проекта", "Project website" },
	{ "about_source", "Исходный код", "Source code" },
	{ "about_version", "Версия приложения", "App version" },
	{ "about_updated", "Последнее обновление", "Last update" },
	{ "about_engine", "Движок", "Engine" },
	{ "about_more", "Подробности, лицензии и авторы — на GitHub", "Details, licenses and credits are on GitHub" },
	{ "quit_title", "Выйти из игры?", "Quit the game?" },
	{ "quit_yes", "Выйти", "Quit" },
	{ "pause", "ПАУЗА", "PAUSED" },
	{ "resume", "Продолжить", "Resume" },
	{ "settings", "Настройки", "Settings" },
	{ "to_menu", "Выйти в меню", "Leave to menu" },
	// settings
	{ "set_title", "НАСТРОЙКИ", "SETTINGS" },
	{ "tab_controls", "Управление", "Controls" },
	{ "tab_graphics", "Графика", "Graphics" },
	{ "tab_sound", "Звук", "Sound" },
	{ "tab_game", "Игра", "Game" },
	{ "tab_hud", "HUD", "HUD" },
	{ "tab_profile", "Профиль", "Profile" },
	{ "s_look", "Обзор", "Look" },
	{ "s_look_hint", "Как быстро поворачивается камера", "How fast the camera turns" },
	{ "s_zoom", "В прицеле", "While aiming" },
	{ "s_zoom_hint", "Чувствительность с оптикой", "Sensitivity with a scope" },
	{ "s_move", "Ходьба", "Movement" },
	{ "s_move_hint", "Чем больше, тем короче движение пальца", "Higher means a shorter finger move" },
	{ "s_gyro", "Гироскоп", "Gyroscope" },
	{ "s_gyro_hint", "Наклон телефона двигает прицел", "Tilt the phone to aim" },
	{ "s_gyro_none", "На этом телефоне нет гироскопа", "This phone has no gyroscope" },
	{ "s_gyro_power", "Сила гироскопа", "Gyroscope strength" },
	{ "s_scheme", "Схема кнопок", "Button layout" },
	{ "s_scheme_hint", "Три раскладки, у каждой свои изменения", "Three layouts, each keeps its own changes" },
	{ "opt_scheme1", "Классика", "Classic" },
	{ "opt_scheme2", "Шутер", "Shooter" },
	{ "opt_scheme3", "Минимум", "Minimal" },
	{ "s_buttons", "Кнопки и интерфейс", "Buttons and HUD" },
	{ "s_buttons_hint", "Кнопки и HUD матча на одном экране, перекрытия видно сразу", "Buttons and the match HUD on one screen, overlaps are shown" },
	{ "b_edit", "Изменить", "Edit" },
	{ "b_reset", "Сбросить", "Reset" },
	{ "reset_confirm", "Сбросить кнопки и интерфейс?", "Reset the buttons and HUD?" },
	{ "reset_done", "Кнопки и интерфейс сброшены", "Buttons and HUD reset" },
	{ "s_brightness", "Яркость", "Brightness" },
	{ "s_parallax", "Живой фон меню", "Animated menu background" },
	{ "s_parallax_hint", "Движение трёх слоёв и света", "Animated layers and light" },
	{ "s_fps", "Лимит FPS", "FPS limit" },
	{ "s_fps_hint", "Больше — плавнее, но телефон греется", "Higher is smoother but warms the phone" },
	{ "s_render", "Режим отрисовки", "Rendering mode" },
	{ "s_render_hint", "Картинка с ошибками — попробуй другой режим", "Picture looks wrong? Try another mode" },
	{ "render_classic", "Классический", "Classic" },
	{ "render_compatible", "Совместимый", "Compatible" },
	{ "render_modern", "Современный", "Modern" },
	{ "map_not_loaded", "Карта не загружена", "The map is not loaded" },
	{ "map_not_downloaded", "не скачана", "not downloaded" },
	{ "s_render_restart", "Включится после перезапуска игры", "Takes effect after restarting the game" },
	{ "s_showfps", "FPS на экране", "Show FPS" },
	{ "s_showping", "Пинг на экране", "Show ping" },
	{ "s_textsize", "Размер текста", "Text size" },
	{ "s_textsize_hint", "Чат и сообщения на экране", "Chat and messages on the screen" },
	{ "s_hudsize", "Размер HUD", "HUD size" },
	{ "s_hudsize_hint", "Здоровье, деньги, патроны. Со следующей карты", "Health, money, ammo. From the next map" },
	{ "s_shadows", "Тени игроков", "Player shadows" },
	{ "s_weather", "Погода", "Weather" },
	{ "s_weather_hint", "Дождь и снег на картах, где они есть", "Rain and snow on maps that have them" },
	{ "s_mic", "Проверка микрофона", "Microphone test" },
	{ "s_mic_hint", "Скажи что-нибудь — полоска покажет громкость", "Say something, the bar shows the level" },
	{ "s_mic_ok", "Микрофон работает", "The microphone works" },
	{ "s_mic_none", "Нет доступа к микрофону. Разреши его в настройках телефона", "No microphone access. Allow it in the phone settings" },
	{ "s_mic_match", "Проверка работает в главном меню", "The test works in the main menu" },
	{ "b_check", "Проверить", "Test" },
	{ "b_stop", "Стоп", "Stop" },
	{ "s_effects", "Эффекты", "Effects" },
	{ "s_effects_hint", "Гильзы, дым и тела. Меньше — быстрее", "Shells, smoke and bodies. Less is faster" },
	{ "opt_low", "Мало", "Low" },
	{ "opt_mid", "Средне", "Medium" },
	{ "opt_high", "Много", "High" },
	{ "s_volume", "Громкость", "Volume" },
	{ "s_music", "Музыка в меню", "Menu music" },
	{ "s_ui_volume", "Звуки кнопок", "Button sounds" },
	{ "s_voice", "Голосовой чат", "Voice chat" },
	{ "s_voice_hint", "Слышать игроков и говорить", "Hear and talk to players" },
	{ "s_voice_in", "Громкость голосов", "Voice volume" },
	{ "s_voice_out", "Громкость микрофона", "Microphone volume" },
	{ "s_lang", "Язык", "Language" },
	{ "s_xhair", "Прицел", "Crosshair" },
	{ "s_xhair_hint", "Так он выглядит в игре", "How it looks in the game" },
	{ "s_xhair_size", "Размер прицела", "Crosshair size" },
	{ "opt_auto", "Авто", "Auto" },
	{ "opt_small", "Малый", "Small" },
	{ "opt_medium", "Средний", "Medium" },
	{ "opt_large", "Большой", "Large" },
	{ "s_xhair_color", "Цвет прицела", "Crosshair color" },
	{ "s_xhair_color_hint", "Радужный круг — любой цвет", "Rainbow wheel — any color" },
	{ "s_tab_style", "Таблица игроков", "Player scoreboard" },
	{ "s_tab_style_hint", "Оформление окна TAB в матче", "The TAB scoreboard during a match" },
	{ "s_tab_preview", "Предпросмотр", "Preview" },
	{ "s_tab_preview_hint", "Команды, статус и статистика во всех вариантах", "Teams, status and statistics in every style" },
	{ "opt_tab_default", "Обычный", "Default" },
	{ "opt_tab_compact", "Компактный", "Compact" },
	{ "opt_tab_tactical", "Тактический", "Tactical" },
	{ "s_xhair_dyn", "Динамический прицел", "Dynamic crosshair" },
	{ "s_xhair_dyn_hint", "Расходится при беге и прыжке. Выключи — будет маленький и ровный", "Spreads when running and jumping. Off keeps it small and still" },
	{ "s_xhair_trans", "Прозрачный прицел", "Translucent crosshair" },
	{ "s_hand", "Оружие в руке", "Weapon hand" },
	{ "opt_right", "Правой", "Right" },
	{ "opt_left", "Левой", "Left" },
	{ "s_autoswitch", "Брать лучшее оружие", "Switch to better weapons" },
	{ "s_autoswitch_hint", "Подобрал оружие мощнее — оно сразу в руке", "A stronger weapon you pick up is used at once" },
	{ "s_buymenu", "Меню покупки", "Buy menu" },
	{ "s_shop", "Магазин", "Shop" },
	{ "s_shop_hint", "Колесо или сетка. Классика — текстовое меню сервера", "Wheel or grid. Classic is the server's text menu" },
	{ "opt_wheel", "Колесо", "Wheel" },
	{ "opt_grid", "Сетка", "Grid" },
	{ "s_shop_auto", "Автооткрытие магазина", "Open the shop automatically" },
	{ "s_shop_auto_hint", "В начале каждого раунда", "At the start of every round" },
	{ "s_menucards", "Сенсорное меню", "Touch menus" },
	{ "s_menucards_hint", "Голосования и меню плагинов — кнопками вместо цифр", "Votes and plugin menus: tap buttons instead of digits" },
	{ "opt_new", "Новое", "New" },
	{ "opt_classic", "Классика", "Classic" },
	{ "s_nick", "Ник", "Nickname" },
	{ "s_account", "Аккаунт и почта", "Account and email" },
	{ "s_account_hint", "Вход, привязка почты и настройки облака", "Sign in, link email and manage cloud settings" },
	{ "s_account_open", "Открыть", "Open" },
	{ "s_nick_hint", "Так тебя видят другие игроки", "How other players see you" },
	{ "nick_placeholder", "Твой ник", "Your nickname" },
	{ "nick_bad", "Введи свой ник, от 2 символов", "Enter your nickname, 2 characters or more" },
	{ "s_avatar", "Аватар", "Avatar" },
	{ "s_avatar_hint", "Нажми «Фото», чтобы взять картинку из галереи. В чате его увидят все", "Tap Photo to use a picture from your gallery. Everyone sees it in the chat" },
	{ "s_avatar_photo", "Фото", "Photo" },
	{ "s_avatar_wait", "Выбери картинку в галерее", "Pick a picture in the gallery" },
	{ "s_spray", "Спрей", "Spray" },
	{ "s_spray_hint", "Рисуется кнопкой спрея в игре", "Drawn with the spray button in the game" },
	// server list
	{ "srv_title", "СЕРВЕРЫ", "SERVERS" },
	{ "srv_tab_all", "Все", "All" },
	{ "srv_tab_fav", "Избранное", "Favorites" },
	{ "srv_tab_hist", "История", "History" },
	{ "srv_search", "Поиск: название, карта, IP", "Search: name, map, IP" },
	{ "srv_f_notempty", "Не пустые", "Not empty" },
	{ "srv_f_notfull", "Есть места", "Free slots" },
	{ "srv_f_nopass", "Без пароля", "No password" },
	{ "srv_f_zombie", "Зомби", "Zombie" },
	{ "srv_sort_players", "По игрокам", "By players" },
	{ "srv_sort_ping", "По пингу", "By ping" },
	{ "srv_sort_name", "По названию", "By name" },
	{ "srv_sort_recent", "Недавние", "Recent" },
	{ "srv_updating", "  ·  обновляем…", "  ·  refreshing…" },
	{ "srv_searching", "Ищем серверы", "Looking for servers" },
	{ "srv_nothing", "Ничего не найдено", "Nothing found" },
	{ "srv_nothing_hint", "Попробуй другой запрос или сбрось фильтры", "Try another search or clear the filters" },
	{ "srv_reset", "Сбросить фильтры", "Clear filters" },
	{ "srv_fav_empty", "Здесь будут избранные серверы", "Your favorite servers live here" },
	{ "srv_fav_hint", "Нажми на звёздочку у сервера или добавь его по IP", "Tap the star next to a server or add one by IP" },
	{ "srv_hist_empty", "Здесь будут серверы, где ты играл", "Servers you played on show up here" },
	{ "srv_hist_hint", "Выбери сервер во вкладке «Все»", "Pick a server on the All tab" },
	{ "srv_none", "Серверы не ответили", "No servers answered" },
	{ "srv_none_hint", "Проверь интернет и обнови список", "Check your connection and refresh the list" },
	{ "srv_refresh", "Обновить", "Refresh" },
	{ "srv_pick", "Выбери сервер в списке", "Pick a server from the list" },
	{ "srv_password", "С паролем", "Password" },
	{ "srv_players", "ИГРОКИ", "PLAYERS" },
	{ "srv_frags", "Фраги", "Frags" },
	{ "srv_players_wait", "Загружаем список игроков…", "Loading players…" },
	{ "srv_players_none", "На сервере пока никого", "Nobody is playing right now" },
	{ "srv_players_hidden", "Сервер не показывает список игроков", "The server hides its players" },
	{ "srv_more", "и ещё %d", "and %d more" },
	{ "srv_play", "ИГРАТЬ", "PLAY" },
	{ "srv_fav_add", "В избранное", "Favorite" },
	{ "srv_fav_in", "В избранном", "Favorited" },
	{ "srv_fav_on", "Добавлено в избранное", "Added to favorites" },
	{ "srv_fav_off", "Убрано из избранного", "Removed from favorites" },
	{ "srv_pin_on", "Закреплено на главной", "Pinned to the main screen" },
	{ "srv_pin_off", "Убрано с главной", "Unpinned from the main screen" },
	{ "srv_pin_full", "Закрепить можно 3. Сними одно сердечко", "Up to 3 can be pinned. Remove one heart" },
	{ "srv_pinned", "закреплено", "pinned" },
	{ "tile_add", "Добавить сервер", "Add a server" },
	{ "tile_add_hint", "Нажми, чтобы выбрать", "Tap to choose" },
	{ "srv_add_title", "Добавить сервер", "Add a server" },
	{ "srv_add_text", "Адрес сервера, например 1.2.3.4:27015", "Server address, e.g. 1.2.3.4:27015" },
	{ "srv_add_bad", "Не похоже на адрес сервера", "That does not look like a server address" },
	{ "srv_add_ok", "Добавить", "Add" },
	{ "srv_add_done", "Сервер добавлен в избранное", "Server added to favorites" },
	{ "srv_paste", "Вставить", "Paste" },
	{ "srv_pass_title", "Пароль сервера", "Server password" },
	{ "srv_pass_text", "Этот сервер закрыт паролем", "This server needs a password" },
	{ "srv_pass_hint", "Пароль", "Password" },
	{ "srv_pass_go", "Войти", "Join" },
	// chat
	{ "chat_title", "ЧАТ", "CHAT" },
	{ "chat_rules", "Без мата и оскорблений. Нажми на сообщение, чтобы пожаловаться", "No swearing or insults. Tap a message to report it" },
	{ "chat_placeholder", "Сообщение в %s…", "Message to %s…" },
	{ "chat_connecting", "Подключаемся к чату…", "Connecting to the chat…" },
	{ "chat_loading", "Загружаем сообщения…", "Loading messages…" },
	{ "chat_empty", "Здесь пока тихо. Напиши первым!", "It's quiet here. Say something first!" },
	{ "chat_offline", "Нет связи с сервером, попробуй позже", "No connection to the server, try again later" },
	{ "chat_slow", "Не так быстро — подожди %d с", "Not so fast — wait %d s" },
	{ "chat_repeat", "Это сообщение уже отправлено", "You already sent this message" },
	{ "chat_reported", "Жалоба отправлена, спасибо", "Report sent, thank you" },
	{ "chat_report_slow", "Слишком много жалоб, попробуй позже", "Too many reports, try again later" },
	{ "chat_report_title", "Пожаловаться на %s?", "Report %s?" },
	{ "chat_report_message", "На сообщение", "The message" },
	{ "chat_report_avatar", "На аватар", "The avatar" },
	{ "chat_banned_until", "Чат закрыт для тебя до %s. Вопросы — Telegram @blackmodru", "You can't chat until %s. Questions: Telegram @blackmodru" },
	{ "chat_banned_forever", "Чат закрыт для тебя навсегда. Вопросы — Telegram @blackmodru", "You can't chat anymore. Questions: Telegram @blackmodru" },
	// news and updates
	{ "upd_title", "Доступно обновление", "Update available" },
	{ "upd_download", "Скачать", "Download" },
	{ "upd_downloading", "Скачиваем… %d%%", "Downloading… %d%%" },
	{ "upd_verifying", "Проверяем файл…", "Checking the file…" },
	{ "upd_install", "Установить", "Install" },
	{ "upd_installing", "Устанавливаем…", "Installing…" },
	{ "upd_permission", "Разреши установку для игры в настройках Android и нажми ещё раз", "Allow installs for the game in Android settings, then tap again" },
	{ "upd_error_network", "Связь прервалась. Нажми, чтобы продолжить", "The download stopped. Tap to continue" },
	{ "upd_error_broken", "Файл повреждён, скачаем заново", "The file is damaged, it will download again" },
	{ "upd_error_install", "Не удалось установить. Попробуй ещё раз", "Could not install. Try again" },
	{ "upd_error_storage", "Освободи место на телефоне и попробуй ещё раз", "Free some space on your phone and try again" },
	{ "upd_cancel", "Отмена", "Cancel" },
	{ "news_loading", "Загружаем новости…", "Loading news…" },
	// first start
	{ "s_layouts", "Обмен раскладками", "Share layouts" },
	{ "s_layouts_hint", "Поделиться файлом · импорт с просмотром · отмена", "Share file · preview before import · undo" },
	{ "s_hud_edit", "Интерфейс в матче", "In-match HUD" },
	{ "s_hud_edit_hint", "Вместе с кнопками: стиль, место, размер, видимость", "Together with the buttons: style, place, size, opacity" },
	{ "s_radar_style", "Радар", "Radar" },
	{ "s_radar_style_hint", "Вид мини-карты. Место и размер — в «Интерфейс в матче»", "How the minimap looks. Place and size are in the in-match HUD editor" },
	{ "setup_title", "Добро пожаловать!", "Welcome!" },
	{ "setup_text", "Выбери язык и придумай ник", "Choose a language and a nickname" },
	{ "setup_go", "Играть", "Play" },
	{ "setup_login", "Уже играл? Войти в аккаунт", "Played before? Sign in" },
	{ "quick_title", "БЫСТРАЯ ИГРА", "QUICK PLAY" },
	{ "quick_search", "ИЩЕМ СЕРВЕР", "SEARCHING" },
	{ "quick_hint", "Лучший открытый зомби-сервер по онлайну и пингу", "The best open zombie server by players and ping" },
	{ "quick_cancel", "Нажми ещё раз, чтобы отменить", "Tap again to cancel" },
	{ "quick_none", "Свободных зомби-серверов не нашли — открой «Серверы»", "No open zombie server found, open Servers" },
};

static bool s_bInitialized;

void CZM_Init( void )
{
	// This also runs after config.cfg: existing players may have saved the old value.
	if( EngFuncs::GetCvarFloat( "cl_advertise_engine_in_name" ) != 0.0f )
		EngFuncs::CvarSetValue( "cl_advertise_engine_in_name", 0.0f );

	if( s_bInitialized )
		return;

	// archived cvars must exist before config.cfg runs, the menu creates its fonts early enough
	s_bInitialized = true;
	EngFuncs::CvarRegister( "czm_lang", "", FCVAR_ARCHIVE );
	EngFuncs::CvarRegister( "czm_setup", "0", FCVAR_ARCHIVE );
	EngFuncs::CvarRegister( "czm_defaults", "0", FCVAR_ARCHIVE );
	EngFuncs::CvarRegister( "czm_zoom_sens", "1.2", FCVAR_ARCHIVE );
	EngFuncs::CvarRegister( "czm_connect_name", "", 0 );
	EngFuncs::CvarRegister( "czm_connect_adr", "", 0 );
	EngFuncs::CvarRegister( "czm_touch_scheme", "1", FCVAR_ARCHIVE );
	EngFuncs::CvarRegister( "czm_touch_version", "0", FCVAR_ARCHIVE );
	EngFuncs::CvarRegister( "czm_shop", "1", FCVAR_ARCHIVE );       // 1 wheel, 2 grid
	EngFuncs::CvarRegister( "czm_shop_auto", "0", FCVAR_ARCHIVE );  // open the shop when a round starts
	EngFuncs::CvarRegister( "czm_menu_cards", "1", FCVAR_ARCHIVE ); // server menus as cards
	EngFuncs::CvarRegister( "czm_hud_style", "0", FCVAR_ARCHIVE );
	EngFuncs::CvarRegister( "czm_parallax", "1", FCVAR_ARCHIVE );
	EngFuncs::CvarRegister( "czm_hud_radar_style", "0", FCVAR_ARCHIVE ); // classic, tactical, minimal
	for( int i=0;i<CzmHud::BLOCKS;i++ ) for( int k=0;k<5;k++ ) {
		char name[64],value[32];
		CzmHud::Key(name,sizeof(name),i,CzmHud::fields[k]);
		snprintf(value,sizeof(value),"%.4f",k<2?CzmHud::defaults[i][k]:k<4?1.f:0.f);
		EngFuncs::CvarRegister(name,value,FCVAR_ARCHIVE);
	}
	EngFuncs::CvarRegister( "czm_open_profile", "0", 0 );
	EngFuncs::CvarRegister( "czm_current_map", "", 0 );
	EngFuncs::CvarRegister( "czm_profile_id", "0", FCVAR_PRIVILEGED );
	EngFuncs::CvarRegister( "czm_touch_profile_aspect", "0", FCVAR_PRIVILEGED );
	EngFuncs::CvarRegister( "czm_tab_style", "0", FCVAR_ARCHIVE ); // keep the current scoreboard by default
	EngFuncs::CvarRegister( "czm_tag", "", FCVAR_USERINFO|FCVAR_PRIVILEGED ); // public connection binding, never an account token
	for( int slot = 1; slot <= 32; slot++ )
	{
		char name[40]; snprintf( name, sizeof( name ), "czm_tab_avatar_%d", slot );
		EngFuncs::CvarRegister( name, "", FCVAR_PRIVILEGED );
		snprintf( name, sizeof( name ), "czm_tab_profile_%d", slot );
		EngFuncs::CvarRegister( name, "", FCVAR_PRIVILEGED );
	}
	EngFuncs::CvarRegister( "czm_avatar", "", FCVAR_ARCHIVE );       // "", "1".."10" or "photo"
	EngFuncs::CvarRegister( "czm_avatar_photo", "", FCVAR_ARCHIVE ); // the player's own photo file
	EngFuncs::CvarRegister( "czm_avatar_sent", "", FCVAR_ARCHIVE );  // the photo the service already has
	EngFuncs::CvarRegister( "czm_news_seen", "0", FCVAR_ARCHIVE );   // the newest news the player opened
	EngFuncs::CvarRegister( "czm_chat_room", "0", FCVAR_ARCHIVE );   // 0 global, 1 ru, 2 en
	EngFuncs::CvarRegister( "czm_ui_volume", "0.65", FCVAR_ARCHIVE );
	EngFuncs::CvarRegister( "czm_srv_filters", "0", FCVAR_ARCHIVE ); // server list filters, bits
	EngFuncs::CvarRegister( "czm_srv_sort", "0", FCVAR_ARCHIVE );    // 0 players, 1 ping, 2 name
}

// the phone language, passed by the launcher
static bool CZM_LocaleIsRussian( void )
{
	const char *locale = getenv( "CZM_LOCALE" );

	return !locale || !locale[0] || !strncmp( locale, "ru", 2 ) || !strncmp( locale, "uk", 2 )
		|| !strncmp( locale, "be", 2 ) || !strncmp( locale, "kk", 2 );
}

bool CZM_IsRussian( void )
{
	const char *lang;

	CZM_Init();

	// the player's choice, saved in config.cfg, wins over the phone language
	lang = EngFuncs::GetCvarString( "czm_lang" );
	if( lang && lang[0] )
		return !strcmp( lang, "ru" );

	return CZM_LocaleIsRussian();
}

const char *CZM_T( const char *key )
{
	bool russian = CZM_IsRussian();

	for( size_t i = 0; i < sizeof( s_strings ) / sizeof( s_strings[0] ); i++ )
	{
		if( !strcmp( s_strings[i].key, key ))
			return russian ? s_strings[i].ru : s_strings[i].en;
	}

	return key;
}

void CZM_SetLanguage( bool russian )
{
	CZM_Init();
	EngFuncs::CvarSetString( "czm_lang", russian ? "ru" : "en" );
	// the stock menus read their translations from ui_language on the next start
	EngFuncs::CvarSetString( "ui_language", russian ? "russian" : "english" );
	EngFuncs::ClientCmd( false, "host_writeconfig\n" );
}

/*
=================
fonts
=================
*/
static HFont s_hFonts[CZMF_COUNT];

bool CZM_FindFontFile( const char *name, char *dataFile, size_t dataFileChars )
{
	static const struct { const char *name, *file; } fonts[] =
	{
		{ "CZM Black", "gfx/fonts/czm/InterDisplay-Black.otf" },
		{ "CZM BlackItalic", "gfx/fonts/czm/InterDisplay-BlackItalic.otf" },
		{ "CZM Bold", "gfx/fonts/czm/InterDisplay-Bold.otf" },
		{ "CZM Semibold", "gfx/fonts/czm/Inter-SemiBold.otf" },
		{ "CZM Medium", "gfx/fonts/czm/Inter-Medium.otf" },
	};

	for( size_t i = 0; i < sizeof( fonts ) / sizeof( fonts[0] ); i++ )
	{
		if( !strcmp( name, fonts[i].name ))
		{
			Q_strncpy( dataFile, fonts[i].file, dataFileChars );
			return true;
		}
	}

	return false;
}

void CZM_CreateFonts( float scale )
{
	CZM_Init();

	static const struct { const char *name; int tall, weight; } specs[CZMF_COUNT] =
	{
		// sizes are in 768-line units, like the rest of the menu
		{ "CZM Black", 46, 900 },       // CZMF_LOAD_HOST
		{ "CZM Black", 40, 900 },       // CZMF_LOAD_PERCENT
		{ "CZM Semibold", 25, 600 },    // CZMF_LOAD_INFO
		{ "CZM Semibold", 23, 600 },    // CZMF_LOAD_STATUS
		{ "CZM Medium", 21, 500 },      // CZMF_LOAD_TIP
		{ "CZM Semibold", 26, 600 },    // CZMF_BUTTON
		{ "CZM BlackItalic", 42, 900 }, // CZMF_TILE_TITLE
		{ "CZM Medium", 19, 500 },      // CZMF_TILE_TEXT
		{ "CZM Semibold", 21, 600 },    // CZMF_TILE_STATUS
		{ "CZM Semibold", 29, 600 },    // CZMF_NICK
		{ "CZM Medium", 17, 500 },      // CZMF_SMALL
		{ "CZM Semibold", 20, 600 },    // CZMF_NAV
		{ "CZM Semibold", 24, 600 },    // CZMF_LANG
		{ "CZM BlackItalic", 42, 900 }, // CZMF_PANEL_TITLE
		{ "CZM Medium", 21, 500 },      // CZMF_PANEL_TEXT
		{ "CZM Black", 38, 900 },       // CZMF_SHOP_MONEY
		{ "CZM Bold", 21, 700 },        // CZMF_SHOP_NAME
		{ "CZM Black", 20, 900 },       // CZMF_SHOP_PRICE
		{ "CZM BlackItalic", 43, 900 }, // CZMF_SHOP_BIG
		{ "CZM Black", 28, 900 },       // CZMF_SHOP_CARD
		{ "CZM Black", 25, 900 },       // CZMF_SHOP_CARD_PRICE
		{ "CZM BlackItalic", 36, 900 }, // CZMF_MENU_TITLE
		{ "CZM BlackItalic", 30, 900 }, // CZMF_TILE_NAME
	};

	for( int i = 0; i < CZMF_COUNT; i++ )
		s_hFonts[i] = CFontBuilder( specs[i].name, specs[i].tall * scale, specs[i].weight ).Create();
}

HFont CZM_Font( int id )
{
	return ( id >= 0 && id < CZMF_COUNT ) ? s_hFonts[id] : uiStatic.hDefaultFont;
}

int CZM_FontHeight( HFont font )
{
	return g_FontMgr->GetFontTall( font );
}

int CZM_TextWidth( HFont font, const char *text )
{
	if( !text || !text[0] )
		return 0;
	return g_FontMgr->GetTextWideScaled( font, text, CZM_FontHeight( font ));
}

void CZM_DrawText( HFont font, int x, int y, int w, const char *text, unsigned int color, unsigned int justify )
{
	int h = CZM_FontHeight( font );

	if( !text || !text[0] || w <= 0 )
		return;

	UI_DrawString( font, x, y, w, h, text, color, h, justify | QM_TOP, ETF_NO_WRAP | ETF_FORCECOL );
}

/*
=================
images
=================
*/
static struct { char path[64]; HIMAGE handle; } s_images[160];
static int s_numImages;

HIMAGE CZM_Image( const char *path )
{
	for( int i = 0; i < s_numImages; i++ )
	{
		if( !strcmp( s_images[i].path, path ))
			return s_images[i].handle;
	}

	HIMAGE handle = EngFuncs::PIC_Load( path );
	if( s_numImages < (int)( sizeof( s_images ) / sizeof( s_images[0] )))
	{
		Q_strncpy( s_images[s_numImages].path, path, sizeof( s_images[0].path ));
		s_images[s_numImages].handle = handle;
		s_numImages++;
	}

	return handle;
}

void CZM_DrawImage( const char *path, int x, int y, int w, int h, unsigned int color, bool transparent )
{
	HIMAGE image = CZM_Image( path );
	int r, g, b, a;

	if( !image || w <= 0 || h <= 0 )
		return;

	UnpackRGBA( r, g, b, a, color );
	EngFuncs::PIC_Set( image, r, g, b, a );
	if( transparent )
		EngFuncs::PIC_DrawTrans( x, y, w, h );
	else
		EngFuncs::PIC_Draw( x, y, w, h );
}

void CZM_DrawSliced( const char *path, int x, int y, int w, int h, int imageBorder, int screenBorder, unsigned int color )
{
	HIMAGE image = CZM_Image( path );
	int iw, ih, r, g, b, a;

	if( !image || w <= 0 || h <= 0 )
		return;

	iw = EngFuncs::PIC_Width( image );
	ih = EngFuncs::PIC_Height( image );
	imageBorder = Q_min( imageBorder, Q_min( iw, ih ) / 2 - 1 );
	screenBorder = Q_min( screenBorder, Q_min( w, h ) / 2 );
	UnpackRGBA( r, g, b, a, color );

	const int xs[4] = { x, x + screenBorder, x + w - screenBorder, x + w };
	const int ys[4] = { y, y + screenBorder, y + h - screenBorder, y + h };
	const int us[4] = { 0, imageBorder, iw - imageBorder, iw };
	const int vs[4] = { 0, imageBorder, ih - imageBorder, ih };

	for( int j = 0; j < 3; j++ )
	{
		for( int i = 0; i < 3; i++ )
		{
			wrect_t rc;

			if( xs[i + 1] <= xs[i] || ys[j + 1] <= ys[j] )
				continue;

			rc.left = us[i];
			rc.right = us[i + 1];
			rc.top = vs[j];
			rc.bottom = vs[j + 1];
			// the engine resets the colour after every picture
			EngFuncs::PIC_Set( image, r, g, b, a );
			EngFuncs::PIC_DrawTrans( xs[i], ys[j], xs[i + 1] - xs[i], ys[j + 1] - ys[j], &rc );
		}
	}
}

void CZM_DrawPill( const char *path, int x, int y, int w, int h, unsigned int color )
{
	HIMAGE image = CZM_Image( path );
	int iw, ih, cap, icap, r, g, b, a;

	if( !image || w <= 0 || h <= 0 )
		return;

	iw = EngFuncs::PIC_Width( image );
	ih = EngFuncs::PIC_Height( image );
	cap = Q_min( h / 2, w / 2 );
	icap = Q_min( ih / 2, iw / 2 );
	UnpackRGBA( r, g, b, a, color );

	const int xs[4] = { x, x + cap, x + w - cap, x + w };
	const int us[4] = { 0, icap, iw - icap, iw };

	for( int i = 0; i < 3; i++ )
	{
		wrect_t rc;

		if( xs[i + 1] <= xs[i] )
			continue;

		rc.left = us[i];
		rc.right = us[i + 1];
		rc.top = 0;
		rc.bottom = ih;
		EngFuncs::PIC_Set( image, r, g, b, a );
		EngFuncs::PIC_DrawTrans( xs[i], y, xs[i + 1] - xs[i], h, &rc );
	}
}

int CZM_ImageAspect1000( const char *path )
{
	HIMAGE image = CZM_Image( path );
	int w = image ? EngFuncs::PIC_Width( image ) : 0;
	int h = image ? EngFuncs::PIC_Height( image ) : 0;

	return ( w > 0 && h > 0 ) ? w * 1000 / h : 0;
}

void CZM_DrawCover( HIMAGE image, int x, int y, int w, int h )
{
	int iw = image ? EngFuncs::PIC_Width( image ) : 0;
	int ih = image ? EngFuncs::PIC_Height( image ) : 0;

	if( iw <= 0 || ih <= 0 )
	{
		UI_FillRect( x, y, w, h, PackRGBA( 0, 0, 0, 255 ));
		return;
	}

	float s = Q_max( (float)w / iw, (float)h / ih );
	int dw = (int)ceilf( iw * s );
	int dh = (int)ceilf( ih * s );

	EngFuncs::PIC_Set( image, 255, 255, 255, 255 );
	EngFuncs::PIC_Draw( x + ( w - dw ) / 2, y + ( h - dh ) / 2, dw, dh );
}

unsigned int CZM_PingColor( int ping )
{
	if( ping < 80 )
		return PackRGBA( 74, 222, 128, 255 );
	if( ping < 150 )
		return PackRGBA( 250, 204, 21, 255 );
	return PackRGBA( 248, 113, 113, 255 );
}

void CZM_CleanName( const char *in, char *out, size_t size )
{
	size_t len = 0;

	for( const char *s = in ? in : ""; *s && len + 1 < size; s++ )
	{
		// colour codes like ^1
		if( s[0] == '^' && s[1] >= '0' && s[1] <= '9' )
		{
			s++;
			continue;
		}
		out[len++] = *s;
	}

	out[len] = 0;
}

static bool CZM_IsLineBreak( char c )
{
	return c == '\n' || c == '\r';
}

// line starts of text wrapped into width; long words are cut between letters,
// a line break in the text always starts a new line (an empty one too)
int CZM_WrapText( HFont font, const char *text, int width, int *starts, int maxLines )
{
	int len = strlen( text ), lines = 0, start = 0;
	char buf[1024];

	while( start < len && lines < maxLines )
	{
		int lastSpace = -1, end = start, fit = start;

		starts[lines++] = start;
		// the longest piece from start that fits, never past a line break
		while( end < len && !CZM_IsLineBreak( text[end] ))
		{
			int next = end + 1;

			while( next < len && ( text[next] & 0xC0 ) == 0x80 )
				next++;
			// no line on the screen is that long: cut it here
			if( next - start >= (int)sizeof( buf ))
				break;
			memcpy( buf, text + start, next - start );
			buf[next - start] = 0;
			if( CZM_TextWidth( font, buf ) > width )
				break;
			if( text[end] == ' ' )
				lastSpace = end;
			fit = next;
			end = next;
		}

		if( end >= len )
		{
			start = len;
			break;
		}

		// the text breaks the line itself: go on after the break ("\r\n" is one)
		if( CZM_IsLineBreak( text[end] ))
		{
			start = end + (( text[end] == '\r' && text[end + 1] == '\n' ) ? 2 : 1 );
			continue;
		}

		// cut at the last space if there is one, else between letters
		start = lastSpace > start ? lastSpace + 1 : Q_max( fit, start + 1 );
		while( start < len && text[start] == ' ' )
			start++;
	}

	starts[lines] = len;
	return lines;
}

// line l of a text wrapped by CZM_WrapText, without the line break and the spaces at its end
void CZM_WrapLine( const char *text, const int *starts, int l, char *out, size_t size )
{
	int start = starts[l], end = starts[l + 1], len;

	for( int i = start; i < end; i++ )
	{
		if( CZM_IsLineBreak( text[i] ))
		{
			end = i;
			break;
		}
	}
	while( end > start && ( text[end - 1] == ' ' || text[end - 1] == '\t' ))
		end--;

	len = Q_min( end - start, (int)size - 1 );
	// a cut never splits a letter
	while( len > 0 && len < end - start && ( text[start + len] & 0xC0 ) == 0x80 )
		len--;
	memcpy( out, text + start, len );
	out[len] = 0;
}

bool CZM_CursorIn( int x, int y, int w, int h )
{
	return uiStatic.cursorX >= x && uiStatic.cursorX < x + w && uiStatic.cursorY >= y && uiStatic.cursorY < y + h;
}

const char *CZM_Version( void )
{
	// the app version from the launcher, the client build number otherwise
	const char *version = getenv( "CZM_APP_VERSION" );

	if( version && version[0] )
		return version;

	return EngFuncs::GetCvarString( "cscl_ver" );
}

void CZM_OpenConsole( void )
{
	EngFuncs::ClientCmd( true, "ui_allowconsole\n" );
	UI_SetActiveMenu( false );
	EngFuncs::KEY_SetDest( KEY_CONSOLE );
}

static void CZM_DrawFade( const char *path, int x, int y, int w, int h, int alpha )
{
	CZM_DrawImage( path, x, y, w, h, PackRGBA( 255, 255, 255, alpha ));
}

static void CZM_DrawTitle( int x, int y, int h )
{
	int aspect = CZM_ImageAspect1000( "gfx/czm/title.png" );

	if( aspect > 0 )
		CZM_DrawImage( "gfx/czm/title.png", x, y, h * aspect / 1000, h );
}

/*
=================
servers

Fallback list used until the engine receives the master server replies.
=================
*/
#define CZM_HOME_FILE "home_servers.lst"

static CzmServer s_home[CZM_HOME_MAX];
static int s_homeCount = 0;
static bool s_homeLoaded = false;

static void CZM_HomeResetLive( CzmServer *s )
{
	s->map[0] = 0;
	s->players = 0;
	s->maxplayers = 0;
	s->ping = -1;
	s->queryTime = 0.0;
	s->answerTime = 0.0;
	s->misses = 0;
}

static void CZM_HomeInit( CzmServer *s, const char *address, const char *prot )
{
	memset( s, 0, sizeof( *s ));
	Q_strncpy( s->address, address, sizeof( s->address ));
	Q_strncpy( s->prot, ( prot && prot[0] ) ? prot : "gs", sizeof( s->prot ));
	Q_strncpy( s->name, address, sizeof( s->name ));
	s->accent = CZM_MapAccent( "", "" );
	CZM_HomeResetLive( s );
}

void CZM_HomeReload( void )
{
	int length = 0;
	byte *data = EngFuncs::COM_LoadFile( CZM_HOME_FILE, &length );
	char *p = (char *)data;

	s_homeLoaded = true;
	s_homeCount = 0;

	while( p && s_homeCount < CZM_HOME_MAX )
	{
		char address[64], prot[8];

		p = EngFuncs::COM_ParseFile( p, address, sizeof( address ));
		if( !p || !address[0] )
			break;
		p = EngFuncs::COM_ParseFile( p, prot, sizeof( prot ));
		if( !p )
			break;
		if( !strcmp( prot, "48" )) // the legacy protocol is gone from the engine
			continue;

		CZM_HomeInit( &s_home[s_homeCount++], address, prot );
	}

	if( data )
		EngFuncs::COM_FreeFile( data );
}

static void CZM_HomeEnsureLoaded( void )
{
	if( !s_homeLoaded )
		CZM_HomeReload();
}

int CZM_ServerCount( void )
{
	CZM_HomeEnsureLoaded();
	return s_homeCount;
}

CzmServer *CZM_Server( int index )
{
	CZM_HomeEnsureLoaded();
	return ( index >= 0 && index < s_homeCount ) ? &s_home[index] : NULL;
}

int CZM_HomePinCount( void )
{
	return CZM_ServerCount();
}

bool CZM_HomePinned( const char *address )
{
	for( int i = 0; i < CZM_ServerCount(); i++ )
	{
		if( !strcmp( s_home[i].address, address ))
			return true;
	}
	return false;
}

static void CZM_HomeSaveFile( void )
{
	char buf[CZM_HOME_MAX * 80];
	int n = 0;

	if( s_homeCount <= 0 )
	{
		EngFuncs::DeleteFile( CZM_HOME_FILE );
		return;
	}

	for( int i = 0; i < s_homeCount && n < (int)sizeof( buf ); i++ )
		n += snprintf( buf + n, sizeof( buf ) - n, "%s %s\n", s_home[i].address, s_home[i].prot[0] ? s_home[i].prot : "gs" );

	EngFuncs::COM_SaveFile( CZM_HOME_FILE, buf, n );
}

bool CZM_HomeSetPinned( const char *address, const char *prot, bool on )
{
	int found = -1;

	CZM_HomeEnsureLoaded();

	for( int i = 0; i < s_homeCount; i++ )
	{
		if( !strcmp( s_home[i].address, address ))
		{
			found = i;
			break;
		}
	}

	if( on )
	{
		if( found >= 0 )
			return true;                      // already pinned
		if( s_homeCount >= CZM_HOME_MAX )
			return false;                     // no free slot, the caller shows a hint
		CZM_HomeInit( &s_home[s_homeCount++], address, prot );
	}
	else
	{
		if( found < 0 )
			return true;
		for( int i = found; i < s_homeCount - 1; i++ )
			s_home[i] = s_home[i + 1];
		s_homeCount--;
	}

	CZM_HomeSaveFile();
	return true;
}

void CZM_QueryServers( bool force )
{
	double now = EngFuncs::DoubleTime();

	for( int i = 0; i < CZM_ServerCount(); i++ )
	{
		CzmServer *server = CZM_Server( i );

		if( !force && now - server->queryTime < 6.0 )
			continue;

		// the previous query got no answer
		if( server->queryTime > 0.0 && server->answerTime < server->queryTime && now - server->queryTime > 3.0 )
			server->misses++;

		server->queryTime = now;
		EngFuncs::ClientCmdF( false, "czm_queryserver \"%s\"\n", server->address );
	}
}

bool CZM_OnServerInfo( netadr_t adr, const char *info )
{
	const char *address = EngFuncs::NET_AdrToString( adr );
	const char *value;

	// our server list sees every answer
	CZM_ServerListInfo( adr, info );

	for( int i = 0; i < CZM_ServerCount(); i++ )
	{
		CzmServer *server = CZM_Server( i );

		if( strcmp( server->address, address ))
			continue;

		value = Info_ValueForKey( info, "czmping" );
		if( value && value[0] )
		{
			server->ping = CZM_PingUpdate( server->ping, atoi( value ));
			return true; // our own message, not a server entry
		}

		value = Info_ValueForKey( info, "map" );
		if( value )
			Q_strncpy( server->map, value, sizeof( server->map ));
		value = Info_ValueForKey( info, "numcl" );
		server->players = value ? atoi( value ) : 0;
		value = Info_ValueForKey( info, "maxcl" );
		server->maxplayers = value ? atoi( value ) : 0;

		// the server name, for the tile
		value = Info_ValueForKey( info, "host" );
		if( !value || !value[0] )
			value = Info_ValueForKey( info, "name" );
		if( value && value[0] )
			Q_strncpy( server->name, value, sizeof( server->name ));
		server->accent = CZM_MapAccent( server->map, server->name );

		server->answerTime = EngFuncs::DoubleTime();
		server->misses = 0;

		// rough ping until the real one arrives
		if( server->ping < 0 )
			server->ping = CZM_PingUpdate( server->ping, (int)(( server->answerTime - server->queryTime ) * 1000.0 ));
		return false;
	}

	value = Info_ValueForKey( info, "czmping" );
	return value && value[0];
}

/*
A late answer to an earlier query can arrive right after a new query of the same
server (the card asks the selected server again and again): it would read as 0 ms.
Internet servers are never that close to a phone, so such a value is ignored and
the next real measurement fills the ping.
*/
int CZM_PingUpdate( int old, int fresh )
{
	if( fresh < 3 )
		return old;
	return fresh;
}

void CZM_ConnectToServer( int index )
{
	CzmServer *server = CZM_Server( index );

	if( !server )
		return;

	EngFuncs::CvarSetString( "czm_connect_name", server->name );
	EngFuncs::CvarSetString( "czm_connect_adr", server->address );
	EngFuncs::ClientCmdF( false, "connect \"%s\" %s\n", server->address, server->prot[0] ? server->prot : "gs" );
}

static CzmServer *CZM_ServerByAddress( const char *address )
{
	for( int i = 0; address && address[0] && i < CZM_ServerCount(); i++ )
	{
		if( !strcmp( CZM_Server( i )->address, address ))
			return CZM_Server( i );
	}
	return NULL;
}

/*
=================
connection errors
=================
*/
static void CZM_CleanReason( const char *in, char *out, size_t size )
{
	size_t len = 0;
	const char *s = in;

	// skip the engine's "Server message" header line
	if( !strncmp( s, "^3", 2 ) && strchr( s, '\n' ))
		s = strchr( s, '\n' ) + 1;

	while( *s && len + 1 < size )
	{
		if( s[0] == '^' && s[1] >= '0' && s[1] <= '9' )
		{
			s += 2;
			continue;
		}

		out[len++] = *s++;
	}

	while( len > 0 && ( out[len - 1] == '\n' || out[len - 1] == ' ' ))
		len--;

	out[len] = 0;
}

// ASCII case-insensitive search, server messages are in English
static bool CZM_Contains( const char *text, const char *word )
{
	for( const char *p = text; *p; p++ )
	{
		const char *a = p, *b = word;

		while( *a && *b && tolower( (unsigned char)*a ) == tolower( (unsigned char)*b ))
			a++, b++;

		if( !*b )
			return true;
	}

	return false;
}

static void CZM_ShowPendingError( void )
{
	const char *error = EngFuncs::GetCvarString( "czm_loading_error" );
	char reason[256], text[512];

	if( !error || !error[0] || !uiStatic.menu.IsActive( ))
		return;

	CZM_CleanReason( error, reason, sizeof( reason ));

	if( !strcmp( reason, "#connect_failed" ))
		snprintf( text, sizeof( text ), "%s", CZM_T( "err_connect" ));
	else if( !strcmp( reason, "#connection_timeout" ))
		snprintf( text, sizeof( text ), "%s", CZM_T( "err_timeout" ));
	else if( CZM_Contains( reason, "full" ))
		snprintf( text, sizeof( text ), "%s", CZM_T( "err_full" ));
	else if( CZM_Contains( reason, "password" ))
		snprintf( text, sizeof( text ), "%s", CZM_T( "err_password" ));
	else if( CZM_Contains( reason, "ban" ))
		snprintf( text, sizeof( text ), "%s\n%s", CZM_T( "err_banned" ), reason );
	else if( CZM_Contains( reason, "kick" ))
		snprintf( text, sizeof( text ), "%s\n%s", CZM_T( "err_kicked" ), reason );
	else
		snprintf( text, sizeof( text ), "%s\n%s", CZM_T( "err_generic" ), reason );

	EngFuncs::CvarSetString( "czm_loading_error", "" );
	UI_ShowMessageBox( text );
}

/*
=================
menu background
=================
*/
static bool s_bGameVisible;

static void CZM_DrawParallaxLayer( HIMAGE image, int x, int y, int w, int h, float dx, float dy, bool alpha )
{
 int iw=EngFuncs::PIC_Width(image),ih=EngFuncs::PIC_Height(image);if(iw<=0||ih<=0)return;
 // Extra image margin covers the full foreground travel, even on narrow screens.
 float scale=Q_max((float)w/iw,(float)h/ih)*1.12f;
 int dw=(int)ceilf(iw*scale),dh=(int)ceilf(ih*scale);
 EngFuncs::PIC_Set(image,255,255,255,255);
 if(alpha)EngFuncs::PIC_DrawTrans(x+(w-dw)/2+(int)dx,y+(h-dh)/2+(int)dy,dw,dh);
 else EngFuncs::PIC_Draw(x+(w-dw)/2+(int)dx,y+(h-dh)/2+(int)dy,dw,dh);
}

void CZM_SetGameVisible( bool visible )
{
	s_bGameVisible = visible;
}

bool CZM_DrawMenuBackground( Point pos, Size size )
{
	HIMAGE art = CZM_Image( "gfx/czm/menu_bg.png" );

	if( !art )
		return false;

	// in the game, keep the world visible behind the pause window and settings
	if( CL_IsActive( ))
	{
		if( !s_bGameVisible )
			UI_FillRect( pos.x, pos.y, size.w, size.h, PackRGBA( 0, 0, 0, 150 ));
		return true;
	}

	HIMAGE environment=0,soldier=0,zombies=0;
	if(EngFuncs::GetCvarFloat("czm_parallax")!=0){
		environment=CZM_Image("gfx/czm/menu_environment.png");
		soldier=CZM_Image("gfx/czm/menu_ct.png");
		zombies=CZM_Image("gfx/czm/menu_zombies.png");
	}
	if(environment&&soldier&&zombies){
		float t=uiStatic.realTime*.001f,w=size.w,h=size.h;
		// A ten-second sweep makes depth visible immediately; smaller independent
		// movements keep the figures from looking like one sliding picture.
		float x=sinf(t*.62f),y=sinf(t*.43f+.75f);
		UI::Scissor::PushScissor(pos.x,pos.y,size.w,size.h);
		CZM_DrawParallaxLayer(environment,pos.x,pos.y,size.w,size.h,x*w*.014f,y*h*.010f,false);
		CZM_DrawParallaxLayer(soldier,pos.x,pos.y,size.w,size.h,
			w*(-x*.028f+.004f*sinf(t*.91f)),h*(-y*.014f+.004f*sinf(t*1.2f)),true);
		CZM_DrawParallaxLayer(zombies,pos.x,pos.y,size.w,size.h,
			w*(-x*.048f+.006f*sinf(t*.9f+.7f)),h*(-y*.021f+.004f*sinf(t*1.4f)),true);
		// A few low-alpha light wisps and sparks, with no moving controls or text.
		for(int i=0;i<3;i++){
			int px=pos.x+(int)(w*(.15f+.31f*i+.025f*sinf(t*.12f+i)));
			int py=pos.y+(int)(h*(.72f+.03f*sinf(t*.16f+i*2)));
			CZM_DrawImage("gfx/czm/ui/dot.png",px-(int)(w*.22f),py,(int)(w*.44f),(int)(h*.32f),i==0?PackRGBA(55,128,210,22):PackRGBA(245,86,47,18),true);
		}
		for(int i=0;i<12;i++){
			float a=fmodf(t*(.075f+i*.0012f)+i*.073f,1.0f);
			int px=pos.x+(int)(w*(.12f+fmodf(i*.137f, .83f)+.008f*sinf(t*.7f+i)));
			int py=pos.y+(int)(h*(1.02f-a*.75f));
			int s=Q_max(2,(int)(h*.006f));
			CZM_DrawImage("gfx/czm/ui/dot.png",px,py,s,s,PackRGBA(255,131,70,(int)(100*sinf(a*3.14159265f))),true);
		}
		UI::Scissor::PopScissor();
	}else CZM_DrawCover( art, pos.x, pos.y, size.w, size.h );
	CZM_DrawFade( "gfx/czm/fade_left.png", pos.x, pos.y, size.w * 0.58f, size.h, 200 );
	CZM_DrawFade( "gfx/czm/fade_bottom.png", pos.x, pos.y + size.h * 0.62f, size.w, size.h * 0.38f + 1, 140 );
	return true;
}

/*
=================
loading screen
=================
*/
static void CZM_DrawInfoRow( int x, int y, int w, CzmServer *cached )
{
	HFont font = CZM_Font( CZMF_LOAD_INFO );
	const char *map = EngFuncs::GetCvarString( "czm_loading_map" );
	const char *players = EngFuncs::GetCvarString( "czm_loading_players" );
	const char *ping = EngFuncs::GetCvarString( "czm_loading_ping" );
	const unsigned int label = PackRGBA( 160, 168, 178, 255 );
	const unsigned int value = PackRGBA( 240, 240, 240, 255 );
	const char *separator = "   ·   ";
	char mapText[64], playersText[32], pingText[32];
	struct { const char *label, *value; } parts[3];
	int count = 0, right = x + w;

	// what the menu already knows about our server fills the gaps
	if(( !map || !map[0] ) && cached && cached->map[0] )
		map = cached->map;
	if(( !players || !players[0] ) && cached && cached->maxplayers > 0 )
	{
		snprintf( playersText, sizeof( playersText ), "%d/%d", cached->players, cached->maxplayers );
		players = playersText;
	}
	if(( !ping || !ping[0] ) && cached && cached->ping > 0 )
	{
		snprintf( pingText, sizeof( pingText ), "%d", cached->ping );
		ping = pingText;
	}

	if( map && map[0] )
	{
		Q_strncpy( mapText, map, sizeof( mapText ));
		parts[count].label = CZM_T( "lbl_map" ), parts[count++].value = mapText;
	}
	if( players && players[0] )
		parts[count].label = CZM_T( "lbl_players" ), parts[count++].value = players;
	if( ping && ping[0] )
	{
		static char pingValue[32];
		snprintf( pingValue, sizeof( pingValue ), "%s %s", ping, CZM_T( "ms" ));
		parts[count].label = CZM_T( "lbl_ping" ), parts[count++].value = pingValue;
	}

	for( int i = 0; i < count && x < right; i++ )
	{
		char label_text[64];

		if( i > 0 )
		{
			CZM_DrawText( font, x, y, right - x, separator, label );
			x += CZM_TextWidth( font, separator );
		}

		snprintf( label_text, sizeof( label_text ), "%s  ", parts[i].label );
		CZM_DrawText( font, x, y, right - x, label_text, label );
		x += CZM_TextWidth( font, label_text );
		CZM_DrawText( font, x, y, right - x, parts[i].value, value );
		x += CZM_TextWidth( font, parts[i].value );
	}
}

static void CZM_FormatMegabytes( char *buf, size_t size, int bytes )
{
	snprintf( buf, size, "%.1f", bytes / ( 1024.0f * 1024.0f ));
	if( CZM_IsRussian( ))
	{
		for( char *p = buf; *p; p++ )
		{
			if( *p == '.' )
				*p = ',';
		}
	}
}

static void CZM_StageText( int stage, char *buf, size_t size )
{
	switch( stage )
	{
	case CZM_STAGE_LOCAL:
		snprintf( buf, size, "%s", CZM_T( "st_local" ));
		break;
	case CZM_STAGE_HANDSHAKE:
		snprintf( buf, size, "%s", CZM_T( "st_handshake" ));
		break;
	case CZM_STAGE_DOWNLOAD:
	{
		int files_done = 0, files_total = 0, bytes_done = 0, bytes_total = 0, speed = 0;
		char done[32], total[32], rate[48];
		const char *sep = "   ·   ";

		sscanf( EngFuncs::GetCvarString( "czm_loading_dl" ), "%d %d %d %d %d",
			&files_done, &files_total, &bytes_done, &bytes_total, &speed );

		if( files_total <= 0 )
		{
			snprintf( buf, size, "%s…", CZM_T( "st_download" ));
			break;
		}

		files_done = Q_min( files_done + 1, files_total ); // the file being downloaded now

		if( speed >= 1024 * 1024 )
		{
			char mb[32];
			CZM_FormatMegabytes( mb, sizeof( mb ), speed );
			snprintf( rate, sizeof( rate ), "%s%s %s", sep, mb, CZM_T( "mbps" ));
		}
		else if( speed > 0 )
			snprintf( rate, sizeof( rate ), "%s%d %s", sep, Q_max( 1, speed / 1024 ), CZM_T( "kbps" ));
		else rate[0] = 0;

		if( bytes_total > 0 )
		{
			CZM_FormatMegabytes( done, sizeof( done ), bytes_done );
			CZM_FormatMegabytes( total, sizeof( total ), bytes_total );
			snprintf( buf, size, "%s%s%d %s %d%s%s %s %s %s%s", CZM_T( "st_download" ), sep, files_done, CZM_T( "of" ),
				files_total, sep, done, CZM_T( "of" ), total, CZM_T( "mb" ), rate );
		}
		else
		{
			snprintf( buf, size, "%s%s%d %s %d%s", CZM_T( "st_download" ), sep, files_done, CZM_T( "of" ), files_total, rate );
		}
		break;
	}
	case CZM_STAGE_PRECACHE:
		snprintf( buf, size, "%s", CZM_T( "st_precache" ));
		break;
	case CZM_STAGE_ENTER:
		snprintf( buf, size, "%s", CZM_T( "st_enter" ));
		break;
	case CZM_STAGE_CONNECT:
	default:
		snprintf( buf, size, "%s", CZM_T( "st_connect" ));
		break;
	}
}

static void CZM_DrawProgressBar( int x0, int x1, int y, int h, float percent )
{
	const int count = 40;
	int gap = Q_max( 2, (int)( ScreenWidth * 0.0032f ));
	float segment = (float)( x1 - x0 - gap * ( count - 1 )) / count;
	float filled = bound( 0.0f, percent, 100.0f ) * count / 100.0f;

	for( int i = 0; i < count; i++ )
	{
		int sx = x0 + (int)( i * ( segment + gap ));
		int sw = (int)segment;
		float fraction = bound( 0.0f, filled - i, 1.0f );

		UI_FillRect( sx, y, sw, h, PackRGBA( 255, 255, 255, 46 ));

		if( fraction > 0.0f )
		{
			float k = (float)i / ( count - 1 );
			unsigned int color = PackRGBA( (int)( 196 + 59 * k ), (int)( 18 + 88 * k ), (int)( 18 + 8 * k ), 255 );
			UI_FillRect( sx, y, Q_max( 1, (int)( sw * fraction )), h, color );
		}
	}
}

static void CZM_DrawCancelButton( void )
{
	HFont font = CZM_Font( CZMF_BUTTON );
	int x0 = ScreenWidth * CZM_CANCEL_X0, x1 = ScreenWidth * CZM_CANCEL_X1;
	int y0 = ScreenHeight * CZM_CANCEL_Y0, y1 = ScreenHeight * CZM_CANCEL_Y1;
	int border = Q_max( 2, ScreenHeight / 400 );
	int th = CZM_FontHeight( font );

	UI_FillRect( x0, y0, x1 - x0, y1 - y0, PackRGBA( 0, 0, 0, 110 ));
	UI_DrawRectangleExt( x0, y0, x1 - x0, y1 - y0, PackRGBA( 255, 255, 255, 170 ), border );
	CZM_DrawText( font, x0, y0 + ( y1 - y0 - th ) / 2, x1 - x0, CZM_T( "cancel" ), PackRGBA( 255, 255, 255, 255 ), QM_CENTER );
#ifdef __ANDROID__
	if( EngFuncs::GetCvarFloat( "czm_loading_stage" ) <= CZM_STAGE_DOWNLOAD )
	{
		y0 = ScreenHeight * CZM_BACKGROUND_Y0;
		y1 = ScreenHeight * CZM_BACKGROUND_Y1;
		const char *label = CZM_IsRussian() ? "Скачать в фоне" : "Download in background";
		int padding = Q_max( 4, ( x1 - x0 ) / 24 );
		int textWidth = CZM_TextWidth( font, label );
		int tall = textWidth > x1 - x0 - 2 * padding
			? Q_max( 1, th * ( x1 - x0 - 2 * padding ) / textWidth ) : th;
		UI_FillRect( x0, y0, x1 - x0, y1 - y0, PackRGBA( 145, 20, 32, 215 ));
		UI_DrawString( font, x0 + padding, y0 + ( y1 - y0 - tall ) / 2, x1 - x0 - 2 * padding,
			tall, label, PackRGBA( 255, 255, 255, 255 ), tall, QM_CENTER | QM_TOP, ETF_NO_WRAP | ETF_FORCECOL );
	}
#endif
}

bool CZM_DrawLoadingScreen( void )
{
	static int lastSession = -1, image = 0, tip = 0;
	const int W = ScreenWidth, H = ScreenHeight;
	int session, stage, x0, x1, percentTop;
	float percent;
	char text[256];
	const char *title;
	CzmServer *cached;

	CZM_Init();

	if( EngFuncs::GetCvarFloat( "czm_loading" ) == 0.0f )
	{
		CZM_ShowPendingError();
		return false;
	}

	// new picture and tip for every loading
	session = (int)EngFuncs::GetCvarFloat( "czm_loading_session" );
	if( session != lastSession )
	{
		static bool seeded = false;
		int next;

		if( !seeded )
		{
			srand( (unsigned int)time( NULL ));
			seeded = true;
		}

		do next = rand() % CZM_LOADING_IMAGES;
		while( next == image && lastSession >= 0 && CZM_LOADING_IMAGES > 1 );

		image = next;
		tip = rand() % CZM_TIPS;
		lastSession = session;
	}

	stage = (int)EngFuncs::GetCvarFloat( "czm_loading_stage" );
	percent = EngFuncs::GetCvarFloat( "scr_loading" );
	cached = CZM_ServerByAddress( EngFuncs::GetCvarString( "czm_connect_adr" ));

	snprintf( text, sizeof( text ), "gfx/czm/loading_%d.png", image + 1 );
	CZM_DrawCover( CZM_Image( text ), 0, 0, W, H );
	CZM_DrawFade( "gfx/czm/fade_left.png", 0, 0, W * 0.62f, H, 150 );
	CZM_DrawFade( "gfx/czm/fade_bottom.png", 0, H * 0.36f, W, H * 0.64f + 1, 240 );
	CZM_DrawTitle( W * 0.045f, H * 0.06f, H * 0.07f );

	x0 = W * 0.045f;
	x1 = W * 0.775f;

	// our mode name, the server's own name only if we connect somewhere else
	title = EngFuncs::GetCvarString( "czm_connect_name" );
	if( !cached || !title || !title[0] )
		title = EngFuncs::GetCvarString( "czm_loading_host" );

	CZM_DrawText( CZM_Font( CZMF_LOAD_HOST ), x0, H * 0.56f, x1 - x0, title, PackRGBA( 255, 255, 255, 255 ));
	CZM_DrawInfoRow( x0, H * 0.655f, x1 - x0, cached );
	snprintf( text, sizeof( text ), "tip%d", tip + 1 );
	CZM_DrawText( CZM_Font( CZMF_LOAD_TIP ), x0, H * 0.712f, x1 - x0, CZM_T( text ), PackRGBA( 205, 205, 205, 255 ));

	CZM_StageText( stage, text, sizeof( text ));
	percentTop = H * 0.845f - CZM_FontHeight( CZM_Font( CZMF_LOAD_PERCENT ));
	CZM_DrawText( CZM_Font( CZMF_LOAD_STATUS ), x0, H * 0.795f, ( x1 - x0 ) * 0.8f, text, PackRGBA( 235, 235, 235, 255 ));

	snprintf( text, sizeof( text ), "%d%%", (int)percent );
	CZM_DrawText( CZM_Font( CZMF_LOAD_PERCENT ), x0, percentTop, x1 - x0, text, PackRGBA( 255, 255, 255, 255 ), QM_RIGHT );

	CZM_DrawProgressBar( x0, x1, H * 0.852f, Q_max( 4, (int)( H * 0.024f )), percent );
	CZM_DrawCancelButton();

	return true;
}

/*
=================
shared pieces of our windows
=================
*/
bool CzmRect::HasCursor( void ) const
{
	return Contains( uiStatic.cursorX, uiStatic.cursorY );
}

CzmRect CZM_Rect( int x, int y, int w, int h )
{
	CzmRect r = { x, y, w, h };
	return r;
}

unsigned int CZM_White( int alpha )
{
	return PackRGBA( 255, 255, 255, alpha );
}

unsigned int CZM_Grey( void )
{
	return PackRGBA( 170, 176, 186, 255 );
}

int CZM_LineWidth( void )
{
	return Q_max( 1, ScreenHeight / 600 );
}

void CZM_PlayClick( void )
{
	EngFuncs::PlayLocalSound( uiStatic.sounds[SND_LAUNCH] );
}

void CZM_MenuAudioFrame( void )
{
	static bool playing;
	CZM_Init();
	const bool inMenu = !CL_IsActive() && !gpGlobals->demoplayback && uiStatic.menu.IsActive()
		&& EngFuncs::GetCvarFloat( "czm_loading_stage" ) == CZM_STAGE_NONE;
	if( !inMenu )
	{
		if( playing ) EngFuncs::StopBackgroundTrack();
		playing = false;
		return;
	}
	if( !playing )
	{
		EngFuncs::PlayBackgroundTrack( "media/czm_sound.mp3", "media/czm_sound.mp3" );
		playing = true;
	}
}

void CZM_DrawPanel( const CzmRect &r )
{
	CZM_DrawSliced( "gfx/czm/ui/panel.png", r.x, r.y, r.w, r.h, 40, (int)( ScreenHeight * 0.026f ));
}

void CZM_DrawButton( const char *image, const CzmRect &r, const char *label, unsigned int textColor, bool pressed, int font )
{
	HFont hfont = CZM_Font( font );

	CZM_DrawPill( image, r.x, r.y, r.w, r.h, pressed ? PackRGBA( 185, 185, 185, 255 ) : CZM_White());
	CZM_DrawText( hfont, r.x + r.h / 4, r.y + ( r.h - CZM_FontHeight( hfont )) / 2, r.w - r.h / 2, label, textColor, QM_CENTER );
}

/*
=================
text input
=================
*/
void CzmTextEdit::Begin( const char *initial, const CzmRect &r )
{
	Q_strncpy( text, initial ? initial : "", sizeof( text ));
	active = true;
	EngFuncs::SetTextInputRect( r.x, r.y, r.w, r.h );
	UI_EnableTextInput( true );
}

void CzmTextEdit::End( void )
{
	if( !active )
		return;

	active = false;
	UI_EnableTextInput( false );
}

bool CzmTextEdit::KeyDown( int key )
{
	if( !active )
		return false;

	if( UI::Key::IsBackspace( key ))
	{
		size_t len = strlen( text );

		// remove one whole UTF-8 character
		if( len > 0 )
		{
			len--;
			while( len > 0 && ( (unsigned char)text[len] & 0xC0 ) == 0x80 )
				len--;
			text[len] = 0;
		}
		return true;
	}

	if( UI::Key::IsEnter( key ))
	{
		End();
		return true;
	}

	return false;
}

void CzmTextEdit::Char( int ch )
{
	size_t len;

	// characters that break names in commands and colour codes
	if( !active || ch < 32 || ch == '"' || ch == '\\' || ch == '^' || ch == ';' || ch == '%' )
		return;

	len = strlen( text );

	// keep room for a whole UTF-8 character
	if( len + ( ch >= 0xC0 ? 4 : 1 ) >= sizeof( text ))
		return;

	text[len] = (char)ch;
	text[len + 1] = 0;
}

void CZM_DrawField( const CzmRect &r, const CzmTextEdit &edit, const char *value, const char *placeholder, bool pressed )
{
	HFont font = CZM_Font( CZMF_TILE_STATUS );
	int pad = r.h * 0.45f;
	int textY = r.y + ( r.h - CZM_FontHeight( font )) / 2;
	int pencil = r.h * 0.40f;
	const char *text = edit.active ? edit.text : value;

	CZM_DrawPill( edit.active ? "gfx/czm/ui/button_danger.png" : "gfx/czm/ui/button_secondary.png",
		r.x, r.y, r.w, r.h, pressed ? PackRGBA( 200, 200, 200, 255 ) : CZM_White());

	if( text && text[0] )
		CZM_DrawText( font, r.x + pad, textY, r.w - pad * 2 - pencil, text, CZM_White());
	else
		CZM_DrawText( font, r.x + pad, textY, r.w - pad * 2 - pencil, placeholder, PackRGBA( 130, 136, 146, 255 ));

	if( edit.active )
	{
		// blinking cursor after the text
		if(( uiStatic.realTime / 500 ) % 2 == 0 )
		{
			int x = r.x + pad + Q_min( CZM_TextWidth( font, text ), r.w - pad * 2 - pencil ) + 2;
			UI_FillRect( x, textY, Q_max( 2, ScreenHeight / 400 ), CZM_FontHeight( font ), PackRGBA( 239, 68, 68, 255 ));
		}
	}
	else
	{
		CZM_DrawImage( "gfx/czm/ui/icon_pencil.png", r.x + r.w - pad - pencil, r.y + ( r.h - pencil ) / 2, pencil, pencil,
			PackRGBA( 200, 205, 215, 255 ));
	}
}

/*
=================
nickname and sprays
=================
*/
static int CZM_Utf8Length( const char *s )
{
	int count = 0;

	for( ; *s; s++ )
	{
		if(( (unsigned char)*s & 0xC0 ) != 0x80 )
			count++;
	}

	return count;
}

bool CZM_NickIsValid( const char *nick )
{
	// names the engine and stock configs give everyone, servers dislike them
	static const char *stock[] = { "CS_Mobile_Xash3D", "Player", "unnamed" };
	char clean[64];
	const char *s;
	int letters = 0;

	if( !nick )
		return false;

	CZM_CleanName( nick, clean, sizeof( clean ));

	for( s = clean; *s; s++ )
	{
		if( *s != ' ' )
			letters++;
	}

	if( letters < 2 || CZM_Utf8Length( clean ) < 2 )
		return false;

	for( size_t i = 0; i < sizeof( stock ) / sizeof( stock[0] ); i++ )
	{
		if( !stricmp( clean, stock[i] ))
			return false;
	}

	return true;
}

void CZM_SetNick( const char *nick )
{
	EngFuncs::CvarSetString( "name", nick );
}

static const char *s_sprays[] =
{
	"czm_logo", "czm_zombie", "czm_hunter", "czm_soldier", "czm_biohazard",
	"czm_skull", "czm_claws", "czm_gg", "czm_zm",
};
static char s_preparedSpray[32];
static double s_sprayRetry;

int CZM_SprayCount( void )
{
	return sizeof( s_sprays ) / sizeof( s_sprays[0] );
}

const char *CZM_SprayName( int index )
{
	return ( index >= 0 && index < CZM_SprayCount()) ? s_sprays[index] : "";
}

const char *CZM_SprayImage( int index )
{
	static char path[64];

	snprintf( path, sizeof( path ), "logos/%s.png", CZM_SprayName( index ));
	return path;
}

int CZM_CurrentSpray( void )
{
	const char *current = EngFuncs::GetCvarString( "cl_logofile" );

	for( int i = 0; current && i < CZM_SprayCount(); i++ )
	{
		if( !stricmp( current, s_sprays[i] ))
			return i;
	}

	return -1;
}

void CZM_SetSpray( int index )
{
	int length = 0;
	byte *data;

	if( index < 0 || index >= CZM_SprayCount())
		return;

	// Keep the legacy menu cache in sync; the engine uploads the selected source PNG.
	data = EngFuncs::COM_LoadFile( CZM_SprayImage( index ), &length );
	if( !data || length <= 0 )
		return;

	int saved = EngFuncs::COM_SaveFile( "logos/remapped.png", data, length );
	EngFuncs::COM_FreeFile( data );
	if( !saved )
		return;
	EngFuncs::DeleteFile( "logos/remapped.bmp" );

	EngFuncs::CvarSetString( "cl_logoext", "png" );
	EngFuncs::CvarSetString( "cl_logofile", s_sprays[index] );
	EngFuncs::CvarSetValue( "cl_allowupload", 1 );
	EngFuncs::CvarSetValue( "@cl_logoupdate", !EngFuncs::GetCvarFloat( "@cl_logoupdate" ));
	Q_strncpy( s_preparedSpray, s_sprays[index], sizeof( s_preparedSpray ));
}

void CZM_SprayFrame( void )
{
	int index=CZM_CurrentSpray();
	const char *name=EngFuncs::GetCvarString("cl_logofile");
	if(EngFuncs::DoubleTime()<s_sprayRetry)return;
	if(index<0 && name && !strcmp(name,"lambda")){
		index=0;
		for(int i=0;i<CZM_SprayCount();i++)if(!strcmp(s_preparedSpray,s_sprays[i]))index=i;
	}
	if(index>=0 && (strcmp(s_preparedSpray,s_sprays[index]) || strcmp(name,s_sprays[index]) || strcmp(EngFuncs::GetCvarString("cl_logoext"),"png"))){
		s_sprayRetry=EngFuncs::DoubleTime()+2.0;
		CZM_SetSpray(index);
	}
}

/*
=================
avatars

czm_avatar: "" the game logo, "1".."10" our pictures, "photo:czm_avatar_N.png" the player's
own photo. The photo comes from the gallery through AvatarPickerActivity.java: the menu
picks a new file name, opens czmavatar://pick?file=<name> and waits for the file to appear
in the game folder. A new name every time, so the engine never shows an old picture.
=================
*/
#define CZM_AVATARS 10
#define CZM_AVATAR_WAIT 300.0 // seconds the gallery may stay open

static char s_avatarPending[64];
static double s_avatarPendingTime;

int CZM_AvatarCount( void )
{
	return CZM_AVATARS;
}

const char *CZM_AvatarImage( int index )
{
	static char path[64];

	if( index < 0 || index >= CZM_AVATARS )
		return "gfx/czm/ui/avatar.png";

	snprintf( path, sizeof( path ), "gfx/czm/avatars/avatar_%02d.png", index + 1 );
	return path;
}

// the photo file, "" if there is none
const char *CZM_AvatarPhoto( void )
{
	static char checked[64];
	static bool exists;
	const char *value = EngFuncs::GetCvarString( "czm_avatar_photo" );

	if( !value || !value[0] )
		return "";

	// A pending download can appear later under the same filename.
	if( strcmp( checked, value ) || !exists )
	{
		Q_strncpy( checked, value, sizeof( checked ));
		exists = EngFuncs::FileExists( value, true ) != 0;
	}

	return exists ? value : "";
}

int CZM_CurrentAvatar( void )
{
	const char *value = EngFuncs::GetCvarString( "czm_avatar" );
	int index;

	if( !value || !value[0] )
		return CZM_AVATAR_LOGO;
	if( !strcmp( value, "photo" ))
		return CZM_AvatarPhoto()[0] ? CZM_AVATAR_PHOTO : CZM_AVATAR_LOGO;

	index = atoi( value ) - 1;
	return ( index >= 0 && index < CZM_AVATARS ) ? index : CZM_AVATAR_LOGO;
}

const char *CZM_CurrentAvatarImage( void )
{
	int current = CZM_CurrentAvatar();

	if( current == CZM_AVATAR_PHOTO )
		return CZM_AvatarPhoto();
	return CZM_AvatarImage( current );
}

void CZM_SetAvatar( int index )
{
	char value[16];

	CZM_Init();
	if( index == CZM_AVATAR_PHOTO )
		Q_strncpy( value, CZM_AvatarPhoto()[0] ? "photo" : "", sizeof( value ));
	else if( index >= 0 && index < CZM_AVATARS )
		snprintf( value, sizeof( value ), "%d", index + 1 );
	else
		value[0] = 0;

	EngFuncs::CvarSetString( "czm_avatar", value );
	EngFuncs::ClientCmd( false, "host_writeconfig\n" );
}

void CZM_PickAvatarPhoto( void )
{
	char url[128];

	snprintf( s_avatarPending, sizeof( s_avatarPending ), "czm_avatar_%d.png", EngFuncs::RandomLong( 100000, 999999 ));
	s_avatarPendingTime = EngFuncs::DoubleTime();
	snprintf( url, sizeof( url ), "czmavatar://pick?file=%s", s_avatarPending );
	EngFuncs::ShellExecute( url, NULL, false );
}

bool CZM_AvatarPending( void )
{
	static double lastCheck;
	double now = EngFuncs::DoubleTime();

	if( !s_avatarPending[0] )
		return false;

	if( now - s_avatarPendingTime > CZM_AVATAR_WAIT )
	{
		s_avatarPending[0] = 0;
		return false;
	}

	// the gallery wrote the photo: it becomes the avatar
	if( now - lastCheck > 0.5 )
	{
		lastCheck = now;
		if( EngFuncs::FileExists( s_avatarPending, true ))
		{
			EngFuncs::CvarSetString( "czm_avatar_photo", s_avatarPending );
			s_avatarPending[0] = 0;
			CZM_SetAvatar( CZM_AVATAR_PHOTO );
			return false;
		}
	}

	return true;
}

/*
=================
first start and startup settings
=================
*/
static void CZM_RegisterSettingsCvars( void )
{
	CZM_Init();
}

bool CZM_FirstStart( void )
{
	CZM_RegisterSettingsCvars();
	return EngFuncs::GetCvarFloat( "czm_setup" ) == 0.0f;
}

void CZM_FinishFirstStart( void )
{
	CZM_RegisterSettingsCvars();
	EngFuncs::CvarSetValue( "czm_setup", 1.0f );

	if( CZM_CurrentSpray() < 0 )
		CZM_SetSpray( 0 );

	EngFuncs::ClientCmd( false, "host_writeconfig\n" );
}

void CZM_ApplyStartupSettings( void )
{
	CZM_RegisterSettingsCvars();

	// the client does not save the zoom sensitivity, we keep our own copy
	EngFuncs::CvarSetValue( "zoom_sensitivity_ratio", EngFuncs::GetCvarFloat( "czm_zoom_sens" ));

	// settings players no longer see: smooth network play and server downloads
	if( EngFuncs::GetCvarFloat( "czm_defaults" ) < 1.0f )
	{
		EngFuncs::CvarSetValue( "rate", 100000.0f );
		EngFuncs::CvarSetValue( "cl_updaterate", 60.0f );
		EngFuncs::CvarSetValue( "cl_cmdrate", 60.0f );
		EngFuncs::CvarSetValue( "czm_defaults", 1.0f );
	}

	// version 2: smoother hit registration on good internet (the engine keeps it under the FPS),
	// readable chat on phone screens
	if( EngFuncs::GetCvarFloat( "czm_defaults" ) < 2.0f )
	{
		EngFuncs::CvarSetValue( "cl_updaterate", 101.0f );
		EngFuncs::CvarSetValue( "cl_cmdrate", 101.0f );
		EngFuncs::CvarSetValue( "con_fontscale", 2.0f );
		EngFuncs::CvarSetValue( "czm_defaults", 2.0f );
	}

	EngFuncs::CvarSetValue( "cl_allowdownload", 1.0f );

	CZM_TouchStartup();
}

void CZM_CloudFrame( void )
{
 CUtlString body;if(!CZM_CloudEvent(body))return;
 CzmJson j;if(!j.Parse(body.Get()))return;
 int cvars=j.Get(0,"cvars"),files=j.Get(0,"files");
 const int request=(int)j.Number(j.Get(0,"cloudId"));
 if(j.Type(cvars)!=CzmJson::T_OBJECT || j.Type(files)!=CzmJson::T_OBJECT){if(request>0)CZM_CloudApplied(request,false);return;}
 // The Java boundary validates the data schema and constructs commands from allowlisted actions.
 CUtlString backup[3];bool existed[3]={false,false,false},written[3]={false,false,false};bool success=true;
 for(int i=1;i<=3;i++) {
  char index[8],path[80];snprintf(index,sizeof(index),"%d",i);int n=j.Get(files,index);if(j.Type(n)!=CzmJson::T_STRING)continue;
  snprintf(path,sizeof(path),"touch_profiles/czm_scheme%d.cfg",i);const char *cfg=j.String(n);
  int length=0;byte *old=EngFuncs::COM_LoadFile(path,&length);existed[i-1]=old!=NULL;
  if(old){backup[i-1].SetDirect((char *)old,length);EngFuncs::COM_FreeFile(old);}
  written[i-1]=true;
  if(!EngFuncs::COM_SaveFile(path,(void *)cfg,strlen(cfg))){success=false;break;}
 }
 if(!success){
  for(int i=0;i<3;i++)if(written[i]){char path[80];snprintf(path,sizeof(path),"touch_profiles/czm_scheme%d.cfg",i+1);if(existed[i])EngFuncs::COM_SaveFile(path,backup[i].Get(),backup[i].Length());else EngFuncs::DeleteFile(path);}
  if(request>0)CZM_CloudApplied(request,false);return;
 }
 for(size_t i=0;i<sizeof(czm_settings_names)/sizeof(czm_settings_names[0]);i++) {
  int n=j.Get(cvars,czm_settings_names[i]);if(j.Type(n)==CzmJson::T_STRING)EngFuncs::CvarSetString(czm_settings_names[i],j.String(n));
 }
 CZM_SetTouchScheme(CZM_TouchScheme(),false);EngFuncs::ClientCmd(true,"host_writeconfig\n");if(request>0)CZM_CloudApplied(request,true);
}
