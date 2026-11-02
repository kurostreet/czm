"""Owner-only control panel for the existing single zombie server."""
import asyncio
from dataclasses import dataclass
import hmac
import json
import logging
import os
from pathlib import Path
import shutil
import socket
import time

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from .server_panel_auth import COOKIE, SESSION_SECONDS, LocalAuth, Sessions, csrf
from .server_panel_storage import FileStore, MAX_UPLOAD, PanelError

logging.getLogger("httpx").setLevel(logging.WARNING)
PREFIX = "/api/v1/server-panel"


@dataclass
class Config:
    root: str = "/srv/czm-zm-test/game/cstrike"
    state: str = "/var/lib/czm-server-panel"
    fastdl: str = "/srv/czm-zm-test/fastdl"
    socket: str = "/run/czm-server-panel/control.sock"
    origin: str = "https://counter-zombie.ru"
    address: str = "194.226.112.249:27016"
    owners: tuple = ()
    auth_file: str = "/etc/czm-server-panel/credentials.json"

    @classmethod
    def environment(cls):
        values = {key: os.environ["CZM_PANEL_" + key.upper()] for key in cls.__dataclass_fields__
                  if key != "owners" and "CZM_PANEL_" + key.upper() in os.environ}
        values["owners"] = tuple(int(x) for x in os.getenv("CZM_PANEL_OWNERS", "").split(",") if x.strip().isdigit())
        return cls(**values)


def agent_call(path, action, **values):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(30)
        sock.connect(path)
        sock.sendall(json.dumps({"action": action, **values}).encode() + b"\n")
        out = bytearray()
        while len(out) < 100000:
            chunk = sock.recv(8192)
            if not chunk:
                break
            out.extend(chunk)
            if out.endswith(b"\n"):
                break
    result = json.loads(out)
    if not result.get("ok"):
        raise PanelError(result.get("error", "agent_unavailable"), 503)
    return result["result"]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Input):
    mode: str = Field(default="password", max_length=24)
    nick: str = Field(default="", max_length=64)
    password: str = Field(default="", max_length=128)


class Power(Input):
    action: str = Field(max_length=16)


class Command(Input):
    command: str = Field(min_length=1, max_length=512)


class Edit(Input):
    path: str = Field(max_length=512)
    text: str = Field(max_length=1024 * 1024)
    revision: str = Field(max_length=64)
    encoding: str = Field(default="utf-8", max_length=16)


class PathInput(Input):
    path: str = Field(max_length=512)
    revision: str = Field(default="", max_length=64)
    backup: str = Field(default="", max_length=80)


def create_app(config=None, auth=None, control=None):
    cfg = config or Config.environment()
    Path(cfg.state).mkdir(parents=True, exist_ok=True, mode=0o700)
    sessions = Sessions(cfg.state)
    files = FileStore(cfg.root, cfg.state, cfg.fastdl)
    gateway = auth or LocalAuth(cfg.auth_file)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.sessions, app.state.files = sessions, files
    mutation = asyncio.Lock()
    reads = asyncio.Semaphore(3)
    metrics = {"time": 0, "data": None, "disk_time": 0, "disk": 0, "cpu_ns": None, "cpu_time": None}

    async def control_call(action, **values):
        try:
            if control:
                return await asyncio.to_thread(control, action, **values)
            return await asyncio.to_thread(agent_call, cfg.socket, action, **values)
        except (OSError, ValueError):
            raise PanelError("agent_unavailable", 503) from None

    @app.middleware("http")
    async def guard(request, call_next):
        try:
            if request.method not in {"GET", "HEAD"}:
                if request.headers.get("origin") != cfg.origin:
                    raise PanelError("origin", 403)
                maximum = MAX_UPLOAD if request.method == "PUT" else 2 * 1024 * 1024
                length = request.headers.get("content-length")
                if length and (not length.isdigit() or int(length) > maximum):
                    raise PanelError("large", 413)
            response = await call_next(request)
        except PanelError as error:
            response = JSONResponse({"error": error.code}, status_code=error.status)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(PanelError)
    async def error(request, exc):
        return JSONResponse({"error": exc.code}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def invalid(request, exc):
        return JSONResponse({"error": "request"}, status_code=400)

    @app.exception_handler(FileNotFoundError)
    async def missing(request, exc):
        return JSONResponse({"error": "missing"}, status_code=404)

    @app.exception_handler(OSError)
    async def filesystem(request, exc):
        return JSONResponse({"error": "filesystem"}, status_code=400)

    def actor(request, changing=False):
        token = request.cookies.get(COOKIE, "")
        who = sessions.get(token)
        if who["owner"] not in cfg.owners:
            raise PanelError("forbidden", 403)
        if changing and not hmac.compare_digest(request.headers.get("x-czm-csrf", ""), csrf(token)):
            raise PanelError("csrf", 403)
        return who

    @app.get(PREFIX + "/session")
    async def session(request: Request):
        who = actor(request)
        return {"profile": {"id": who["owner"], "nick": who["nick"]}, "csrf": csrf(request.cookies[COOKIE]),
                "address": cfg.address, "max_upload": MAX_UPLOAD}

    @app.post(PREFIX + "/login")
    async def login(body: Login, request: Request):
        ip = request.client.host if request.client else "unknown"
        sessions.rate("login:" + ip)
        if body.mode != "password" or not cfg.owners:
            raise PanelError("forbidden", 403)
        sessions.rate("login-global", 40, 900)
        result = await gateway.action("login", {"nick": body.nick, "password": body.password}, ip)
        profile = result.get("profile", {})
        if profile.get("id") not in cfg.owners:
            raise PanelError("forbidden", 403)
        cookie = sessions.issue(profile["id"], profile.get("nick", "Owner"))
        sessions.audit(profile["id"], "login")
        response = JSONResponse({"ok": True})
        response.set_cookie(COOKIE, cookie, max_age=SESSION_SECONDS, secure=True, httponly=True, samesite="strict", path="/")
        return response

    @app.post(PREFIX + "/logout")
    async def logout(request: Request):
        actor(request, True)
        sessions.revoke(request.cookies[COOKIE])
        response = JSONResponse({"ok": True})
        response.delete_cookie(COOKIE, path="/", secure=True, httponly=True, samesite="strict")
        return response

    def disk_size():
        total = 0
        for folder, dirs, names in os.walk(cfg.root, followlinks=False):
            dirs[:] = [d for d in dirs if not Path(folder, d).is_symlink()]
            for name in names:
                try:
                    file = Path(folder, name)
                    if not file.is_symlink():
                        total += file.stat().st_size
                except OSError:
                    pass
        return total

    @app.get(PREFIX + "/status")
    async def status(request: Request):
        actor(request)
        async with reads:
            now = time.monotonic()
            if now - metrics["time"] > 3 or metrics["data"] is None:
                result = await control_call("status")
                cpu = 0
                if metrics["cpu_ns"] is not None and metrics["cpu_time"] is not None:
                    cpu = max(0, min(100, (result["cpu_ns"] - metrics["cpu_ns"]) / 1e9 / max(.1, now - metrics["cpu_time"]) * 100))
                metrics.update(cpu_ns=result["cpu_ns"], cpu_time=now)
                if now - metrics["disk_time"] > 30:
                    metrics.update(disk=await asyncio.to_thread(disk_size), disk_time=now)
                metrics.update(time=now, data={**result, "cpu": round(cpu, 1), "disk": metrics["disk"],
                                              "address": cfg.address, "observed_at": int(time.time())})
            return metrics["data"]

    @app.post(PREFIX + "/power")
    async def power(body: Power, request: Request):
        who = actor(request, True)
        if body.action not in {"start", "stop", "restart"}:
            raise PanelError("action")
        sessions.rate("power:" + str(who["owner"]), 10, 60)
        async with mutation:
            sessions.audit(who["owner"], "power:" + body.action, result="requested")
            result = await control_call("power", verb=body.action)
            metrics["time"] = 0
            sessions.audit(who["owner"], "power:" + body.action)
            return result

    @app.get(PREFIX + "/console")
    async def logs(request: Request):
        actor(request)
        return await control_call("logs")

    @app.post(PREFIX + "/console")
    async def console(body: Command, request: Request):
        who = actor(request, True)
        sessions.rate("console:" + str(who["owner"]), 30, 60)
        # Commands can contain private cvars. Audit the operation, never its content.
        sessions.audit(who["owner"], "console")
        return await control_call("console", command=body.command)

    @app.get(PREFIX + "/files")
    async def listing(request: Request, path: str = ""):
        actor(request)
        return await asyncio.to_thread(files.list, path)

    @app.get(PREFIX + "/file")
    async def read(request: Request, path: str):
        actor(request)
        return await asyncio.to_thread(files.read, path)

    @app.get(PREFIX + "/metadata")
    async def metadata(request: Request, path: str):
        actor(request)
        return await asyncio.to_thread(files.metadata, path)

    @app.post(PREFIX + "/file")
    async def save(body: Edit, request: Request):
        who = actor(request, True)
        async with mutation:
            result = await asyncio.to_thread(files.write, body.path, body.text.encode(), body.revision, True, body.encoding)
        sessions.audit(who["owner"], "save", body.path)
        return result

    @app.post(PREFIX + "/directory")
    async def mkdir(body: PathInput, request: Request):
        who = actor(request, True)
        result = await asyncio.to_thread(files.mkdir, body.path)
        sessions.audit(who["owner"], "mkdir", body.path)
        return result

    @app.put(PREFIX + "/upload")
    async def upload(request: Request, path: str):
        who = actor(request, True)
        files.parts(path)
        sessions.rate("upload:" + str(who["owner"]), 30, 60)
        revision = request.headers.get("if-match", "")
        if not revision:
            raise PanelError("revision")
        async with mutation:
            if shutil.disk_usage(cfg.root).free < MAX_UPLOAD * 4:
                raise PanelError("disk_full", 507)
            import tempfile
            with tempfile.TemporaryFile(dir=cfg.state) as temp:
                size = 0
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > MAX_UPLOAD:
                        raise PanelError("large", 413)
                    temp.write(chunk)
                temp.seek(0)
                result = await asyncio.to_thread(files.write, path, temp.read(), revision)
        sessions.audit(who["owner"], "upload", path)
        metrics["disk_time"] = 0
        return result

    @app.get(PREFIX + "/download")
    async def download(request: Request, path: str):
        actor(request)
        # server.cfg goes through the editor so management credentials never leave the host.
        if path == "server.cfg":
            raise PanelError("use_editor", 403)
        files.parts(path)
        def stream():
            with files.open_file(path) as file:
                while chunk := file.read(128 * 1024):
                    yield chunk
        from urllib.parse import quote
        return StreamingResponse(stream(), media_type="application/octet-stream", headers={
            "Content-Disposition": "attachment; filename*=UTF-8''" + quote(Path(path).name)})

    @app.delete(PREFIX + "/file")
    async def delete(request: Request, path: str):
        who = actor(request, True)
        async with mutation:
            result = await asyncio.to_thread(files.delete, path, request.headers.get("if-match", ""))
        sessions.audit(who["owner"], "delete", path)
        metrics["disk_time"] = 0
        return result

    @app.get(PREFIX + "/history")
    async def history(request: Request, path: str):
        actor(request)
        return {"entries": await asyncio.to_thread(files.history, path)}

    @app.post(PREFIX + "/restore")
    async def restore(body: PathInput, request: Request):
        who = actor(request, True)
        async with mutation:
            result = await asyncio.to_thread(files.restore, body.path, body.backup, body.revision)
        sessions.audit(who["owner"], "restore", body.path)
        return result

    return app


def application():
    return create_app()
