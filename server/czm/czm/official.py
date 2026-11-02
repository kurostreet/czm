"""The project's own servers: two cards on the main screen (Survival and Escape) and a golden
frame around them in the server list.

The head administrator sets them in the game's admin panel: a switch for the whole feature and
one public IP:port per slot. An empty slot shows «Скоро открытие» on its card. The game gets
the state with every hello, so a new address reaches every player without an app update. The
golden frame follows the address, never the server name: anyone can call a server «official».
"""
import sqlite3

from . import accounts, community
from .db import now

SLOTS = ("survival", "escape")
SCHEMA = """
CREATE TABLE IF NOT EXISTS official_servers (
 slot TEXT PRIMARY KEY, address TEXT NOT NULL DEFAULT '',
 updated INTEGER NOT NULL DEFAULT 0, actor INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS official_switch (
 id INTEGER PRIMARY KEY CHECK (id = 1), enabled INTEGER NOT NULL DEFAULT 0,
 updated INTEGER NOT NULL DEFAULT 0, actor INTEGER NOT NULL DEFAULT 0
);
"""


def state(conn: sqlite3.Connection) -> dict:
    """{"enabled": bool, "survival": "ip:port" or "", "escape": ...}; off until first set."""
    row = conn.execute("SELECT enabled FROM official_switch WHERE id = 1").fetchone()
    result = {"enabled": bool(row and row["enabled"])}
    addresses = {r["slot"]: r["address"] for r in conn.execute("SELECT slot, address FROM official_servers")}
    for slot in SLOTS:
        result[slot] = addresses.get(slot, "")
    return result


def _address(value: str) -> str:
    value = (value or "").strip()
    return community.public_endpoint(value) if value else ""


def update(conn: sqlite3.Connection, enabled: bool, survival: str, escape: str, actor: int) -> dict:
    """Sets the switch and both slots at once; an invalid address changes nothing."""
    addresses = {"survival": _address(survival), "escape": _address(escape)}
    if addresses["survival"] and addresses["survival"] == addresses["escape"]:
        raise accounts.AuthError("official_same")
    t = now()
    conn.execute("INSERT INTO official_switch(id, enabled, updated, actor) VALUES (1, ?, ?, ?) "
                 "ON CONFLICT(id) DO UPDATE SET enabled = excluded.enabled, updated = excluded.updated, actor = excluded.actor",
                 (int(bool(enabled)), t, actor))
    for slot, address in addresses.items():
        conn.execute("INSERT INTO official_servers(slot, address, updated, actor) VALUES (?, ?, ?, ?) "
                     "ON CONFLICT(slot) DO UPDATE SET address = excluded.address, updated = excluded.updated, actor = excluded.actor",
                     (slot, address, t, actor))
    return state(conn)
