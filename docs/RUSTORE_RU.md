# RuStore

Игра в RuStore — отдельная сборка `rustore`:

- пакет `ru.kurostreet.counterzombiemobile` (основной идентификатор игры, см. BRANDING_RU.md).
  Версия из Google Play (`dev.gaming.czm`) и тестовая с сайта (`.test`) ставятся рядом, конфликта подписей нет;
- обновляет RuStore: в сборке нет своего установщика, разрешения REQUEST_INSTALL_PACKAGES и библиотек Google Play.
  Колокольчик об обновлениях молчит, `StoreUpdates.start` открывает карточку игры в RuStore;
- аккаунт разработчика — физлицо. Платёжка RuStore физлицам отключена (с 01.02.2026), игре она не нужна.

## Как собрать

1. GitHub → Actions → «Counter Zombie Mobile for RuStore» → Run workflow.
   Получается ядро без игровых файлов и без подписи (артефакт `CZM-RUSTORE-CORE-NOT-INSTALLABLE`) — его нельзя ставить.
2. Ядро кладётся на VDS, там:
   `python -m czm.cli rustore-assemble <core.apk> <version>` (от пользователя czm, с `/etc/czm/env`).
   Сервер добавляет игровые файлы из последнего релиза и подписывает ключом RuStore.
   Готовый файл лежит в `/var/lib/czm/rustore/` — сайт его не раздаёт.
3. APK загружается в консоль RuStore.

## Ключ

- `/var/lib/czm/signing/rustore.p12`, пароль `CZM_RUSTORE_KEY_PASSWORD` в `/etc/czm/env`; делает install.sh один раз,
  копия ключа — `/var/backups/czm-signing/`. Пароль и ключ не печатать.
- Каждое обновление в RuStore должно быть подписано тем же ключом. Переезд на новый VDS — только с ключом и паролем.
- `CERT_SHA256` в `server/czm/czm/rustore.py` закрепляет сертификат первого релиза: сервер с чужим ключом не подпишет.
