"""New builds from GitHub Actions: POST /api/v1/builds.

The workflow proves itself with its OIDC token (no shared secret): the token is signed by
GitHub and names the repository, branch, workflow and commit. The body is the core APK.
It is stored in the incoming folder and `czm.cli assemble` (czm-assemble.service, started
by czm-assemble.path) turns it into a release.
"""
import asyncio
import base64
import binascii
import hashlib
import logging
import re
import time

import jwt
from fastapi import APIRouter, Header, HTTPException, Request

from . import play, service
from .config import get_settings
from .db import db

log = logging.getLogger("czm.builds")
router = APIRouter(prefix="/api/v1")

ISSUER = "https://token.actions.githubusercontent.com"
_jwks = jwt.PyJWKClient(ISSUER + "/.well-known/jwks", cache_keys=True, lifespan=3600, timeout=15)
_busy = asyncio.Lock()

VERSION = re.compile(r"^[0-9A-Za-z._-]{1,32}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def check_token(token: str, workflow_file: str | None = None) -> dict:
    """The claims of a valid token of our build workflow (or of play.yml), or HTTPException 403."""
    settings = get_settings()
    try:
        key = _jwks.get_signing_key_from_jwt(token)
        claims = jwt.decode(token, key.key, algorithms=["RS256"], audience=settings.build_audience,
                            issuer=ISSUER, leeway=60, options={"require": ["exp", "iat", "aud", "iss", "sub"]})
    except Exception as e:
        log.warning("build token rejected: %s", e)
        raise HTTPException(403, {"error": "token"})
    expected = {
        "repository_id": str(settings.build_repository_id),
        "repository": settings.build_repository,
        "ref": settings.build_ref,
    }
    for name, value in expected.items():
        if str(claims.get(name, "")) != value:
            log.warning("build token for another %s: %s", name, claims.get(name))
            raise HTTPException(403, {"error": "token"})
    workflow = f"{settings.build_repository}/{workflow_file or settings.build_workflow}@{settings.build_ref}"
    # play.yml also starts by itself after a successful players' build (workflow_run, default branch only)
    events = ("push", "workflow_dispatch") + (("workflow_run",) if workflow_file == settings.play_workflow else ())
    if claims.get("workflow_ref") != workflow or claims.get("event_name") not in events:
        log.warning("build token from workflow %s (%s)", claims.get("workflow_ref"), claims.get("event_name"))
        raise HTTPException(403, {"error": "token"})
    return claims


def trigger_assembly() -> None:
    """czm-assemble.path watches this file."""
    folder = get_settings().incoming_dir
    folder.mkdir(parents=True, exist_ok=True)
    (folder / ".trigger").write_text(f"{time.time()}\n")


@router.post("/builds")
async def receive_build(request: Request, version: str, code: int, sha256: str, commit: str,
                        authorization: str | None = Header(default=None),
                        x_czm_notes: str | None = Header(default=None)):
    settings = get_settings()
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, {"error": "token"})
    claims = await asyncio.to_thread(check_token, authorization[7:].strip())
    if not VERSION.match(version) or not COMMIT.match(commit) or not SHA256.match(sha256) or not 0 < code < 2**31:
        raise HTTPException(400, {"error": "request"})
    if claims.get("sha") != commit:
        raise HTTPException(403, {"error": "commit"})
    try:
        notes = base64.b64decode(x_czm_notes or "", validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        notes = ""

    def known(conn):
        row = service.build_by_commit(conn, commit)
        return dict(row) if row else None

    def inner(fn, *args):
        def run():
            with db() as conn:
                return fn(conn, *args)
        return asyncio.to_thread(run)

    old = await inner(known)
    if old and old["status"] != "failed":
        return {"ok": True, "build": old["id"], "status": old["status"]}   # a retry of the workflow

    if _busy.locked():
        raise HTTPException(409, {"error": "busy"})
    async with _busy:
        folder = settings.incoming_dir
        folder.mkdir(parents=True, exist_ok=True)
        name = f"{commit[:12]}.core.apk"
        part = folder / (name + ".part")
        limit = settings.build_max_mb * 1024 * 1024
        digest, size = hashlib.sha256(), 0
        try:
            with part.open("wb") as f:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > limit:
                        raise HTTPException(413, {"error": "size"})
                    digest.update(chunk)
                    f.write(chunk)
            if size == 0 or digest.hexdigest() != sha256:
                raise HTTPException(400, {"error": "sha256"})
            part.replace(folder / name)
        finally:
            part.unlink(missing_ok=True)

        build_id = await inner(service.add_build, commit, version, code, notes, name)
        trigger_assembly()
        log.info("build %s (%s, %d MB) received", version, commit[:7], size // 1048576)
        return {"ok": True, "build": build_id, "status": "new"}


@router.post("/play-builds")
async def receive_play_build(request: Request, version: str, code: int, sha256: str, commit: str,
                             authorization: str | None = Header(default=None),
                             x_czm_notes: str | None = Header(default=None)):
    """An unsigned bundle for Google Play from play.yml; `czm.cli assemble` adds the game data and signs it."""
    settings = get_settings()
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, {"error": "token"})
    claims = await asyncio.to_thread(check_token, authorization[7:].strip(), settings.play_workflow)
    if not VERSION.match(version) or not COMMIT.match(commit) or not SHA256.match(sha256) or not 0 < code < 2**31:
        raise HTTPException(400, {"error": "request"})
    if claims.get("sha") != commit:
        raise HTTPException(403, {"error": "commit"})
    if (settings.play_dir / play.bundle_name(version)).is_file():
        return {"ok": True, "status": "done"}                     # a retry of the workflow
    if _busy.locked():
        raise HTTPException(409, {"error": "busy"})
    async with _busy:
        folder = settings.incoming_dir
        folder.mkdir(parents=True, exist_ok=True)
        name = play.incoming_name(commit)
        part = folder / (name + ".part")
        limit = settings.build_max_mb * 1024 * 1024
        digest, size = hashlib.sha256(), 0
        try:
            with part.open("wb") as f:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > limit:
                        raise HTTPException(413, {"error": "size"})
                    digest.update(chunk)
                    f.write(chunk)
            if size == 0 or digest.hexdigest() != sha256:
                raise HTTPException(400, {"error": "sha256"})
            (folder / name).with_suffix(".version").write_text(version + "\n")
            try:                              # what's new, for the testers in Google Play
                notes = base64.b64decode(x_czm_notes or "", validate=True).decode("utf-8")
            except (binascii.Error, UnicodeDecodeError):
                notes = ""
            (folder / name).with_suffix(".notes").write_text(notes)
            part.replace(folder / name)
        finally:
            part.unlink(missing_ok=True)
        trigger_assembly()
        log.info("Google Play bundle %s (%s, %d MB) received", version, commit[:7], size // 1048576)
        return {"ok": True, "status": "new"}
