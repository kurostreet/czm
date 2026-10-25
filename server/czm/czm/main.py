"""Counter Zombie Mobile service: API for the game, the owner's bot and the world server list.

One process (uvicorn) keeps the memory use small: the API, the bot polling and the
background jobs share the event loop.
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from . import api, builds, db, play_feed, steam
from .config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
# request lines of httpx would carry the Steam key
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("czm")


async def cleanup_loop() -> None:
    settings = get_settings()
    while True:
        try:
            def run():
                with db.db() as conn:
                    db.cleanup(conn, settings.keep_days, settings.room_history, settings.room_list)
            await asyncio.to_thread(run)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("cleanup failed: %s", e)
        await asyncio.sleep(3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    db.init()
    for folder in (settings.avatar_dir, settings.apk_dir, settings.incoming_dir, settings.serverlist_file.parent):
        folder.mkdir(parents=True, exist_ok=True)

    tasks = [asyncio.create_task(cleanup_loop()), asyncio.create_task(steam.run()), asyncio.create_task(play_feed.run())]
    bot = None
    if settings.bot_token and settings.owner_ids:
        from . import bot as botmod
        bot, dispatcher, owner = botmod.build(settings)
        api.notify_report = owner.notify_report
        tasks.append(asyncio.create_task(botmod.run_bot(bot, dispatcher)))
        tasks.append(asyncio.create_task(botmod.builds_loop(owner)))
    else:
        log.info("no bot token or owners, complaints only stay in the database")

    yield

    for task in tasks:
        task.cancel()
    if bot is not None:
        await bot.session.close()


app = FastAPI(title="Counter Zombie Mobile", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(api.router)
app.include_router(api.download_router)
app.include_router(builds.router)


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    # the game reads {"error": ...} at the top level
    body = exc.detail if isinstance(exc.detail, dict) else {"error": str(exc.detail)}
    return JSONResponse(body, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def bad_request(request: Request, exc: RequestValidationError):
    return JSONResponse({"error": "request"}, status_code=400)


@app.get("/api/v1/ping")
async def ping():
    return {"ok": True}
