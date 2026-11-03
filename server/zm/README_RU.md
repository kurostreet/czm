# Сервер Survival (перенос Kontra на CS 1.6)

Тестовый сервер: `194.226.112.249:27016` (`czm-zm-test.service`, `/srv/czm-zm-test/game`).
Движок: ReHLDS + ReGameDLL + Metamod + AMX Mod X 1.10 + Zombie Plague 4.3 + ReAPI + AmxxEasyHttp.

## Что откуда

| Kontra (Lua) | Здесь |
|---|---|
| SoundWelcome, Z_RoundRandomSongs, EndGameMusic, Music_AutoPlay, SoundChangeMap, Sound_weather, SoundZombieAtack, ZOMBIE_BULLET_PAIN, heartbeat_T_CT | `czm_sounds.amxx` |
| AUTO_LANGUAGE, /sound_on /sound_off, /info_on /info_off | `czm_core.amxx` |
| ZombieAutoRevive | `czm_revive.amxx` |
| AmmoManager | `czm_ammo.amxx` |
| ADS_HUD | `czm_info.amxx` |
| LVL_MOD (уровни, токены, магазин, прокачка, пропуск, перевод, промокоды, топ карты, лавка) | `czm_lvl.amxx` + API `server/czm/czm/survival.py` |
| Ящик с оружием, критические пули, звуки оружия, аирдроп | `czm_lvl_fx.amxx` |
| GAME_MENU, голосования (кик, мут, карта, rtv), TeleportRequest, сообщения админам, новости | `czm_game.amxx` |
| A_ADMIN_MENU, A_BAN_MANAGER, привилегии VIP+ / PREMIUM / DELUXE / TESTER, LogsServer | `czm_admin.amxx` + API `server/czm/czm/survival_mod.py` |
| WEB_AUTH_BRIDGE, WEB_CONTROL_BRIDGE, сайт kontra-main | `/panel` на counter-zombie.ru |

Ещё не перенесено: PropsManager, Strafes, дуэли, мини-карта (в CS есть свой радар).

Скины Gsg9 admin, Sas custom, Leet pirate, Professional и Survivor — свои модели
`models/player/czm_*` (откуда — в `CREDITS.md`); остальные скины — стоковые модели CS.
Если своей модели на сервере нет, игрок получает стоковую из поля `base` каталога.

Картинки скинов и ножей в панели рисует `tools/render_models.py` из этих же моделей (поза и
оружие как в игре, ножи — как их видит игрок) при установке контента: `/zm-test-files/czm-art/`.
Пока картинки нет, панель показывает прежнюю из `site/assets/lvl/`.

## Профиль игрока

Игра перед подключением к нашему серверу берёт у API билет (`/api/v1/game/ticket`) и кладёт его в
`setinfo _czm`; через минуту убирает. `czm_core` проверяет подпись ключом
`/etc/czm/game-ticket.key` и адресом сервера (`czm_public_address`). Без билета игрок — гость:
звуки и меню есть, LVL MOD нет.

## Экономика

Все числа — в API (`survival.py`), игровой сервер только сообщает события и показывает ответ.
У каждого сервера своя экономика, как на Kontra: режим задаёт `czm_server_name` в server.cfg —
`survival` (ZM) или `escape` (ZE); плагины добавляют его к каждому запросу (`?mode=`), а панель
игрока переключает серверы вверху страницы. Профиль, вход, промокоды, баны и новости — общие.
Второй сервер (Escape) — те же плагины с `czm_server_name "escape"` и своим `czm_public_address`;
адрес вписывается в слот Escape в админ-настройках игры, и он сразу появляется в игре и в панели.

- раз в 10 секунд пачка (`/survival/server/report`): время, убийства, раунды; пачка повторяется
  с тем же номером, пока API не ответит, — дважды не засчитывается;
- покупки из меню игры и с сайта идут одной функцией `survival.action` с номером операции;
- сервер подписывается заголовком `X-CZM-Server` = sha256(ключ билетов + `|server`).

Промокоды создаёт владелец в боте: `/promo free50k tokens 50000`, `/promo free20lvl lvl 20`,
`/promo del код`, `/promo` — список. Игроки вводят `/promo КОД` в игре или на сайте.

## Установка

С телефона: `~/.czm-zm.sh <commit> check|install|content`
(`content` ещё раз ставит карты, звуки и модели из `/var/lib/czm/survival-src`).
`deploy/install.sh` сначала собирает все плагины, при ошибке ничего не меняет; конфиги
дописываются блоками между `// >>> CZM Survival` и `// <<< CZM Survival`; копия прежних
конфигов и плагинов — `/var/backups/czm-zm/before-*.tgz`.

Карты Kontra и звуки — данные владельца, лежат только на сервере (`/var/lib/czm/survival-src`),
в репозиторий не попадают. Сторонние файлы перечислены в `CREDITS.md`.
