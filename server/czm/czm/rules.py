"""Community rules: a player accepts them once before posting anything other players see.

The game declares in /hello that it can show the rules (`rules: 1`). The server enforces
acceptance only for such clients, so older builds keep working until they update.
"""
import sqlite3

from . import accounts, service
from .db import now

VERSION = 2
URL = "https://counter-zombie.ru/rules"


def state(player: sqlite3.Row) -> dict:
    return {"version": VERSION, "accepted": player["rules_version"] >= VERSION, "url": URL}


def required(player: sqlite3.Row | None) -> bool:
    return player is not None and player["rules_client"] >= 1 and player["rules_version"] < VERSION


def guard(conn: sqlite3.Connection, key: str) -> None:
    """Refuse player content until the rules are accepted. Unknown keys fall through to the caller."""
    if required(service.player_by_key(conn, key or "")):
        raise accounts.AuthError("rules", 403)


def guarded(key: str | None, operation):
    def run(conn):
        guard(conn, key or "")
        return operation(conn)
    return run


def remember_client(conn: sqlite3.Connection, player_id: int, capability: int) -> None:
    conn.execute("UPDATE players SET rules_client=? WHERE id=?", (max(0, min(capability, 100)), player_id))


def accept(conn: sqlite3.Connection, key: str, version: int) -> dict:
    player = service.player_by_key(conn, key or "")
    if player is None:
        raise accounts.AuthError("hello", 401)
    if version != VERSION:
        raise accounts.AuthError("rules_version", 409)
    if player["rules_version"] < VERSION:
        conn.execute("UPDATE players SET rules_version=?, rules_at=? WHERE id=?", (VERSION, now(), player["id"]))
    return {"rules": {"version": VERSION, "accepted": True, "url": URL}}
