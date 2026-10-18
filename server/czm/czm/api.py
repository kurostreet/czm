"""HTTP API for the game. JSON, the player's secret key comes in the X-CZM-Key header."""
import asyncio
import io
import logging
import time
from collections import defaultdict, deque
from typing import Any, Callable

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from PIL import Image
from pydantic import BaseModel, Field

from . import service, mappics, accounts, settings, tab, social, website
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


@router.post("/hello")
async def hello(body: HelloIn, request: Request):
    _hello_limit.check(client_ip(request))

    def run(conn):
        player = service.hello(conn, body.key, body.device, body.nick, body.avatar, body.lang, body.version, body.keep_avatar)
        release = service.latest_release(conn, base_code=body.code)
        return {
            "id": player["id"],
            "avatar": service.avatar_ref(player),
            "ban": service.active_ban(conn, player),
            "news": service.last_news_id(conn),
            "update": release if release and release["code"] > body.code else None,
            "rooms": get_settings().room_list,
            "max_chars": get_settings().message_max_chars,
        }

    try:
        return await in_db(run)
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
    return JSONResponse(result, status_code=status, headers={"Cache-Control": "no-store"})


@router.get("/chat/{room}")
async def chat(room: str, request: Request, after: int = 0, x_czm_key: str | None = Header(default=None)):
    _read_limit.check(client_ip(request))
    check_room(room)
    player = await current_player(x_czm_key)

    def run(conn):
        return {
            "messages": service.messages(conn, room, max(0, after)),
            "deleted": service.deleted_since(conn, room, after),
            "ban": service.active_ban(conn, player),
        }

    return await in_db(run)


class MessageIn(BaseModel):
    text: str = Field(max_length=1000)


@router.post("/chat/{room}")
async def post(room: str, body: MessageIn, x_czm_key: str | None = Header(default=None)):
    check_room(room)
    player = await current_player(x_czm_key)
    try:
        return await in_db(service.post_message, player, room, body.text)
    except service.ChatError as e:
        return JSONResponse({"error": e.code, **e.extra}, status_code=e.status)


class ReportIn(BaseModel):
    message: int | None = None
    player: int | None = None
    private_message: int | None = None


@router.post("/report")
async def report(body: ReportIn, x_czm_key: str | None = Header(default=None)):
    reporter = await current_player(x_czm_key)
    try:
        info = await in_db(service.report, reporter, body.message, body.player, body.private_message)
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
    return await social_result(request, lambda c: social.update_status(c, x_czm_key or "", body.text))


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
    return await social_result(request, lambda c: social.send(c, x_czm_key or "", target, body.text, body.nonce))


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
async def update(request: Request, code: int = 0):
    _read_limit.check(client_ip(request))
    release = await in_db(lambda conn: service.latest_release(conn, base_code=code))
    return {"update": release if release and release["code"] > code else None}


@download_router.api_route("/download", methods=["GET", "HEAD"])
@download_router.api_route("/download/CounterZombieMobile.apk", methods=["GET", "HEAD"])
async def download_latest(request: Request):
    """One shareable link follows the published full APK, including rollbacks."""
    def available(conn):
        release = service.latest_release(conn)
        if not release:
            return None
        name = release["url"].rsplit("/", 1)[-1]
        path = get_settings().apk_dir / name
        if path.is_file() and release["size"] > 0 and path.stat().st_size == release["size"]:
            return release["url"]
        return None

    url = await in_db(available)
    headers = {"Cache-Control": "no-store"}
    if url and request.method == "GET":
        try:
            await in_db(website.record_download, client_ip(request))
        except Exception:
            log.warning("download not counted")  # the download itself goes on
    if not url:
        return JSONResponse({"error": "unavailable"}, status_code=503,
                            headers={**headers, "Retry-After": "60"})
    return RedirectResponse(url, status_code=307, headers=headers)


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
