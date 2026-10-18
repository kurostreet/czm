# Counter Zombie Mobile 32 players

<img align="right" width="160" height="160" src="assets/branding/logo-512.png" alt="Counter Zombie Mobile 32 players" />

Мобильный зомби-шутер на движке [Xash3D FWGS](https://github.com/FWGS/xash3d-fwgs).
Рабочая ветка: `feature/mobile-launcher`. Исходный `main` сохранён.

## Один APK

Движок Xash3D, SDL, клиент, меню, серверная библиотека и боты собираются из исходников
и работают внутри одного Android-приложения. Все компоненты устанавливаются одним APK.

Полный тестовый APK включает предоставленный владельцем архив игровых ресурсов.
Первый запуск проверяет и распаковывает данные автоматически, показывает прогресс
и открывает игру. Следующие запуски используют подготовленные данные.
Ручное копирование файлов в `/sdcard/xash` не требуется.

- Название: **Counter Zombie Mobile 32 players**.
- Пакет: `ru.kurostreet.counterzombiemobile` (`.test` у тестовых сборок).
- Одна иконка запуска с нашим логотипом.
- Игровые ресурсы и настройки игрока хранятся раздельно, во внутренней папке приложения.
- Контроль SHA-256, CRC, путей и размера при подготовке ресурсов.
- Избранные серверы на главной, поиск и фильтры, профиль, чат и автоматические обновления.
- 32 players — утверждённое название; нагрузочные испытания на 32 игрока ещё не проведены.

## Сборка

```sh
git clone --recurse-submodules https://github.com/kurostreet/czm.git
cd czm
git switch feature/mobile-launcher
python3 scripts/prepare_game_bundle.py /path/to/game-cache.zip android/offline-assets
cd android
CZM_GAME_ASSETS_DIR="$PWD/offline-assets" ./gradlew assembleGitDebug
```

Нужны Java 21, Python 3.11+, Ninja, CMake, Android SDK 36 и NDK 28.2.13676358.
Движок закреплён на коммите `51353ff8d65e58300eeb2bd014867673f1f367c6`;
SDL — `98d1f3a45aae568ccd6ed5fec179330f47d4d356` (2.32.8).

[GitHub Actions](https://github.com/kurostreet/czm/actions) собирает
**Core APK** с движком и клиентом, без закрытого архива игровых данных.
Это промежуточный артефакт сборки. Инструкция добавления локального архива:
[STANDALONE_ANDROID_RU.md](docs/STANDALONE_ANDROID_RU.md).

Результат проверки полного APK: [STANDALONE_TEST_2026-10-10.md](docs/STANDALONE_TEST_2026-10-10.md).

## Лицензии и дальнейшая разработка

Исходные лицензии и уведомления авторов сохранены:
[Уведомления исходных авторов](docs/UPSTREAM_README.md), [LICENSE](LICENSE),
[Xash3D FWGS](3rdparty/xash3d-fwgs), [SDL](3rdparty/SDL).
Игровые модели, карты, звуки и текстуры имеют отдельные условия распространения;
для публичного выпуска и Google Play нужны соответствующие права.

### Музыка главного меню

Игрок выбирает трек в «Настройки → Звук → Трек меню». Файлы в `3rdparty/cs16client-extras/media/`:

- `czm_music_silent.mp3` (по умолчанию) — «The World Fell Silent», автор Tsorthan Grove,
  [OpenGameArt](https://opengameart.org/node/177977), лицензия [CC0](https://creativecommons.org/publicdomain/zero/1.0/).
  Изменения: версия-петля, 44,1 кГц, MP3 160 кбит/с, громкость +0,4 дБ.
- `czm_music_city.mp3` — «EmptyCity: Background Music», автор yd,
  [OpenGameArt](https://opengameart.org/node/6681), лицензия CC0.
- `czm_music_thoughts.mp3` — «Contemplation», автор Joth,
  [OpenGameArt](https://opengameart.org/node/85636), лицензия CC0.
- `czm_sound.mp3` — трек «menu_loop_rain_3» из набора
  [Unreleased Zombie soundtrack](https://opengameart.org/content/unreleased-zombie-soundtrack),
  автор — Emma M. Andersson (Emma_MA), лицензия [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/).
  Изменения: перекодирован из WAV в MP3 160 кбит/с, громкость понижена на 0,4 дБ.

Текущий план: [ROADMAP_RU.md](docs/ROADMAP_RU.md).
Исходный план: [MOBILE_LAUNCHER_PLAN_RU.md](docs/MOBILE_LAUNCHER_PLAN_RU.md).
Оформление: [BRANDING_RU.md](docs/BRANDING_RU.md).
Меню и экран загрузки: [LOADING_SCREEN_RU.md](docs/LOADING_SCREEN_RU.md).
Новое главное меню: [MAIN_SCREEN_RU.md](docs/MAIN_SCREEN_RU.md).
Настройки, спреи, первый запуск: [SETTINGS_RU.md](docs/SETTINGS_RU.md).
Кнопки на экране и редактор раскладки: [TOUCH_BUTTONS_RU.md](docs/TOUCH_BUTTONS_RU.md).
Магазин и меню сервера карточками: [SHOP_RU.md](docs/SHOP_RU.md).
Список серверов: [SERVERS_RU.md](docs/SERVERS_RU.md).
Чат, колокольчик, обновления: [ONLINE_RU.md](docs/ONLINE_RU.md), сервер: [server/czm](server/czm/README_RU.md).
