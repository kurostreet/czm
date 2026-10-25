"""HTTP API for the game. JSON, the player's secret key comes in the X-CZM-Key header."""
import asyncio
import io
import logging
import time
from collections import defaultdict, deque
from typing import Any, Callable

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, WebSocket
from fastapi.responses import JSONResponse, RedirectResponse, FileResponse, HTMLResponse
from PIL import Image
from pydantic import BaseModel, Field

from . import service, mappics, accounts, settings, tab, social, website, distribution, lobbies, game_probe, voice_lobby, notifications, rules, moderation, play_feed, playtime
from .config import get_settings
from .db import db

log = logging.getLogger("czm.api")
router = APIRouter(prefix="/api/v1")
download_router = APIRouter()

# the bot gets complaints through this hook (set by main.py)
notify_report: Callable[[dict], Any] | None = None


async def in_db(fn: Callable, *args: Any) -> Any:
    def run():
        with db() as conn:
            return fn(conn, *args)
    return await asyncio.to_thread(run)


class _Limiter:
    """At most `count` calls per `seconds` for one key (an IP address)."""

    def __init__(self, count: int, seconds: float):
        self.count, self.seconds = count, seconds
        self.calls: dict[str, deque] = defaultdict(deque)

    def check(self, key: str) -> None:
        t = time.monotonic()
        q = self.calls[key]
        while q and q[0] < t - self.seconds:
            q.popleft()
        if len(q) >= self.count:
            raise HTTPException(429, {"error": "slow", "wait": int(self.seconds)})
        q.append(t)
        if len(self.calls) > 20000:
            self.calls.clear()


_hello_limit = _Limiter(20, 60)
_read_limit = _Limiter(120, 60)
_upload_limit = _Limiter(6, 600)
_tab_limit = _Limiter(240, 60)
_social_limit = _Limiter(240, 60)


def client_ip(request: Request) -> str:
    # Caddy in front sets X-Forwarded-For
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "")


async def current_player(key: str | None):
    player = await in_db(service.player_by_key, key or "")
    if player is None:
        raise HTTPException(401, {"error": "hello"})
    return player


def check_room(room: str) -> str:
    if room not in get_settings().room_list:
        raise HTTPException(404, {"error": "room"})
    return room


class HelloIn(BaseModel):
    key: str = Field(min_length=16, max_length=128)
    device: str = Field(default="", max_length=128)
    nick: str = Field(default="", max_length=64)
    avatar: str = Field(default="", max_length=16)
    lang: str = Field(default="", max_length=8)
    version: str = Field(default="", max_length=32)
    code: int = 0
    keep_avatar: bool = False
    # 1: the game shows the community rules and asks to accept them before posting
    rules: int = Field(default=0, ge=0, le=100)
    # 1: installed from Google Play, 0: the site build; absent in older games
    store: int | None = Field(default=None, ge=0, le=1)


@router.post("/hello")
async def hello(body: HelloIn, request: Request):
    _hello_limit.check(client_ip(request))

    def run(conn):
        try:
            before = service.player_by_key(conn, body.key)
        except accounts.AuthError:
            before = None
        player = service.hello(conn, body.key, body.device, body.nick, body.avatar, body.lang, body.version, body.keep_avatar)
        play_feed.witness(conn, before, player, body.code, body.store)  # the bot tells the owner
        rules.remember_client(conn, player["id"], body.rules)
        release = distribution.update_for(conn, body.key, body.code, player=player)
        return {
            "id": player["id"],
            "avatar": service.avatar_ref(player),
            "ban": service.active_ban(conn, player),
            "news": service.last_news_id(conn),
            "update": release if release and release["code"] > body.code else None,
            "rooms": get_settings().room_list,
            "max_chars": get_settings().message_max_chars,
            "distribution": {"development": distribution.allowed(conn, player)},
            "rules": rules.state(player),
            "role": moderation.role(conn, player["id"]),
            "moderation": moderation.state(conn, player),
            # the bell shows the notes of the code Google Play offers this player
            "play": play_feed.latest(conn),
        }

    try:
        return JSONResponse(await in_db(run), headers={"Cache-Control": "no-store"})
    except accounts.AuthError as error:
        return JSONResponse({"error": error.code}, status_code=error.status)


class TabPlayer(BaseModel):
    userid: int = Field(gt=0, le=2147483647)
    tag: str = Field(pattern=r"^[0-9a-f]{32}$")


class TabBindIn(BaseModel):
    server: str = Field(min_length=7, max_length=64)
    userid: int = Field(gt=0, le=2147483647)
    tag: str = Field(default="", pattern=r"^([0-9a-f]{32})?$")


class TabResolveIn(BaseModel):
    server: str = Field(min_length=7, max_length=64)
    players: list[TabPlayer] = Field(max_length=32)


@router.post("/tab/bind")
async def tab_bind(body: TabBindIn, request: Request, x_czm_key: str | None = Header(default=None)):
    _tab_limit.check(client_ip(request))
    try:
        result = await in_db(tab.bind, x_czm_key or "", body.server, body.userid, body.tag)
        return JSONResponse(result, headers={"Cache-Control": "no-store"})
    except accounts.AuthError as error:
        return JSONResponse({"error": error.code}, status_code=error.status)


@router.post("/tab/resolve")
async def tab_resolve(body: TabResolveIn, request: Request, x_czm_key: str | None = Header(default=None)):
    _tab_limit.check(client_ip(request))
    try:
        result = await in_db(tab.resolve, x_czm_key or "", body.server, [p.model_dump() for p in body.players])
        return JSONResponse(result, headers={"Cache-Control": "no-store"})
    except accounts.AuthError as error:
        return JSONResponse({"error": error.code}, status_code=error.status)


class AuthIn(BaseModel):
    nick: str = Field(default="", max_length=64)
    password: str = Field(default="", max_length=128)
    repeat: str = Field(default="", max_length=128)
    email: str = Field(default="", max_length=254)
    code: str = Field(default="", max_length=16)


@router.post("/auth/{action}")
async def account_action(action: str, body: AuthIn, request: Request, background_tasks: BackgroundTasks, x_czm_key: str | None = Header(default=None)):
    key, ip = x_czm_key or "", client_ip(request)
    operations = {
        "register": lambda c: accounts.register(c, key, body.nick, body.password, body.repeat, ip),
        "login": lambda c: accounts.login(c, body.nick, body.password, ip),
        "email-login": lambda c: accounts.email_login_request(c, body.email, ip),
        "email-login-confirm": lambda c: accounts.email_login_confirm(c, body.email, body.code, ip),
        "me": lambda c: accounts.me(c, key),
        "logout": lambda c: accounts.logout(c, key),
        "logout-all": lambda c: accounts.logout(c, key, True),
        "delete-account": lambda c: accounts.delete_account(c, key, body.password, ip),
        "email": lambda c: accounts.email_request(c, key, body.email, ip),
        "email-confirm": lambda c: accounts.email_confirm(c, key, body.code, ip),
        "password-change": lambda c: accounts.password_change_request(c, key, ip),
        "password-change-confirm": lambda c: accounts.password_change_confirm(c, key, body.code, body.password, body.repeat, ip),
        "recover": lambda c: accounts.recover(c, body.nick, ip),
        "reset": lambda c: accounts.reset(c, body.nick, body.code, body.password, body.repeat, ip),
    }
    if action not in operations:
        raise HTTPException(404)

    def run(conn):
        # Catch inside the transaction: failed attempts and consumed codes must commit.
        try:
            return 200, operations[action](conn)
        except accounts.AuthError as error:
            return error.status, {"error": error.code}

    status, result = await in_db(run)
    if action == "email-login" and status == 200:
        if result:
            background_tasks.add_task(accounts.deliver_login_code, *result)
        result = {"ok": True}
    elif action == "password-change" and status == 200:
        address, code, purpose, owner = result
        background_tasks.add_task(accounts.deliver_login_code, address, code, purpose)
        result = {"ok": True, "email": address, "id": owner}
    return JSONResponse(result, status_code=status, headers={"Cache-Control": "no-store"})


@router.get("/chat/{room}")
async def chat(room: str, request: Request, after: int = 0, x_czm_key: str | None = Header(default=None)):
    _read_limit.check(client_ip(request))
    check_room(room)
    player = await current_player(x_czm_key)

    def run(conn):
        return {
            "messages": service.messages(conn, room, max(0, after), player["id"]),
            "deleted": service.deleted_since(conn, room, after),
            "ban": service.active_ban(conn, player),
        }

    return await in_db(run)


class MessageIn(BaseModel):
    text: str = Field(max_length=1000)


class RulesIn(BaseModel):
    version: int = Field(ge=1, le=1000)


@router.post("/rules/accept")
async def rules_accept(body: RulesIn, request: Request, x_czm_key: str | None = Header(default=None)):
    _social_limit.check(client_ip(request))
    try:
        return JSONResponse(await in_db(rules.accept, x_czm_key or "", body.version), headers={"Cache-Control": "no-store"})
    except accounts.AuthError as error:
        return JSONResponse({"error": error.code, "version": rules.VERSION}, status_code=error.status)


class ModerationActIn(BaseModel):
    target: int = Field(gt=0, le=2147483647)
    action: str = Field(pattern=r"^(delete_message|remove_avatar|warn|mute_text|mute_voice|restrict_photo|ban|dismiss|close_lobby)$")
    minutes: int | None = Field(default=None, ge=0, le=365 * 24 * 60)
    reason: str = Field(default="", max_length=200)
    report: int | None = Field(default=None, gt=0)
    message: int | None = Field(default=None, gt=0)
    lobby_message: int | None = Field(default=None, gt=0)
    nonce: str = Field(pattern=r"^[A-Za-z0-9_-]{12,64}$")


class ModerationNonceIn(BaseModel):
    nonce: str = Field(pattern=r"^[A-Za-z0-9_-]{12,64}$")


class WarningSeenIn(BaseModel):
    id: int = Field(gt=0)


# The SUPPORT panel. Every request is checked for the role on the server.
@router.get("/top")
async def top(request: Request, x_czm_key: str | None = Header(default=None)):
    """The Top 100 by time on game servers, and the viewer's own place."""
    def run(conn):
        viewer = service.player_by_key(conn, x_czm_key or "") if x_czm_key else None
        return playtime.board(conn, viewer["id"] if viewer else 0)
    return JSONResponse(await in_db(run), headers={"Cache-Control": "no-store"})


@router.get("/moderation/summary")
async def moderation_summary(request: Request, x_czm_key: str | None = Header(default=None)):
    return await social_result(request, lambda c: moderation.summary(c, x_czm_key or ""))


@router.get("/moderation/reports")
async def moderation_reports(request: Request, offset: int = 0, x_czm_key: str | None = Header(default=None)):
    return await social_result(request, lambda c: moderation.reports(c, x_czm_key or "", max(0, min(offset, 100000))))


@router.get("/moderation/sanctions")
async def moderation_sanctions(request: Request, x_czm_key: str | None = Header(default=None)):
    return await social_result(request, lambda c: moderation.sanctions(c, x_czm_key or ""))


@router.get("/moderation/history")
async def moderation_history(request: Request, offset: int = 0, x_czm_key: str | None = Header(default=None)):
    return await social_result(request, lambda c: moderation.history(c, x_czm_key or "", max(0, min(offset, 100000))))


@router.get("/moderation/player/{target}")
async def moderation_player(target: int, request: Request, message: int = 0, lobby_message: int = 0,
                            x_czm_key: str | None = Header(default=None)):
    return await social_result(request, lambda c: moderation.player(c, x_czm_key or "", target,
                                                                    max(0, message), max(0, lobby_message)))


@router.post("/moderation/act")
async def moderation_act(body: ModerationActIn, request: Request, x_czm_key: str | None = Header(default=None)):
    return await social_result(request, lambda c: moderation.act(
        c, x_czm_key or "", body.target, body.action, body.minutes, body.reason,
        body.report, body.message, body.lobby_message, body.nonce))


@router.post("/moderation/sanctions/{sanction}/lift")
async def moderation_lift(sanction: int, body: ModerationNonceIn, request: Request, x_czm_key: str | None = Header(default=None)):
    return await social_result(request, lambda c: moderation.lift(c, x_czm_key or "", sanction, body.nonce))


@router.post("/moderation/warning/seen")
async def moderation_warning_seen(body: WarningSeenIn, request: Request, x_czm_key: str | None = Header(default=None)):
    return await social_result(request, lambda c: moderation.warning_seen(c, x_czm_key or "", body.id))


def rules_refused():
    return JSONResponse({"error": "rules", "version": rules.VERSION}, status_code=403, headers={"Cache-Control": "no-store"})


@router.post("/chat/{room}")
async def post(room: str, body: MessageIn, x_czm_key: str | None = Header(default=None)):
    check_room(room)
    player = await current_player(x_czm_key)
    if rules.required(player):
        return rules_refused()
    try:
        return await in_db(service.post_message, player, room, body.text)
    except service.ChatError as e:
        return JSONResponse({"error": e.code, **e.extra}, status_code=e.status)


class ReportIn(BaseModel):
    message: int | None = None
    player: int | None = None
    private_message: int | None = None
    lobby_message: int | None = None
    # with player: someone in that room (voice, behaviour); alone: the room's name
    lobby: str | None = Field(default=None, max_length=64)


@router.post("/report")
async def report(body: ReportIn, x_czm_key: str | None = Header(default=None)):
    reporter = await current_player(x_czm_key)
    try:
        info = await in_db(service.report, reporter, body.message, body.player, body.private_message,
                           body.lobby_message, body.lobby)
    except service.ChatError as e:
        return JSONResponse({"error": e.code, **e.extra}, status_code=e.status)
    if info and notify_report:
        asyncio.create_task(notify_report(info))
    return {"ok": True}


# Social data is private to the authenticated viewer; never cache these responses.
async def social_result(request, operation):
    _social_limit.check(client_ip(request))

    def run(conn):
        try:
            return 200, operation(conn)
        except accounts.AuthError as error:
            # Rate counters are committed even when an operation is rejected.
            return error.status, {"error": error.code}

    status, result = await in_db(run)
    return JSONResponse(result, status_code=status, headers={"Cache-Control": "no-store"})


class PresenceIn(BaseModel):
    server: str = Field(default="", max_length=64)
    map: str = Field(default="", max_length=64)


class SocialStatusIn(BaseModel):
    text: str = Field(max_length=400)


class SocialActionIn(BaseModel):
    target: int = Field(default=0, ge=0, le=2147483647)
    action: str = Field(pattern=r"^(follow|unfollow|block|unblock|seen)$")


class PrivateMessageIn(BaseModel):
    text: str = Field(max_length=1600)
    nonce: str = Field(pattern=r"^[A-Za-z0-9_-]{16,64}$")


class PrivateReadIn(BaseModel):
    through: int = Field(ge=0, le=2147483647)


class NoticeReadIn(BaseModel):
    kind: str = Field(pattern=r"^(friends|followers|following)$")
    ids: list[int] = Field(min_length=0, max_length=40)


@router.post("/social/notifications/read")
async def social_notice_read(body: NoticeReadIn, request: Request, x_czm_key: str | None = Header(default=None)):
    def run(conn):
        player = social.actor(conn, x_czm_key or "")["id"]
        notifications.read_events(conn, player, body.kind, body.ids)
        return {"counts": social.counts(conn, player)}
    return await social_result(request, run)


@router.post("/chat/{room}/read")
async def chat_read(room: str, body: PrivateReadIn, request: Request, x_czm_key: str | None = Header(default=None)):
    check_room(room)
    def run(conn):
        player = social.actor(conn, x_czm_key or "")["id"]
        notifications.read_chat(conn, player, room, body.through)
        return {"counts": social.counts(conn, player)}
    return await social_result(request, run)


@router.post("/social/presence")
async def social_presence(body: PresenceIn, request: Request, x_czm_key: str | None = Header(default=None)):
    return await social_result(request, lambda c: social.heartbeat(c, x_czm_key or "", body.server, body.map))


@router.get("/social/summary")
async def social_summary(request: Request, x_czm_key: str | None = Header(default=None)):
    return await social_result(request, lambda c: social.summary(c, x_czm_key or ""))


@router.get("/social/profile/{target}")
async def social_profile(target: int, request: Request, x_czm_key: str | None = Header(default=None)):
    return await social_result(request, lambda c: {"profile": social.profile(c, social.actor(c, x_czm_key or "", False), target)})


@router.post("/social/status")
async def social_status(body: SocialStatusIn, request: Request, x_czm_key: str | None = Header(default=None)):
    return await social_result(request, rules.guarded(x_czm_key, lambda c: social.update_status(c, x_czm_key or "", body.text)))


@router.post("/social/action")
async def social_action(body: SocialActionIn, request: Request, x_czm_key: str | None = Header(default=None)):
    return await social_result(request, lambda c: social.action(c, x_czm_key or "", body.target, body.action))


@router.get("/social/people/{kind}")
async def social_people(kind: str, request: Request, offset: int = 0, x_czm_key: str | None = Header(default=None)):
    return await social_result(request, lambda c: social.people(c, x_czm_key or "", kind, max(0, min(1000000, offset))))


@router.get("/social/dialogs")
async def social_dialogs(request: Request, offset: int = 0, x_czm_key: str | None = Header(default=None)):
    return await social_result(request, lambda c: social.dialogs(c, x_czm_key or "", max(0, min(1000000, offset))))


@router.get("/social/dialog/{target}")
async def social_history(target: int, request: Request, before: int = 0, x_czm_key: str | None = Header(default=None)):
    return await social_result(request, lambda c: social.history(c, x_czm_key or "", target, max(0, before)))


@router.post("/social/dialog/{target}")
async def social_send(target: int, body: PrivateMessageIn, request: Request, x_czm_key: str | None = Header(default=None)):
    return await social_result(request, rules.guarded(x_czm_key, lambda c: social.send(c, x_czm_key or "", target, body.text, body.nonce)))


class InviteIn(BaseModel):
    server: str = Field(max_length=21)
    proto: str = Field(pattern=r"^(gs|49)$")
    name: str = Field(default="", max_length=128)
    nonce: str = Field(pattern=r"^[A-Za-z0-9_-]{16,64}$")


@router.post("/social/invite/{target}")
async def social_invite(target: int, body: InviteIn, request: Request, x_czm_key: str | None = Header(default=None)):
    return await social_result(request, lambda c: social.invite(c, x_czm_key or "", target, body.server, body.proto, body.name, body.nonce))


@router.post("/social/dialog/{target}/read")
async def social_read(target: int, body: PrivateReadIn, request: Request, x_czm_key: str | None = Header(default=None)):
    return await social_result(request, lambda c: social.mark_read(c, x_czm_key or "", target, body.through))


@router.post("/mappic/{name}")
async def mappic(name: str, request: Request, x_czm_key: str | None = Header(default=None)):
    player = await current_player(x_czm_key)
    if await in_db(service.active_ban, player):
        raise HTTPException(403, {"error": "banned"})
    try:
        name = mappics.map_name(name)
    except ValueError:
        raise HTTPException(400, {"error": "map"})
    folder = get_settings().mappic_dir
    if (folder / f"{name}.png").is_file():
        return JSONResponse({"ok": True, "exists": True}, status_code=409)
    data = await request.body()
    try:
        png = await asyncio.to_thread(mappics.prepare, data)
    except ValueError as error:
        code = str(error)
        raise HTTPException(413 if code == "size" else 422 if code == "dark" else 400, {"error": code})
    except Exception:
        raise HTTPException(400, {"error": "image"})
    created = await asyncio.to_thread(mappics.publish, folder, name, png)
    return JSONResponse({"ok": True, "exists": not created}, status_code=201 if created else 409)


@router.post("/avatar")
async def avatar(request: Request, x_czm_key: str | None = Header(default=None)):
    """The player's own photo: a PNG or JPEG up to 512 KB, stored as a 192 px PNG."""
    _upload_limit.check(client_ip(request))
    player = await current_player(x_czm_key)
    if rules.required(player):
        return rules_refused()
    photo = await in_db(moderation.sanction, player, "photo")
    if photo:
        return JSONResponse({"error": "photo_restricted", "restriction": photo}, status_code=403)
    data = await request.body()
    if not data or len(data) > 512 * 1024:
        raise HTTPException(413, {"error": "size"})

    def convert() -> bytes:
        image = Image.open(io.BytesIO(data))
        if image.format not in ("PNG", "JPEG", "WEBP") or image.width * image.height > 4096 * 4096:
            raise ValueError("format")
        image = image.convert("RGBA").resize((192, 192), Image.LANCZOS)
        out = io.BytesIO()
        image.save(out, "PNG", optimize=True)
        return out.getvalue()

    try:
        png = await asyncio.to_thread(convert)
    except Exception:
        raise HTTPException(400, {"error": "image"})

    ban = await in_db(service.active_ban, player)
    if ban:
        return JSONResponse({"error": "banned", "ban": ban}, status_code=403)

    folder = get_settings().avatar_dir
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{player['id']}.png"
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(png)
    tmp.replace(path)
    rev = await in_db(service.set_photo, player["id"])
    return {"avatar": f"photo:{rev}"}


_online = {"time": 0.0, "count": 0}


@router.get("/online")
async def online(request: Request):
    """How many players have the game open, for the chat button. Counted at most every 30 s."""
    _read_limit.check(client_ip(request))
    if time.monotonic() - _online["time"] > 30:
        _online["count"] = await in_db(social.online_count)
        _online["time"] = time.monotonic()
    return {"online": _online["count"]}


_site_stats = {"time": 0.0, "data": None}


@router.get("/site/stats")
async def site_stats(request: Request):
    """Live numbers for counter-zombie.ru, counted at most every 20 s."""
    _read_limit.check(client_ip(request))
    if _site_stats["data"] is None or time.monotonic() - _site_stats["time"] > 20:
        _site_stats["data"] = await in_db(website.stats)
        _site_stats["time"] = time.monotonic()
    return JSONResponse(_site_stats["data"], headers={"Cache-Control": "no-cache"})


@router.get("/site/chat")
async def site_chat(request: Request, after: int = 0):
    """The game chat as a read-only broadcast: nobody writes from the site."""
    _read_limit.check(client_ip(request))

    def run(conn):
        return {"messages": website.chat(conn, after), "deleted": website.deleted(conn, after)}

    return JSONResponse(await in_db(run), headers={"Cache-Control": "no-cache"})


@router.get("/site/news")
async def site_news(request: Request):
    _read_limit.check(client_ip(request))
    return JSONResponse({"news": await in_db(website.news)}, headers={"Cache-Control": "public, max-age=300"})


@router.get("/news")
async def news(request: Request, after: int = 0):
    _read_limit.check(client_ip(request))
    return {"news": await in_db(service.news, max(0, after))}


@router.get("/update")
async def update(request: Request, code: int = 0, x_czm_key: str | None = Header(default=None)):
    _read_limit.check(client_ip(request))
    release = await in_db(distribution.update_for, x_czm_key or "", code)
    return JSONResponse({"update": release}, headers={"Cache-Control": "no-store"})


class DevelopmentIn(BaseModel):
    invite: str = Field(min_length=32, max_length=32, pattern=r"^[A-Za-z0-9_-]{32}$")


@router.post("/development/activate")
async def development_activate(body: DevelopmentIn, request: Request, x_czm_key: str | None = Header(default=None)):
    _upload_limit.check(client_ip(request))
    try:
        return JSONResponse(await in_db(distribution.activate, x_czm_key or "", body.invite), headers={"Cache-Control": "no-store"})
    except accounts.AuthError as e:
        return JSONResponse({"error": e.code}, status_code=e.status, headers={"Cache-Control": "no-store"})


@router.get("/development/invite/{token}")
async def development_invitation(token: str, request: Request):
    _read_limit.check(client_ip(request))
    page = await in_db(distribution.invite_page, token)
    if page is None:
        raise HTTPException(404)
    return HTMLResponse(page, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"})


@download_router.api_route("/dl/{filename}", methods=["GET", "HEAD"])
async def distribution_download(filename: str, ticket: str = "", invite: str = ""):
    path = await in_db(distribution.download_path, filename, ticket, invite)
    if path is None:
        return JSONResponse({"error": "google_play_only"}, status_code=403, headers={"Cache-Control": "no-store"})
    return FileResponse(path, filename=path.name, headers={"Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer"})


@download_router.api_route("/download", methods=["GET", "HEAD"])
@download_router.api_route("/download/CounterZombieMobile.apk", methods=["GET", "HEAD"])
async def download_latest(request: Request):
    """Legacy website APK entry point; installation is now Google Play only."""
    return JSONResponse({"error": "google_play_only", "message": "Join the Google Play beta"},
                        status_code=410, headers={"Cache-Control": "no-store"})


class SettingsIn(BaseModel):
    revision: int = Field(ge=0,le=2147483647)
    payload: dict

@router.get("/settings")
async def get_account_settings(x_czm_key: str | None = Header(default=None)):
    try:
        return JSONResponse(await in_db(settings.load,x_czm_key or ""),headers={"Cache-Control":"no-store"})
    except accounts.AuthError as e:
        return JSONResponse({"error":e.code},status_code=e.status,headers={"Cache-Control":"no-store"})

@router.post("/settings")
async def save_account_settings(body: SettingsIn,x_czm_key: str | None = Header(default=None)):
    def run(conn):
        try:return 200,settings.save(conn,x_czm_key or "",body.revision,body.payload)
        except accounts.AuthError as e:return e.status,{"error":e.code}
    status,result=await in_db(run)
    return JSONResponse(result,status_code=status,headers={"Cache-Control":"no-store"})


# Ephemeral team lobbies. Existing clients do not call these routes.
_lobby_limit = _Limiter(180, 60)

async def lobby_result(request, action):
    _lobby_limit.check(client_ip(request))
    try:
        result=await in_db(action)
        if isinstance(result,dict) and "_status" in result:
            result=dict(result)
            status=result.pop("_status")
            return JSONResponse(result,status_code=status,headers={"Cache-Control":"no-store"})
        return JSONResponse(result, headers={"Cache-Control":"no-store"})
    except accounts.AuthError as error:
        return JSONResponse({"error": error.code}, status_code=error.status,
                            headers={"Cache-Control":"no-store"})

class LobbyCreateIn(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    description: str = Field(default="", max_length=400)
    visibility: str = Field(pattern=r"^(public|private)$")
    capacity: int = Field(ge=2, le=6)
    server: str = Field(min_length=7, max_length=64)
    proto: str = Field(pattern=r"^(gs|49)$")
    nonce: str = Field(min_length=12, max_length=64)
    language: str = Field(default="", pattern=r"^(ru|en)?$")

class LobbyReadyIn(BaseModel):
    revision: int = Field(ge=1)
    ready: bool

class LobbyServerIn(BaseModel):
    server: str = Field(min_length=7,max_length=64)
    proto: str = Field(pattern=r"^(gs|49)$")

class LobbyTargetIn(BaseModel):
    target: int = Field(gt=0)

class LobbyMessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=400)
    nonce: str = Field(min_length=12, max_length=64)

@router.post("/lobbies")
async def lobby_create(body:LobbyCreateIn, request:Request,
                       x_czm_key:str|None=Header(default=None)):
    return await lobby_result(request,rules.guarded(x_czm_key,lambda c:lobbies.create(
        c,x_czm_key or "",body.title,body.description,body.visibility,
        body.capacity,body.server,body.proto,body.nonce,body.language)))

@router.get("/lobbies")
async def lobby_catalog(request:Request, offset:int=0, mode:str="", language:str="",
                        x_czm_key:str|None=Header(default=None)):
    return await lobby_result(request,lambda c:lobbies.catalog(c,x_czm_key or "",max(0,min(offset,1000000)),mode,language))

@router.get("/lobbies/mine")
async def lobby_mine(request:Request,x_czm_key:str|None=Header(default=None)):
    return await lobby_result(request,lambda c:lobbies.mine(c,x_czm_key or ""))

class LobbyInviteIn(BaseModel):
    nonce: str = Field(min_length=12,max_length=64)

class LobbyInviteAnswerIn(BaseModel):
    accept: bool

class LobbyEditIn(BaseModel):
    title: str = Field(min_length=3,max_length=160)
    description: str = Field(default="",max_length=400)
    visibility: str = Field(pattern=r"^(public|private)$")
    capacity: int = Field(ge=2,le=6)

@router.get("/lobbies/invitations")
async def lobby_invitations(request:Request,x_czm_key:str|None=Header(default=None)):
    return await lobby_result(request,lambda c:lobbies.invitations(c,x_czm_key or ""))

@router.post("/lobbies/invitations/{invitation}/answer")
async def lobby_invite_answer(invitation:str,body:LobbyInviteAnswerIn,request:Request,
                              x_czm_key:str|None=Header(default=None)):
    return await lobby_result(request,lambda c:lobbies.answer_invitation(
        c,x_czm_key or "",invitation,body.accept))

@router.get("/lobbies/launches/pending")
async def lobby_pending_launches(request:Request,x_czm_key:str|None=Header(default=None)):
    return await lobby_result(request,lambda c:lobbies.pending_launch(c,x_czm_key or ""))


@router.get("/lobbies/{room}")
async def lobby_detail(room:str,request:Request,x_czm_key:str|None=Header(default=None)):
    return await lobby_result(request,lambda c:lobbies.detail(c,x_czm_key or "",room))

@router.post("/lobbies/{room}/join")
async def lobby_join(room:str,request:Request,x_czm_key:str|None=Header(default=None)):
    return await lobby_result(request,lambda c:lobbies.join(c,x_czm_key or "",room))

@router.post("/lobbies/{room}/leave")
async def lobby_leave(room:str,request:Request,x_czm_key:str|None=Header(default=None)):
    return await lobby_result(request,lambda c:lobbies.leave(c,x_czm_key or "",room))

@router.post("/lobbies/{room}/ready")
async def lobby_ready(room:str,body:LobbyReadyIn,request:Request,
                      x_czm_key:str|None=Header(default=None)):
    return await lobby_result(request,lambda c:lobbies.ready(c,x_czm_key or "",room,body.revision,body.ready))

@router.post("/lobbies/{room}/server")
async def lobby_server(room:str,body:LobbyServerIn,request:Request,
                       x_czm_key:str|None=Header(default=None)):
    return await lobby_result(request,lambda c:lobbies.change_server(c,x_czm_key or "",room,body.server,body.proto))

@router.post("/lobbies/{room}/transfer")
async def lobby_transfer(room:str,body:LobbyTargetIn,request:Request,
                         x_czm_key:str|None=Header(default=None)):
    return await lobby_result(request,lambda c:lobbies.transfer(c,x_czm_key or "",room,body.target))

@router.post("/lobbies/{room}/kick")
async def lobby_kick(room:str,body:LobbyTargetIn,request:Request,
                     x_czm_key:str|None=Header(default=None)):
    return await lobby_result(request,lambda c:lobbies.kick(c,x_czm_key or "",room,body.target))

@router.get("/lobbies/{room}/messages")
async def lobby_messages(room:str,request:Request,before:int=0,
                         x_czm_key:str|None=Header(default=None)):
    return await lobby_result(request,lambda c:lobbies.chat(c,x_czm_key or "",room,max(0,before)))

@router.post("/lobbies/{room}/messages")
async def lobby_send(room:str,body:LobbyMessageIn,request:Request,
                     x_czm_key:str|None=Header(default=None)):
    return await lobby_result(request,rules.guarded(x_czm_key,lambda c:lobbies.send(c,x_czm_key or "",room,body.text,body.nonce)))


@router.post("/lobbies/{room}/invite/{target}")
async def lobby_invite(room:str,target:int,body:LobbyInviteIn,request:Request,
                       x_czm_key:str|None=Header(default=None)):
    return await lobby_result(request,lambda c:lobbies.invite(c,x_czm_key or "",room,target,body.nonce))

@router.post("/lobbies/{room}/edit")
async def lobby_edit(room:str,body:LobbyEditIn,request:Request,
                     x_czm_key:str|None=Header(default=None)):
    return await lobby_result(request,rules.guarded(x_czm_key,lambda c:lobbies.edit(
        c,x_czm_key or "",room,body.title,body.description,body.visibility,body.capacity)))


class LobbyLaunchIn(BaseModel):
    nonce: str = Field(min_length=12,max_length=64)
    revision: int = Field(ge=1)


@router.post("/lobbies/{room}/heartbeat")
async def lobby_heartbeat(room:str,request:Request,x_czm_key:str|None=Header(default=None)):
    return await lobby_result(request,lambda c:lobbies.owner_heartbeat(c,x_czm_key or "",room))


@router.post("/lobbies/{room}/launch")
async def lobby_launch_checked(room:str,body:LobbyLaunchIn,request:Request,
                               x_czm_key:str|None=Header(default=None)):
    _lobby_limit.check(client_ip(request))
    key=x_czm_key or ""
    try:
        snap=await in_db(lobbies.launch_snapshot,key,room,body.nonce,body.revision)
        if snap["previous"]:
            return JSONResponse({"launch":snap["previous"]},headers={"Cache-Control":"no-store"})
        probe=await asyncio.to_thread(game_probe.probe,snap["server"])
        if probe["max_players"]-probe["players"]<len(snap["members"]):
            raise accounts.AuthError("server_full",409)
        result=await in_db(lobbies.commit_launch_snapshot,key,room,body.nonce,body.revision,snap)
        return JSONResponse(result,headers={"Cache-Control":"no-store"})
    except accounts.AuthError as e:
        return JSONResponse({"error":e.code},status_code=e.status,headers={"Cache-Control":"no-store"})
    except game_probe.ProbeError as e:
        return JSONResponse({"error":"server_unavailable"},status_code=503,headers={"Cache-Control":"no-store"})


@router.post("/lobbies/launches/{launch}/ack")
async def lobby_launch_ack(launch:str,request:Request,x_czm_key:str|None=Header(default=None)):
    return await lobby_result(request,lambda c:lobbies.acknowledge_launch(c,x_czm_key or "",launch))


# Ephemeral Opus audio relay. WS headers authenticate the user; no tokens in
# URLs or in room broadcasts. No audio recording or persistent message history.
@router.websocket("/lobbies/{room}/voice")
async def lobby_voice_socket(room: str, websocket: WebSocket):
    await voice_lobby.websocket_voice(websocket,room)


class LobbyVoiceMuteIn(BaseModel):
    target: int | None = Field(default=None,ge=1)
    muted: bool


@router.post("/lobbies/{room}/voice/mute")
async def lobby_voice_mute(room:str,body:LobbyVoiceMuteIn,request:Request,
                           x_czm_key:str|None=Header(default=None)):
    return await lobby_result(request,lambda c:voice_lobby.set_host_mute(
        c,x_czm_key or "",room,body.target,body.muted))
