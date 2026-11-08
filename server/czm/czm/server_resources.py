"""Trusted data packs for the two owner-managed logical server slots.

The visibility switch is intentionally not consulted here. A pack is offered only
when a configured slot has an explicitly activated immutable published revision.
"""
import hashlib
import json
import re
import sqlite3
from pathlib import Path

from . import official
from .config import get_settings
from .db import now

SCHEMA = """
CREATE TABLE IF NOT EXISTS official_resources (
 slot TEXT PRIMARY KEY CHECK(slot IN ('survival','escape')),
 enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
 pack_id TEXT NOT NULL DEFAULT '', revision TEXT NOT NULL DEFAULT '',
 manifest_sha256 TEXT NOT NULL DEFAULT '', download_bytes INTEGER NOT NULL DEFAULT 0,
 updated INTEGER NOT NULL DEFAULT 0
);
"""
ORIGIN = "https://kontrafps.ru"
MAX_AGE = 60
MAX_FILES = 16384
MAX_FILE_BYTES = 512 * 1024 * 1024
MAX_TOTAL_BYTES = 8 * 1024 * 1024 * 1024
MAX_MANIFEST_BYTES = 8 * 1024 * 1024
ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
HASH = re.compile(r"[0-9a-f]{64}\Z")
COMPONENT = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9_. -]{0,79}\Z")


def identifier(value: str) -> str:
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError("invalid pack/revision identifier")
    return value


def asset_path(value: str) -> str:
    if not isinstance(value, str) or len(value) > 240:
        raise ValueError("invalid asset path")
    parts = value.split("/")
    if not 1 <= len(parts) <= 8 or any(not COMPONENT.fullmatch(p) or p.endswith((".", " ")) for p in parts):
        raise ValueError("invalid asset path")
    return value


def root() -> Path:
    return get_settings().data_dir / "server-resources"


def url(pack_id: str, revision: str, leaf: str) -> str:
    return f"{ORIGIN}/server-resources/{identifier(pack_id)}/{identifier(revision)}/{leaf}"


def published_file(pack_id: str, revision: str, leaf: str, resource_root: Path | None = None) -> Path:
    """Only immutable manifest/archive/hash objects, never arbitrary relative files."""
    identifier(pack_id); identifier(revision)
    if leaf not in ("manifest.json", "bundle.zip") and not (leaf.startswith("files/") and HASH.fullmatch(leaf[6:])):
        raise ValueError("invalid resource object")
    store = resource_root or root()
    if store.is_symlink():
        raise ValueError("linked resource store")
    base = store / "published"
    path = base / pack_id / revision / leaf
    # Refuse linked files and linked parents, including a symlinked published root.
    probe = base
    for component in ("", pack_id, revision, *leaf.split("/")):
        if component:
            probe = probe / component
        if probe.is_symlink():
            raise ValueError("linked resource object")
    if not path.is_file():
        raise FileNotFoundError("resource object missing")
    return path


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def catalog(conn: sqlite3.Connection) -> dict:
    addresses = official.state(conn)  # enabled is visibility only, never eligibility
    assigned = {row["slot"]: row for row in conn.execute("SELECT * FROM official_resources")}
    servers = []
    for slot in official.SLOTS:
        item = {"server_id": slot, "address": addresses[slot], "resources_enabled": False}
        row = assigned.get(slot)
        if addresses[slot] and row and row["enabled"]:
            try:
                manifest = published_file(row["pack_id"], row["revision"], "manifest.json")
                if not HASH.fullmatch(row["manifest_sha256"]) or not 0 < manifest.stat().st_size <= MAX_MANIFEST_BYTES:
                    raise ValueError("invalid manifest")
                # Failure to read the activated manifest closes eligibility immediately.
                if digest(manifest) != row["manifest_sha256"]:
                    raise ValueError("manifest changed")
                item.update(resources_enabled=True, pack_id=row["pack_id"], revision=row["revision"],
                            manifest_url=url(row["pack_id"], row["revision"], "manifest.json"),
                            manifest_sha256=row["manifest_sha256"], download_bytes=row["download_bytes"])
            except (ValueError, OSError):
                pass
        servers.append(item)
    return {"schema": 1, "max_age_seconds": MAX_AGE, "servers": servers}


def activate(conn: sqlite3.Connection, slot: str, pack_id: str, revision: str, resource_root: Path | None = None) -> dict:
    """Local operator action after publish. Never called by a game or import automatically."""
    if slot not in official.SLOTS:
        raise ValueError("unknown server slot")
    if not official.state(conn)[slot]:
        raise ValueError("configure the server slot before activating resources")
    from .resource_publish import verify_revision
    result = verify_revision(pack_id, revision, resource_root or root())
    conn.execute("INSERT INTO official_resources(slot,enabled,pack_id,revision,manifest_sha256,download_bytes,updated) "
                 "VALUES(?,1,?,?,?,?,?) ON CONFLICT(slot) DO UPDATE SET enabled=1, pack_id=excluded.pack_id, "
                 "revision=excluded.revision, manifest_sha256=excluded.manifest_sha256, "
                 "download_bytes=excluded.download_bytes, updated=excluded.updated",
                 (slot, pack_id, revision, result["manifest_sha256"], result["archive_bytes"], now()))
    return result


def disable(conn: sqlite3.Connection, slot: str) -> None:
    if slot not in official.SLOTS:
        raise ValueError("unknown server slot")
    conn.execute("UPDATE official_resources SET enabled=0,updated=? WHERE slot=?", (now(), slot))
