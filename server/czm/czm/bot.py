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
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (BotCommand, BufferedInputFile, CallbackQuery, InlineKeyboardButton,
                           InlineKeyboardMarkup, Message)

from . import service, website, accounts, server_moderation, community, moderator_guard
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
    "/news <i>текст</i> — новость в колокольчик всем игрокам; "
    "<i>по-русски | in English</i> — английский текст для игры на английском\n"
    "/news — последние новости, /delnews <i>номер</i> — убрать новость\n"
    "/editnews <i>номер</i> <i>текст</i> или <i>по-русски | in English</i> — поправить новость (колокольчик и сайт)\n"
    "Обновления выходят сами: после каждой правки сервер собирает игру и выпускает её, "
    "сюда приходит сообщение с кнопкой отмены.\n"
    "/release — что сейчас у игроков, /release <i>текст</i> — поправить «что нового»\n"
    "/ban <i>ID</i> week|month|forever <i>причина</i> — бан игрока\n"
    "/unban <i>ID</i> — разбан, /bans — кто забанен\n"
    "/server_reports — серверы и число жалоб; /server <i>IP:порт</i> — один сервер\n"
    "/server_ban <i>IP:порт причина</i> — блокировка в CZM; /server_unban <i>IP:порт</i> — разбан\n"
    "/role <i>ID moderator|tester|server_owner [Проект]</i> — назначить роль; /unrole <i>ID роль</i> — снять\n"
    "/moderators — модераторы; /moderator <i>ID</i> — действия и причины\n"
    "/mod_pause <i>ID</i> — приостановить; /mod_resume <i>ID</i> — проверить и вернуть права\n"
    "/mod_undo <i>ID [all]</i> — отмена текущей серии или всей истории с подтверждением\n"
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


def server_report_text(info: dict) -> str:
    name = html.escape(info["name"] or "Сервер")
    state = " · 🚫" if info["blocked"] else ""
    text = (f"<b>{name}</b>\n<code>{html.escape(info['server'])}</code> · Жалоб: <b>{info['count']}</b>"
            f" · Игроков: {info['reporters']}{state}")
    if "reporter" in info:
        text += (f"\nОт: {html.escape(info['reporter_nick'])} · ID {info['reporter']}"
                 f"\nОт автора: {info['author_count']} жалоб · Серверов: {info['author_servers']}")
    if info.get("reason") and "reporter" in info:
        labels = {"sexual": "Сексуальный контент", "hate": "Нацизм / ненависть", "harassment": "Оскорбления / травля",
                  "copyright": "Авторские права", "spam": "Спам / обман", "other": "Своя причина"}
        text += "\nПричины: " + "; ".join(labels.get(code,"Другое") for code in info["reason"].split(","))
    elif info.get("reason"):
        text += "\nПричина блокировки: " + html.escape(info["reason"])
    if info.get("comment"):
        text += "\nСвоя причина: " + html.escape(info["comment"])
    return text


def moderation_event_text(info: dict) -> str:
    labels = {"ban": "Блокировка", "mute_text": "Отключение чата", "mute_voice": "Отключение голоса",
              "warn": "Предупреждение", "delete_message": "Удаление сообщения", "dismiss": "Отклонение жалобы",
              "lift": "Снятие ограничения", "remove_avatar": "Сброс аватара", "restrict_photo": "Запрет фото", "close_lobby": "Закрытие лобби"}
    stamp = datetime.fromtimestamp(info["created"], MSK).strftime("%d.%m %H:%M:%S МСК")
    text = (f"<b>{labels.get(info['action'], 'Модерация')}</b> · {stamp}\n"
            f"Модератор: {html.escape(info['moderator_nick'] or 'Удалённый аккаунт')} · ID {info['moderator']}\n"
            f"Игрок: {html.escape(info['target_nick'] or 'Удалённый аккаунт')} · ID {info['target']}\n"
            f"Причина: {html.escape(info['reason'] or 'Не указана')}")
    if info["paused"]:
        text += (f"\n<b>10 действий: права приостановлены до твоей проверки.</b>\n"
                 f"/moderator {info['moderator']} · /mod_undo {info['moderator']}")
    return text


def moderator_status_text(info: dict) -> str:
    period = "—"
    if info["first"]:
        period = datetime.fromtimestamp(info["first"], MSK).strftime("%d.%m %H:%M:%S") + " — " + datetime.fromtimestamp(info["last"], MSK).strftime("%d.%m %H:%M:%S МСК")
    return (f"<b>{html.escape(info['nick'])} · ID {info['player']}</b>\n"
            f"Права: {'приостановлены' if info['paused'] else 'активны'}\n"
            f"На проверку: {info['count']}/10 · Всего действий: {info['total']}\n"
            f"Банов: {info['bans_total']} · За 24 часа: {info['bans_day']}\nПериод: {period}")


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

    def server_owner(self, message: Message) -> bool:
        return self.allowed(message.from_user and message.from_user.id) and getattr(
            getattr(message, "chat", None), "type", "private") == "private"

    async def _chunks(self, message, lines):
        chunk = ""
        for line in lines:
            candidate = (chunk + "\n\n" if chunk else "") + line
            if chunk and len(candidate.encode("utf-16-le")) > 7000:
                await message.answer(chunk); chunk = line
            else:
                chunk = candidate
        if chunk:
            await message.answer(chunk)

    async def on_role(self, message: Message, command: CommandObject) -> None:
        if not self.server_owner(message):
            return
        args = (command.args or "").split(maxsplit=2)
        if len(args) < 2 or not args[0].isdigit():
            await message.answer("Так: /role ID moderator|tester|server_owner [Проект]"); return
        try:
            info = await in_db(community.grant, int(args[0]), args[1].lower(), args[2] if len(args) > 2 else "", f"telegram:{message.from_user.id}")
        except accounts.AuthError as exc:
            await message.answer("Аккаунт не найден или роль неверна. Роли: moderator, tester, server_owner."); return
        await message.answer(f"{html.escape(info['nick'])} · ID {info['id']}\nРоль: <b>{info['role']}</b>"
                             + (f" · {html.escape(info['project'])}" if info['project'] else ""))

    async def on_unrole(self, message: Message, command: CommandObject) -> None:
        if not self.server_owner(message):
            return
        args = (command.args or "").split()
        if len(args) != 2 or not args[0].isdigit() or args[1].lower() not in community.ROLES:
            await message.answer("Так: /unrole ID moderator|tester|server_owner"); return
        await in_db(community.revoke, int(args[0]), args[1].lower(), f"telegram:{message.from_user.id}")
        await message.answer(f"Роль {args[1].lower()} снята у ID {args[0]}. Журнал сохранён.")

    async def on_moderators(self, message: Message, command: CommandObject) -> None:
        if not self.server_owner(message):
            return
        people = await in_db(moderator_guard.moderators)
        await self._chunks(message, [moderator_status_text(p) for p in people] or ["Модераторов пока нет."])

    async def on_moderator(self, message: Message, command: CommandObject) -> None:
        if not self.server_owner(message):
            return
        args = (command.args or "").split()
        if not 1 <= len(args) <= 2 or not all(a.isdigit() for a in args) or (len(args)>1 and not 1<=int(args[1])<=10000):
            await message.answer("Так: /moderator ID или /moderator ID 2"); return
        await self._moderator_details(message, int(args[0]), int(args[1])-1 if len(args)>1 else 0)

    async def _moderator_details(self, message, player, page=0):
        try:
            info = await in_db(moderator_guard.status, player)
        except accounts.AuthError:
            await message.answer("Аккаунт не найден."); return
        lines = [moderator_status_text(info)]
        actions = await in_db(moderator_guard.history, player, page)
        states = {"pending": "на проверке", "approved": "проверено", "reverted": "отменено"}
        for action in actions:
            stamp = datetime.fromtimestamp(action["created"], MSK).strftime("%d.%m %H:%M:%S")
            lines.append(f"{stamp} · {html.escape(action['action'])} · ID {action['target']} · {states.get(action['state'],'')}\n{html.escape(action['reason'])}")
        if len(actions)==10:
            lines.append(f"Дальше: /moderator {player} {page+2}")
        await self._chunks(message, lines)

    async def on_mod_control(self, message: Message, command: CommandObject) -> None:
        if not self.server_owner(message):
            return
        args = (command.args or "").split()
        if not args or not args[0].isdigit() or len(args)>2 or (len(args)>1 and (command.command!="mod_undo" or args[1]!="all")):
            await message.answer("Так: /mod_pause ID, /mod_resume ID или /mod_undo ID"); return
        player = int(args[0])
        try:
            if command.command == "mod_undo":
                await in_db(moderator_guard.pause, player, f"telegram:{message.from_user.id}")
                info = await in_db(moderator_guard.status, player)
                all_batches = len(args)>1
                scope = await in_db(moderator_guard.reviewable, player) if all_batches else {"count":info["count"],"last_log":info["batch"]}
                if not scope["count"]:
                    await message.answer("Непроверенных действий нет."); return
                keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
                    text=f"Отменить {scope['count']} действий", callback_data=f"{'ma' if all_batches else 'mu'}:{player}:{scope['last_log']}")]])
                label = "всю историю этого модератора" if all_batches else "эту серию"
                await message.answer(moderator_status_text(info) + f"\n\nОтменить {label} ({scope['count']} действий)? Более поздние решения сохранятся. Права останутся приостановлены.", reply_markup=keyboard)
                return
            operation = moderator_guard.resume if command.command == "mod_resume" else moderator_guard.pause
            info = await in_db(operation, player, f"telegram:{message.from_user.id}")
            await message.answer(moderator_status_text(info))
        except accounts.AuthError:
            await message.answer("Не найден модератор для этого действия.")

    async def notify_moderation(self):
        for owner in self.owners:
            for event in await in_db(moderator_guard.pending, owner):
                keyboard = None
                if event["paused"]:
                    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
                        text="Статистика и причины", callback_data=f"ms:{event['moderator']}")]])
                try:
                    await self.bot.send_message(owner, moderation_event_text(event), reply_markup=keyboard)
                except TelegramAPIError:
                    break
                await in_db(moderator_guard.delivered, event["log"], owner)

    async def notify_tickets(self):
        for owner in self.owners:
            for receipt in await in_db(community.ticket_cleanup_pending, owner):
                try:
                    await self.bot.delete_message(owner, receipt["message"])
                except TelegramBadRequest as exc:
                    if "not found" not in str(exc).lower():
                        await self.bot.send_message(owner, f"Тикет #{receipt['ticket']} удалён из CZM. Удали оставшиеся копии этого тикета в переписке: Telegram не разрешил автоматическое удаление.")
                except TelegramAPIError:
                    break
                await in_db(community.ticket_cleanup_done, owner, receipt["message"])
            for ticket in await in_db(community.tickets_pending, owner):
                title = f"<b>Тикет #{ticket['id']}: {html.escape(ticket['subject'])}</b>"
                author = f"{html.escape(ticket['nick'])} · ID {ticket['player']}"
                try:
                    if not ticket["parts"] & 1:
                        for start in range(0, len(ticket["text"]), 1600):
                            sent = await self.bot.send_message(owner, title + "\n" + author + "\n\n" + html.escape(ticket["text"][start:start+1600]))
                            await in_db(community.ticket_receipt, ticket["id"], owner, sent.message_id)
                        await in_db(community.ticket_delivered, ticket["id"], owner, 1)
                    if ticket["photo"] is not None and not ticket["parts"] & 2:
                        sent = await self.bot.send_photo(owner, BufferedInputFile(ticket["photo"], f"ticket-{ticket['id']}.jpg"), caption=title + "\nФото")
                        await in_db(community.ticket_delivered, ticket["id"], owner, 2, sent.message_id)
                    if ticket["text_file"] is not None and not ticket["parts"] & 4:
                        sent = await self.bot.send_document(owner, BufferedInputFile(ticket["text_file"], ticket["file_name"]), caption=title + "\nТекстовый файл")
                        await in_db(community.ticket_delivered, ticket["id"], owner, 4, sent.message_id)
                except TelegramAPIError:
                    break

    async def notify_server_reports(self) -> None:
        for owner in self.owners:
            failed_servers = set()
            for info in await in_db(server_moderation.pending, owner):
                if info["id"] in failed_servers:
                    continue
                try:
                    await self.bot.send_message(owner, server_report_text(info))
                except TelegramAPIError:
                    log.warning("could not deliver server report %s", info["id"])
                    failed_servers.add(info["id"])
                    continue
                await in_db(server_moderation.delivered, info["id"], owner, info["last_report"])

    async def on_server_reports(self, message: Message, command: CommandObject) -> None:
        if not self.server_owner(message):
            return
        arg = (command.args or "1").strip()
        if not arg.isdigit() or not 1 <= int(arg) <= 10000:
            await message.answer("Так: /server_reports или /server_reports 2")
            return
        page = int(arg) - 1
        data = await in_db(server_moderation.listing, page)
        lines = [f"{html.escape(s['name'][:64] or 'Сервер')}\n"
                 f"<code>{html.escape(s['server'])}</code> — <b>{s['count']}</b> · Игроков: {s['reporters']}"
                 + (" · 🚫" if s["blocked"] else "") for s in data["servers"]]
        if data["more"]:
            lines.append(f"Дальше: /server_reports {page + 2}")
        chunk = ""
        for line in lines:
            candidate = (chunk + "\n\n" if chunk else "") + line
            if chunk and len(candidate.encode("utf-16-le")) > 7000:
                await message.answer(chunk); chunk = line
            else:
                chunk = candidate
        await message.answer(chunk or "Жалоб на серверы нет.")

    async def on_server(self, message: Message, command: CommandObject) -> None:
        if not self.server_owner(message):
            return
        try:
            info = await in_db(server_moderation.info, (command.args or "").strip())
        except accounts.AuthError:
            await message.answer("Так: /server IP:порт")
            return
        await message.answer(server_report_text(info))

    async def on_server_ban(self, message: Message, command: CommandObject) -> None:
        if not self.server_owner(message):
            return
        address, _, reason = (command.args or "").strip().partition(" ")
        try:
            info = await in_db(server_moderation.set_blocked, address, True,
                               f"telegram:{message.from_user.id}", reason)
        except accounts.AuthError:
            await message.answer("Так: /server_ban IP:порт причина")
            return
        await message.answer(f"🚫 <code>{html.escape(info['server'])}</code> заблокирован в CZM.")

    async def on_server_unban(self, message: Message, command: CommandObject) -> None:
        if not self.server_owner(message):
            return
        try:
            info = await in_db(server_moderation.set_blocked, (command.args or "").strip(), False,
                               f"telegram:{message.from_user.id}")
        except accounts.AuthError:
            await message.answer("Так: /server_unban IP:порт")
            return
        await message.answer(f"✅ <code>{html.escape(info['server'])}</code> "
                             + ("разблокирован." if info["changed"] else "не заблокирован."))

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
            english = {n["id"]: n["text"] for n in await in_db(service.news, 0, 10, "en")}
            lines = [f"#{n['id']} · {datetime.fromtimestamp(n['ts'], MSK):%d.%m %H:%M}\n{html.escape(n['text'])}"
                     + (f"\n🇬🇧 {html.escape(english[n['id']])}" if english.get(n["id"], n["text"]) != n["text"] else "")
                     for n in items]
            await message.answer("\n\n".join(lines))
            return
        ru, en = service.bilingual(text)
        if not ru:
            await message.answer("Сначала текст по-русски, потом, если нужно, «|» и текст по-английски.")
            return
        news_id = await in_db(service.add_news, ru, en)
        await message.answer(f"✅ Новость #{news_id} в колокольчике у всех игроков"
                             + (" (у игры на английском — по-английски)." if en else "."))

    async def on_delnews(self, message: Message, command: CommandObject) -> None:
        if not self.allowed(message.from_user and message.from_user.id):
            return
        arg = (command.args or "").strip().lstrip("#")
        ok = arg.isdigit() and await in_db(service.delete_news, int(arg))
        await message.answer("Новость убрана." if ok else "Нет такой новости. Номер — в списке /news.")

    async def on_editnews(self, message: Message, command: CommandObject) -> None:
        if not self.allowed(message.from_user and message.from_user.id):
            return
        number, _, text = (command.args or "").strip().lstrip("#").partition(" ")
        if not number.isdigit() or not text.strip():
            await message.answer("Напиши /editnews, номер новости и новый текст. Номер — в списке /news.")
            return
        ru, en = service.bilingual(text)
        ok = bool(ru) and await in_db(service.edit_news, int(number), ru, en if "|" in text else None)
        await message.answer(f"✅ Новость #{number} поправлена: колокольчик и сайт покажут новый текст."
                             if ok else "Нет такой новости. Номер — в списке /news.")

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
            await message.answer(f"✏️ Текст сборки {release['version']} изменён.")
            return
        await in_db(service.publish_release, release["id"], notes)
        await message.answer(f"✅ Сборка {release['version']} выпущена в тестовый канал. "
                             "Новость для игроков появится сама, когда обновление дойдёт до них в Google Play.")

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

    async def notify_play_news(self) -> None:
        """A Google Play release is on the public track: the owner learns it became news."""
        from . import play_feed
        for r in await in_db(play_feed.unnotified):
            name = html.escape(play_feed.version_name(r["version"]) or r["version"])
            text = (f"📣 Google Play: версия {name} ({r['code']}) вышла для игроков. "
                    f"Новость #{r['news_id']} в колокольчике, «Что нового» на сайте обновлено.\n"
                    f"Поправить текст: /editnews {r['news_id']} <i>текст</i>\nУбрать: /delnews {r['news_id']}")
            sent = False
            for owner in self.owners:
                try:
                    await self.bot.send_message(owner, text)
                    sent = True
                except TelegramAPIError as e:
                    log.warning("could not send the Play news notice %s to %s: %s", r["code"], owner, e)
            if sent or not self.owners:
                await in_db(play_feed.mark_notified, r["code"])

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
        kinds = {"text": "мут чата", "voice": "мут голоса", "photo": "запрет фото"}
        lines = [f"{html.escape(b['nick'])} (ID {b['player']}) — "
                 + (kinds[b["kind"]] + " " if b.get("kind") in kinds else "") + when(b["until"])
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
        if parts[0] in ("ms", "mu", "ma"):
            if not query.message or getattr(query.message.chat, "type", "") != "private":
                await query.answer(); return
            if parts[0] == "ms" and len(parts) == 2 and parts[1].isdigit():
                await self._moderator_details(query.message, int(parts[1])); await query.answer(); return
            if parts[0] in ("mu", "ma") and len(parts) == 3 and all(p.isdigit() for p in parts[1:]):
                try:
                    operation = moderator_guard.undo_all if parts[0] == "ma" else moderator_guard.undo
                    result = await in_db(operation, int(parts[1]), int(parts[2]), f"telegram:{query.from_user.id}")
                    await query.message.answer(f"Серия отменена. Восстановлено записей: {result['restored']}; пропущено из-за последующих изменений: {result['skipped']}.\nПрава модератора остаются приостановлены.")
                    await query.message.edit_reply_markup(reply_markup=None)
                except accounts.AuthError:
                    await query.message.answer("Серия уже проверена или больше недоступна.")
                await query.answer(); return
            await query.answer(); return
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
                BotCommand(command="server_reports", description="Серверы и количество жалоб"),
                BotCommand(command="server", description="Жалобы на один сервер"),
                BotCommand(command="server_ban", description="Заблокировать сервер в CZM"),
                BotCommand(command="server_unban", description="Разблокировать сервер"),
                BotCommand(command="role", description="Назначить роль аккаунту"),
                BotCommand(command="unrole", description="Снять роль аккаунта"),
                BotCommand(command="moderators", description="Модераторы и состояние прав"),
                BotCommand(command="moderator", description="Действия модератора и причины"),
                BotCommand(command="mod_pause", description="Приостановить модератора"),
                BotCommand(command="mod_resume", description="Проверить и вернуть права"),
                BotCommand(command="mod_undo", description="Отменить непроверенную серию"),
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
    router.message.register(owner.on_editnews, Command("editnews"))
    router.message.register(owner.on_release, Command("release"))
    router.message.register(owner.on_ban, Command("ban"))
    router.message.register(owner.on_unban, Command("unban"))
    router.message.register(owner.on_bans, Command("bans"))
    router.message.register(owner.on_tester, Command("tester"))
    router.message.register(owner.on_role, Command("role"))
    router.message.register(owner.on_unrole, Command("unrole"))
    router.message.register(owner.on_moderators, Command("moderators"))
    router.message.register(owner.on_moderator, Command("moderator"))
    router.message.register(owner.on_mod_control, Command("mod_pause", "mod_resume", "mod_undo"))
    router.message.register(owner.on_server_reports, Command("server_reports"))
    router.message.register(owner.on_server, Command("server"))
    router.message.register(owner.on_server_ban, Command("server_ban"))
    router.message.register(owner.on_server_unban, Command("server_unban"))
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
            await owner.notify_play_news()
            await owner.notify_server_reports()
            await owner.notify_moderation()
            await owner.notify_tickets()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("build notices failed: %s", e)
        await asyncio.sleep(15)
