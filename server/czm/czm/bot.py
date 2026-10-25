"""Telegram bot of the owner: complaints with ban buttons, news, releases, bans.

Only the owners (CZM_BOT_OWNER_IDS) are served. Telegram is blocked from the server,
the Bot API goes through the owner's relay (CZM_BOT_API_URL).
"""
import asyncio
import html
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Callable

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (BotCommand, BufferedInputFile, CallbackQuery, InlineKeyboardButton,
                           InlineKeyboardMarkup, Message)

from . import service, website
from .config import Settings, get_settings
from .db import db

log = logging.getLogger("czm.bot")
MSK = timezone(timedelta(hours=3))
LENGTHS = {"w": "week", "m": "month", "f": "forever"}
LENGTH_NAMES = {"week": "неделю", "month": "месяц", "forever": "навсегда"}
BETA_GOAL = 50                                  # the scale of the beta counter on the site

HELP = (
    "<b>Counter Zombie Mobile — бот владельца</b>\n\n"
    "Жалобы из игрового чата приходят сюда с кнопками бана.\n\n"
    "/news <i>текст</i> — новость в колокольчик всем игрокам\n"
    "/news — последние новости, /delnews <i>номер</i> — убрать новость\n"
    "Обновления выходят сами: после каждой правки сервер собирает игру и выпускает её, "
    "сюда приходит сообщение с кнопкой отмены.\n"
    "/release — что сейчас у игроков, /release <i>текст</i> — поправить «что нового»\n"
    "/ban <i>ID</i> week|month|forever <i>причина</i> — бан игрока\n"
    "/unban <i>ID</i> — разбан, /bans — кто забанен\n"
    "/tester <i>число</i> — сколько тестировщиков в бете Google Play показывает сайт, /tester — сколько сейчас\n"
    "/stats — сводка"
)


class RelaySession(AiohttpSession):
    """HTTPS relays need fresh connections instead of reusing a stale edge connection."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._connector_init["force_close"] = True

    async def create_session(self):
        session = await super().create_session()
        session.headers["User-Agent"] = "CounterZombieMobileBot/1.0 (+https://counter-zombie.ru)"
        return session


async def in_db(fn: Callable, *args: Any) -> Any:
    def run():
        with db() as conn:
            return fn(conn, *args)
    return await asyncio.to_thread(run)


def when(ts: int | None) -> str:
    if not ts:
        return "навсегда"
    return datetime.fromtimestamp(ts, MSK).strftime("до %d.%m.%Y %H:%M")


REPORT_SUBJECT = {
    "chat": "На сообщение в комнате {context}:",
    "private": "На личное сообщение:",
    "lobby_message": "На сообщение в лобби «{context}»:",
    "lobby": "На название или описание лобби:",
    "lobby_member": "На игрока в лобби «{context}»: голос или поведение.",
    "profile": "На профиль: ник, аватар или статус.",
}
REMOVE_BUTTON = {
    "chat": "🗑 Удалить сообщение",
    "private": "🗑 Удалить сообщение",
    "lobby_message": "🗑 Удалить сообщение",
    "lobby": "🗑 Закрыть лобби",
    "profile": "🧹 Сбросить аватар и статус",
}


def report_text(info: dict, result: str = "") -> str:
    target = f"<b>{html.escape(info['nick'])}</b> (ID {info['target']})"
    kind = info.get("kind", "profile")
    context = info.get("context") or ""
    if kind == "chat":
        context = context.upper()
    lines = [f"⚠️ <b>Жалоба #{info['id']}</b>",
             html.escape(REPORT_SUBJECT.get(kind, REPORT_SUBJECT["profile"]).format(context=context))]
    if info.get("evidence"):
        lines.append(f"«{html.escape(info['evidence'])}»")
    lines.append(f"Автор: {target}, жалоб за неделю: {info['reports_week']}")
    lines.append(f"Пожаловался: {html.escape(info['reporter_nick'])} (ID {info['reporter']})")
    if result:
        lines.append("")
        lines.append(result)
    return "\n".join(lines)


def report_keyboard(info: dict) -> InlineKeyboardMarkup:
    r = info["id"]
    rows = [[
        InlineKeyboardButton(text="🚫 Неделя", callback_data=f"b:{r}:w"),
        InlineKeyboardButton(text="🚫 Месяц", callback_data=f"b:{r}:m"),
        InlineKeyboardButton(text="🚫 Навсегда", callback_data=f"b:{r}:f"),
    ]]
    second = []
    if info.get("kind") in REMOVE_BUTTON:
        second.append(InlineKeyboardButton(text=REMOVE_BUTTON[info["kind"]], callback_data=f"d:{r}"))
    second.append(InlineKeyboardButton(text="✅ Не нарушение", callback_data=f"k:{r}"))
    rows.append(second)
    return InlineKeyboardMarkup(inline_keyboard=rows)


class OwnerBot:
    def __init__(self, bot: Bot, settings: Settings):
        self.bot = bot
        self.settings = settings
        self.owners = settings.owner_ids

    def allowed(self, user_id: int | None) -> bool:
        return user_id is not None and user_id in self.owners

    async def notify_report(self, info: dict) -> None:
        for owner in self.owners:
            try:
                photo = self.settings.avatar_dir / f"{info['target']}.png"
                profile = info.get("kind") == "profile"
                if profile and info["avatar"] == "photo" and photo.exists():
                    await self.bot.send_photo(owner, BufferedInputFile(photo.read_bytes(), "avatar.png"),
                                              caption=report_text(info), reply_markup=report_keyboard(info))
                else:
                    text = report_text(info)
                    if profile:
                        text += f"\nАватар: {'свой' if info['avatar'] == 'photo' else ('№' + info['avatar'] if info['avatar'] else 'логотип игры')}"
                    await self.bot.send_message(owner, text, reply_markup=report_keyboard(info))
            except TelegramAPIError as e:
                log.warning("could not send report %s to %s: %s", info["id"], owner, e)

    # commands -------------------------------------------------------------

    async def on_start(self, message: Message) -> None:
        if not self.allowed(message.from_user and message.from_user.id):
            await message.answer("Это служебный бот Counter Zombie Mobile.")
            return
        await message.answer(HELP)

    async def on_stats(self, message: Message) -> None:
        if not self.allowed(message.from_user and message.from_user.id):
            return
        s = await in_db(service.stats)
        await message.answer(
            f"Игроков всего: {s['players']}\nЗаходили за сутки: {s['players_day']} (новых {s['players_new_day']})\n"
            f"Сообщений за сутки: {s['messages_day']}\nОткрытых жалоб: {s['reports_open']}\nБанов сейчас: {s['bans_active']}"
        )

    async def on_news(self, message: Message, command: CommandObject) -> None:
        if not self.allowed(message.from_user and message.from_user.id):
            return
        text = (command.args or "").strip()
        if not text:
            items = await in_db(service.news, 0, 10)
            if not items:
                await message.answer("Новостей пока нет. Напиши /news и текст.")
                return
            lines = [f"#{n['id']} · {datetime.fromtimestamp(n['ts'], MSK):%d.%m %H:%M}\n{html.escape(n['text'])}" for n in items]
            await message.answer("\n\n".join(lines))
            return
        news_id = await in_db(service.add_news, text)
        await message.answer(f"✅ Новость #{news_id} в колокольчике у всех игроков.")

    async def on_delnews(self, message: Message, command: CommandObject) -> None:
        if not self.allowed(message.from_user and message.from_user.id):
            return
        arg = (command.args or "").strip().lstrip("#")
        ok = arg.isdigit() and await in_db(service.delete_news, int(arg))
        await message.answer("Новость убрана." if ok else "Нет такой новости. Номер — в списке /news.")

    async def on_release(self, message: Message, command: CommandObject) -> None:
        if not self.allowed(message.from_user and message.from_user.id):
            return
        release = await in_db(service.latest_release, False)
        if release is None:
            await message.answer("Сборок пока нет: первая появится после следующей правки.")
            return
        size = f"{release['size'] / 1024 / 1024:.0f} МБ"
        notes = (command.args or "").strip()
        if not notes:
            if release["published"]:
                await message.answer(
                    f"У игроков <b>{release['version']}</b> ({size}).\nЧто нового: {html.escape(release['notes'])}\n\n"
                    "Новые сборки выходят сами. Поправить текст: <code>/release новый текст</code>"
                )
            else:
                await message.answer(
                    f"Сборка <b>{release['version']}</b> ({size}) не выпущена.\n"
                    "Выпустить: /release и что нового, например:\n<code>/release Новый список серверов и аватары</code>"
                )
            return
        if release["published"]:
            await in_db(service.set_release_notes, release["id"], notes)
            await message.answer(f"✏️ Текст обновления {release['version']} изменён, в колокольчике тоже.")
            return
        await in_db(service.publish_release, release["id"], notes)
        await message.answer(f"✅ Обновление {release['version']} выпущено, игроки увидят его в игре.")

    # automatic builds -----------------------------------------------------

    @staticmethod
    def build_text(b: dict, state: str = "") -> tuple[str, InlineKeyboardMarkup | None]:
        version = html.escape(b["version"])
        if b["status"] == "failed":
            return (f"⚠️ Сборка {version} не собралась на сервере: {html.escape(b['error'])}\n"
                    "У игроков осталась прошлая версия."), None
        size = f"{(b.get('release_size') or 0) / 1024 / 1024:.0f} МБ"
        notes = html.escape(b.get("release_notes") or "")
        published = state == "published" if state else bool(b.get("release_published"))
        rid = b["release_id"]
        if b.get("release_channel") == "development":
            text = f"Готова личная тестовая сборка <b>{version}</b> ({size})\n{notes}\n\nДоступна только аккаунтам разработки. В Google Play не отправлена."
            return text, None
        if published:
            text = f"🚀 <b>Вышло обновление {version}</b> ({size})\n{notes}\n\nИгроки увидят его в колокольчике в течение 10 минут."
            button = InlineKeyboardButton(text="↩️ Отменить выпуск", callback_data=f"ru:{rid}")
        else:
            text = (f"↩️ Выпуск {version} отменён, у игроков прошлая версия." if state == "undone"
                    else f"📦 Готова сборка <b>{version}</b> ({size})\n{notes}")
            button = InlineKeyboardButton(text="🚀 Выпустить", callback_data=f"rp:{rid}")
        return text, InlineKeyboardMarkup(inline_keyboard=[[button]])

    async def notify_builds(self) -> None:
        for b in await in_db(service.unnotified_builds):
            text, keyboard = self.build_text(b)
            sent = False
            for owner in self.owners:
                try:
                    await self.bot.send_message(owner, text, reply_markup=keyboard)
                    sent = True
                except TelegramAPIError as e:
                    log.warning("could not send build %s to %s: %s", b["id"], owner, e)
            if sent or not self.owners:
                await in_db(service.mark_build_notified, b["id"])

    @staticmethod
    def play_text(p: dict) -> str:
        version = html.escape(p["version"])
        if p["status"] == "sent":
            return (f"🧪 Сборка <b>{version}</b> ({p['version_code']}) отправлена в Google Play: "
                    f"{html.escape(p['tracks'])}.\nGoogle проверит её, после одобрения тестеры получат обновление.")
        return (f"⚠️ Сборку {version} не удалось отправить в Google Play: {html.escape(p['error'])}\n"
                "Подписанный файл лежит на сервере, его можно загрузить в Play Console вручную.")

    async def notify_play(self) -> None:
        for p in await in_db(service.unnotified_play_publishes):
            sent = False
            for owner in self.owners:
                try:
                    await self.bot.send_message(owner, self.play_text(p))
                    sent = True
                except TelegramAPIError as e:
                    log.warning("could not send Google Play notice %s to %s: %s", p["id"], owner, e)
            if sent or not self.owners:
                await in_db(service.mark_play_publish_notified, p["id"])

    async def on_release_button(self, query: CallbackQuery, action: str, release_id: int) -> None:
        def act(conn):
            release = service.release_by_id(conn, release_id)
            if release is None:
                return None
            if action == "ru" and release["published"]:
                service.unpublish_release(conn, release_id)
            elif action == "rp" and not release["published"]:
                service.publish_release(conn, release_id, release["notes"])
            return service.release_by_id(conn, release_id)

        release = await in_db(act)
        if release is None:
            await query.answer("Нет такой сборки")
            return
        published = bool(release["published"])
        await query.answer("Выпущено" if published else "Отменено")
        info = {"version": release["version"], "status": "done", "release_id": release_id,
                "release_size": release["size"], "release_notes": release["notes"]}
        text, keyboard = self.build_text(info, "published" if published else "undone")
        if query.message:
            try:
                await query.message.edit_text(text, reply_markup=keyboard)
            except TelegramAPIError as e:
                log.warning("could not edit build message: %s", e)

    async def on_tester(self, message: Message, command: CommandObject) -> None:
        """The number of beta testers on the site, entered by the owner from Play Console."""
        if not self.allowed(message.from_user and message.from_user.id):
            return
        arg = (command.args or "").strip()
        if not arg:
            s = await in_db(website.stats)
            count = s["play_beta_testers"]
            if count is None:
                await message.answer("На сайте число тестировщиков ещё не указано. Так: /tester 7")
                return
            checked = datetime.fromtimestamp(s["play_beta_checked_at"], MSK).strftime("%d.%m.%Y %H:%M")
            await message.answer(f"На сайте тестировщиков: {count} из {BETA_GOAL} (указано {checked}).\n"
                                 "Поменять: /tester число")
            return
        if not arg.isdigit() or int(arg) > 1000000:
            await message.answer("Так: /tester 7 — сколько тестировщиков в бете Google Play")
            return
        await in_db(website.set_play_beta_testers, int(arg))
        await message.answer(f"✅ На сайте теперь тестировщиков: {int(arg)} из {BETA_GOAL}.")

    async def on_ban(self, message: Message, command: CommandObject) -> None:
        if not self.allowed(message.from_user and message.from_user.id):
            return
        parts = (command.args or "").split(maxsplit=2)
        if len(parts) < 2 or not parts[0].isdigit() or parts[1] not in service.BAN_LENGTHS:
            await message.answer("Так: /ban ID week|month|forever причина")
            return
        result = await in_db(service.ban, int(parts[0]), parts[1], parts[2] if len(parts) > 2 else "")
        if result is None:
            await message.answer("Нет такого игрока.")
            return
        await message.answer(f"🚫 {html.escape(result['nick'])} (ID {result['player']}) забанен {LENGTH_NAMES[parts[1]]}.")

    async def on_unban(self, message: Message, command: CommandObject) -> None:
        if not self.allowed(message.from_user and message.from_user.id):
            return
        arg = (command.args or "").strip()
        if not arg.isdigit():
            await message.answer("Так: /unban ID (ID — в жалобе или в /bans)")
            return
        count = await in_db(service.unban, int(arg))
        await message.answer("✅ Разбанен." if count else "У этого игрока нет бана.")

    async def on_bans(self, message: Message) -> None:
        if not self.allowed(message.from_user and message.from_user.id):
            return
        bans = await in_db(service.active_bans)
        if not bans:
            await message.answer("Банов нет.")
            return
        lines = [f"{html.escape(b['nick'])} (ID {b['player']}) — {when(b['until'])}"
                 + (f", {html.escape(b['reason'])}" if b["reason"] else "") for b in bans]
        await message.answer("\n".join(lines))

    async def on_message(self, message: Message) -> None:
        if not self.allowed(message.from_user and message.from_user.id):
            await message.answer("Это служебный бот Counter Zombie Mobile.")
            return
        await message.answer(HELP)

    # complaint buttons ----------------------------------------------------

    async def on_callback(self, query: CallbackQuery) -> None:
        if not self.allowed(query.from_user and query.from_user.id):
            await query.answer()
            return
        parts = (query.data or "").split(":")
        if len(parts) < 2 or not parts[1].isdigit():
            await query.answer()
            return
        if parts[0] in ("ru", "rp"):
            await self.on_release_button(query, parts[0], int(parts[1]))
            return
        report_id = int(parts[1])

        def act(conn):
            info = service.report_info(conn, report_id)
            if info is None:
                return None, ""
            if info["status"] != "open":
                return info, "Уже решено."
            if parts[0] == "b" and len(parts) == 3 and parts[2] in LENGTHS:
                length = LENGTHS[parts[2]]
                service.ban(conn, info["target"], length, f"жалоба #{report_id}")
                removed = service.remove_report_content(conn, info)
                # the other complaints about this player are answered too
                conn.execute("UPDATE reports SET status = 'banned', resolved = strftime('%s','now') WHERE target = ? AND status = 'open'",
                             (info["target"],))
                return info, f"🚫 Забанен {LENGTH_NAMES[length]}" + (f", {removed}." if removed else ".")
            if parts[0] == "d" and info.get("kind") in REMOVE_BUTTON:
                removed = service.remove_report_content(conn, info)
                service.resolve_report(conn, report_id, "deleted")
                return info, f"🗑 {removed[:1].upper()}{removed[1:]}."
            if parts[0] == "k":
                service.resolve_report(conn, report_id, "dismissed")
                return info, "✅ Не нарушение."
            return info, ""

        info, result = await in_db(act)
        await query.answer(result or "Готово")
        if info and result:
            try:
                if query.message and query.message.photo:
                    await query.message.edit_caption(caption=report_text(info, result), reply_markup=None)
                elif query.message:
                    await query.message.edit_text(report_text(info, result), reply_markup=None)
            except TelegramAPIError as e:
                log.warning("could not edit report message: %s", e)

    async def on_startup(self) -> None:
        try:
            await self.bot.set_my_commands([
                BotCommand(command="news", description="Новость в колокольчик"),
                BotCommand(command="release", description="Что сейчас у игроков"),
                BotCommand(command="bans", description="Кто забанен"),
                BotCommand(command="tester", description="Тестировщики беты на сайте"),
                BotCommand(command="unban", description="Разбан игрока"),
                BotCommand(command="stats", description="Сводка"),
                BotCommand(command="help", description="Как пользоваться"),
            ])
        except TelegramAPIError as e:
            log.warning("set_my_commands failed: %s", e)


def build(settings: Settings) -> tuple[Bot, Dispatcher, OwnerBot]:
    kwargs: dict[str, Any] = {}
    if settings.bot_api_url:
        kwargs["api"] = TelegramAPIServer.from_base(settings.bot_api_url)
    session = RelaySession(**kwargs) if settings.bot_api_url.startswith("https://") else AiohttpSession(**kwargs)
    bot = Bot(settings.bot_token, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    owner = OwnerBot(bot, settings)
    router = Router()
    router.message.register(owner.on_start, CommandStart())
    router.message.register(owner.on_start, Command("help"))
    router.message.register(owner.on_stats, Command("stats"))
    router.message.register(owner.on_news, Command("news"))
    router.message.register(owner.on_delnews, Command("delnews"))
    router.message.register(owner.on_release, Command("release"))
    router.message.register(owner.on_ban, Command("ban"))
    router.message.register(owner.on_unban, Command("unban"))
    router.message.register(owner.on_bans, Command("bans"))
    router.message.register(owner.on_tester, Command("tester"))
    router.message.register(owner.on_message)
    router.callback_query.register(owner.on_callback)
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    dispatcher.startup.register(owner.on_startup)
    return bot, dispatcher, owner


async def run_bot(bot: Bot, dispatcher: Dispatcher) -> None:
    """Polling that survives relay hiccups."""
    settings = get_settings()
    while True:
        try:
            await dispatcher.start_polling(bot, polling_timeout=settings.bot_polling_timeout_seconds,
                                           allowed_updates=["message", "callback_query"], handle_signals=False)
            return
        except asyncio.CancelledError:
            raise
        except Exception as e:  # keep the API alive whatever the bot does
            log.warning("bot stopped: %s, restarting in 30 s", e)
            await asyncio.sleep(30)


async def builds_loop(owner: OwnerBot) -> None:
    """Tells the owner about every assembled or failed build."""
    while True:
        try:
            await owner.notify_builds()
            await owner.notify_play()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("build notices failed: %s", e)
        await asyncio.sleep(15)
