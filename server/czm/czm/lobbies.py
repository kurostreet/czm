"""Ephemeral CZM pre-match rooms. Server authority; no game-server reservations."""
import re
import secrets
import unicodedata

from . import accounts, service, social
from .db import now

LOBBY_SCHEMA = """
CREATE TABLE IF NOT EXISTS lobbies (
 id TEXT PRIMARY KEY, owner INTEGER NOT NULL REFERENCES accounts(player),
 title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
 visibility TEXT NOT NULL CHECK(visibility IN ('public','private')),
 capacity INTEGER NOT NULL CHECK(capacity BETWEEN 2 AND 6),
 server TEXT NOT NULL, proto TEXT NOT NULL CHECK(proto IN ('gs','49')),
 revision INTEGER NOT NULL DEFAULT 1, created INTEGER NOT NULL,
 CHECK(length(title) BETWEEN 3 AND 160)
);
CREATE TABLE IF NOT EXISTS lobby_members (
 player INTEGER PRIMARY KEY REFERENCES accounts(player),
 lobby TEXT NOT NULL REFERENCES lobbies(id) ON DELETE CASCADE,
 ready_revision INTEGER NOT NULL DEFAULT 0,
 joined INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS lobby_members_lobby ON lobby_members(lobby,joined);
CREATE TABLE IF NOT EXISTS lobby_messages (
 id INTEGER PRIMARY KEY, lobby TEXT NOT NULL REFERENCES lobbies(id) ON DELETE CASCADE,
 sender INTEGER NOT NULL REFERENCES accounts(player),
 text TEXT NOT NULL, created INTEGER NOT NULL, nonce TEXT NOT NULL,
 UNIQUE(sender,nonce)
);
CREATE INDEX IF NOT EXISTS lobby_messages_history ON lobby_messages(lobby,id);
CREATE TABLE IF NOT EXISTS lobby_creation_ops (
 player INTEGER NOT NULL REFERENCES accounts(player),
 nonce TEXT NOT NULL, lobby TEXT NOT NULL,
 created INTEGER NOT NULL, PRIMARY KEY(player,nonce)
);
"""

TITLE_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
NONCE = re.compile(r"[A-Za-z0-9_-]{12,64}\Z")


def _actor(conn, key):
    actor = social.actor(conn, key)
    if service.active_ban(conn, actor):
        raise accounts.AuthError("banned", 403)
    return actor["id"]


def _title(value):
    text = unicodedata.normalize("NFKC", value).strip()
    if not 3 <= len(text) <= 40 or TITLE_CONTROL.search(text) or not text.strip():
        raise accounts.AuthError("title")
    # Name/content moderation is separate from links, with sanctions added later.
    return text


def _nonce(value):
    if not NONCE.fullmatch(value or ""):
        raise accounts.AuthError("nonce")
    return value


def _room(conn, room):
    result = conn.execute("SELECT * FROM lobbies WHERE id=?", (room,)).fetchone()
    if result is None:
        raise accounts.AuthError("lobby_not_found", 404)
    return result


def _membership(conn, room, player):
    item = conn.execute("SELECT * FROM lobby_members WHERE player=? AND lobby=?", (player, room)).fetchone()
    if not item:
        raise accounts.AuthError("not_in_lobby", 403)
    return item


def _state(conn, room):
    people = conn.execute(
        "SELECT m.player, m.ready_revision, p.nick, p.avatar FROM lobby_members m "
        "JOIN players p ON p.id=m.player WHERE m.lobby=? ORDER BY m.joined,m.player",
        (room["id"],)).fetchall()
    return {"id": room["id"], "title": room["title"], "description": room["description"],
            "visibility": room["visibility"], "owner": room["owner"],
            "capacity": room["capacity"], "server": room["server"], "proto": room["proto"],
            "revision": room["revision"], "members": [
                {"id": p["player"], "nick": p["nick"], "avatar": p["avatar"],
                 "ready": p["ready_revision"] == room["revision"]} for p in people]}


def _current(conn, player):
    return conn.execute(
        "SELECT l.* FROM lobbies l JOIN lobby_members m ON m.lobby=l.id WHERE m.player=?",
        (player,)).fetchone()


def create(conn, key, title, description, visibility, capacity, server, proto, nonce):
    player = _actor(conn, key)
    _nonce(nonce)
    title = _title(title)
    description = unicodedata.normalize("NFKC", description).strip()
    if len(description) > 120 or TITLE_CONTROL.search(description):
        raise accounts.AuthError("description")
    if visibility not in ("public", "private") or type(capacity) is not int or capacity not in range(2, 7):
        raise accounts.AuthError("settings")
    if not social._valid_server(server) or proto not in ("gs", "49"):
        raise accounts.AuthError("server")
    old = conn.execute("SELECT * FROM lobby_creation_ops WHERE player=? AND nonce=?", (player, nonce)).fetchone()
    if old:
        room = conn.execute("SELECT * FROM lobbies WHERE id=?", (old["lobby"],)).fetchone()
        if room and (room["title"], room["description"], room["visibility"], room["capacity"],
                     room["server"], room["proto"]) == (title, description, visibility, capacity, server, proto):
            return {"lobby": _state(conn, room)}
        raise accounts.AuthError("nonce", 409)
    if _current(conn, player):
        raise accounts.AuthError("already_in_lobby", 409)
    accounts.rate(conn, "lobby_create", str(player), 10, 3600)
    room_id = secrets.token_urlsafe(15)
    conn.execute("INSERT INTO lobbies(id,owner,title,description,visibility,capacity,server,proto,created) "
                 "VALUES (?,?,?,?,?,?,?,?,?)",
                 (room_id, player, title, description, visibility, capacity, server, proto, now()))
    conn.execute("INSERT INTO lobby_members(player,lobby,joined) VALUES (?,?,?)",
                 (player, room_id, now()))
    conn.execute("INSERT INTO lobby_creation_ops(player,nonce,lobby,created) VALUES (?,?,?,?)",
                 (player, nonce, room_id, now()))
    return {"lobby": _state(conn, _room(conn, room_id))}


def mine(conn, key):
    player = _actor(conn, key)
    room = _current(conn, player)
    return {"lobby": _state(conn, room) if room else None}


def catalog(conn, key, offset=0):
    _actor(conn, key)
    rows = conn.execute("SELECT l.*, (SELECT COUNT(*) FROM lobby_members m WHERE m.lobby=l.id) AS count "
                        "FROM lobbies l WHERE l.visibility='public' "
                        "ORDER BY l.created DESC,l.id DESC LIMIT 41 OFFSET ?", (max(0,offset),)).fetchall()
    return {"lobbies": [{"id": l["id"], "title": l["title"], "owner": l["owner"],
                        "capacity": l["capacity"], "count": l["count"],
                        "server": l["server"], "proto": l["proto"]} for l in rows[:40]],
            "next": max(0,offset)+40 if len(rows)>40 else -1}


def detail(conn, key, room_id):
    player = _actor(conn, key)
    room = _room(conn, room_id)
    _membership(conn, room_id, player)
    return {"lobby": _state(conn, room)}


def join(conn, key, room_id):
    player = _actor(conn, key)
    room = _room(conn, room_id)
    if _current(conn, player):
        if conn.execute("SELECT 1 FROM lobby_members WHERE player=? AND lobby=?", (player, room_id)).fetchone():
            return {"lobby": _state(conn, room)}
        raise accounts.AuthError("already_in_lobby", 409)
    if room["visibility"] != "public":
        raise accounts.AuthError("invite_required", 403)
    if social.blocked(conn, player, room["owner"]):
        raise accounts.AuthError("unavailable", 403)
    if conn.execute("SELECT COUNT(*) FROM lobby_members WHERE lobby=?", (room_id,)).fetchone()[0] >= room["capacity"]:
        raise accounts.AuthError("lobby_full", 409)
    conn.execute("INSERT INTO lobby_members(player,lobby,joined) VALUES (?,?,?)",
                 (player, room_id, now()))
    return {"lobby": _state(conn, room)}


def leave(conn, key, room_id):
    player = _actor(conn, key)
    room = _room(conn, room_id)
    _membership(conn, room_id, player)
    if player == room["owner"]:
        conn.execute("DELETE FROM lobbies WHERE id=?", (room_id,))
        return {"closed": True}
    conn.execute("DELETE FROM lobby_members WHERE lobby=? AND player=?", (room_id, player))
    return {"closed": False}


def ready(conn, key, room_id, revision, value):
    player = _actor(conn, key)
    room = _room(conn, room_id)
    _membership(conn, room_id, player)
    if revision != room["revision"]:
        raise accounts.AuthError("stale_revision", 409)
    conn.execute("UPDATE lobby_members SET ready_revision=? WHERE lobby=? AND player=?",
                 (revision if value else 0, room_id, player))
    return {"lobby": _state(conn, room)}


def change_server(conn, key, room_id, server, proto):
    player = _actor(conn, key)
    room = _room(conn, room_id)
    if player != room["owner"]:
        raise accounts.AuthError("not_owner", 403)
    if not social._valid_server(server) or proto not in ("gs", "49"):
        raise accounts.AuthError("server")
    if (server, proto) != (room["server"], room["proto"]):
        conn.execute("UPDATE lobbies SET server=?,proto=?,revision=revision+1 WHERE id=?",
                     (server, proto, room_id))
        conn.execute("UPDATE lobby_members SET ready_revision=0 WHERE lobby=?", (room_id,))
    return {"lobby": _state(conn, _room(conn, room_id))}


def transfer(conn, key, room_id, target):
    player = _actor(conn, key)
    room = _room(conn, room_id)
    if player != room["owner"]:
        raise accounts.AuthError("not_owner", 403)
    _membership(conn, room_id, target)
    conn.execute("UPDATE lobbies SET owner=? WHERE id=?", (target, room_id))
    return {"lobby": _state(conn, _room(conn, room_id))}


def kick(conn, key, room_id, target):
    player = _actor(conn, key)
    room = _room(conn, room_id)
    if player != room["owner"] or target == player:
        raise accounts.AuthError("not_owner", 403)
    _membership(conn, room_id, target)
    conn.execute("DELETE FROM lobby_members WHERE lobby=? AND player=?", (room_id, target))
    return {"lobby": _state(conn, room)}


def chat(conn, key, room_id, before=0):
    player = _actor(conn, key)
    _room(conn, room_id)
    _membership(conn, room_id, player)
    rows = conn.execute("SELECT id,sender,text,created FROM lobby_messages WHERE lobby=? AND (?=0 OR id<?) "
                        "ORDER BY id DESC LIMIT 50", (room_id, before)).fetchall()
    return {"messages": [dict(r) for r in reversed(rows)]}


def send(conn, key, room_id, text, nonce):
    player = _actor(conn, key)
    _nonce(nonce)
    _room(conn, room_id)
    _membership(conn, room_id, player)
    text = service.profanity.clean(service.clean_text(text, 400))
    if not text:
        raise accounts.AuthError("empty")
    old = conn.execute("SELECT * FROM lobby_messages WHERE sender=? AND nonce=?", (player, nonce)).fetchone()
    if old:
        if old["lobby"] != room_id or old["text"] != text:
            raise accounts.AuthError("nonce", 409)
        return {"message": dict(old)}
    accounts.rate(conn, "lobby_send", str(player), 30, 60)
    cur = conn.execute("INSERT INTO lobby_messages(lobby,sender,text,created,nonce) VALUES (?,?,?,?,?)",
                       (room_id, player, text, now(), nonce))
    return {"message": dict(conn.execute("SELECT * FROM lobby_messages WHERE id=?", (cur.lastrowid,)).fetchone())}
