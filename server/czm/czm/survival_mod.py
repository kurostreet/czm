"""Order on the Survival server: bans and mutes, the staff, messages to the staff and the news.

A player is known by the CZM profile the game ticket proves; a guest only by the address. A profile
is judged by the profile alone: phones share addresses behind the carrier's NAT, so an address ban
holds guests only. Bans and mutes come from the staff in the game menu or from the players' vote
(by_player 0). Addresses never leave this database: the board shows names, the reason, who and how long.
"""
import ipaddress
import sqlite3

from . import accounts, community
from .db import now

KINDS = ("ban", "mute")
FOREVER = 0
MAX_SECONDS = 365 * 86400
MODERATOR_MAX = 7 * 86400      # a moderator's ban or mute lasts a week at most
MESSAGE_LIMIT = 3              # messages to the staff from one player in MESSAGE_WINDOW
MESSAGE_WINDOW = 600
NEWS_KEEP = 40

SCHEMA = """
CREATE TABLE IF NOT EXISTS survival_sanctions (
 id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL CHECK(kind IN ('ban','mute')),
 player INTEGER NOT NULL DEFAULT 0, ip TEXT NOT NULL DEFAULT '', name TEXT NOT NULL DEFAULT '',
 until INTEGER NOT NULL, reason TEXT NOT NULL DEFAULT '', by_player INTEGER NOT NULL DEFAULT 0,
 by_name TEXT NOT NULL DEFAULT '', created INTEGER NOT NULL, lifted INTEGER NOT NULL DEFAULT 0,
 lifted_by INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS survival_sanctions_player ON survival_sanctions(player, kind, lifted);
CREATE INDEX IF NOT EXISTS survival_sanctions_ip ON survival_sanctions(ip, kind, lifted);
CREATE TABLE IF NOT EXISTS survival_messages (
 id INTEGER PRIMARY KEY AUTOINCREMENT, player INTEGER NOT NULL DEFAULT 0, ip TEXT NOT NULL DEFAULT '',
 name TEXT NOT NULL, text TEXT NOT NULL, server TEXT NOT NULL DEFAULT '', created INTEGER NOT NULL,
 delivered INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS survival_news (
 id INTEGER PRIMARY KEY AUTOINCREMENT, ru TEXT NOT NULL, en TEXT NOT NULL DEFAULT '', created INTEGER NOT NULL
);
"""


class Error(accounts.AuthError):
    """A refused request; the code is what the game and the bot translate."""


def _text(value, limit: int) -> str:
    """One line of printable text: the game chat and the menus break on control characters."""
    text = "".join(ch for ch in str(value or "") if ch.isprintable() and ch not in "^%\\\"")
    return " ".join(text.split())[:limit]


def _ip(value) -> str:
    text = str(value or "").strip()
    if text.count(":") == 1:          # 1.2.3.4:27005 from the game
        text = text.split(":")[0]
    if not text or text == "loopback":
        return ""
    try:
        return str(ipaddress.ip_address(text))
    except ValueError:
        return ""


def role(conn: sqlite3.Connection, player: int) -> str:
    """admin (the head administrators of CZM), moderator or nothing."""
    if not player:
        return ""
    from . import admin
    if admin.allowed(conn, player):
        return "admin"
    if community.has(conn, player, "moderator"):
        return "moderator"
    return ""


def _left(row, t: int) -> int:
    return -1 if row["until"] == FOREVER else max(0, row["until"] - t)


def _active(conn, kind: str, player: int, ip: str, t: int):
    """The strongest active sanction of a kind: a forever one first, else the latest end."""
    if player:
        where, args = "player=?", (player,)
    elif ip:
        where, args = "player=0 AND ip=?", (ip,)
    else:
        return None
    return conn.execute(
        f"SELECT * FROM survival_sanctions WHERE kind=? AND lifted=0 AND (until=0 OR until>?) AND {where} "
        "ORDER BY until=0 DESC, until DESC LIMIT 1", (kind, t, *args)).fetchone()


def check(conn: sqlite3.Connection, player: int, ip: str = "", name: str = "") -> dict:
    """What the game server needs when someone joins: the role and any active ban or mute."""
    t = now()
    ip = _ip(ip)
    result = {"role": role(conn, player)}
    for kind in KINDS:
        row = _active(conn, kind, player, ip, t)
        result[kind] = None if row is None else {
            "id": row["id"], "left": _left(row, t), "reason": row["reason"], "by": row["by_name"]}
    return result


def add(conn: sqlite3.Connection, kind: str, player: int, ip: str, name: str, seconds: int, reason: str,
        by_player: int, by_name: str) -> dict:
    """A ban or a mute. by_player 0 is the players' vote; otherwise the staff member's profile."""
    if kind not in KINDS:
        raise Error("kind")
    ip = "" if player else _ip(ip)
    if not player and not ip:
        raise Error("target")
    seconds = int(seconds)
    if seconds < 0 or seconds > MAX_SECONDS:
        raise Error("seconds")
    by = role(conn, by_player)
    if by_player and not by:
        raise Error("staff_only", 403)
    if not by_player and seconds == FOREVER:
        raise Error("seconds")                     # a vote never bans forever
    if by == "moderator" and (seconds == FOREVER or seconds > MODERATOR_MAX):
        raise Error("too_long", 403)
    target = role(conn, player)
    if target == "admin" or (target and by != "admin"):
        raise Error("immune", 403)                 # staff are judged by the head administrators only
    t = now()
    cur = conn.execute(
        "INSERT INTO survival_sanctions(kind, player, ip, name, until, reason, by_player, by_name, created) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (kind, int(player or 0), ip, _text(name, 32), FOREVER if seconds == FOREVER else t + seconds,
         _text(reason, 64), int(by_player or 0), _text(by_name, 32) or "vote", t))
    return {"ok": True, "id": cur.lastrowid, "left": -1 if seconds == FOREVER else seconds}


def lift(conn: sqlite3.Connection, sanction: int, by_player: int, owner: bool = False) -> dict:
    """Ends a ban or a mute early. Moderators lift what moderators or the vote gave; the owner's bot
    (owner=True) lifts anything."""
    by = "admin" if owner else role(conn, by_player)
    if not by:
        raise Error("staff_only", 403)
    row = conn.execute("SELECT * FROM survival_sanctions WHERE id=?", (int(sanction),)).fetchone()
    if row is None:
        raise Error("not_found", 404)
    if by != "admin" and row["by_player"] and role(conn, row["by_player"]) == "admin":
        raise Error("immune", 403)
    changed = conn.execute("UPDATE survival_sanctions SET lifted=?, lifted_by=? WHERE id=? AND lifted=0",
                           (now(), int(by_player), int(sanction))).rowcount
    return {"ok": True, "changed": bool(changed), "kind": row["kind"], "player": row["player"], "name": row["name"]}


def board(conn: sqlite3.Connection, limit: int = 30) -> list[dict]:
    """Active bans and mutes, newest first, without addresses: the violators board."""
    t = now()
    rows = conn.execute(
        "SELECT * FROM survival_sanctions WHERE lifted=0 AND (until=0 OR until>?) ORDER BY id DESC LIMIT ?",
        (t, max(1, min(int(limit), 100)))).fetchall()
    return [{"id": r["id"], "kind": r["kind"], "player": r["player"], "name": r["name"] or "?",
             "left": _left(r, t), "reason": r["reason"], "by": r["by_name"], "vote": r["by_player"] == 0,
             "created": r["created"]} for r in rows]


def message(conn: sqlite3.Connection, player: int, ip: str, name: str, text: str, server: str) -> dict:
    """A player's message to the staff: the owner's bot gets it."""
    text = _text(text, 180)
    if len(text) < 3:
        raise Error("message_short")
    ip = _ip(ip)
    t = now()
    recent = conn.execute(
        "SELECT COUNT(*) FROM survival_messages WHERE created>? AND ((?>0 AND player=?) OR (?<>'' AND ip=?))",
        (t - MESSAGE_WINDOW, player, player, ip, ip)).fetchone()[0]
    if recent >= MESSAGE_LIMIT:
        raise Error("message_limit", 429)
    conn.execute("INSERT INTO survival_messages(player, ip, name, text, server, created) VALUES (?, ?, ?, ?, ?, ?)",
                 (int(player or 0), ip, _text(name, 32) or "?", text, _text(server, 32), t))
    conn.execute("DELETE FROM survival_messages WHERE created<?", (t - 90 * 86400,))
    return {"ok": True}


def pending_messages(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT id, player, name, text, server, created FROM survival_messages "
                        "WHERE delivered=0 ORDER BY id LIMIT 20").fetchall()
    return [dict(r) for r in rows]


def messages_delivered(conn: sqlite3.Connection, ids: list[int]):
    conn.executemany("UPDATE survival_messages SET delivered=1 WHERE id=?", [(int(i),) for i in ids])


def recent_messages(conn: sqlite3.Connection, limit: int = 8) -> list[dict]:
    rows = conn.execute("SELECT id, player, name, text, created FROM survival_messages ORDER BY id DESC LIMIT ?",
                        (max(1, min(int(limit), 30)),)).fetchall()
    return [dict(r) for r in rows]


def news_add(conn: sqlite3.Connection, ru: str, en: str = "") -> dict:
    ru, en = _text(ru, 160), _text(en, 160)
    if len(ru) < 3:
        raise Error("news_short")
    cur = conn.execute("INSERT INTO survival_news(ru, en, created) VALUES (?, ?, ?)", (ru, en, now()))
    conn.execute("DELETE FROM survival_news WHERE id NOT IN (SELECT id FROM survival_news ORDER BY id DESC LIMIT ?)",
                 (NEWS_KEEP,))
    return {"ok": True, "id": cur.lastrowid}


def news_delete(conn: sqlite3.Connection, news: int) -> bool:
    return conn.execute("DELETE FROM survival_news WHERE id=?", (int(news),)).rowcount > 0


def news(conn: sqlite3.Connection, limit: int = 10) -> list[dict]:
    rows = conn.execute("SELECT id, ru, en, created FROM survival_news ORDER BY id DESC LIMIT ?",
                        (max(1, min(int(limit), NEWS_KEEP)),)).fetchall()
    return [{"id": r["id"], "ru": r["ru"], "en": r["en"] or r["ru"], "created": r["created"]} for r in rows]
