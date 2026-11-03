"""Tickets that tell our game servers which CZM profile a player is.

The game asks for a ticket for one of our servers' addresses and passes it to that server in
setinfo _czm. The server's czm_core.amxx checks the signature with the same key
(/etc/czm/game-ticket.key, installed by server/zm/deploy/install.sh) and its own public
address, so a ticket that reached any other server does not open ours. A ticket lives
15 minutes; the game asks for a new one before every connection.

    ticket    = "<profile>.<expires>.<signature>"
    signature = sha256(key "|v1|" profile "|" expires "|" address "|" key), first 32 hex digits
"""
import hashlib
import sqlite3
from pathlib import Path

from . import accounts, community, official, service
from .db import now

LIFE = 15 * 60
KEY_FILE = Path("/etc/czm/game-ticket.key")


def _key(path: Path = KEY_FILE) -> str:
    try:
        key = path.read_text().strip()
    except OSError:
        key = ""
    if len(key) < 32:
        raise accounts.AuthError("ticket_unavailable", 503)
    return key


def sign(key: str, profile: int, expires: int, address: str) -> str:
    message = f"{key}|v1|{profile}|{expires}|{address}|{key}"
    return hashlib.sha256(message.encode()).hexdigest()[:32]


def issue(conn: sqlite3.Connection, player_key: str, address: str, key_path: Path = KEY_FILE) -> dict:
    player = service.player_by_key(conn, player_key)
    if player is None:
        raise accounts.AuthError("hello", 401)
    address = community.public_endpoint((address or "").strip())
    state = official.state(conn)
    if address not in {state[slot] for slot in official.SLOTS} - {""}:
        raise accounts.AuthError("not_official", 403)
    expires = now() + LIFE
    ticket = f"{player['id']}.{expires}.{sign(_key(key_path), player['id'], expires, address)}"
    return {"ticket": ticket, "address": address, "expires": expires}
